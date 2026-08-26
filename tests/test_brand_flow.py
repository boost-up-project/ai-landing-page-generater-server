from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.brand.ai_parser import AIParserError
from app.brand.router import get_brand_service
from app.brand.schemas import (
    BrandIdentity,
    BrandKnowledge,
    BrandStatus,
    ReviewSection,
    SourceReference,
    VerbalGuideline,
    VisualGuideline,
)
from app.brand.service import (
    BrandService,
    BrandStateError,
    UploadedDocument,
)
from app.common.pdf import PDFParseError, parse_pdf
from app.core.config import Settings
from app.main import app


def make_section(content: str = "") -> ReviewSection:
    references = [SourceReference(filename="brand.pdf", page=1)] if content else []
    return ReviewSection(content=content, source_references=references)


def make_knowledge(overview: str = "Brand name: Example") -> BrandKnowledge:
    return BrandKnowledge(
        brand_identity=BrandIdentity(
            brand_overview=make_section(overview),
            brand_philosophy=make_section(),
            brand_positioning=make_section(),
            brand_target=make_section(),
            brand_personality=make_section(),
        ),
        verbal_guideline=VerbalGuideline(
            brand_voice=make_section(),
            tone_of_voice=make_section(),
            writing_style=make_section(),
            messaging_principles=make_section(),
            vocabulary_and_expressions=make_section(),
            copy_rules=make_section(),
        ),
        visual_guideline=VisualGuideline(
            logo=make_section(),
            icon=make_section(),
            color=make_section(),
            fonts=make_section(),
        ),
    )


def make_pdf_bytes(text: str = "Example brand source document") -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


class FakeParser:
    def __init__(self, result: BrandKnowledge) -> None:
        self.result = result
        self.extracted_text = ""

    async def analyze(self, extracted_text: str) -> BrandKnowledge:
        self.extracted_text = extracted_text
        return self.result


@pytest.mark.asyncio
async def test_brand_service_rejects_unknown_ai_source_reference(
    tmp_path: Path,
) -> None:
    knowledge = make_knowledge()
    knowledge.brand_identity.brand_overview.source_references = [
        SourceReference(filename="invented.pdf", page=99)
    ]
    service = BrandService(
        Settings(storage_root=tmp_path),
        parser=FakeParser(knowledge),
    )

    with pytest.raises(AIParserError, match="unknown source reference"):
        await service.analyze(
            [UploadedDocument(filename="brand.pdf", data=make_pdf_bytes())]
        )


@pytest.mark.asyncio
async def test_brand_service_review_and_finalize_flow(tmp_path: Path) -> None:
    fake_parser = FakeParser(make_knowledge())
    service = BrandService(Settings(storage_root=tmp_path), parser=fake_parser)

    analyzed = await service.analyze(
        [UploadedDocument(filename="brand.pdf", data=make_pdf_bytes())]
    )

    assert analyzed.status == BrandStatus.DRAFT
    assert "[SOURCE_FILE: brand.pdf]" in fake_parser.extracted_text
    assert "[SOURCE_PAGE: 1]" in fake_parser.extracted_text
    assert (
        tmp_path / "generated" / "brands" / analyzed.brand_id / "analyzed.json"
    ).is_file()

    with pytest.raises(BrandStateError):
        service.finalize(analyzed.brand_id)

    reviewed = service.review(
        analyzed.brand_id,
        make_knowledge("Brand name: Reviewed Example"),
    )
    assert reviewed.status == BrandStatus.REVIEWED

    finalized = service.finalize(analyzed.brand_id)
    assert finalized.status == BrandStatus.FINALIZED
    assert "### 01. Brand Overview" in finalized.markdown
    assert "Brand name: Reviewed Example" in finalized.markdown
    assert "## 02. Verbal Guideline" in finalized.markdown
    assert "## 03. Visual Guideline" in finalized.markdown
    assert service.get_markdown(analyzed.brand_id).markdown == finalized.markdown


def test_pdf_parser_rejects_pdf_without_selectable_text() -> None:
    document = pymupdf.open()
    document.new_page()
    content = document.tobytes()
    document.close()

    with pytest.raises(PDFParseError, match="no selectable text"):
        parse_pdf(
            content,
            "scan.pdf",
            max_size_bytes=1_000_000,
            max_pages=10,
        )


def test_analyze_api_returns_fixed_review_structure(tmp_path: Path) -> None:
    service = BrandService(
        Settings(storage_root=tmp_path),
        parser=FakeParser(make_knowledge()),
    )
    app.dependency_overrides[get_brand_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/brands/analyze",
                files=[("files", ("brand.pdf", make_pdf_bytes(), "application/pdf"))],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert set(body["data"]) == {
        "brand_identity",
        "verbal_guideline",
        "visual_guideline",
    }
    assert len(body["data"]["brand_identity"]) == 5
    assert len(body["data"]["verbal_guideline"]) == 6
    assert len(body["data"]["visual_guideline"]) == 4


def test_local_frontend_origin_is_allowed() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/brands/analyze",
            headers={
                "Origin": "http://127.0.0.1:5500",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://127.0.0.1:5500"
    )

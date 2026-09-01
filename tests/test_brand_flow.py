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
    UploadedVisualAsset,
    _normalize_hex_colors,
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
    assert analyzed.project_id
    assert "[SOURCE_FILE: brand.pdf]" in fake_parser.extracted_text
    assert "[SOURCE_PAGE: 1]" in fake_parser.extracted_text
    assert (
        tmp_path / "projects" / analyzed.project_id / "brand" / "analyzed.json"
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
    assert finalized.project_id == analyzed.project_id
    assert finalized.next_route == "/#campaign-input"
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
    assert body["project_id"]
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


@pytest.mark.asyncio
async def test_brand_service_merges_and_stores_visual_inputs(tmp_path: Path) -> None:
    service = BrandService(
        Settings(storage_root=tmp_path),
        parser=FakeParser(make_knowledge()),
    )
    visual_assets = [
        UploadedVisualAsset(
            kind="logo",
            filename="wordmark.svg",
            data=b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
        ),
        UploadedVisualAsset(
            kind="logo",
            filename="wordmark.jpg",
            data=b"\xff\xd8\xffimage-data",
        ),
        UploadedVisualAsset(
            kind="icon",
            filename="app-icon.png",
            data=b"\x89PNG\r\n\x1a\nimage-data",
        ),
        UploadedVisualAsset(
            kind="icon",
            filename="app-icon.jpeg",
            data=b"\xff\xd8\xffimage-data",
        ),
        UploadedVisualAsset(
            kind="font",
            filename="brand.ttf",
            data=b"\x00\x01\x00\x00font-data",
        ),
    ]

    analyzed = await service.analyze(
        [UploadedDocument(filename="brand.pdf", data=make_pdf_bytes())],
        visual_assets=visual_assets,
        colors=["#1f4d3a", "d8c3a5"],
    )

    visual = analyzed.data.visual_guideline
    assert "wordmark.svg" in visual.logo.content
    assert "wordmark.jpg" in visual.logo.content
    assert "app-icon.png" in visual.icon.content
    assert "app-icon.jpeg" in visual.icon.content
    assert "brand.ttf" in visual.fonts.content
    assert "#1F4D3A, #D8C3A5" in visual.color.content
    upload_root = tmp_path / "projects" / analyzed.project_id / "brand" / "uploads"
    assert (upload_root / "logo" / "01_wordmark.svg").is_file()
    assert (upload_root / "logo" / "02_wordmark.jpg").is_file()
    assert (upload_root / "icon" / "03_app-icon.png").is_file()
    assert (upload_root / "icon" / "04_app-icon.jpeg").is_file()
    assert (upload_root / "font" / "05_brand.ttf").is_file()


def test_analyze_api_accepts_visual_inputs(tmp_path: Path) -> None:
    service = BrandService(
        Settings(storage_root=tmp_path),
        parser=FakeParser(make_knowledge()),
    )
    app.dependency_overrides[get_brand_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/brands/analyze",
                files=[
                    ("files", ("brand.pdf", make_pdf_bytes(), "application/pdf")),
                    (
                        "logo_files",
                        (
                            "wordmark.svg",
                            b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
                            "image/svg+xml",
                        ),
                    ),
                    (
                        "font_files",
                        ("brand.ttf", b"\x00\x01\x00\x00font-data", "font/ttf"),
                    ),
                ],
                data={"colors": ["#abc", "112233"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    visual = response.json()["data"]["visual_guideline"]
    assert "wordmark.svg" in visual["logo"]["content"]
    assert "brand.ttf" in visual["fonts"]["content"]
    assert "#AABBCC, #112233" in visual["color"]["content"]


def test_hex_colors_are_normalized_and_deduplicated() -> None:
    assert _normalize_hex_colors(["#abc", "AABBCC", "#123456"]) == [
        "#AABBCC",
        "#123456",
    ]

    with pytest.raises(ValueError, match="Invalid HEX color"):
        _normalize_hex_colors(["#12GG00"])

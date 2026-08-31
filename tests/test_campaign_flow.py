from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.campaign.router import get_campaign_service
from app.campaign.schemas import (
    CampaignKnowledge,
    CampaignSection,
    CampaignStatus,
    SourceReference,
)
from app.campaign.service import CampaignService, UploadedFile
from app.core.config import Settings
from app.main import app


def make_section(content: str = "", filename: str = "strategy.pdf") -> CampaignSection:
    references = [SourceReference(filename=filename, page=1)] if content else []
    return CampaignSection(content=content, source_references=references)


def make_campaign_knowledge(
    overview: str = "캠페인 배경: 신규 서비스 출시",
    filename: str = "strategy.pdf",
) -> CampaignKnowledge:
    return CampaignKnowledge(
        campaign_overview=make_section(overview, filename),
        objective=make_section("목표: 인지도 향상 / KPI: 도달률", filename),
        campaign_opportunity=make_section(),
        audience_insight=make_section(),
        campaign_idea=make_section(),
        offering=make_section(),
        communication_strategy=make_section(),
        cta_map=make_section(),
    )


def make_pdf_bytes(text: str = "Campaign strategy source") -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


class FakeCampaignParser:
    def __init__(self, result: CampaignKnowledge) -> None:
        self.result = result
        self.extracted_text = ""
        self.calls = 0

    async def analyze(self, extracted_text: str) -> CampaignKnowledge:
        self.calls += 1
        self.extracted_text = extracted_text
        return self.result


@pytest.mark.asyncio
async def test_campaign_service_stores_files_and_creates_draft(tmp_path: Path) -> None:
    parser = FakeCampaignParser(make_campaign_knowledge())
    service = CampaignService(Settings(storage_root=tmp_path), parser=parser)

    result = await service.analyze(
        UploadedFile("strategy.pdf", make_pdf_bytes()),
        component_files=[
            UploadedFile("hero.html", b"<section>Hero</section>"),
        ],
        asset_files=[
            UploadedFile("hero.png", b"\x89PNG\r\n\x1a\nimage-data"),
        ],
    )

    assert result.status == CampaignStatus.DRAFT
    assert result.source_checksum
    assert result.reused_from_campaign_id is None
    assert "[SOURCE_FILE: strategy.pdf]" in parser.extracted_text
    assert parser.calls == 1
    root = tmp_path / "generated" / "campaigns" / result.campaign_id
    assert (root / "component" / "01_hero.html").read_text() == (
        "<section>Hero</section>"
    )
    assert (root / "assets" / "01_hero.png").is_file()
    assert (tmp_path / "uploads" / result.campaign_id / "strategy.pdf").is_file()

@pytest.mark.asyncio
async def test_campaign_review_and_finalize_flow(tmp_path: Path) -> None:
    service = CampaignService(
        Settings(storage_root=tmp_path),
        parser=FakeCampaignParser(make_campaign_knowledge()),
    )
    analyzed = await service.analyze(UploadedFile("strategy.pdf", make_pdf_bytes()))

    reviewed = service.review(
        analyzed.campaign_id,
        make_campaign_knowledge("사용자가 수정한 캠페인 개요"),
    )
    assert reviewed.status == CampaignStatus.REVIEWED

    finalized = service.finalize(analyzed.campaign_id)
    assert finalized.status == CampaignStatus.FINALIZED
    assert finalized.next_route == "/#persona-input"
    assert "## 01. Campaign Overview" in finalized.markdown
    assert "사용자가 수정한 캠페인 개요" in finalized.markdown
    assert service.get_markdown(analyzed.campaign_id) == finalized


@pytest.mark.asyncio
async def test_campaign_service_reuses_analysis_for_identical_pdf(
    tmp_path: Path,
) -> None:
    parser = FakeCampaignParser(make_campaign_knowledge())
    service = CampaignService(Settings(storage_root=tmp_path), parser=parser)
    pdf_bytes = make_pdf_bytes()

    first = await service.analyze(UploadedFile("strategy.pdf", pdf_bytes))
    second = await service.analyze(
        UploadedFile("strategy-copy.pdf", pdf_bytes),
        component_files=[UploadedFile("hero.html", b"<section>Hero</section>")],
    )

    assert parser.calls == 1
    assert second.campaign_id != first.campaign_id
    assert second.reused_from_campaign_id == first.campaign_id
    assert second.source_checksum == first.source_checksum
    assert second.data.campaign_overview.source_references[0].filename == (
        "strategy-copy.pdf"
    )
    assert (
        tmp_path
        / "generated"
        / "campaigns"
        / second.campaign_id
        / "component"
        / "01_hero.html"
    ).is_file()


def test_campaign_api_accepts_pdf_components_and_assets(tmp_path: Path) -> None:
    service = CampaignService(
        Settings(storage_root=tmp_path),
        parser=FakeCampaignParser(make_campaign_knowledge()),
    )
    app.dependency_overrides[get_campaign_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/campaigns",
                files=[
                    (
                        "strategy_file",
                        ("strategy.pdf", make_pdf_bytes(), "application/pdf"),
                    ),
                    (
                        "component_files",
                        ("card.html", b"<article>Card</article>", "text/html"),
                    ),
                    (
                        "asset_files",
                        ("card.jpg", b"\xff\xd8\xffimage-data", "image/jpeg"),
                    ),
                ],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["component_files"] == ["card.html"]
    assert body["asset_files"] == ["card.jpg"]
    assert len(body["data"]) == 8


def test_campaign_api_requires_exactly_one_pdf(tmp_path: Path) -> None:
    service = CampaignService(
        Settings(storage_root=tmp_path),
        parser=FakeCampaignParser(make_campaign_knowledge()),
    )
    app.dependency_overrides[get_campaign_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/campaigns",
                files=[
                    ("strategy_file", ("one.pdf", make_pdf_bytes(), "application/pdf")),
                    ("strategy_file", ("two.pdf", make_pdf_bytes(), "application/pdf")),
                ],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "Exactly one campaign strategy PDF is required"


@pytest.mark.asyncio
async def test_campaign_service_rejects_invalid_html_and_image(tmp_path: Path) -> None:
    service = CampaignService(
        Settings(storage_root=tmp_path),
        parser=FakeCampaignParser(make_campaign_knowledge()),
    )

    with pytest.raises(ValueError, match="must be HTML"):
        await service.analyze(
            UploadedFile("strategy.pdf", make_pdf_bytes()),
            component_files=[UploadedFile("component.txt", b"text")],
        )

    with pytest.raises(ValueError, match="not a valid image"):
        await service.analyze(
            UploadedFile("strategy.pdf", make_pdf_bytes()),
            asset_files=[UploadedFile("broken.png", b"not-png")],
        )

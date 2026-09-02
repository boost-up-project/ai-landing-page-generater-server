from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.landing.router import get_landing_service
from app.landing.schemas import (
    CopyCandidateRequest,
    CopyCandidateResponse,
    EditableImage,
    LandingComponentSelection,
    LandingPagePlan,
    LandingPlan,
)
from app.landing.service import LandingService
from app.main import app
from app.persona.schemas import (
    PersonaAnalysisResponse,
    PersonaAppendix,
    PersonaBatch,
    PersonaKnowledge,
    PersonaStatus,
)
from app.project.service import create_project_id, project_dir


class FakeLandingParser:
    async def compose(self, **_: object) -> LandingPlan:
        return LandingPlan(
            pages=[
                LandingPagePlan(
                    persona_key="persona-a",
                    ai_intent="작게 시작할 수 있다는 메시지로 구매 부담을 낮췄습니다.",
                    components=[
                        LandingComponentSelection(
                            template_id="component-1",
                            copy_values=["작은 변화로 시작하는 새로운 공간"],
                            image_values=[
                                EditableImage(
                                    asset_filename="01_room.png",
                                    alt="밝고 정돈된 거실",
                                )
                            ],
                        )
                    ],
                )
            ]
        )

    async def generate_copy_candidates(self, **_: object) -> CopyCandidateResponse:
        return CopyCandidateResponse(
            candidates=[
                "작은 변화로 완성하는 나만의 공간",
                "오늘 시작하는 가벼운 공간 변화",
                "내 예산에 맞춘 첫 번째 공간",
            ]
        )


def make_project(settings: Settings) -> str:
    project_id = create_project_id()
    root = project_dir(settings, project_id)
    brand_id = "brand-record"
    campaign_id = "campaign-record"
    persona_id = "persona-record"
    (root / "brand" / brand_id).mkdir(parents=True)
    (root / "campaign" / campaign_id / "component").mkdir(parents=True)
    (root / "campaign" / campaign_id / "assets").mkdir(parents=True)
    (root / "persona" / persona_id).mkdir(parents=True)
    (root / "brand" / brand_id / "brand.md").write_text(
        "# Brand\n친근하고 실용적인 브랜드", encoding="utf-8"
    )
    (root / "campaign" / campaign_id / "campaign.md").write_text(
        "# Campaign\n첫 구매 부담을 낮춘다", encoding="utf-8"
    )
    (root / "campaign" / campaign_id / "component" / "01_hero.html").write_text(
        '<section data-component-name="히어로" data-component-category="기본">'
        '<h1 class="title" data-editable="copy">기존 제목</h1>'
        '<img class="kv" data-editable="image" src="old.png" alt="기존 이미지">'
        "</section>",
        encoding="utf-8",
    )
    (root / "campaign" / campaign_id / "assets" / "01_room.png").write_bytes(
        b"fake-png"
    )
    now = datetime.now(timezone.utc)
    persona = PersonaKnowledge(
        name="새 출발 민지",
        profile=["첫 독립을 준비한다"],
        situation=["작은 집을 꾸미고 있다"],
        needs=["예산 안에서 완성하고 싶다"],
        pain_points=["선택지가 많아 어렵다"],
        interests=["정돈된 공간"],
        behaviors=["후기와 가격을 비교한다"],
        appendix=PersonaAppendix(
            purchase_journey=["검색 후 비교한다"],
            dislikes=["복잡한 구매 과정"],
        ),
    )
    record = PersonaAnalysisResponse(
        project_id=project_id,
        persona_id=persona_id,
        status=PersonaStatus.FINALIZED,
        inputs=["첫 독립을 준비하는 사람"],
        data=PersonaBatch(personas=[persona]),
        created_at=now,
        updated_at=now,
    )
    (root / "persona" / persona_id / "record.json").write_text(
        record.model_dump_json(indent=2), encoding="utf-8"
    )
    (root / "project.json").write_text(
        json.dumps(
            {
                "project_id": project_id,
                "brand": {"current_brand_id": brand_id},
                "campaign": {"current_campaign_id": campaign_id},
                "persona": {"current_persona_id": persona_id},
            }
        ),
        encoding="utf-8",
    )
    return project_id


@pytest.mark.asyncio
async def test_landing_service_creates_persona_page_without_structure_changes(
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project(settings)
    service = LandingService(settings, parser=FakeLandingParser())

    result = await service.create(project_id)

    assert result.pages[0].persona_name == "새 출발 민지"
    assert result.component_library[0].name == "히어로"
    html = result.pages[0].components[0].html
    assert '<h1 class="title" data-editable="copy">' in html
    assert "작은 변화로 시작하는 새로운 공간" in html
    assert 'src="asset://01_room.png"' in html
    assert 'alt="밝고 정돈된 거실"' in html
    assert service.get(result.landing_id) == result

    candidates = await service.copy_candidates(
        result.landing_id,
        CopyCandidateRequest(
            persona_key="persona-a",
            instance_id=result.pages[0].components[0].instance_id,
            editable_index=0,
            current_value="작은 변화로 시작하는 새로운 공간",
            prompt="조금 더 가볍게",
        ),
    )
    assert len(candidates.candidates) == 3


def test_landing_api_creates_page_and_serves_campaign_asset(tmp_path: Path) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project(settings)
    service = LandingService(settings, parser=FakeLandingParser())
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_landing_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post("/api/landings", json={"project_id": project_id})
            assert response.status_code == 201
            landing_id = response.json()["landing_id"]
            asset = client.get(f"/api/landings/{landing_id}/assets/01_room.png")
            assert asset.status_code == 200
            assert asset.content == b"fake-png"
    finally:
        app.dependency_overrides.clear()

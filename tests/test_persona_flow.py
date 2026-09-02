from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.brand.ai_parser import AIParserError
from app.core.config import Settings
from app.main import app
from app.persona.router import get_persona_service
from app.persona.schemas import PersonaAppendix, PersonaBatch, PersonaKnowledge
from app.persona.service import PersonaService, PersonaStateError
from app.project.service import create_project_id, project_dir


def make_persona(name: str = "김민지") -> PersonaKnowledge:
    return PersonaKnowledge(
        name=name,
        profile=["30대 초반의 직장인", "공간 효율을 중시하는 1인 가구"],
        situation=["이사 후 작은 집을 정리하고 있다"],
        needs=["제한된 공간을 효율적으로 활용하고 싶다"],
        pain_points=["제품 크기를 실제 공간과 비교하기 어렵다"],
        interests=["미니멀 인테리어", "합리적인 소비"],
        behaviors=["온라인 비교 후 매장에서 실물을 확인한다"],
        appendix=PersonaAppendix(
            purchase_journey=["검색", "후기 비교", "매장 확인", "구매"],
            dislikes=["복잡한 조립", "불명확한 배송 일정"],
        ),
    )


class FakePersonaParser:
    def __init__(self, result: PersonaBatch) -> None:
        self.result = result
        self.inputs: list[str] = []
        self.brand_context = ""
        self.campaign_context = ""

    async def analyze(
        self,
        inputs: list[str],
        *,
        brand_context: str,
        campaign_context: str,
    ) -> PersonaBatch:
        self.inputs = inputs
        self.brand_context = brand_context
        self.campaign_context = campaign_context
        return self.result


def make_project_with_context(settings: Settings) -> str:
    project_id = create_project_id()
    root = project_dir(settings, project_id)
    brand_id = "brand-record"
    campaign_id = "campaign-record"
    (root / "brand" / brand_id).mkdir(parents=True)
    (root / "campaign" / campaign_id).mkdir(parents=True)
    (root / "brand" / brand_id / "brand.md").write_text(
        "# Brand Knowledge\n\n실용적인 가구 브랜드", encoding="utf-8"
    )
    (root / "campaign" / campaign_id / "campaign.md").write_text(
        "# Campaign Knowledge\n\n작은 공간 캠페인", encoding="utf-8"
    )
    (root / "project.json").write_text(
        json.dumps(
            {
                "project_id": project_id,
                "brand": {"current_brand_id": brand_id},
                "campaign": {"current_campaign_id": campaign_id},
            }
        ),
        encoding="utf-8",
    )
    return project_id


@pytest.mark.asyncio
async def test_persona_service_uses_project_context_and_stores_draft(
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project_with_context(settings)
    parser = FakePersonaParser(PersonaBatch(personas=[make_persona()]))
    service = PersonaService(settings, parser=parser)

    result = await service.analyze(project_id, ["작은 집으로 이사한 직장인"])

    assert result.status.value == "draft"
    assert parser.inputs == ["작은 집으로 이사한 직장인"]
    assert "실용적인 가구 브랜드" in parser.brand_context
    assert "작은 공간 캠페인" in parser.campaign_context
    root = tmp_path / "projects" / project_id / "persona" / result.persona_id
    assert (root / "inputs.json").is_file()
    assert (root / "analyzed.json").is_file()
    project_record = json.loads(
        (tmp_path / "projects" / project_id / "project.json").read_text()
    )
    assert project_record["persona"]["current_persona_id"] == result.persona_id


@pytest.mark.asyncio
async def test_persona_review_and_finalize_writes_one_markdown_per_persona(
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project_with_context(settings)
    initial = PersonaBatch(personas=[make_persona(), make_persona("박준호")])
    service = PersonaService(settings, parser=FakePersonaParser(initial))
    analyzed = await service.analyze(project_id, ["첫 번째", "두 번째"])

    edited = initial.model_copy(deep=True)
    edited.personas[0].needs = ["사용자가 수정한 목표"]
    reviewed = service.review(analyzed.persona_id, edited)
    finalized = service.finalize(analyzed.persona_id)

    assert reviewed.status.value == "reviewed"
    assert finalized.status.value == "finalized"
    assert [item.filename for item in finalized.files] == [
        "persona-a.md",
        "persona-b.md",
    ]
    assert "# Persona: 김민지" in finalized.files[0].markdown
    assert "- 사용자가 수정한 목표" in finalized.files[0].markdown
    assert "### Purchase Journey" in finalized.files[0].markdown
    assert finalized.next_route is None
    assert service.get_markdown(analyzed.persona_id) == finalized


@pytest.mark.asyncio
async def test_persona_service_rejects_wrong_ai_persona_count(tmp_path: Path) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project_with_context(settings)
    service = PersonaService(
        settings,
        parser=FakePersonaParser(PersonaBatch(personas=[make_persona()])),
    )

    with pytest.raises(AIParserError, match="exactly one persona"):
        await service.analyze(project_id, ["첫 번째", "두 번째"])


@pytest.mark.asyncio
async def test_persona_finalize_requires_review(tmp_path: Path) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project_with_context(settings)
    service = PersonaService(
        settings,
        parser=FakePersonaParser(PersonaBatch(personas=[make_persona()])),
    )
    analyzed = await service.analyze(project_id, ["입력"])

    with pytest.raises(PersonaStateError, match="must be reviewed"):
        service.finalize(analyzed.persona_id)


def test_persona_api_accepts_one_to_five_inputs(tmp_path: Path) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project_with_context(settings)
    service = PersonaService(
        settings,
        parser=FakePersonaParser(PersonaBatch(personas=[make_persona()])),
    )
    app.dependency_overrides[get_persona_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/personas",
                json={"project_id": project_id, "inputs": ["작은 집의 직장인"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["data"]["personas"][0]["name"] == "김민지"


def test_persona_api_rejects_more_than_five_inputs(tmp_path: Path) -> None:
    settings = Settings(storage_root=tmp_path)
    service = PersonaService(
        settings,
        parser=FakePersonaParser(PersonaBatch(personas=[make_persona()])),
    )
    app.dependency_overrides[get_persona_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/personas",
                json={"project_id": "unused", "inputs": ["입력"] * 6},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_persona_batch_requires_unique_ai_names() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        PersonaBatch(personas=[make_persona(), make_persona()])

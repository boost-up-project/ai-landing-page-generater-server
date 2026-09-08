from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.brand.ai_parser import AIParserError
from app.core.config import Settings, get_settings
from app.landing.router import get_landing_service
from app.landing.schemas import (
    CopyCandidateRequest,
    CopyCandidateResponse,
    EditableImage,
    ImageGenerateRequest,
    LandingComponentSelection,
    LandingPagePlan,
    LandingPageUpdate,
    LandingPlan,
    LandingSaveRequest,
    PersonaUXStrategy,
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
    async def compose(self, **kwargs: object) -> LandingPlan:
        manifest = kwargs["components"]
        assert isinstance(manifest, list)
        selected = [manifest[index]["template_id"] for index in (0, 1, 2, 0, 1)]
        return LandingPlan(
            pages=[
                LandingPagePlan(
                    persona_key="persona-a",
                    ai_intent="작게 시작할 수 있다는 메시지로 구매 부담을 낮췄습니다.",
                    ux_strategy=PersonaUXStrategy(
                        primary_context="작은 집을 꾸미는 첫 독립 상황",
                        primary_value="예산 안에서 효율적인 공간 완성",
                        primary_problem="선택지가 많아 생기는 결정 부담",
                        interaction_strategy=["간결한 추천 경로"],
                        component_strategy=["핵심 가치가 담긴 히어로를 먼저 배치"],
                        copy_strategy="작게 시작할 수 있다는 실용적 표현",
                    ),
                    components=[
                        LandingComponentSelection(
                            template_id=template_id,
                            copy_values=["작은 변화로 시작하는 새로운 공간"],
                            image_values=[
                                EditableImage(
                                    asset_filename="01_room.png",
                                    alt="밝고 정돈된 거실",
                                )
                            ],
                        ) for template_id in selected
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

    async def generate_image(self, **_: object) -> tuple[str, bytes]:
        return "image/png", b"generated-image"


class HeaderAwareLandingParser(FakeLandingParser):
    async def compose(self, **kwargs: object) -> LandingPlan:
        components = kwargs["components"]
        assert isinstance(components, list)
        selected = [components[index]["template_id"] for index in (0, 1, 2, 0, 1)]
        return LandingPlan(
            pages=[
                LandingPagePlan(
                    persona_key="persona-a",
                    ai_intent="본문만 페르소나에 맞춰 구성했습니다.",
                    components=[
                        LandingComponentSelection(
                            template_id=template_id,
                            copy_values=["캠페인에 맞춘 본문 제목"],
                            image_values=[
                                EditableImage(
                                    asset_filename="01_room.png",
                                    alt="밝고 정돈된 거실",
                                )
                            ],
                        ) for template_id in selected
                    ],
                )
            ]
        )


class AllComponentsLandingParser(FakeLandingParser):
    async def compose(self, **kwargs: object) -> LandingPlan:
        components = kwargs["components"]
        assert isinstance(components, list)
        return LandingPlan(
            pages=[
                LandingPagePlan(
                    persona_key="persona-a",
                    ai_intent="모든 본문 컴포넌트를 순서대로 유지했습니다.",
                    components=[
                        LandingComponentSelection(
                            template_id=item["template_id"],
                            copy_values=["캠페인에 맞춘 본문 제목"],
                            image_values=[
                                EditableImage(
                                    asset_filename="01_room.png",
                                    alt="밝고 정돈된 거실",
                                )
                            ],
                        )
                        for item in [*components, *components[: max(0, 5 - len(components))]]
                    ],
                )
            ]
        )


class PartialLandingParser(FakeLandingParser):
    async def compose(self, **kwargs: object) -> LandingPlan:
        components = kwargs["components"]
        assert isinstance(components, list)
        selected = [components[index]["template_id"] for index in (0, 1, 2, 0, 1)]
        return LandingPlan(
            pages=[
                LandingPagePlan(
                    persona_key="persona-a",
                    ai_intent="AI가 일부 편집값만 반환했습니다.",
                    components=[
                        LandingComponentSelection(
                            template_id=template_id,
                            copy_values=[],
                            image_values=[],
                        )
                        for template_id in selected
                    ],
                )
            ]
        )


class RepeatedComponentLandingParser(FakeLandingParser):
    def __init__(self, count: int) -> None:
        self.count = count

    async def compose(self, **kwargs: object) -> LandingPlan:
        components = kwargs["components"]
        assert isinstance(components, list)
        selected = [components[0]["template_id"]] * self.count
        selected.extend([components[1]["template_id"]] * 2)
        selected.extend([components[2]["template_id"]] * (5 - len(selected)))
        return LandingPlan(
            pages=[
                LandingPagePlan(
                    persona_key="persona-a",
                    ai_intent="같은 템플릿을 서로 다른 역할로 반복합니다.",
                    components=[
                        LandingComponentSelection(
                            template_id=template_id,
                            copy_values=[f"맞춤 메시지 {index + 1}"],
                            image_values=[],
                        )
                        for index, template_id in enumerate(selected)
                    ],
                )
            ]
        )


class UnderfilledLandingParser(FakeLandingParser):
    async def compose(self, **kwargs: object) -> LandingPlan:
        components = kwargs["components"]
        assert isinstance(components, list)
        selected = [components[index]["template_id"] for index in (0, 1, 2, 0)]
        return LandingPlan(
            pages=[
                LandingPagePlan(
                    persona_key="persona-a",
                    ai_intent="컴포넌트 수가 부족한 계획입니다.",
                    components=[
                        LandingComponentSelection(
                            template_id=template_id,
                            copy_values=[],
                            image_values=[],
                        )
                        for template_id in selected
                    ],
                )
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
    (root / "campaign" / campaign_id / "component" / "02_proof.html").write_text(
        '<section data-component-name="근거"><p data-editable="copy">기존 근거</p></section>',
        encoding="utf-8",
    )
    (root / "campaign" / campaign_id / "component" / "03_cta.html").write_text(
        '<section data-component-name="CTA"><p data-editable="copy">기존 CTA</p></section>',
        encoding="utf-8",
    )
    (root / "campaign" / campaign_id / "assets" / "01_room.png").write_bytes(
        b"fake-png"
    )
    now = datetime.now(timezone.utc)
    persona = PersonaKnowledge(
        name="민지",
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

    assert result.pages[0].persona_name == "민지"
    assert result.pages[0].ux_strategy.primary_problem == "선택지가 많아 생기는 결정 부담"
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

    uploaded = service.upload_asset(
        result.landing_id,
        filename="new-room.png",
        content_type="image/png",
        data=b"uploaded-image",
    )
    assert uploaded.source == "landing"
    assert (
        service.asset_path(result.landing_id, uploaded.filename).read_bytes()
        == b"uploaded-image"
    )

    generated = await service.generate_image_asset(
        result.landing_id,
        ImageGenerateRequest(
            persona_key="persona-a",
            instance_id=result.pages[0].components[0].instance_id,
            editable_index=0,
            prompt="햇살이 드는 작은 거실",
            aspect_ratio="16:9",
        ),
    )
    assert generated.source == "landing"
    assert (
        service.asset_path(result.landing_id, generated.filename).read_bytes()
        == b"generated-image"
    )

    component = result.pages[0].components[0]
    saved = service.save(
        result.landing_id,
        LandingSaveRequest(
            pages=[
                LandingPageUpdate(
                    persona_key="persona-a",
                    components=[
                        {
                            "instance_id": component.instance_id,
                            "template_id": component.template_id,
                            "html": component.html.replace(
                                "작은 변화로 시작하는 새로운 공간",
                                "내 예산에 맞춘 첫 번째 공간",
                            ),
                            "hidden": False,
                        }
                    ],
                )
            ]
        ),
    )
    assert saved.status.value == "saved"
    assert "내 예산에 맞춘 첫 번째 공간" in (
        tmp_path
        / "projects"
        / project_id
        / "landing"
        / result.landing_id
        / "pages"
        / "persona-a"
        / "index.html"
    ).read_text(encoding="utf-8")

    invalid_html = component.html.replace("<h1", "<h2").replace("</h1>", "</h2>")
    with pytest.raises(RuntimeError, match="Only editable copy"):
        service.save(
            result.landing_id,
            LandingSaveRequest(
                pages=[
                    LandingPageUpdate(
                        persona_key="persona-a",
                        components=[
                            {
                                "instance_id": component.instance_id,
                                "template_id": component.template_id,
                                "html": invalid_html,
                            }
                        ],
                    )
                ]
            ),
        )


def test_apply_editable_values_preserves_safe_semantic_line_breaks() -> None:
    from app.landing.html import apply_editable_values

    source = '<h2 data-editable="copy">기존 제목</h2>'
    html = apply_editable_values(
        source,
        ["복잡한 공간을\n말끔히 정리해 줄\nKALLAX 칼락스<script>"],
        [],
    )

    assert html == (
        '<h2 data-editable="copy">복잡한 공간을<br>말끔히 정리해 줄<br>'
        'KALLAX 칼락스&lt;script&gt;</h2>'
    )


@pytest.mark.asyncio
async def test_landing_plan_may_omit_normalized_components(
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project(settings)
    component_dir = (
        tmp_path
        / "projects"
        / project_id
        / "campaign"
        / "campaign-record"
        / "component"
    )
    (component_dir / "02_proof.html").write_text(
        '<section data-component-name="근거" data-component-category="proof" '
        'data-layout-options="source cards"><p data-editable="copy">기존 근거</p></section>',
        encoding="utf-8",
    )
    (component_dir / "04_optional.html").write_text(
        '<section data-component-name="선택 콘텐츠"><p data-editable="copy">선택</p></section>',
        encoding="utf-8",
    )
    service = LandingService(settings, parser=FakeLandingParser())

    result = await service.create(project_id)

    selected_ids = [item.template_id for item in result.pages[0].components]
    assert len(selected_ids) == 5
    assert "component-4" not in selected_ids


@pytest.mark.asyncio
async def test_landing_plan_may_use_a_component_twice(tmp_path: Path) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project(settings)
    service = LandingService(settings, parser=RepeatedComponentLandingParser(2))

    result = await service.create(project_id)

    assert len(result.pages[0].components) == 5
    assert result.pages[0].components[0].instance_id != result.pages[0].components[1].instance_id


@pytest.mark.asyncio
async def test_landing_plan_rejects_a_component_used_more_than_twice(
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project(settings)
    service = LandingService(settings, parser=RepeatedComponentLandingParser(3))

    with pytest.raises(AIParserError, match="at most twice"):
        await service.create(project_id)


@pytest.mark.asyncio
async def test_landing_plan_requires_at_least_five_components(tmp_path: Path) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project(settings)
    service = LandingService(settings, parser=UnderfilledLandingParser())

    with pytest.raises(AIParserError, match="at least five"):
        await service.create(project_id)


@pytest.mark.asyncio
async def test_landing_keeps_source_values_when_ai_omits_editable_targets(
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project(settings)
    service = LandingService(settings, parser=PartialLandingParser())

    result = await service.create(project_id)

    html = result.pages[0].components[0].html
    assert "기존 제목" in html
    assert 'src="old.png"' in html
    assert 'alt="기존 이미지"' in html


@pytest.mark.asyncio
async def test_landing_assigns_ikea_metadata_image_urls_to_body_components(
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project(settings)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True)
    (upload_dir / "ikea_metadata_300_v2.json").write_text(
        json.dumps(
            [
                {
                    "id": "IKEA-HERO",
                    "image": {
                        "cdn_url": "https://www.ikea.com/hero-room.jpg",
                        "alt_text": "Hero room",
                        "context_text": "living room gallery roomset",
                        "image_type": "roomset",
                        "recommended_component": "hero",
                    },
                    "classification": {
                        "room": "living_room",
                        "category": "living_room_furniture",
                        "sub_category": None,
                        "products": [],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    service = LandingService(settings, parser=FakeLandingParser())

    result = await service.create(project_id)

    html = result.pages[0].components[0].html
    assert 'src="https://www.ikea.com/hero-room.jpg"' in html
    assert 'src="asset://https://www.ikea.com/hero-room.jpg"' not in html
    assert 'alt="IKEA living room gallery roomset"' in html


@pytest.mark.asyncio
async def test_navigation_is_fixed_header_and_excluded_from_body_library(
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project(settings)
    component_dir = (
        tmp_path
        / "projects"
        / project_id
        / "campaign"
        / "campaign-record"
        / "component"
    )
    (component_dir / "00_header.html").write_text(
        '<header data-component-name="공통 헤더" data-component-category="navigation">'
        "공통 메뉴"
        "</header>",
        encoding="utf-8",
    )
    service = LandingService(settings, parser=HeaderAwareLandingParser())

    result = await service.create(project_id)

    assert [item.name for item in result.component_library] == ["히어로", "근거", "CTA"]
    page = result.pages[0]
    assert [item.name for item in page.header_components] == ["공통 헤더"]
    assert page.components[0].name == "히어로"
    assert len(page.components) == 5
    exported = (
        tmp_path
        / "projects"
        / project_id
        / "landing"
        / result.landing_id
        / "pages"
        / "persona-a"
        / "index.html"
    ).read_text(encoding="utf-8")
    assert exported.index("공통 메뉴") < exported.index("캠페인에 맞춘 본문 제목")

    legacy = result.model_copy(
        update={
            "component_library": [
                result.pages[0].header_components[0].model_copy(
                    update={
                        "filename": "00_header.html",
                        "editable_targets": [],
                    }
                ),
                *result.component_library,
            ],
            "pages": [
                result.pages[0].model_copy(
                    update={
                        "header_components": [],
                        "components": [
                            *result.pages[0].header_components,
                            *result.pages[0].components,
                        ],
                    }
                )
            ],
        }
    )
    service._save_record(legacy)

    upgraded = service.get(result.landing_id)

    assert [item.name for item in upgraded.component_library] == ["히어로", "근거", "CTA"]
    assert [item.name for item in upgraded.pages[0].header_components] == ["공통 헤더"]
    assert upgraded.pages[0].components[0].name == "히어로"


@pytest.mark.asyncio
async def test_uploaded_project_header_is_fixed_when_campaign_has_no_header(
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project(settings)
    upload_dir = tmp_path / "uploads" / project_id
    upload_dir.mkdir(parents=True)
    (upload_dir / "header.html").write_text(
        '<header data-component-name="업로드 헤더">업로드 공통 메뉴</header>',
        encoding="utf-8",
    )
    service = LandingService(settings, parser=HeaderAwareLandingParser())

    result = await service.create(project_id)

    assert [item.name for item in result.component_library] == ["히어로", "근거", "CTA"]
    page = result.pages[0]
    assert [item.name for item in page.header_components] == ["업로드 헤더"]
    assert [item.category for item in page.header_components] == ["navigation"]
    exported = (
        tmp_path
        / "projects"
        / project_id
        / "landing"
        / result.landing_id
        / "pages"
        / "persona-a"
        / "index.html"
    ).read_text(encoding="utf-8")
    assert exported.index("업로드 공통 메뉴") < exported.index("캠페인에 맞춘 본문 제목")


@pytest.mark.asyncio
async def test_navigation_body_component_does_not_move_above_uploaded_header(
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project(settings)
    upload_dir = tmp_path / "uploads" / project_id
    upload_dir.mkdir(parents=True)
    (upload_dir / "header.html").write_text(
        '<header data-component-name="업로드 헤더">업로드 공통 메뉴</header>',
        encoding="utf-8",
    )
    component_dir = (
        tmp_path
        / "projects"
        / project_id
        / "campaign"
        / "campaign-record"
        / "component"
    )
    (component_dir / "00_navigation.html").write_text(
        '<div data-component-name="본문 내비게이션" data-component-category="navigation">'
        "캠페인 보조 내비게이션"
        "</div>",
        encoding="utf-8",
    )
    service = LandingService(settings, parser=AllComponentsLandingParser())

    result = await service.create(project_id)

    page = result.pages[0]
    assert [item.name for item in page.header_components] == ["업로드 헤더"]
    assert "본문 내비게이션" in [item.name for item in page.components]
    exported = (
        tmp_path
        / "projects"
        / project_id
        / "landing"
        / result.landing_id
        / "pages"
        / "persona-a"
        / "index.html"
    ).read_text(encoding="utf-8")
    assert exported.index("업로드 공통 메뉴") < exported.index("캠페인 보조 내비게이션")


@pytest.mark.asyncio
async def test_header_root_component_is_fixed_even_without_navigation_category(
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path)
    project_id = make_project(settings)
    component_dir = (
        tmp_path
        / "projects"
        / project_id
        / "campaign"
        / "campaign-record"
        / "component"
    )
    (component_dir / "header.html").write_text(
        '<header data-component-name="파일명 헤더">파일명 공통 메뉴</header>',
        encoding="utf-8",
    )
    service = LandingService(settings, parser=HeaderAwareLandingParser())

    result = await service.create(project_id)

    page = result.pages[0]
    assert [item.name for item in page.header_components] == ["파일명 헤더"]
    assert page.components[0].name == "히어로"
    assert len(page.components) == 5
    exported = (
        tmp_path
        / "projects"
        / project_id
        / "landing"
        / result.landing_id
        / "pages"
        / "persona-a"
        / "index.html"
    ).read_text(encoding="utf-8")
    assert exported.startswith('<header data-component-name="파일명 헤더"')
    assert exported.index("파일명 공통 메뉴") < exported.index("캠페인에 맞춘 본문 제목")


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

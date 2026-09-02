from __future__ import annotations

import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.brand.ai_parser import AIParserError
from app.brand.service import _safe_filename, _write_bytes, _write_text
from app.campaign.componentization import split_components
from app.core.config import Settings
from app.landing.ai_parser import GeminiLandingParser
from app.landing.html import (
    apply_editable_values,
    apply_layout_variant,
    component_layout_options,
    component_metadata,
    editable_counts,
    editable_image_sources,
    editable_structure,
    inspect_editable_targets,
)
from app.landing.schemas import (
    ComponentTemplate,
    CopyCandidateRequest,
    CopyCandidateResponse,
    ImageGenerateRequest,
    LandingAsset,
    LandingComponent,
    LandingPage,
    LandingPlan,
    LandingResponse,
    LandingSaveRequest,
    LandingStatus,
)
from app.persona.schemas import PersonaAnalysisResponse, PersonaStatus
from app.project.service import ensure_project, project_dir, update_project_stage


class LandingNotFoundError(FileNotFoundError):
    pass


class LandingStateError(RuntimeError):
    pass


class LandingParser(Protocol):
    async def compose(
        self,
        *,
        brand_context: str,
        campaign_context: str,
        personas: list[dict[str, Any]],
        components: list[dict[str, Any]],
        asset_filenames: list[str],
        reference_context: dict[str, Any] | None = None,
    ) -> LandingPlan: ...

    async def generate_copy_candidates(
        self,
        *,
        current_value: str,
        user_prompt: str,
        persona_name: str,
        page_intent: str,
        brand_context: str,
        campaign_context: str,
    ) -> CopyCandidateResponse: ...

    async def generate_image(
        self,
        *,
        prompt: str,
        persona_name: str,
        page_intent: str,
        brand_context: str,
        campaign_context: str,
        aspect_ratio: str,
    ) -> tuple[str, bytes]: ...


class LandingService:
    def __init__(
        self,
        settings: Settings,
        parser: LandingParser | None = None,
    ) -> None:
        self._settings = settings
        self._parser = parser or GeminiLandingParser(settings)

    async def create(self, project_id: str) -> LandingResponse:
        root = ensure_project(self._settings, project_id)
        project_record = _load_json(root / "project.json")
        campaign_id = _stage_id(project_record, "campaign", "current_campaign_id")
        persona_id = _stage_id(project_record, "persona", "current_persona_id")
        campaign_dir = root / "campaign" / campaign_id
        persona_dir = root / "persona" / persona_id
        persona_record = PersonaAnalysisResponse.model_validate_json(
            (persona_dir / "record.json").read_text(encoding="utf-8")
        )
        if persona_record.status != PersonaStatus.FINALIZED:
            raise LandingStateError("Persona data must be finalized first")

        all_templates = _load_templates(campaign_dir / "component")
        if not all_templates:
            raise LandingStateError("At least one campaign HTML component is required")
        header_templates = [
            item for item in all_templates if item.category == "navigation"
        ]
        templates = [
            item for item in all_templates if item.category != "navigation"
        ]
        if not templates:
            raise LandingStateError("At least one campaign body component is required")
        assets, asset_paths = _load_assets(campaign_dir / "assets")
        personas = [
            {
                "persona_key": f"persona-{chr(97 + index)}",
                "name": persona.name,
                "data": persona.model_dump(),
            }
            for index, persona in enumerate(persona_record.data.personas)
        ]
        component_manifest = [
            {
                "template_id": item.template_id,
                "name": item.name,
                "category": item.category,
                "editable_targets": [
                    target.model_dump() for target in item.editable_targets
                ],
                "layout_options": item.layout_options,
            }
            for item in templates
        ]
        plan = await self._parser.compose(
            brand_context=_stage_markdown(
                root, project_record, "brand", "current_brand_id", "brand.md"
            ),
            campaign_context=_stage_markdown(
                root, project_record, "campaign", "current_campaign_id", "campaign.md"
            ),
            personas=personas,
            components=component_manifest,
            asset_filenames=[item.filename for item in assets],
            reference_context=_reference_layout_context(campaign_dir),
        )
        pages = _build_pages(
            plan,
            personas,
            templates,
            set(asset_paths),
            header_templates=header_templates,
        )

        landing_id = str(uuid4())
        now = datetime.now(timezone.utc)
        response = LandingResponse(
            project_id=project_id,
            landing_id=landing_id,
            source_campaign_id=campaign_id,
            source_persona_id=persona_id,
            status=LandingStatus.DRAFT,
            component_library=templates,
            assets=assets,
            pages=pages,
            created_at=now,
            updated_at=now,
        )
        landing_dir = root / "landing" / landing_id
        self._save_record(response)
        for page in pages:
            _write_text(
                landing_dir / "pages" / page.persona_key / "index.html",
                _page_html(page),
            )
        update_project_stage(
            self._settings,
            project_id,
            "landing",
            status=response.status.value,
            item_id_name="current_landing_id",
            item_id=landing_id,
            next_route="/#landing-editor",
        )
        return response

    def get(self, landing_id: str) -> LandingResponse:
        record = self._load_record(landing_id)
        upgraded = _upgrade_legacy_header(record)
        if upgraded == record:
            return record
        upgraded = upgraded.model_copy(
            update={"updated_at": datetime.now(timezone.utc)}
        )
        self._save_record(upgraded)
        landing_dir = (
            project_dir(self._settings, upgraded.project_id)
            / "landing"
            / upgraded.landing_id
        )
        for page in upgraded.pages:
            _write_text(
                landing_dir / "pages" / page.persona_key / "index.html",
                _page_html(page),
            )
        return upgraded

    def save(self, landing_id: str, request: LandingSaveRequest) -> LandingResponse:
        record = self.get(landing_id)
        if [item.persona_key for item in request.pages] != [
            item.persona_key for item in record.pages
        ]:
            raise LandingStateError("Every persona page must be saved in order")
        template_map = {item.template_id: item for item in record.component_library}
        allowed_assets = {item.filename for item in record.assets}
        saved_pages: list[LandingPage] = []
        seen_instance_ids: set[str] = set()
        for page, update in zip(record.pages, request.pages, strict=True):
            components: list[LandingComponent] = []
            for item in update.components:
                if item.instance_id in seen_instance_ids:
                    raise LandingStateError("Component instance IDs must be unique")
                seen_instance_ids.add(item.instance_id)
                template = template_map.get(item.template_id)
                if template is None:
                    raise LandingStateError("Unknown component template")
                if editable_structure(item.html) != editable_structure(template.html):
                    raise LandingStateError(
                        "Only editable copy and image values may be changed"
                    )
                for source in editable_image_sources(item.html):
                    if (
                        source.startswith("asset://")
                        and source[8:] not in allowed_assets
                    ):
                        raise LandingStateError(
                            "Component references an unknown image asset"
                        )
                if item.layout_variant not in template.layout_options:
                    raise LandingStateError("Unknown component layout variant")
                components.append(
                    LandingComponent(
                        instance_id=item.instance_id,
                        template_id=template.template_id,
                        name=template.name,
                        category=template.category,
                        html=item.html,
                        layout_variant=item.layout_variant,
                        layout_options=template.layout_options,
                        hidden=item.hidden,
                    )
                )
            saved_pages.append(page.model_copy(update={"components": components}))
        now = datetime.now(timezone.utc)
        saved = record.model_copy(
            update={
                "status": LandingStatus.SAVED,
                "pages": saved_pages,
                "updated_at": now,
            }
        )
        landing_dir = (
            project_dir(self._settings, record.project_id) / "landing" / landing_id
        )
        for page in saved.pages:
            _write_text(
                landing_dir / "pages" / page.persona_key / "index.html",
                _page_html(page),
            )
        self._save_record(saved)
        update_project_stage(
            self._settings,
            record.project_id,
            "landing",
            status=saved.status.value,
            item_id_name="current_landing_id",
            item_id=landing_id,
            next_route="/#landing-editor",
        )
        return saved

    async def copy_candidates(
        self,
        landing_id: str,
        request: CopyCandidateRequest,
    ) -> CopyCandidateResponse:
        record = self._load_record(landing_id)
        page = next(
            (item for item in record.pages if item.persona_key == request.persona_key),
            None,
        )
        if page is None:
            raise LandingStateError("Landing persona page was not found")
        root = project_dir(self._settings, record.project_id)
        project_record = _load_json(root / "project.json")
        return await self._parser.generate_copy_candidates(
            current_value=request.current_value,
            user_prompt=request.prompt,
            persona_name=page.persona_name,
            page_intent=page.ai_intent,
            brand_context=_stage_markdown(
                root, project_record, "brand", "current_brand_id", "brand.md"
            ),
            campaign_context=_stage_markdown(
                root, project_record, "campaign", "current_campaign_id", "campaign.md"
            ),
        )

    def upload_asset(
        self,
        landing_id: str,
        *,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> LandingAsset:
        if not data:
            raise LandingStateError("Uploaded image is empty")
        if len(data) > self._settings.max_campaign_asset_size_bytes:
            raise LandingStateError("Uploaded image exceeds the size limit")
        safe_name = _safe_filename(filename)
        guessed_type = mimetypes.guess_type(safe_name)[0] or content_type
        if guessed_type not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
            raise LandingStateError("PNG, JPG, GIF, or WEBP image is required")
        suffix = (
            Path(safe_name).suffix.lower()
            or mimetypes.guess_extension(guessed_type)
            or ".png"
        )
        asset = LandingAsset(
            filename=f"upload-{uuid4().hex}{suffix}",
            content_type=guessed_type,
            source="landing",
        )
        record = self._load_record(landing_id)
        _write_bytes(
            project_dir(self._settings, record.project_id)
            / "landing"
            / landing_id
            / "assets"
            / asset.filename,
            data,
        )
        record.assets.append(asset)
        record.updated_at = datetime.now(timezone.utc)
        self._save_record(record)
        return asset

    async def generate_image_asset(
        self,
        landing_id: str,
        request: ImageGenerateRequest,
    ) -> LandingAsset:
        record = self._load_record(landing_id)
        page = next(
            (item for item in record.pages if item.persona_key == request.persona_key),
            None,
        )
        if page is None:
            raise LandingStateError("Landing persona page was not found")
        root = project_dir(self._settings, record.project_id)
        project_record = _load_json(root / "project.json")
        content_type, data = await self._parser.generate_image(
            prompt=request.prompt,
            persona_name=page.persona_name,
            page_intent=page.ai_intent,
            brand_context=_stage_markdown(
                root, project_record, "brand", "current_brand_id", "brand.md"
            ),
            campaign_context=_stage_markdown(
                root, project_record, "campaign", "current_campaign_id", "campaign.md"
            ),
            aspect_ratio=request.aspect_ratio,
        )
        suffix = mimetypes.guess_extension(content_type) or ".png"
        if suffix == ".jpe":
            suffix = ".jpg"
        asset = LandingAsset(
            filename=f"generated-{uuid4().hex}{suffix}",
            content_type=content_type,
            source="landing",
        )
        _write_bytes(
            root / "landing" / landing_id / "assets" / asset.filename,
            data,
        )
        record.assets.append(asset)
        record.updated_at = datetime.now(timezone.utc)
        self._save_record(record)
        return asset

    def asset_path(self, landing_id: str, filename: str) -> Path:
        record = self._load_record(landing_id)
        asset = next(
            (item for item in record.assets if item.filename == filename), None
        )
        if asset is None:
            raise LandingNotFoundError("Landing asset was not found")
        root = project_dir(self._settings, record.project_id)
        path = (
            root / "landing" / landing_id / "assets" / filename
            if asset.source == "landing"
            else root / "campaign" / record.source_campaign_id / "assets" / filename
        )
        if not path.is_file():
            raise LandingNotFoundError("Landing asset was not found")
        return path

    def _record_path(self, landing_id: str) -> Path:
        try:
            normalized = str(UUID(landing_id))
        except ValueError as exc:
            raise LandingNotFoundError("Landing was not found") from exc
        projects_root = self._settings.storage_root / "projects"
        for path in projects_root.glob(f"*/landing/{normalized}/record.json"):
            return path
        raise LandingNotFoundError("Landing was not found")

    def _load_record(self, landing_id: str) -> LandingResponse:
        return LandingResponse.model_validate_json(
            self._record_path(landing_id).read_text(encoding="utf-8")
        )

    def _save_record(self, record: LandingResponse) -> None:
        _write_text(
            project_dir(self._settings, record.project_id)
            / "landing"
            / record.landing_id
            / "record.json",
            record.model_dump_json(indent=2),
        )


def _load_templates(component_dir: Path) -> list[ComponentTemplate]:
    templates: list[ComponentTemplate] = []
    if not component_dir.is_dir():
        return templates
    template_index = 0
    for path in sorted(component_dir.glob("*.htm*")):
        source = path.read_text(encoding="utf-8")
        fragments = (
            [source]
            if "data-component-name" in source
            else [fragment.html for fragment in split_components(source, path.name)]
        )
        for fragment_index, fragment in enumerate(fragments, start=1):
            template_index += 1
            name, category = component_metadata(fragment, path.name)
            filename = (
                path.name
                if len(fragments) == 1
                else f"{path.stem}-{fragment_index}.html"
            )
            templates.append(
                ComponentTemplate(
                    template_id=f"component-{template_index}",
                    name=name,
                    category=category,
                    filename=filename,
                    html=fragment,
                    editable_targets=inspect_editable_targets(fragment),
                    layout_options=component_layout_options(fragment),
                )
            )
    return templates


def _load_assets(asset_dir: Path) -> tuple[list[LandingAsset], dict[str, Path]]:
    if not asset_dir.is_dir():
        return [], {}
    paths = {path.name: path for path in sorted(asset_dir.iterdir()) if path.is_file()}
    assets = [
        LandingAsset(
            filename=name,
            content_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
        )
        for name in paths
    ]
    return assets, paths


def _build_pages(
    plan: LandingPlan,
    personas: list[dict[str, Any]],
    templates: list[ComponentTemplate],
    asset_filenames: set[str],
    *,
    header_templates: list[ComponentTemplate] | None = None,
) -> list[LandingPage]:
    expected_keys = [item["persona_key"] for item in personas]
    if [page.persona_key for page in plan.pages] != expected_keys:
        raise AIParserError("Landing plan must contain every persona in order")
    template_map = {item.template_id: item for item in templates}
    persona_map = {item["persona_key"]: item for item in personas}
    pages: list[LandingPage] = []
    for page_plan in plan.pages:
        selected_ids = [selection.template_id for selection in page_plan.components]
        expected_ids = [template.template_id for template in templates]
        if len(selected_ids) != len(expected_ids) or set(selected_ids) != set(
            expected_ids
        ):
            raise AIParserError(
                "Landing plan must include every component template exactly once"
            )
        components: list[LandingComponent] = []
        for selection in page_plan.components:
            template = template_map.get(selection.template_id)
            if template is None:
                raise AIParserError("Landing plan referenced an unknown component")
            if selection.layout_variant not in template.layout_options:
                raise AIParserError("Landing plan referenced an unknown layout variant")
            copy_count, image_count = editable_counts(template.html)
            if (
                len(selection.copy_values) != copy_count
                or len(selection.image_values) != image_count
            ):
                raise AIParserError(
                    "Landing plan did not replace every editable target"
                )
            if any(
                image.asset_filename and image.asset_filename not in asset_filenames
                for image in selection.image_values
            ):
                raise AIParserError("Landing plan referenced an unknown image asset")
            components.append(
                LandingComponent(
                    instance_id=str(uuid4()),
                    template_id=template.template_id,
                    name=template.name,
                    category=template.category,
                    html=apply_editable_values(
                        apply_layout_variant(template.html, selection.layout_variant),
                        selection.copy_values,
                        selection.image_values,
                    ),
                    layout_variant=selection.layout_variant,
                    layout_options=template.layout_options,
                )
            )
        persona = persona_map[page_plan.persona_key]
        header_components = [
            LandingComponent(
                instance_id=str(uuid4()),
                template_id=template.template_id,
                name=template.name,
                category=template.category,
                html=template.html,
                layout_variant="source",
                layout_options=["source"],
            )
            for template in header_templates or []
        ]
        pages.append(
            LandingPage(
                persona_key=page_plan.persona_key,
                persona_name=str(persona["name"]),
                ai_intent=page_plan.ai_intent,
                header_components=header_components,
                components=components,
            )
        )
    return pages


def _page_html(page: LandingPage) -> str:
    """Persist the non-editable shared header before each persona-specific body."""
    return "\n".join(
        component.html
        for component in [*page.header_components, *page.components]
        if not component.hidden
    )


def _upgrade_legacy_header(record: LandingResponse) -> LandingResponse:
    """Move navigation templates from pre-header records into immutable page headers."""
    header_templates = [
        template
        for template in record.component_library
        if template.category == "navigation"
    ]
    if not header_templates:
        return record
    header_template_ids = {template.template_id for template in header_templates}
    body_library = [
        template
        for template in record.component_library
        if template.template_id not in header_template_ids
    ]
    pages: list[LandingPage] = []
    for page in record.pages:
        body_components = [
            component
            for component in page.components
            if component.template_id not in header_template_ids
            and component.category != "navigation"
        ]
        header_components = page.header_components or [
            LandingComponent(
                instance_id=str(uuid4()),
                template_id=template.template_id,
                name=template.name,
                category=template.category,
                html=template.html,
                layout_variant="source",
                layout_options=["source"],
            )
            for template in header_templates
        ]
        pages.append(
            page.model_copy(
                update={
                    "header_components": header_components,
                    "components": body_components,
                }
            )
        )
    return record.model_copy(
        update={"component_library": body_library, "pages": pages}
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise LandingStateError("Project workflow data is incomplete") from exc


def _reference_layout_context(campaign_dir: Path) -> dict[str, Any] | None:
    path = campaign_dir / "reference" / "summary.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _stage_id(record: dict[str, Any], stage: str, key: str) -> str:
    value = record.get(stage, {})
    item_id = value.get(key) if isinstance(value, dict) else None
    if not isinstance(item_id, str):
        raise LandingStateError(f"{stage.title()} data is required")
    return item_id


def _stage_markdown(
    root: Path,
    record: dict[str, Any],
    stage: str,
    key: str,
    filename: str,
) -> str:
    item_id = _stage_id(record, stage, key)
    path = root / stage / item_id / filename
    if not path.is_file():
        raise LandingStateError(f"Finalized {stage} markdown is required")
    return path.read_text(encoding="utf-8")

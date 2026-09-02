from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from app.brand.ai_parser import AIParserError
from app.brand.service import _write_text
from app.core.config import Settings
from app.persona.ai_parser import GeminiPersonaParser
from app.persona.markdown import generate_persona_markdowns
from app.persona.schemas import (
    PersonaAnalysisResponse,
    PersonaBatch,
    PersonaMarkdownFile,
    PersonaMarkdownResponse,
    PersonaStatus,
)
from app.project.service import ensure_project, project_dir, update_project_stage


class PersonaNotFoundError(FileNotFoundError):
    pass


class PersonaStateError(RuntimeError):
    pass


class PersonaParser(Protocol):
    async def analyze(
        self,
        inputs: list[str],
        *,
        brand_context: str,
        campaign_context: str,
    ) -> PersonaBatch: ...


class PersonaService:
    def __init__(
        self,
        settings: Settings,
        parser: PersonaParser | None = None,
    ) -> None:
        self._settings = settings
        self._parser = parser or GeminiPersonaParser(settings)

    async def analyze(
        self, project_id: str, inputs: list[str]
    ) -> PersonaAnalysisResponse:
        project_path = ensure_project(self._settings, project_id)
        brand_context, campaign_context = _load_project_context(project_path)
        data = await self._parser.analyze(
            inputs,
            brand_context=brand_context,
            campaign_context=campaign_context,
        )
        if len(data.personas) != len(inputs):
            raise AIParserError(
                "Gemini must return exactly one persona for every input"
            )

        persona_id = str(uuid4())
        now = datetime.now(timezone.utc)
        record = PersonaAnalysisResponse(
            project_id=project_id,
            persona_id=persona_id,
            status=PersonaStatus.DRAFT,
            inputs=inputs,
            data=data,
            created_at=now,
            updated_at=now,
        )
        persona_dir = self._persona_dir(project_id, persona_id)
        _write_text(
            persona_dir / "inputs.json",
            json.dumps(inputs, ensure_ascii=False, indent=2),
        )
        _write_text(persona_dir / "analyzed.json", data.model_dump_json(indent=2))
        self._save_record(record)
        update_project_stage(
            self._settings,
            project_id,
            "persona",
            status=record.status.value,
            item_id_name="current_persona_id",
            item_id=persona_id,
            next_route="/#persona-check",
        )
        return record

    def get(self, persona_id: str) -> PersonaAnalysisResponse:
        return self._load_record(persona_id)

    def review(
        self, persona_id: str, data: PersonaBatch
    ) -> PersonaAnalysisResponse:
        record = self._load_record(persona_id)
        if record.status == PersonaStatus.FINALIZED:
            raise PersonaStateError("Finalized persona data cannot be reviewed again")
        if len(data.personas) != len(record.inputs):
            raise ValueError("Reviewed persona count must match the analyzed input count")
        updated = record.model_copy(
            update={
                "status": PersonaStatus.REVIEWED,
                "data": data,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        _write_text(
            self._persona_dir(record.project_id, persona_id) / "reviewed.json",
            data.model_dump_json(indent=2),
        )
        self._save_record(updated)
        update_project_stage(
            self._settings,
            record.project_id,
            "persona",
            status=updated.status.value,
            item_id_name="current_persona_id",
            item_id=persona_id,
        )
        return updated

    def finalize(self, persona_id: str) -> PersonaMarkdownResponse:
        record = self._load_record(persona_id)
        if record.status != PersonaStatus.REVIEWED:
            raise PersonaStateError(
                "Persona data must be reviewed before it can be finalized"
            )
        files = generate_persona_markdowns(record.data)
        persona_dir = self._persona_dir(record.project_id, persona_id)
        for item in files:
            _write_text(persona_dir / item.filename, item.markdown)
        finalized = record.model_copy(
            update={
                "status": PersonaStatus.FINALIZED,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._save_record(finalized)
        update_project_stage(
            self._settings,
            record.project_id,
            "persona",
            status=finalized.status.value,
            item_id_name="current_persona_id",
            item_id=persona_id,
        )
        return PersonaMarkdownResponse(
            project_id=record.project_id,
            persona_id=persona_id,
            status=PersonaStatus.FINALIZED,
            files=files,
        )

    def get_markdown(self, persona_id: str) -> PersonaMarkdownResponse:
        record = self._load_record(persona_id)
        if record.status != PersonaStatus.FINALIZED:
            raise PersonaStateError("Persona data has not been finalized")
        persona_dir = self._persona_dir(record.project_id, persona_id)
        files = [
            PersonaMarkdownFile(
                filename=f"persona-{chr(97 + index)}.md",
                name=persona.name,
                markdown=(persona_dir / f"persona-{chr(97 + index)}.md").read_text(
                    encoding="utf-8"
                ),
            )
            for index, persona in enumerate(record.data.personas)
        ]
        return PersonaMarkdownResponse(
            project_id=record.project_id,
            persona_id=persona_id,
            status=record.status,
            files=files,
        )

    def _persona_dir(self, project_id: str, persona_id: str) -> Path:
        return project_dir(self._settings, project_id) / "persona" / persona_id

    def _record_path(self, persona_id: str) -> Path:
        path = self._find_record_path(persona_id)
        if path:
            return path
        raise PersonaNotFoundError("Persona was not found")

    def _find_record_path(self, persona_id: str) -> Path | None:
        try:
            normalized = str(UUID(persona_id))
        except ValueError as exc:
            raise PersonaNotFoundError("Persona was not found") from exc
        projects_root = self._settings.storage_root / "projects"
        if not projects_root.is_dir():
            return None
        for record_path in projects_root.glob(f"*/persona/{normalized}/record.json"):
            try:
                record = PersonaAnalysisResponse.model_validate_json(
                    record_path.read_text(encoding="utf-8")
                )
            except ValueError:
                continue
            if record.persona_id == persona_id:
                return record_path
        return None

    def _load_record(self, persona_id: str) -> PersonaAnalysisResponse:
        return PersonaAnalysisResponse.model_validate_json(
            self._record_path(persona_id).read_text(encoding="utf-8")
        )

    def _save_record(self, record: PersonaAnalysisResponse) -> None:
        _write_text(
            self._persona_dir(record.project_id, record.persona_id) / "record.json",
            record.model_dump_json(indent=2),
        )


def _load_project_context(project_path: Path) -> tuple[str, str]:
    record_path = project_path / "project.json"
    if not record_path.is_file():
        return "", ""
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "", ""
    return (
        _load_stage_markdown(project_path, record, "brand", "current_brand_id", "brand.md"),
        _load_stage_markdown(
            project_path,
            record,
            "campaign",
            "current_campaign_id",
            "campaign.md",
        ),
    )


def _load_stage_markdown(
    project_path: Path,
    record: dict[str, object],
    stage: str,
    id_key: str,
    filename: str,
) -> str:
    stage_data = record.get(stage)
    if not isinstance(stage_data, dict):
        return ""
    item_id = stage_data.get(id_key)
    if not isinstance(item_id, str):
        return ""
    path = project_path / stage / item_id / filename
    return path.read_text(encoding="utf-8") if path.is_file() else ""

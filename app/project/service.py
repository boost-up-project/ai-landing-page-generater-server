from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.core.config import Settings


class ProjectNotFoundError(FileNotFoundError):
    pass


def create_project_id() -> str:
    return str(uuid4())


def project_dir(settings: Settings, project_id: str) -> Path:
    try:
        normalized = str(UUID(project_id))
    except ValueError as exc:
        raise ProjectNotFoundError("Project was not found") from exc
    return settings.storage_root / "projects" / normalized


def ensure_project(settings: Settings, project_id: str) -> Path:
    path = project_dir(settings, project_id)
    if not path.is_dir():
        raise ProjectNotFoundError("Project was not found")
    return path


def update_project_stage(
    settings: Settings,
    project_id: str,
    stage: str,
    *,
    status: str,
    item_id_name: str,
    item_id: str,
    next_route: str | None = None,
) -> None:
    path = project_dir(settings, project_id)
    path.mkdir(parents=True, exist_ok=True)
    record_path = path / "project.json"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record: dict[str, Any]
    if record_path.is_file():
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            record = {}
    else:
        record = {"project_id": project_id, "created_at": now}

    record["project_id"] = project_id
    record["status"] = f"{stage}_{status}"
    record["updated_at"] = now
    record[stage] = {
        item_id_name: item_id,
        "status": status,
        "updated_at": now,
    }
    if next_route:
        record[stage]["next_route"] = next_route

    temporary = record_path.with_suffix(record_path.suffix + ".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(record_path)

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

from app.brand.ai_parser import AIParserError
from app.brand.service import _safe_filename, _write_bytes, _write_text
from app.campaign.ai_parser import GeminiCampaignParser
from app.campaign.componentization import split_components
from app.campaign.markdown import generate_campaign_markdown
from app.campaign.reference import fetch_public_html, reference_layout_summary
from app.campaign.schemas import (
    CampaignAnalysisResponse,
    CampaignKnowledge,
    CampaignMarkdownResponse,
    CampaignStatus,
)
from app.common.pdf import ParsedPDF, combine_parsed_pdfs, parse_pdf
from app.core.config import Settings
from app.project.service import ensure_project, project_dir, update_project_stage


class CampaignNotFoundError(FileNotFoundError):
    pass


class CampaignStateError(RuntimeError):
    pass


class CampaignParser(Protocol):
    async def analyze(self, extracted_text: str) -> CampaignKnowledge: ...


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    data: bytes


@dataclass(frozen=True)
class CachedCampaignAnalysis:
    campaign_id: str
    data: CampaignKnowledge


class CampaignService:
    def __init__(
        self,
        settings: Settings,
        parser: CampaignParser | None = None,
    ) -> None:
        self._settings = settings
        self._parser = parser or GeminiCampaignParser(settings)

    async def analyze(
        self,
        project_id: str,
        strategy_file: UploadedFile,
        *,
        component_files: list[UploadedFile] | None = None,
        style_files: list[UploadedFile] | None = None,
        asset_files: list[UploadedFile] | None = None,
        bundle_files: list[UploadedFile] | None = None,
        reference_url: str | None = None,
    ) -> CampaignAnalysisResponse:
        components = component_files or []
        styles = style_files or []
        assets = asset_files or []
        bundles = bundle_files or []
        _validate_component_files(
            components,
            max_files=self._settings.max_campaign_component_files,
            max_size_bytes=self._settings.max_campaign_component_size_bytes,
        )
        _validate_style_files(
            styles,
            max_files=self._settings.max_campaign_style_files,
            max_size_bytes=self._settings.max_campaign_style_size_bytes,
        )
        _validate_bundle_files(
            bundles,
            max_files=self._settings.max_campaign_bundle_files,
            max_size_bytes=self._settings.max_campaign_bundle_size_bytes,
        )
        bundled_components, bundled_styles, bundled_assets = _expand_bundles(
            bundles,
            max_entries=self._settings.max_campaign_bundle_entries,
        )
        components = [*components, *bundled_components]
        styles = [*styles, *bundled_styles]
        assets = [*assets, *bundled_assets]
        _validate_component_files(
            components,
            max_files=self._settings.max_campaign_component_files,
            max_size_bytes=self._settings.max_campaign_component_size_bytes,
        )
        _validate_style_files(
            styles,
            max_files=self._settings.max_campaign_style_files,
            max_size_bytes=self._settings.max_campaign_style_size_bytes,
        )
        _validate_asset_files(
            assets,
            max_files=self._settings.max_campaign_asset_files,
            max_size_bytes=self._settings.max_campaign_asset_size_bytes,
        )
        ensure_project(self._settings, project_id)
        resolved_reference_url = None
        reference_source = ""
        if reference_url:
            resolved_reference_url, reference_source = await fetch_public_html(
                reference_url,
                max_size_bytes=self._settings.max_campaign_reference_size_bytes,
            )

        parsed = parse_pdf(
            strategy_file.data,
            strategy_file.filename,
            max_size_bytes=self._settings.max_pdf_size_bytes,
            max_pages=self._settings.max_pdf_pages,
        )
        extracted_text = combine_parsed_pdfs(
            [parsed],
            max_characters=self._settings.max_extracted_characters,
        )
        source_checksum = sha256(strategy_file.data).hexdigest()
        cached = self._find_cached_analysis(project_id, source_checksum)
        reused_from_campaign_id = cached.campaign_id if cached else None
        data = (
            _copy_campaign_data_for_source(cached.data, strategy_file.filename)
            if cached
            else await self._parser.analyze(extracted_text)
        )
        _validate_source_references(data, parsed)

        campaign_id = str(uuid4())
        now = datetime.now(timezone.utc)
        record = CampaignAnalysisResponse(
            project_id=project_id,
            campaign_id=campaign_id,
            status=CampaignStatus.DRAFT,
            source_file=strategy_file.filename,
            source_checksum=source_checksum,
            reused_from_campaign_id=reused_from_campaign_id,
            component_files=[],
            style_files=[item.filename for item in styles],
            asset_files=[],
            bundle_files=[item.filename for item in bundles],
            reference_url=resolved_reference_url,
            data=data,
            created_at=now,
            updated_at=now,
        )

        campaign_dir = self._campaign_dir(project_id, campaign_id)
        upload_dir = campaign_dir / "uploads"
        _write_bytes(
            upload_dir / _safe_filename(strategy_file.filename), strategy_file.data
        )
        for index, component in enumerate(components, start=1):
            _write_bytes(
                campaign_dir
                / "uploads"
                / "components"
                / f"{index:02d}_{_safe_filename(component.filename)}",
                component.data,
            )
        for index, style in enumerate(styles, start=1):
            _write_bytes(
                campaign_dir
                / "styles"
                / f"{index:02d}_{_safe_filename(style.filename)}",
                style.data,
            )
        for index, asset in enumerate(assets, start=1):
            _write_bytes(
                campaign_dir
                / "assets"
                / f"{index:02d}_{_safe_filename(asset.filename)}",
                asset.data,
            )
        for index, bundle in enumerate(bundles, start=1):
            _write_bytes(
                campaign_dir
                / "uploads"
                / "bundles"
                / f"{index:02d}_{_safe_filename(bundle.filename)}",
                bundle.data,
            )
        if reference_source:
            _write_text(campaign_dir / "reference" / "source.html", reference_source)
            _write_text(
                campaign_dir / "reference" / "summary.json",
                json.dumps(
                    reference_layout_summary(reference_source), ensure_ascii=False
                ),
            )
        asset_names = {
            Path(item.filename).name: f"{index:02d}_{_safe_filename(item.filename)}"
            for index, item in enumerate(assets, start=1)
        }
        shared_styles = "\n".join(item.data.decode("utf-8") for item in styles)
        normalized_components = []
        for component in components:
            normalized_components.extend(
                split_components(
                    component.data.decode("utf-8"),
                    component.filename,
                    shared_styles=shared_styles,
                    asset_names=asset_names,
                )
            )
        for index, component in enumerate(normalized_components, start=1):
            stored_name = f"{index:02d}_{_safe_filename(component.name)}.html"
            _write_text(campaign_dir / "component" / stored_name, component.html)
            record.component_files.append(stored_name)
        record.asset_files = list(asset_names.values())
        _write_text(campaign_dir / "extracted.txt", extracted_text)
        _write_text(campaign_dir / "analyzed.json", data.model_dump_json(indent=2))
        self._save_record(record)
        update_project_stage(
            self._settings,
            project_id,
            "campaign",
            status=record.status.value,
            item_id_name="current_campaign_id",
            item_id=campaign_id,
            next_route="/#campaign-check",
        )
        return record

    def get(self, campaign_id: str) -> CampaignAnalysisResponse:
        return self._load_record(campaign_id)

    def review(
        self, campaign_id: str, data: CampaignKnowledge
    ) -> CampaignAnalysisResponse:
        record = self._load_record(campaign_id)
        if record.status == CampaignStatus.FINALIZED:
            raise CampaignStateError("Finalized campaign data cannot be reviewed again")
        parsed = parse_pdf(
            self._source_path(record).read_bytes(),
            record.source_file,
            max_size_bytes=self._settings.max_pdf_size_bytes,
            max_pages=self._settings.max_pdf_pages,
        )
        _validate_source_references(
            data,
            parsed,
            allow_unreferenced_content=True,
        )
        updated = record.model_copy(
            update={
                "status": CampaignStatus.REVIEWED,
                "data": data,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        _write_text(
            self._campaign_dir(record.project_id, campaign_id) / "reviewed.json",
            data.model_dump_json(indent=2),
        )
        self._save_record(updated)
        update_project_stage(
            self._settings,
            record.project_id,
            "campaign",
            status=updated.status.value,
            item_id_name="current_campaign_id",
            item_id=campaign_id,
            next_route="/#persona-input",
        )
        return updated

    def finalize(self, campaign_id: str) -> CampaignMarkdownResponse:
        record = self._load_record(campaign_id)
        if record.status != CampaignStatus.REVIEWED:
            raise CampaignStateError(
                "Campaign data must be reviewed before it can be finalized"
            )
        markdown = generate_campaign_markdown(record.data)
        _write_text(
            self._campaign_dir(record.project_id, campaign_id) / "campaign.md",
            markdown,
        )
        finalized = record.model_copy(
            update={
                "status": CampaignStatus.FINALIZED,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._save_record(finalized)
        update_project_stage(
            self._settings,
            record.project_id,
            "campaign",
            status=finalized.status.value,
            item_id_name="current_campaign_id",
            item_id=campaign_id,
            next_route="/#persona-input",
        )
        return CampaignMarkdownResponse(
            project_id=record.project_id,
            campaign_id=campaign_id,
            status=CampaignStatus.FINALIZED,
            markdown=markdown,
        )

    def get_markdown(self, campaign_id: str) -> CampaignMarkdownResponse:
        record = self._load_record(campaign_id)
        markdown_path = (
            self._campaign_dir(record.project_id, campaign_id) / "campaign.md"
        )
        if record.status != CampaignStatus.FINALIZED or not markdown_path.is_file():
            raise CampaignStateError("Campaign data has not been finalized")
        return CampaignMarkdownResponse(
            project_id=record.project_id,
            campaign_id=campaign_id,
            status=record.status,
            markdown=markdown_path.read_text(encoding="utf-8"),
        )

    def _find_cached_analysis(
        self, project_id: str, source_checksum: str
    ) -> CachedCampaignAnalysis | None:
        root = project_dir(self._settings, project_id) / "campaign"
        if not root.is_dir():
            return None

        for record_path in sorted(
            root.glob("*/record.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ):
            try:
                record = CampaignAnalysisResponse.model_validate_json(
                    record_path.read_text(encoding="utf-8")
                )
            except ValueError:
                continue
            checksum_matches = record.source_checksum == source_checksum
            if not record.source_checksum:
                source_path = self._source_path(record)
                checksum_matches = source_path.is_file() and (
                    sha256(source_path.read_bytes()).hexdigest() == source_checksum
                )
            if not checksum_matches:
                continue
            analyzed_path = record_path.parent / "analyzed.json"
            if not analyzed_path.is_file():
                continue
            try:
                data = CampaignKnowledge.model_validate_json(
                    analyzed_path.read_text(encoding="utf-8")
                )
            except ValueError:
                continue
            return CachedCampaignAnalysis(campaign_id=record.campaign_id, data=data)
        return None

    def _campaign_dir(self, project_id: str, campaign_id: str) -> Path:
        return project_dir(self._settings, project_id) / "campaign" / campaign_id

    def _record_path(self, campaign_id: str) -> Path:
        record_path = self._find_record_path(campaign_id)
        if record_path:
            return record_path
        raise CampaignNotFoundError("Campaign was not found")

    def _find_record_path(self, campaign_id: str) -> Path | None:
        try:
            normalized = str(UUID(campaign_id))
        except ValueError as exc:
            raise CampaignNotFoundError("Campaign was not found") from exc
        projects_root = self._settings.storage_root / "projects"
        if not projects_root.is_dir():
            return None
        for record_path in projects_root.glob(f"*/campaign/{normalized}/record.json"):
            try:
                record = CampaignAnalysisResponse.model_validate_json(
                    record_path.read_text(encoding="utf-8")
                )
            except ValueError:
                continue
            if record.campaign_id == campaign_id:
                return record_path
        return None

    def _source_path(self, record: CampaignAnalysisResponse) -> Path:
        return (
            self._campaign_dir(record.project_id, record.campaign_id)
            / "uploads"
            / _safe_filename(record.source_file)
        )

    def _load_record(self, campaign_id: str) -> CampaignAnalysisResponse:
        path = self._record_path(campaign_id)
        if not path.is_file():
            raise CampaignNotFoundError("Campaign was not found")
        return CampaignAnalysisResponse.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def _save_record(self, record: CampaignAnalysisResponse) -> None:
        _write_text(
            self._campaign_dir(record.project_id, record.campaign_id) / "record.json",
            record.model_dump_json(indent=2),
        )


def _validate_component_files(
    files: list[UploadedFile], *, max_files: int, max_size_bytes: int
) -> None:
    if len(files) > max_files:
        raise ValueError(f"A maximum of {max_files} HTML components is allowed")
    for item in files:
        if not item.data:
            raise ValueError(f"{item.filename}: empty file")
        if len(item.data) > max_size_bytes:
            raise ValueError(
                f"{item.filename}: file exceeds the {max_size_bytes}-byte limit"
            )
        if Path(item.filename).suffix.lower() not in {".html", ".htm"}:
            raise ValueError(f"{item.filename}: component files must be HTML")
        try:
            item.data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{item.filename}: HTML must be UTF-8 encoded") from exc


def _validate_style_files(
    files: list[UploadedFile], *, max_files: int, max_size_bytes: int
) -> None:
    if len(files) > max_files:
        raise ValueError(f"A maximum of {max_files} CSS files is allowed")
    for item in files:
        if not item.data:
            raise ValueError(f"{item.filename}: CSS file is empty")
        if len(item.data) > max_size_bytes:
            raise ValueError(
                f"{item.filename}: file exceeds the {max_size_bytes}-byte limit"
            )
        if Path(item.filename).suffix.lower() != ".css":
            raise ValueError(f"{item.filename}: style files must be CSS")
        try:
            item.data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{item.filename}: CSS must be UTF-8 encoded") from exc


def _validate_bundle_files(
    files: list[UploadedFile], *, max_files: int, max_size_bytes: int
) -> None:
    if len(files) > max_files:
        raise ValueError(f"A maximum of {max_files} ZIP bundles is allowed")
    for item in files:
        if not item.data:
            raise ValueError(f"{item.filename}: ZIP bundle is empty")
        if len(item.data) > max_size_bytes:
            raise ValueError(
                f"{item.filename}: file exceeds the {max_size_bytes}-byte limit"
            )
        if Path(item.filename).suffix.lower() != ".zip":
            raise ValueError(f"{item.filename}: bundle files must be ZIP")


def _expand_bundles(
    bundles: list[UploadedFile], *, max_entries: int
) -> tuple[list[UploadedFile], list[UploadedFile], list[UploadedFile]]:
    components: list[UploadedFile] = []
    styles: list[UploadedFile] = []
    assets: list[UploadedFile] = []
    for bundle in bundles:
        try:
            with ZipFile(BytesIO(bundle.data)) as archive:
                entries = [item for item in archive.infolist() if not item.is_dir()]
                if len(entries) > max_entries:
                    raise ValueError(
                        f"{bundle.filename}: ZIP contains more than {max_entries} files"
                    )
                for item in entries:
                    member = Path(item.filename)
                    if member.is_absolute() or ".." in member.parts:
                        raise ValueError(
                            f"{bundle.filename}: ZIP contains an unsafe path"
                        )
                    if (
                        item.is_dir()
                        or (item.external_attr >> 16) & 0o170000 == 0o120000
                    ):
                        raise ValueError(
                            f"{bundle.filename}: ZIP contains an unsupported link"
                        )
                    suffix = member.suffix.lower()
                    data = archive.read(item)
                    filename = member.name
                    if suffix in {".html", ".htm"}:
                        components.append(UploadedFile(filename, data))
                    elif suffix == ".css":
                        styles.append(UploadedFile(filename, data))
                    elif suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                        assets.append(UploadedFile(filename, data))
        except BadZipFile as exc:
            raise ValueError(
                f"{bundle.filename}: bundle is not a valid ZIP file"
            ) from exc
    return components, styles, assets


def _validate_asset_files(
    files: list[UploadedFile], *, max_files: int, max_size_bytes: int
) -> None:
    if len(files) > max_files:
        raise ValueError(f"A maximum of {max_files} image assets is allowed")
    validators = {
        ".png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": lambda data: data.startswith(b"\xff\xd8\xff"),
        ".jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
        ".gif": lambda data: data.startswith((b"GIF87a", b"GIF89a")),
        ".webp": lambda data: data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }
    for item in files:
        if not item.data:
            raise ValueError(f"{item.filename}: empty file")
        if len(item.data) > max_size_bytes:
            raise ValueError(
                f"{item.filename}: file exceeds the {max_size_bytes}-byte limit"
            )
        suffix = Path(item.filename).suffix.lower()
        validator = validators.get(suffix)
        if validator is None:
            raise ValueError(
                f"{item.filename}: image files must be PNG, JPG, JPEG, GIF, or WEBP"
            )
        if not validator(item.data):
            raise ValueError(f"{item.filename}: file is not a valid image")


def _copy_campaign_data_for_source(
    data: CampaignKnowledge, filename: str
) -> CampaignKnowledge:
    copied = data.model_copy(deep=True)
    for field_name in type(copied).model_fields:
        section = getattr(copied, field_name)
        section.source_references = [
            reference.model_copy(update={"filename": filename})
            for reference in section.source_references
        ]
    return copied


def _validate_source_references(
    data: CampaignKnowledge,
    parsed_pdf: ParsedPDF,
    *,
    allow_unreferenced_content: bool = False,
) -> None:
    valid_references = {
        (parsed_pdf.filename, page.page_number) for page in parsed_pdf.pages
    }
    for field_name in type(data).model_fields:
        section = getattr(data, field_name)
        has_content = bool(section.content.strip())
        if (
            has_content
            and not section.source_references
            and not allow_unreferenced_content
        ):
            raise AIParserError(
                f"Campaign content has no source reference: {field_name}"
            )
        if not has_content and section.source_references:
            raise AIParserError(
                f"Empty campaign content has source references: {field_name}"
            )
        for reference in section.source_references:
            if (reference.filename, reference.page) not in valid_references:
                raise AIParserError(
                    "Unknown campaign source reference: "
                    f"{reference.filename} page {reference.page}"
                )

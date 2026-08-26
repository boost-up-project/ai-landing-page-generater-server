from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from app.brand.ai_parser import AIParserError, GeminiBrandParser
from app.brand.markdown import generate_brand_markdown
from app.brand.schemas import (
    BrandAnalysisResponse,
    BrandKnowledge,
    BrandMarkdownResponse,
    BrandStatus,
)
from app.common.pdf import ParsedPDF, combine_parsed_pdfs, parse_pdf
from app.core.config import Settings


class BrandNotFoundError(FileNotFoundError):
    pass


class BrandStateError(RuntimeError):
    pass


class BrandParser(Protocol):
    async def analyze(self, extracted_text: str) -> BrandKnowledge: ...


@dataclass(frozen=True)
class UploadedDocument:
    filename: str
    data: bytes


class BrandService:
    def __init__(
        self,
        settings: Settings,
        parser: BrandParser | None = None,
    ) -> None:
        self._settings = settings
        self._parser = parser or GeminiBrandParser(settings)

    async def analyze(
        self, uploaded_documents: list[UploadedDocument]
    ) -> BrandAnalysisResponse:
        if not uploaded_documents:
            raise ValueError("At least one PDF is required")
        if len(uploaded_documents) > self._settings.max_pdf_files:
            raise ValueError(
                f"A maximum of {self._settings.max_pdf_files} PDFs is allowed"
            )

        parsed = [
            parse_pdf(
                document.data,
                document.filename,
                max_size_bytes=self._settings.max_pdf_size_bytes,
                max_pages=self._settings.max_pdf_pages,
            )
            for document in uploaded_documents
        ]
        extracted_text = combine_parsed_pdfs(
            parsed,
            max_characters=self._settings.max_extracted_characters,
        )
        data = await self._parser.analyze(extracted_text)
        _validate_source_references(data, parsed)

        brand_id = str(uuid4())
        now = datetime.now(timezone.utc)
        record = BrandAnalysisResponse(
            brand_id=brand_id,
            status=BrandStatus.DRAFT,
            source_files=[document.filename for document in uploaded_documents],
            data=data,
            created_at=now,
            updated_at=now,
        )

        upload_dir = self._settings.storage_root / "uploads" / brand_id
        for index, document in enumerate(uploaded_documents, start=1):
            safe_name = _safe_filename(document.filename)
            _write_bytes(upload_dir / f"{index:02d}_{safe_name}", document.data)

        brand_dir = self._brand_dir(brand_id)
        _write_text(brand_dir / "extracted.txt", extracted_text)
        _write_text(brand_dir / "analyzed.json", data.model_dump_json(indent=2))
        self._save_record(record)
        return record

    def get(self, brand_id: str) -> BrandAnalysisResponse:
        return self._load_record(brand_id)

    def review(
        self,
        brand_id: str,
        data: BrandKnowledge,
    ) -> BrandAnalysisResponse:
        record = self._load_record(brand_id)
        updated = record.model_copy(
            update={
                "status": BrandStatus.REVIEWED,
                "data": data,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        _write_text(
            self._brand_dir(brand_id) / "reviewed.json",
            data.model_dump_json(indent=2),
        )
        self._save_record(updated)
        return updated

    def finalize(self, brand_id: str) -> BrandMarkdownResponse:
        record = self._load_record(brand_id)
        if record.status != BrandStatus.REVIEWED:
            raise BrandStateError(
                "Brand data must be reviewed before it can be finalized"
            )

        markdown = generate_brand_markdown(record.data)
        _write_text(self._brand_dir(brand_id) / "brand.md", markdown)
        finalized = record.model_copy(
            update={
                "status": BrandStatus.FINALIZED,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._save_record(finalized)
        return BrandMarkdownResponse(
            brand_id=brand_id,
            status=BrandStatus.FINALIZED,
            markdown=markdown,
        )

    def get_markdown(self, brand_id: str) -> BrandMarkdownResponse:
        record = self._load_record(brand_id)
        markdown_path = self._brand_dir(brand_id) / "brand.md"
        if record.status != BrandStatus.FINALIZED or not markdown_path.is_file():
            raise BrandStateError("Brand data has not been finalized")
        return BrandMarkdownResponse(
            brand_id=brand_id,
            status=record.status,
            markdown=markdown_path.read_text(encoding="utf-8"),
        )

    def _brand_dir(self, brand_id: str) -> Path:
        try:
            normalized = str(UUID(brand_id))
        except ValueError as exc:
            raise BrandNotFoundError("Brand was not found") from exc
        return self._settings.storage_root / "generated" / "brands" / normalized

    def _record_path(self, brand_id: str) -> Path:
        return self._brand_dir(brand_id) / "record.json"

    def _load_record(self, brand_id: str) -> BrandAnalysisResponse:
        path = self._record_path(brand_id)
        if not path.is_file():
            raise BrandNotFoundError("Brand was not found")
        return BrandAnalysisResponse.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def _save_record(self, record: BrandAnalysisResponse) -> None:
        _write_text(
            self._record_path(record.brand_id),
            record.model_dump_json(indent=2),
        )


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name:
        return "document.pdf"
    return "".join(
        character if character.isalnum() or character in {".", "-", "_", " "} else "_"
        for character in name
    )


def _validate_source_references(
    data: BrandKnowledge,
    parsed_pdfs: list[ParsedPDF],
) -> None:
    valid_references = {
        (pdf.filename, page.page_number) for pdf in parsed_pdfs for page in pdf.pages
    }
    groups = (
        data.brand_identity,
        data.verbal_guideline,
        data.visual_guideline,
    )

    for group in groups:
        for field_name in type(group).model_fields:
            section = getattr(group, field_name)
            has_content = bool(section.content.strip())
            if has_content and not section.source_references:
                raise AIParserError(
                    f"Gemini returned content without a source reference: {field_name}"
                )
            if not has_content and section.source_references:
                raise AIParserError(
                    f"Gemini returned source references for empty content: {field_name}"
                )
            for reference in section.source_references:
                if (reference.filename, reference.page) not in valid_references:
                    raise AIParserError(
                        "Gemini returned an unknown source reference: "
                        f"{reference.filename} page {reference.page}"
                    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)

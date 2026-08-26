from __future__ import annotations

from dataclasses import dataclass

import pymupdf


class PDFParseError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class ParsedPDF:
    filename: str
    pages: tuple[ExtractedPage, ...]

    def as_prompt_text(self) -> str:
        parts: list[str] = []
        for page in self.pages:
            parts.append(
                f"[SOURCE_FILE: {self.filename}]\n"
                f"[SOURCE_PAGE: {page.page_number}]\n"
                f"{page.text}"
            )
        return "\n\n".join(parts)


def parse_pdf(
    data: bytes,
    filename: str,
    *,
    max_size_bytes: int,
    max_pages: int,
) -> ParsedPDF:
    if not data:
        raise PDFParseError(f"{filename}: empty file")
    if len(data) > max_size_bytes:
        raise PDFParseError(f"{filename}: file exceeds the {max_size_bytes}-byte limit")
    if not data.startswith(b"%PDF-"):
        raise PDFParseError(f"{filename}: file is not a valid PDF")

    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several format-specific exceptions.
        raise PDFParseError(f"{filename}: cannot open PDF") from exc

    try:
        if document.needs_pass:
            raise PDFParseError(
                f"{filename}: password-protected PDFs are not supported"
            )
        if document.page_count == 0:
            raise PDFParseError(f"{filename}: PDF has no pages")
        if document.page_count > max_pages:
            raise PDFParseError(f"{filename}: PDF exceeds the {max_pages}-page limit")

        pages = tuple(
            ExtractedPage(
                page_number=index + 1,
                text=page.get_text("text", sort=True).strip(),
            )
            for index, page in enumerate(document)
        )
    finally:
        document.close()

    if not any(page.text for page in pages):
        raise PDFParseError(
            f"{filename}: no selectable text was found; scanned PDFs require OCR"
        )

    return ParsedPDF(filename=filename, pages=pages)


def combine_parsed_pdfs(
    parsed_pdfs: list[ParsedPDF],
    *,
    max_characters: int,
) -> str:
    combined = "\n\n".join(pdf.as_prompt_text() for pdf in parsed_pdfs)
    if len(combined) > max_characters:
        raise PDFParseError(
            "Extracted PDF text exceeds the configured character limit "
            f"({max_characters})"
        )
    return combined

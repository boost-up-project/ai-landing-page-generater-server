from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.brand.ai_parser import AIParserError
from app.brand.schemas import (
    BrandAnalysisResponse,
    BrandMarkdownResponse,
    BrandReviewRequest,
)
from app.brand.service import (
    BrandNotFoundError,
    BrandService,
    BrandStateError,
    UploadedDocument,
    UploadedVisualAsset,
)
from app.common.pdf import PDFParseError
from app.core.config import Settings, get_settings

router = APIRouter(prefix="/brands", tags=["brands"])


def get_brand_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> BrandService:
    return BrandService(settings)


@router.post(
    "/analyze",
    response_model=BrandAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_brand(
    files: Annotated[list[UploadFile], File()],
    service: Annotated[BrandService, Depends(get_brand_service)],
    logo_files: Annotated[list[UploadFile] | None, File()] = None,
    icon_files: Annotated[list[UploadFile] | None, File()] = None,
    font_files: Annotated[list[UploadFile] | None, File()] = None,
    colors: Annotated[list[str] | None, Form()] = None,
) -> BrandAnalysisResponse:
    uploaded_documents: list[UploadedDocument] = []
    for file in files:
        filename = file.filename or "document.pdf"
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{filename}: only PDF files are supported",
            )
        uploaded_documents.append(
            UploadedDocument(filename=filename, data=await file.read())
        )

    uploaded_visual_assets: list[UploadedVisualAsset] = []
    for kind, visual_files in (
        ("logo", logo_files or []),
        ("icon", icon_files or []),
        ("font", font_files or []),
    ):
        for file in visual_files:
            uploaded_visual_assets.append(
                UploadedVisualAsset(
                    kind=kind,
                    filename=file.filename or f"{kind}-asset",
                    data=await file.read(),
                )
            )

    try:
        return await service.analyze(
            uploaded_documents,
            visual_assets=uploaded_visual_assets,
            colors=colors or [],
        )
    except (ValueError, PDFParseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AIParserError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get("/{brand_id}", response_model=BrandAnalysisResponse)
async def get_brand(
    brand_id: str,
    service: Annotated[BrandService, Depends(get_brand_service)],
) -> BrandAnalysisResponse:
    try:
        return service.get(brand_id)
    except BrandNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.put("/{brand_id}/review", response_model=BrandAnalysisResponse)
async def review_brand(
    brand_id: str,
    request: BrandReviewRequest,
    service: Annotated[BrandService, Depends(get_brand_service)],
) -> BrandAnalysisResponse:
    try:
        return service.review(brand_id, request.data)
    except BrandNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post("/{brand_id}/finalize", response_model=BrandMarkdownResponse)
async def finalize_brand(
    brand_id: str,
    service: Annotated[BrandService, Depends(get_brand_service)],
) -> BrandMarkdownResponse:
    try:
        return service.finalize(brand_id)
    except BrandNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except BrandStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.get("/{brand_id}/markdown", response_model=BrandMarkdownResponse)
async def get_brand_markdown(
    brand_id: str,
    service: Annotated[BrandService, Depends(get_brand_service)],
) -> BrandMarkdownResponse:
    try:
        return service.get_markdown(brand_id)
    except BrandNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except BrandStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

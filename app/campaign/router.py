from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.brand.ai_parser import AIParserError
from app.campaign.schemas import (
    CampaignAnalysisResponse,
    CampaignMarkdownResponse,
    CampaignReviewRequest,
)
from app.campaign.service import (
    CampaignNotFoundError,
    CampaignService,
    CampaignStateError,
    UploadedFile,
)
from app.common.pdf import PDFParseError
from app.core.config import Settings, get_settings
from app.project.service import ProjectNotFoundError

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def get_campaign_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> CampaignService:
    return CampaignService(settings)


@router.post(
    "",
    response_model=CampaignAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_campaign(
    strategy_file: Annotated[list[UploadFile], File()],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
    project_id: Annotated[str, Form()],
    component_files: Annotated[list[UploadFile] | None, File()] = None,
    asset_files: Annotated[list[UploadFile] | None, File()] = None,
) -> CampaignAnalysisResponse:
    if len(strategy_file) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Exactly one campaign strategy PDF is required",
        )
    source = strategy_file[0]
    source_name = source.filename or "campaign.pdf"
    if not source_name.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{source_name}: only PDF files are supported",
        )

    try:
        return await service.analyze(
            project_id,
            UploadedFile(filename=source_name, data=await source.read()),
            component_files=[
                UploadedFile(
                    filename=item.filename or "component.html", data=await item.read()
                )
                for item in component_files or []
            ],
            asset_files=[
                UploadedFile(filename=item.filename or "asset", data=await item.read())
                for item in asset_files or []
            ],
        )
    except (ValueError, PDFParseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except AIParserError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/{campaign_id}", response_model=CampaignAnalysisResponse)
async def get_campaign(
    campaign_id: str,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> CampaignAnalysisResponse:
    try:
        return service.get(campaign_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.put("/{campaign_id}/review", response_model=CampaignAnalysisResponse)
async def review_campaign(
    campaign_id: str,
    request: CampaignReviewRequest,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> CampaignAnalysisResponse:
    try:
        return service.review(campaign_id, request.data)
    except CampaignNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except CampaignStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except AIParserError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/{campaign_id}/finalize", response_model=CampaignMarkdownResponse)
async def finalize_campaign(
    campaign_id: str,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> CampaignMarkdownResponse:
    try:
        return service.finalize(campaign_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except CampaignStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.get("/{campaign_id}/markdown", response_model=CampaignMarkdownResponse)
async def get_campaign_markdown(
    campaign_id: str,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> CampaignMarkdownResponse:
    try:
        return service.get_markdown(campaign_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except CampaignStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

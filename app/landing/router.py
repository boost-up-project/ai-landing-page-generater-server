from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.brand.ai_parser import AIParserError
from app.core.config import Settings, get_settings
from app.landing.schemas import (
    CopyCandidateRequest,
    CopyCandidateResponse,
    LandingCreateRequest,
    LandingResponse,
)
from app.landing.service import (
    LandingNotFoundError,
    LandingService,
    LandingStateError,
)
from app.project.service import ProjectNotFoundError

router = APIRouter(prefix="/landings", tags=["landings"])


def get_landing_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LandingService:
    return LandingService(settings)


@router.post("", response_model=LandingResponse, status_code=status.HTTP_201_CREATED)
async def create_landing(
    request: LandingCreateRequest,
    service: Annotated[LandingService, Depends(get_landing_service)],
) -> LandingResponse:
    try:
        return await service.create(request.project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LandingStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AIParserError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{landing_id}", response_model=LandingResponse)
async def get_landing(
    landing_id: str,
    service: Annotated[LandingService, Depends(get_landing_service)],
) -> LandingResponse:
    try:
        return service.get(landing_id)
    except LandingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{landing_id}/copy-candidates", response_model=CopyCandidateResponse)
async def generate_copy_candidates(
    landing_id: str,
    request: CopyCandidateRequest,
    service: Annotated[LandingService, Depends(get_landing_service)],
) -> CopyCandidateResponse:
    try:
        return await service.copy_candidates(landing_id, request)
    except LandingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LandingStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AIParserError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{landing_id}/assets/{filename}")
async def get_landing_asset(
    landing_id: str,
    filename: str,
    service: Annotated[LandingService, Depends(get_landing_service)],
) -> FileResponse:
    try:
        return FileResponse(service.asset_path(landing_id, filename))
    except LandingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

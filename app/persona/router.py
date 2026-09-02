from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.brand.ai_parser import AIParserError
from app.core.config import Settings, get_settings
from app.persona.schemas import (
    PersonaAnalysisResponse,
    PersonaAnalyzeRequest,
    PersonaMarkdownResponse,
    PersonaReviewRequest,
)
from app.persona.service import (
    PersonaNotFoundError,
    PersonaService,
    PersonaStateError,
)
from app.project.service import ProjectNotFoundError

router = APIRouter(prefix="/personas", tags=["personas"])


def get_persona_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PersonaService:
    return PersonaService(settings)


@router.post(
    "",
    response_model=PersonaAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_personas(
    request: PersonaAnalyzeRequest,
    service: Annotated[PersonaService, Depends(get_persona_service)],
) -> PersonaAnalysisResponse:
    try:
        return await service.analyze(request.project_id, request.inputs)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except AIParserError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.get("/{persona_id}", response_model=PersonaAnalysisResponse)
async def get_personas(
    persona_id: str,
    service: Annotated[PersonaService, Depends(get_persona_service)],
) -> PersonaAnalysisResponse:
    try:
        return service.get(persona_id)
    except PersonaNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.put("/{persona_id}/review", response_model=PersonaAnalysisResponse)
async def review_personas(
    persona_id: str,
    request: PersonaReviewRequest,
    service: Annotated[PersonaService, Depends(get_persona_service)],
) -> PersonaAnalysisResponse:
    try:
        return service.review(persona_id, request.data)
    except PersonaNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PersonaStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/{persona_id}/finalize", response_model=PersonaMarkdownResponse)
async def finalize_personas(
    persona_id: str,
    service: Annotated[PersonaService, Depends(get_persona_service)],
) -> PersonaMarkdownResponse:
    try:
        return service.finalize(persona_id)
    except PersonaNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PersonaStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.get("/{persona_id}/markdown", response_model=PersonaMarkdownResponse)
async def get_persona_markdown(
    persona_id: str,
    service: Annotated[PersonaService, Depends(get_persona_service)],
) -> PersonaMarkdownResponse:
    try:
        return service.get_markdown(persona_id)
    except PersonaNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except (PersonaStateError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

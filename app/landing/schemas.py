from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EditableImage(StrictModel):
    asset_filename: str
    alt: str = ""


class LandingComponentSelection(StrictModel):
    template_id: str
    copy_values: list[str]
    image_values: list[EditableImage]


class LandingPagePlan(StrictModel):
    persona_key: str
    ai_intent: str = Field(min_length=1, max_length=1000)
    components: list[LandingComponentSelection] = Field(min_length=1)


class LandingPlan(StrictModel):
    pages: list[LandingPagePlan] = Field(min_length=1, max_length=5)


class EditableTarget(StrictModel):
    kind: str
    current_value: str


class ComponentTemplate(StrictModel):
    template_id: str
    name: str
    category: str
    filename: str
    html: str
    editable_targets: list[EditableTarget]


class LandingComponent(StrictModel):
    instance_id: str
    template_id: str
    name: str
    category: str
    html: str
    hidden: bool = False


class LandingPage(StrictModel):
    persona_key: str
    persona_name: str
    ai_intent: str
    components: list[LandingComponent]


class LandingAsset(StrictModel):
    filename: str
    content_type: str


class LandingStatus(str, Enum):
    DRAFT = "draft"
    SAVED = "saved"


class LandingCreateRequest(StrictModel):
    project_id: str


class CopyCandidateRequest(StrictModel):
    persona_key: str
    instance_id: str
    editable_index: int = Field(ge=0)
    current_value: str = Field(max_length=2000)
    prompt: str = Field(default="", max_length=1000)


class CopyCandidateResponse(StrictModel):
    candidates: list[str] = Field(min_length=3, max_length=3)


class LandingResponse(StrictModel):
    project_id: str
    landing_id: str
    source_campaign_id: str
    source_persona_id: str
    status: LandingStatus
    component_library: list[ComponentTemplate]
    assets: list[LandingAsset]
    pages: list[LandingPage]
    created_at: datetime
    updated_at: datetime

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceReference(StrictModel):
    filename: str = Field(description="Name of the source campaign PDF")
    page: int = Field(ge=1, description="One-based page number")


class CampaignSection(StrictModel):
    content: str = Field(
        description=(
            "Compact campaign strategy content supported by the source PDF; empty "
            "when the source does not contain relevant information"
        )
    )
    source_references: list[SourceReference] = Field(
        description="PDF pages that directly support the content"
    )


class CampaignKnowledge(StrictModel):
    campaign_overview: CampaignSection = Field(
        description="Campaign background, purpose, and scope"
    )
    objective: CampaignSection = Field(
        description="Campaign goals, core KPIs, and expected outcomes"
    )
    campaign_opportunity: CampaignSection = Field(
        description="Core problem, market opportunity, and campaign opportunity"
    )
    audience_insight: CampaignSection = Field(
        description="Core audience, audience needs, and behavioral insights"
    )
    campaign_idea: CampaignSection = Field(
        description="Campaign idea, core concept, and creative direction"
    )
    offering: CampaignSection = Field(
        description="Product or service value, customer benefits, and differentiation"
    )
    communication_strategy: CampaignSection = Field(
        description="Core message, message priorities, and communication direction"
    )
    cta_map: CampaignSection = Field(
        description="Core CTA, action flow, and conversion design"
    )


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    FINALIZED = "finalized"


class CampaignAnalysisResponse(StrictModel):
    project_id: str
    campaign_id: str
    status: CampaignStatus
    source_file: str
    source_checksum: str | None = None
    reused_from_campaign_id: str | None = None
    component_files: list[str]
    asset_files: list[str]
    data: CampaignKnowledge
    created_at: datetime
    updated_at: datetime


class CampaignReviewRequest(StrictModel):
    data: CampaignKnowledge


class CampaignMarkdownResponse(StrictModel):
    project_id: str
    campaign_id: str
    status: CampaignStatus
    markdown: str
    next_route: str = "/#persona-input"

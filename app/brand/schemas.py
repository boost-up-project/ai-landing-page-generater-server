from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base model shared by Gemini Structured Output schemas."""

    model_config = ConfigDict(extra="forbid")


class SourceReference(StrictModel):
    filename: str = Field(description="Name of the source PDF")
    page: int = Field(ge=1, description="One-based page number")


class ReviewSection(StrictModel):
    content: str = Field(
        description=(
            "A compact, faithfully condensed textarea value supported by the source; "
            "parallel facts use ' / ' separators. Empty when the source PDFs do not "
            "contain relevant information."
        )
    )
    source_references: list[SourceReference] = Field(
        description="PDF pages that directly support the content"
    )


class BrandIdentity(StrictModel):
    brand_overview: ReviewSection = Field(
        description=(
            "Brand name, founding background, brand meaning, one-line definition, "
            "and customer value proposition. Include every one of these components "
            "when it is directly supported."
        )
    )
    brand_philosophy: ReviewSection = Field(
        description=(
            "Brand vision, business idea, brand philosophy, and core design philosophy"
        )
    )
    brand_positioning: ReviewSection = Field(
        description="Brand positioning and core competencies"
    )
    brand_target: ReviewSection = Field(description="Core target definition and needs")
    brand_personality: ReviewSection = Field(
        description="Brand personality and keywords"
    )


class VerbalGuideline(StrictModel):
    brand_voice: ReviewSection = Field(
        description="The brand's consistent, distinctive voice and personality"
    )
    tone_of_voice: ReviewSection = Field(
        description="Mood and intensity adjusted by situation and channel"
    )
    writing_style: ReviewSection = Field(
        description="Language and writing rules for actual sentences"
    )
    messaging_principles: ReviewSection = Field(
        description="Principles for structuring messages and communicating benefits"
    )
    vocabulary_and_expressions: ReviewSection = Field(
        description=(
            "Recommended and discouraged words, official naming, terminology, and "
            "brand expressions"
        )
    )
    copy_rules: ReviewSection = Field(
        description=(
            "Copywriting rules by customer touchpoint and copy type, especially "
            "headlines, body copy, and CTAs; exclude naming and terminology rules"
        )
    )


class VisualGuideline(StrictModel):
    logo: ReviewSection = Field(description="Logo assets and SVG references")
    icon: ReviewSection = Field(description="Icon assets and SVG references")
    color: ReviewSection = Field(description="Brand colors and HEX color codes")
    fonts: ReviewSection = Field(description="Brand fonts and TTF references")


class BrandKnowledge(StrictModel):
    brand_identity: BrandIdentity
    verbal_guideline: VerbalGuideline
    visual_guideline: VisualGuideline


class BrandStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    FINALIZED = "finalized"


class BrandAnalysisResponse(StrictModel):
    project_id: str
    brand_id: str
    status: BrandStatus
    source_files: list[str]
    data: BrandKnowledge
    created_at: datetime
    updated_at: datetime


class BrandReviewRequest(StrictModel):
    data: BrandKnowledge


class BrandMarkdownResponse(StrictModel):
    project_id: str
    brand_id: str
    status: BrandStatus
    markdown: str
    next_route: str = "/#campaign-input"

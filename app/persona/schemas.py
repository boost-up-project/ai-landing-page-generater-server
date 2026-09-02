from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersonaAppendix(StrictModel):
    purchase_journey: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Steps used to discover, compare, decide on, and buy a solution",
    )
    dislikes: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Experiences, attributes, or trade-offs the persona avoids",
    )

    @field_validator("purchase_journey", "dislikes")
    @classmethod
    def validate_non_empty_items(cls, values: list[str]) -> list[str]:
        return _clean_items(values)


class PersonaKnowledge(StrictModel):
    name: str = Field(
        min_length=1,
        max_length=40,
        description="A concise AI-generated Korean persona name",
    )
    profile: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Basic traits that explain what kind of person this is",
    )
    situation: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Current context in which the product or service is needed",
    )
    needs: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Goals or changes the persona wants to achieve",
    )
    pain_points: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Current problems, inconvenience, and frustration",
    )
    interests: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Tastes, interests, and values that matter to the persona",
    )
    behaviors: list[str] = Field(
        min_length=1,
        max_length=5,
        description="How the persona discovers, compares, and purchases solutions",
    )
    appendix: PersonaAppendix

    @field_validator(
        "profile",
        "situation",
        "needs",
        "pain_points",
        "interests",
        "behaviors",
    )
    @classmethod
    def validate_non_empty_items(cls, values: list[str]) -> list[str]:
        return _clean_items(values)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Persona name must not be blank")
        return cleaned


class PersonaBatch(StrictModel):
    personas: list[PersonaKnowledge] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def validate_unique_names(self) -> PersonaBatch:
        names = [persona.name.casefold() for persona in self.personas]
        if len(names) != len(set(names)):
            raise ValueError("Persona names must be unique within a batch")
        return self


class PersonaAnalyzeRequest(StrictModel):
    project_id: str
    inputs: list[str] = Field(min_length=1, max_length=5)

    @field_validator("inputs")
    @classmethod
    def validate_inputs(cls, values: list[str]) -> list[str]:
        cleaned = _clean_items(values)
        for value in cleaned:
            if len(value) > 5000:
                raise ValueError("Each persona input must be 5,000 characters or fewer")
        return cleaned


class PersonaStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    FINALIZED = "finalized"


class PersonaAnalysisResponse(StrictModel):
    project_id: str
    persona_id: str
    status: PersonaStatus
    inputs: list[str]
    data: PersonaBatch
    created_at: datetime
    updated_at: datetime


class PersonaReviewRequest(StrictModel):
    data: PersonaBatch


class PersonaMarkdownFile(StrictModel):
    filename: str
    name: str
    markdown: str


class PersonaMarkdownResponse(StrictModel):
    project_id: str
    persona_id: str
    status: PersonaStatus
    files: list[PersonaMarkdownFile]
    next_route: str | None = None


def _clean_items(values: list[str]) -> list[str]:
    cleaned = [value.strip() for value in values]
    if any(not value for value in cleaned):
        raise ValueError("List items must not be blank")
    return cleaned

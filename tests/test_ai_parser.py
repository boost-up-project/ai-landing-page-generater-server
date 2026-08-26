import json

import pytest

from app.brand.ai_parser import (
    SYSTEM_PROMPT,
    AIParserError,
    GeminiBrandParser,
    _extract_gemini_text,
)
from app.brand.schemas import BrandKnowledge
from app.core.config import Settings

from .test_brand_flow import make_knowledge


def test_prompt_forbids_inference_but_allows_source_interpretation() -> None:
    assert "Do not use outside knowledge" in SYSTEM_PROMPT
    assert "Do not extend it" in SYSTEM_PROMPT
    assert "return an empty content string" in SYSTEM_PROMPT
    assert 'separate parallel facts or rules with " / "' in SYSTEM_PROMPT
    assert "never more than 400 characters" in SYSTEM_PROMPT
    assert "must not add a" in SYSTEM_PROMPT
    assert "every page" in SYSTEM_PROMPT
    assert "vocabulary_and_expressions includes" in SYSTEM_PROMPT
    assert "COVERAGE CHECKLIST" in SYSTEM_PROMPT
    assert "customer value proposition" in SYSTEM_PROMPT


def test_extract_gemini_text_validates_as_brand_knowledge() -> None:
    expected = make_knowledge()
    text = json.dumps(expected.model_dump())
    response = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"parts": [{"text": text}]},
            }
        ],
    }

    result = BrandKnowledge.model_validate_json(_extract_gemini_text(response))
    assert result == expected


def test_extract_gemini_text_rejects_blocked_prompt() -> None:
    response = {
        "promptFeedback": {"blockReason": "SAFETY"},
    }

    with pytest.raises(AIParserError, match="SAFETY"):
        _extract_gemini_text(response)


@pytest.mark.asyncio
async def test_gemini_parser_sends_json_schema_request(monkeypatch) -> None:
    expected = make_knowledge()
    captured: dict = {}

    class FakeResponse:
        is_error = False

        def __init__(self) -> None:
            self.headers: dict = {}

        def json(self) -> dict:
            return {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [{"text": json.dumps(expected.model_dump())}]
                        },
                    }
                ]
            }

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            captured["client"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def post(self, path: str, **kwargs) -> FakeResponse:
            captured["path"] = path
            captured["request"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(
        "app.brand.ai_parser.httpx.AsyncClient",
        FakeAsyncClient,
    )
    parser = GeminiBrandParser(
        Settings(gemini_api_key="test-key", gemini_model="gemini-3.5-flash-lite")
    )

    result = await parser.analyze("[SOURCE_FILE: brand.pdf]\n[SOURCE_PAGE: 1]\nText")

    assert result == expected
    assert captured["path"] == "/models/gemini-3.5-flash-lite:generateContent"
    assert captured["request"]["headers"]["x-goog-api-key"] == "test-key"
    config = captured["request"]["json"]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"]["type"] == "object"
    assert config["temperature"] == 0.1

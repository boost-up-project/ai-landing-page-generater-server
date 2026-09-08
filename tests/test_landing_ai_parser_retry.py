import json

import pytest

from app.brand.ai_parser import AIParserError
from app.core.config import Settings
from app.landing.ai_parser import GeminiLandingParser


def _plan_response(status_code: int = 200):
    import httpx

    body = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "pages": [
                                        {
                                            "persona_key": "persona-a",
                                            "ai_intent": "테스트 구성",
                                            "components": [],
                                        }
                                    ]
                                }
                            )
                        }
                    ]
                }
            }
        ]
    }
    return httpx.Response(
        status_code,
        json=body if status_code == 200 else {"error": "temporary"},
        request=httpx.Request("POST", "https://example.test"),
    )


async def _compose(parser: GeminiLandingParser):
    return await parser.compose(
        brand_context="brand",
        campaign_context="campaign",
        personas=[{"persona_key": "persona-a"}],
        components=[],
        asset_filenames=[],
    )


@pytest.mark.asyncio
async def test_compose_retries_retryable_gemini_errors(monkeypatch) -> None:
    responses = [_plan_response(503), _plan_response(503), _plan_response()]
    calls = 0

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def post(self, path: str, **kwargs):
            nonlocal calls
            response = responses[calls]
            calls += 1
            return response

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("app.landing.ai_parser.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("app.landing.ai_parser.asyncio.sleep", no_sleep)

    result = await _compose(GeminiLandingParser(Settings(gemini_api_key="test")))

    assert result.pages[0].persona_key == "persona-a"
    assert calls == 3


@pytest.mark.asyncio
async def test_compose_stops_after_three_retries(monkeypatch) -> None:
    calls = 0

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def post(self, path: str, **kwargs):
            nonlocal calls
            calls += 1
            return _plan_response(503)

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("app.landing.ai_parser.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("app.landing.ai_parser.asyncio.sleep", no_sleep)

    with pytest.raises(AIParserError, match="Gemini API returned 503"):
        await _compose(GeminiLandingParser(Settings(gemini_api_key="test")))

    assert calls == 4

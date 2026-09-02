from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from app.brand.ai_parser import AIParserError
from app.core.config import Settings
from app.landing.schemas import LandingPlan

SYSTEM_PROMPT = (
    (Path(__file__).with_name("prompts") / "compose.md")
    .read_text(encoding="utf-8")
    .strip()
)


class GeminiLandingParser:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def compose(
        self,
        *,
        brand_context: str,
        campaign_context: str,
        personas: list[dict[str, Any]],
        components: list[dict[str, Any]],
        asset_filenames: list[str],
    ) -> LandingPlan:
        if not self._settings.gemini_api_key:
            raise AIParserError("GEMINI_API_KEY is not configured")
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"[BRAND_CONTEXT]\n{brand_context}\n\n"
            f"[CAMPAIGN_CONTEXT]\n{campaign_context}\n\n"
            f"[PERSONAS]\n{json.dumps(personas, ensure_ascii=False)}\n\n"
            f"[COMPONENTS]\n{json.dumps(components, ensure_ascii=False)}\n\n"
            f"[ASSET_FILENAMES]\n{json.dumps(asset_filenames, ensure_ascii=False)}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": LandingPlan.model_json_schema(),
                "temperature": 0.35,
            },
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.gemini_base_url.rstrip("/"),
                timeout=self._settings.gemini_timeout_seconds,
            ) as client:
                response = await client.post(
                    f"/models/{self._settings.gemini_model}:generateContent",
                    headers={
                        "x-goog-api-key": self._settings.gemini_api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise AIParserError("Could not reach the Gemini API") from exc
        if response.is_error:
            raise AIParserError(
                f"Gemini API returned {response.status_code}: {response.text}"
            )
        try:
            return LandingPlan.model_validate(
                json.loads(_extract_gemini_text(response.json()))
            )
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            raise AIParserError("Gemini returned an invalid landing plan") from exc


def _extract_gemini_text(response_body: dict[str, Any]) -> str:
    candidates = response_body.get("candidates", [])
    if not candidates:
        raise AIParserError("Gemini returned no landing plan candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if part.get("text"))
    if not text:
        raise AIParserError("Gemini response did not contain landing plan text")
    return text


from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from app.brand.ai_parser import AIParserError
from app.core.config import Settings
from app.persona.schemas import PersonaBatch

SYSTEM_PROMPT = (
    (Path(__file__).with_name("prompts") / "analyze.md")
    .read_text(encoding="utf-8")
    .strip()
)


class GeminiPersonaParser:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def analyze(
        self,
        inputs: list[str],
        *,
        brand_context: str,
        campaign_context: str,
    ) -> PersonaBatch:
        if not self._settings.gemini_api_key:
            raise AIParserError("GEMINI_API_KEY is not configured")
        if not self._settings.gemini_model:
            raise AIParserError("GEMINI_MODEL is not configured")

        labeled_inputs = "\n\n".join(
            f"[PERSONA_INPUT_{chr(64 + index)}]\n{value}"
            for index, value in enumerate(inputs, start=1)
        )
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"[BRAND_CONTEXT]\n{brand_context or '(없음)'}\n\n"
            f"[CAMPAIGN_CONTEXT]\n{campaign_context or '(없음)'}\n\n"
            f"{labeled_inputs}"
        )
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]},
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": PersonaBatch.model_json_schema(),
                "temperature": 0.4,
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
            request_id = response.headers.get("x-request-id", "unknown")
            try:
                detail = response.json().get("error", {}).get("message", response.text)
            except (ValueError, AttributeError):
                detail = response.text
            raise AIParserError(
                f"Gemini API returned {response.status_code} "
                f"(request_id={request_id}): {detail}"
            )

        try:
            output_text = _extract_gemini_text(response.json())
            return PersonaBatch.model_validate(json.loads(output_text))
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            raise AIParserError(
                "Gemini returned an invalid structured persona response"
            ) from exc


def _extract_gemini_text(response_body: dict[str, Any]) -> str:
    candidates = response_body.get("candidates", [])
    if not candidates:
        block_reason = response_body.get("promptFeedback", {}).get(
            "blockReason", "unknown"
        )
        raise AIParserError(f"Gemini returned no candidates: {block_reason}")
    candidate = candidates[0]
    finish_reason = candidate.get("finishReason")
    if finish_reason not in {None, "STOP"}:
        raise AIParserError(f"Gemini response was incomplete: {finish_reason}")
    parts = candidate.get("content", {}).get("parts", [])
    text_parts = [part.get("text", "") for part in parts if part.get("text")]
    if not text_parts:
        raise AIParserError("Gemini response did not contain output text")
    return "".join(text_parts)

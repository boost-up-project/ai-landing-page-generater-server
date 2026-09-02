from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from app.brand.ai_parser import AIParserError
from app.core.config import Settings
from app.landing.schemas import CopyCandidateResponse, LandingPlan

SYSTEM_PROMPT = (
    (Path(__file__).with_name("prompts") / "compose.md")
    .read_text(encoding="utf-8")
    .strip()
)
COPY_PROMPT = (
    (Path(__file__).with_name("prompts") / "copy.md")
    .read_text(encoding="utf-8")
    .strip()
)
IMAGE_ASPECT_RATIOS = {
    "1:1": "ASPECT_RATIO_ONE_BY_ONE",
    "2:3": "ASPECT_RATIO_TWO_BY_THREE",
    "3:2": "ASPECT_RATIO_THREE_BY_TWO",
    "3:4": "ASPECT_RATIO_THREE_BY_FOUR",
    "4:3": "ASPECT_RATIO_FOUR_BY_THREE",
    "4:5": "ASPECT_RATIO_FOUR_BY_FIVE",
    "5:4": "ASPECT_RATIO_FIVE_BY_FOUR",
    "9:16": "ASPECT_RATIO_NINE_BY_SIXTEEN",
    "16:9": "ASPECT_RATIO_SIXTEEN_BY_NINE",
    "21:9": "ASPECT_RATIO_TWENTY_ONE_BY_NINE",
}


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
        reference_context: dict[str, Any] | None = None,
    ) -> LandingPlan:
        if not self._settings.gemini_api_key:
            raise AIParserError("GEMINI_API_KEY is not configured")
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"[BRAND_CONTEXT]\n{brand_context}\n\n"
            f"[CAMPAIGN_CONTEXT]\n{campaign_context}\n\n"
            f"[PERSONAS]\n{json.dumps(personas, ensure_ascii=False)}\n\n"
            f"[COMPONENTS]\n{json.dumps(components, ensure_ascii=False)}\n\n"
            f"[REFERENCE_LAYOUT]\n{json.dumps(reference_context or {}, ensure_ascii=False)}\n\n"
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

    async def generate_copy_candidates(
        self,
        *,
        current_value: str,
        user_prompt: str,
        persona_name: str,
        page_intent: str,
        brand_context: str,
        campaign_context: str,
    ) -> CopyCandidateResponse:
        if not self._settings.gemini_api_key:
            raise AIParserError("GEMINI_API_KEY is not configured")
        prompt = (
            f"{COPY_PROMPT}\n\n"
            f"[BRAND_CONTEXT]\n{brand_context}\n\n"
            f"[CAMPAIGN_CONTEXT]\n{campaign_context}\n\n"
            f"[PERSONA]\n{persona_name}\n\n"
            f"[PAGE_INTENT]\n{page_intent}\n\n"
            f"[CURRENT_COPY]\n{current_value}\n\n"
            f"[USER_REQUEST]\n{user_prompt or '(추가 요청 없음)'}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": CopyCandidateResponse.model_json_schema(),
                "temperature": 0.7,
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
            return CopyCandidateResponse.model_validate(
                json.loads(_extract_gemini_text(response.json()))
            )
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            raise AIParserError("Gemini returned invalid copy candidates") from exc

    async def generate_image(
        self,
        *,
        prompt: str,
        persona_name: str,
        page_intent: str,
        brand_context: str,
        campaign_context: str,
        aspect_ratio: str,
    ) -> tuple[str, bytes]:
        if not self._settings.gemini_api_key:
            raise AIParserError("GEMINI_API_KEY is not configured")
        if not self._settings.gemini_image_model:
            raise AIParserError("GEMINI_IMAGE_MODEL is not configured")
        image_prompt = (
            "Create one polished campaign landing-page image. "
            "Do not add logos, watermarks, UI chrome, or text unless explicitly requested.\n\n"
            f"[BRAND_CONTEXT]\n{brand_context}\n\n"
            f"[CAMPAIGN_CONTEXT]\n{campaign_context}\n\n"
            f"[PERSONA]\n{persona_name}\n\n"
            f"[PAGE_INTENT]\n{page_intent}\n\n"
            f"[USER_REQUEST]\n{prompt}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": image_prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "responseFormat": {
                    "image": {
                        "aspectRatio": IMAGE_ASPECT_RATIOS[aspect_ratio],
                        "imageSize": "IMAGE_SIZE_ONE_K",
                    }
                },
            },
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.gemini_base_url.rstrip("/"),
                timeout=self._settings.gemini_timeout_seconds,
            ) as client:
                response = await client.post(
                    f"/models/{self._settings.gemini_image_model}:generateContent",
                    headers={
                        "x-goog-api-key": self._settings.gemini_api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise AIParserError("Could not reach the Gemini image API") from exc
        if response.status_code == 429:
            raise AIParserError(
                "Gemini image generation quota is exhausted. "
                "Please try again later or configure an image-enabled API plan."
            )
        if response.is_error:
            raise AIParserError(
                f"Gemini image API returned {response.status_code}: {response.text}"
            )
        for candidate in response.json().get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline_data = part.get("inlineData") or part.get("inline_data")
                if isinstance(inline_data, dict) and inline_data.get("data"):
                    try:
                        return (
                            inline_data.get("mimeType")
                            or inline_data.get("mime_type")
                            or "image/png",
                            base64.b64decode(inline_data["data"], validate=True),
                        )
                    except (ValueError, TypeError) as exc:
                        raise AIParserError(
                            "Gemini returned invalid image data"
                        ) from exc
        raise AIParserError("Gemini response did not contain an image")


def _extract_gemini_text(response_body: dict[str, Any]) -> str:
    candidates = response_body.get("candidates", [])
    if not candidates:
        raise AIParserError("Gemini returned no landing plan candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if part.get("text"))
    if not text:
        raise AIParserError("Gemini response did not contain landing plan text")
    return text

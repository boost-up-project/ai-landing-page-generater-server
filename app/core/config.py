from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_image_model: str = "gemini-3.1-flash-image"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: float = 180.0

    cors_origins: list[str] = [
        "https://blanki.ynana.xyz",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8001",
        "http://localhost:8001",
    ]

    storage_root: Path = Path("storage")
    max_pdf_files: int = 10
    max_pdf_size_bytes: int = 20 * 1024 * 1024
    max_pdf_pages: int = 200
    max_extracted_characters: int = 300_000
    max_visual_asset_files: int = 20
    max_visual_asset_size_bytes: int = 20 * 1024 * 1024
    max_campaign_component_files: int = 20
    max_campaign_component_size_bytes: int = 5 * 1024 * 1024
    max_campaign_style_files: int = 20
    max_campaign_style_size_bytes: int = 2 * 1024 * 1024
    max_campaign_bundle_files: int = 5
    max_campaign_bundle_size_bytes: int = 20 * 1024 * 1024
    max_campaign_bundle_entries: int = 100
    max_campaign_reference_size_bytes: int = 2 * 1024 * 1024
    max_campaign_asset_files: int = 50
    max_campaign_asset_size_bytes: int = 20 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()

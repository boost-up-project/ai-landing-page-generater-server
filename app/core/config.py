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
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: float = 180.0

    storage_root: Path = Path("storage")
    max_pdf_files: int = 10
    max_pdf_size_bytes: int = 20 * 1024 * 1024
    max_pdf_pages: int = 200
    max_extracted_characters: int = 300_000


@lru_cache
def get_settings() -> Settings:
    return Settings()

import json
import re
from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

GEMINI_MODEL_PATTERN = re.compile(r"^gemini-[a-zA-Z0-9.\-]+$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://firescope:firescope_local@localhost:5432/firescope"
    cors_origins: list[str] = [
        "http://localhost:5173", "http://localhost:8080",
        "http://127.0.0.1:5173", "http://127.0.0.1:8080",
    ]
    max_query_results: int = Field(default=5000, ge=1, le=50000)
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = Field(
        default="gemini-3.5-flash-lite", pattern=r"^gemini-[a-zA-Z0-9.\-]+$"
    )
    gemini_fallback_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash",
            "gemini-4-hydrogen",
        ]
    )
    ai_requests_per_minute: int = Field(default=8, ge=1, le=60)
    ai_requests_per_day: int = Field(default=100, ge=1, le=10000)
    ai_concurrent_requests: int = Field(default=2, ge=1, le=8)

    @field_validator("gemini_fallback_models", mode="before")
    @classmethod
    def _parse_fallback_models(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                decoded = json.loads(raw)
                if not isinstance(decoded, list):
                    raise ValueError("gemini_fallback_models JSON value must be a list")
                items = decoded
            else:
                items = raw.split(",")
        elif isinstance(value, (list, tuple)):
            items = list(value)
        else:
            raise ValueError("gemini_fallback_models must be a comma-separated string or list")

        models: list[str] = []
        for item in items:
            name = str(item).strip()
            if not name:
                continue
            if not GEMINI_MODEL_PATTERN.fullmatch(name):
                raise ValueError(f"Invalid Gemini model name: {name}")
            if name not in models:
                models.append(name)
        return models


@lru_cache
def get_settings() -> Settings:
    return Settings()

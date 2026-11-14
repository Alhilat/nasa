from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    gemini_model: str = Field(default="gemini-3.5-flash-lite", pattern=r"^gemini-[a-zA-Z0-9.\-]+$")
    ai_requests_per_minute: int = Field(default=8, ge=1, le=60)
    ai_requests_per_day: int = Field(default=100, ge=1, le=10000)
    ai_concurrent_requests: int = Field(default=2, ge=1, le=8)


@lru_cache
def get_settings() -> Settings:
    return Settings()

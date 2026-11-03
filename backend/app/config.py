"""Application settings, read from environment variables (and an optional .env file)."""

import secrets
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/app.db"
    # Unset JWT_SECRET means a random per-process secret: fine for demos, logs everyone
    # out on restart. Always set it in production.
    jwt_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32), min_length=32)
    jwt_ttl_minutes: int = 120
    invite_ttl_hours: int = 72

    llm_provider: Literal["fake", "anthropic", "openai"] = "fake"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-6.1-sol"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3
    llm_max_concurrency: int = 4

    dedup_threshold: float = Field(default=0.85, ge=0.5, le=1.0)
    submit_grace_seconds: int = 60
    snapshot_dir: str = "./data/snapshots"
    snapshot_max_bytes: int = 500_000
    # The public origin candidates use (e.g. https://exams.example.com). SEB hashes the URL
    # it requested, which differs from what the server sees behind a proxy.
    public_base_url: str = ""
    cors_origins: str = "http://localhost:5173"
    frontend_dist: str = "../frontend/dist"
    rate_limit_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

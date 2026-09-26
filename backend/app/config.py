"""Settings from environment variables (or backend/.env, deploy/.env when run from source)."""
from __future__ import annotations

from functools import cached_property
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND = Path(__file__).resolve().parents[1]
# Into the environment too (real environment variables win): SCHOOL_DATA_DIR / SCHOOL_CACHE_DIR are read by
# app.domain.analysis, which is not a settings class.
for _env in (BACKEND / ".env", BACKEND.parent / "deploy" / ".env"):
    load_dotenv(_env, override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(BACKEND.parent / "deploy" / ".env", BACKEND / ".env"), extra="ignore")

    # Full URL wins (the API container gets it from docker-compose); otherwise built from the POSTGRES_* values,
    # which is what deploy/.env holds for the development database on localhost:5433.
    database_url: str | None = None
    postgres_user: str = "school"
    postgres_password: str = "change-me"
    postgres_db: str = "school_planning"
    db_host: str = "localhost"
    db_port: int = 5433

    admin_token: str = ""  # X-Admin-Token for POST /api/admin/reload; empty = disabled
    cors_origins: str = ""  # comma separated, for a dashboard served from another origin
    projection_cache_size: int = 16  # projection results kept in memory (per intake plan)

    @cached_property
    def url(self) -> str:
        return self.database_url or (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.db_host}:{self.db_port}/{self.postgres_db}"
        )


settings = Settings()

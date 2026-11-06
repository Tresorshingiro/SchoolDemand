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
    db_host: str = "127.0.0.1"  # not "localhost": on Windows it tries IPv6 first and Docker's port is IPv4 only (≈2 min)
    db_port: int = 5433

    admin_token: str = ""  # X-Admin-Token for POST /api/admin/reload; empty = disabled
    cors_origins: str = ""  # comma separated, for a dashboard served from another origin
    projection_cache_size: int = 16  # projection results kept in memory (per intake plan)
    # Uploaded data files, their check results and parsed rows (kept: they are the history and the way back)
    upload_dir: str | None = None

    # Sign-in sessions (cookie). Without "Remember me" the cookie ends with the browser and the session after
    # session_hours; with it, after remember_days. Secure cookie: None = when the request came over HTTPS.
    session_hours: int = 12
    remember_days: int = 30
    session_cookie_secure: bool | None = None
    # The dashboard opened inside another site's page (Education Mapping on gh.space.gov.rw shows it in a frame): the
    # browser keeps the cookie there only when it is SameSite=None; Secure; Partitioned. None = whenever the cookie is
    # Secure (HTTPS); plain HTTP (development) keeps SameSite=Lax.
    session_cookie_cross_site: bool | None = None

    # Sign-in goes through the MINEDUC GIS portal (ArcGIS Enterprise, services/portal.py): its users are our users.
    portal_url: str = "https://gh.space.gov.rw/portal"
    portal_referer: str = "https://gh.space.gov.rw/school/"  # the portal ties its token to this referer
    portal_timeout: float = 15  # seconds per request to the portal
    portal_verify_ssl: bool = True  # False only for a portal with a self-signed certificate

    # Rwanda's administrative boundaries (services/boundaries.py): Education Mapping's public feature service on the
    # MINEDUC GIS portal, loaded into the database by the import job; shapes simplified to this many degrees (~20 m)
    boundaries_url: str = ("https://gh.space.gov.rw/server/rest/services/Administrative_boundaries_corrected/"
                           "FeatureServer")
    boundaries_simplify: float = 0.0002

    # Planned schools' walking distance: the Esri Rwanda network analysis services (domain/walking.py). The account
    # (or a fixed token) is Esri Rwanda's, not the MINEDUC portal's; without one, planned schools are unavailable.
    esri_routing_url: str = "https://esrirw.rw/server/rest/services/Routing042026/NetworkAnalysis/NAServer"
    esri_portal_url: str = "https://esrirw.rw/portal"
    esri_username: str | None = None
    esri_password: str | None = None
    esri_token: str | None = None   # instead of the account: a token the portal issued for esri_referer
    esri_referer: str = "https://esrirw.rw"  # the portal ties its token to this referer
    esri_travel_mode: str = "Walking"
    esri_timeout: float = 60        # seconds per request to the service
    esri_verify_ssl: bool = True
    walking_cache_size: int = 256   # walks kept in memory (per point, distance and schools asked about)

    @cached_property
    def url(self) -> str:
        return self.database_url or (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.db_host}:{self.db_port}/{self.postgres_db}"
        )

    @cached_property
    def upload_path(self) -> Path:
        return Path(self.upload_dir) if self.upload_dir else BACKEND.parent / "data-uploads"


settings = Settings()

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


VALID_APP_MODES = {"demo", "pilot", "production"}
VALID_AUTH_PROVIDERS = {"dev_jwt", "oidc"}


@dataclass(frozen=True)
class AppSettings:
    app_mode: str = "demo"
    database_url: str = "sqlite:///backend/app/data/vietsupply.db"
    allow_demo_headers: bool = True
    jwt_issuer: str = "vietsupply-dev"
    jwt_audience: str = "vietsupply-api"
    jwt_secret: str = "dev-secret-change-me"
    auth_provider: str = "dev_jwt"
    jwks_url: str | None = None

    @property
    def is_demo(self) -> bool:
        return self.app_mode == "demo"

    @property
    def database_engine(self) -> str:
        if self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            return "postgresql"
        if self.database_url.startswith("sqlite"):
            return "sqlite"
        return "unknown"

    @property
    def sqlite_path(self) -> Path:
        if self.database_engine != "sqlite" or not self.database_url.startswith("sqlite:///"):
            raise RuntimeError("SQLite DATABASE_URL must use sqlite:///path format.")
        return Path(self.database_url.removeprefix("sqlite:///"))

    def validate_runtime(self) -> None:
        if self.app_mode not in VALID_APP_MODES:
            raise RuntimeError(f"APP_MODE must be one of {sorted(VALID_APP_MODES)}.")
        if self.auth_provider not in VALID_AUTH_PROVIDERS:
            raise RuntimeError(f"AUTH_PROVIDER must be one of {sorted(VALID_AUTH_PROVIDERS)}.")
        if not self.is_demo and self.allow_demo_headers:
            raise RuntimeError("Pilot/production mode must set ALLOW_DEMO_HEADERS=false.")
        if not self.is_demo and self.database_engine != "postgresql":
            raise RuntimeError("Pilot/production mode requires DATABASE_URL to point to PostgreSQL/PostGIS.")
        if not self.is_demo and self.auth_provider != "oidc":
            raise RuntimeError("Pilot/production mode requires AUTH_PROVIDER=oidc.")
        if not self.is_demo and not self.jwks_url:
            raise RuntimeError("Pilot/production mode requires AUTH_JWKS_URL.")


def get_settings() -> AppSettings:
    mode = os.getenv("APP_MODE", "demo").strip().lower()
    allow_demo_headers = os.getenv("ALLOW_DEMO_HEADERS", "true").strip().lower() in {"1", "true", "yes", "on"}
    return AppSettings(
        app_mode=mode,
        database_url=os.getenv("DATABASE_URL", "sqlite:///backend/app/data/vietsupply.db"),
        allow_demo_headers=allow_demo_headers,
        jwt_issuer=os.getenv("AUTH_JWT_ISSUER", "vietsupply-dev"),
        jwt_audience=os.getenv("AUTH_JWT_AUDIENCE", "vietsupply-api"),
        jwt_secret=os.getenv("AUTH_JWT_SECRET", "dev-secret-change-me"),
        auth_provider=os.getenv("AUTH_PROVIDER", "dev_jwt").strip().lower(),
        jwks_url=os.getenv("AUTH_JWKS_URL") or None,
    )

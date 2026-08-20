"""Runtime configuration with safe local defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./promiseguard.db"
_DEFAULT_ENVIRONMENT = "local"


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = _DEFAULT_DATABASE_URL
    environment: str = _DEFAULT_ENVIRONMENT
    auto_create_schema: bool = True
    metrics_enabled: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL),
            environment=os.getenv("PROMISEGUARD_ENV", _DEFAULT_ENVIRONMENT),
            auto_create_schema=os.getenv("AUTO_CREATE_SCHEMA", "true").lower()
            in {"1", "true", "yes"},
            metrics_enabled=os.getenv("METRICS_ENABLED", "true").lower()
            in {"1", "true", "yes"},
        )

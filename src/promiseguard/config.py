"""Runtime configuration with safe local and budget-bounded defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./promiseguard.db"
_DEFAULT_ENVIRONMENT = "local"
_DEFAULT_OPENAI_MODEL = "gpt-5-nano"


def _parse_bool(value: str, *, name: str) -> bool:
    normalised = value.strip().lower()
    if normalised in {"1", "true", "yes", "on"}:
        return True
    if normalised in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _parse_decimal(value: str, *, name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a decimal value") from exc
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    return parsed


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = _DEFAULT_DATABASE_URL
    environment: str = _DEFAULT_ENVIRONMENT
    auto_create_schema: bool = True
    metrics_enabled: bool = True
    openai_enabled: bool = False
    openai_model: str = _DEFAULT_OPENAI_MODEL
    openai_budget_usd: Decimal = Decimal("3.00")
    openai_per_run_limit_usd: Decimal = Decimal("0.001")
    openai_max_output_tokens: int = 320
    openai_timeout_seconds: float = 30.0
    openai_reservation_ttl_seconds: int = 600
    strict_local_identity: bool = False

    def __post_init__(self) -> None:
        if not self.database_url:
            raise ValueError("database_url cannot be empty")
        if not self.openai_model:
            raise ValueError("openai_model cannot be empty")
        if self.openai_budget_usd <= 0:
            raise ValueError("openai_budget_usd must be positive")
        if self.openai_per_run_limit_usd <= 0:
            raise ValueError("openai_per_run_limit_usd must be positive")
        if self.openai_per_run_limit_usd > self.openai_budget_usd:
            raise ValueError("openai_per_run_limit_usd cannot exceed openai_budget_usd")
        if not 64 <= self.openai_max_output_tokens <= 2_000:
            raise ValueError("openai_max_output_tokens must be between 64 and 2000")
        if not 1 <= self.openai_timeout_seconds <= 120:
            raise ValueError("openai_timeout_seconds must be between 1 and 120")
        if self.openai_reservation_ttl_seconds < self.openai_timeout_seconds * 2:
            raise ValueError("OpenAI reservation TTL must be at least twice the request timeout")

    @classmethod
    def from_env(cls) -> Settings:
        openai_mode = os.getenv("OPENAI_ENABLED", "auto").strip().lower()
        if openai_mode == "auto":
            openai_enabled = bool(os.getenv("OPENAI_API_KEY"))
        else:
            openai_enabled = _parse_bool(openai_mode, name="OPENAI_ENABLED")

        return cls(
            database_url=os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL),
            environment=os.getenv("PROMISEGUARD_ENV", _DEFAULT_ENVIRONMENT),
            auto_create_schema=_parse_bool(
                os.getenv("AUTO_CREATE_SCHEMA", "true"), name="AUTO_CREATE_SCHEMA"
            ),
            metrics_enabled=_parse_bool(
                os.getenv("METRICS_ENABLED", "true"), name="METRICS_ENABLED"
            ),
            openai_enabled=openai_enabled,
            openai_model=os.getenv("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL).strip(),
            openai_budget_usd=_parse_decimal(
                os.getenv("OPENAI_BUDGET_USD", "3.00"), name="OPENAI_BUDGET_USD"
            ),
            openai_per_run_limit_usd=_parse_decimal(
                os.getenv("OPENAI_PER_RUN_LIMIT_USD", "0.001"),
                name="OPENAI_PER_RUN_LIMIT_USD",
            ),
            openai_max_output_tokens=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "320")),
            openai_timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30")),
            openai_reservation_ttl_seconds=int(os.getenv("OPENAI_RESERVATION_TTL_SECONDS", "600")),
            strict_local_identity=_parse_bool(
                os.getenv("PROMISEGUARD_STRICT_LOCAL_IDENTITY", "false"),
                name="PROMISEGUARD_STRICT_LOCAL_IDENTITY",
            ),
        )

"""Structured logging, correlation context and defensive field redaction."""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

_CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(address|email|external_notes|name|password|phone|secret|token)",
    re.IGNORECASE,
)
_correlation_id: ContextVar[str] = ContextVar("promiseguard_correlation_id", default="-")


def normalise_correlation_id(candidate: str | None) -> str:
    if candidate and _CORRELATION_PATTERN.fullmatch(candidate):
        return candidate
    return f"corr_{uuid4().hex}"


def bind_correlation_id(correlation_id: str) -> Token[str]:
    return _correlation_id.set(correlation_id)


def reset_correlation_id(token: Token[str]) -> None:
    _correlation_id.reset(token)


def current_correlation_id() -> str:
    return _correlation_id.get()


def redact(value: Any) -> Any:
    """Recursively redact common PII and secret-bearing fields before logging."""

    if isinstance(value, dict):
        return {
            str(key): ("[REDACTED]" if _SENSITIVE_KEY_PATTERN.search(str(key)) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


class JsonLogFormatter(logging.Formatter):
    """Emit stable JSON logs without serialising arbitrary request bodies."""

    reserved: ClassVar[set[str]] = set(logging.LogRecord(None, 0, "", 0, "", (), None).__dict__)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": current_correlation_id(),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self.reserved and key not in {"message", "asctime"}
        }
        if extras:
            payload["context"] = redact(extras)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True, default=str)


def configure_json_logging(*, level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(getattr(handler, "_promiseguard_json", False) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    handler._promiseguard_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)

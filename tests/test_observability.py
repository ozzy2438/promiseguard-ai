from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient

from apps.api.main import create_app
from promiseguard.config import Settings
from promiseguard.observability import (
    JsonLogFormatter,
    bind_correlation_id,
    normalise_correlation_id,
    redact,
    reset_correlation_id,
)


def _client() -> TestClient:
    return TestClient(
        create_app(
            Settings(
                database_url="sqlite+pysqlite:///:memory:",
                environment="test",
                auto_create_schema=True,
            )
        )
    )


def test_api_preserves_valid_correlation_id() -> None:
    with _client() as client:
        response = client.get(
            "/healthz",
            headers={"X-Correlation-ID": "incident-2026-0001"},
        )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "incident-2026-0001"


def test_invalid_correlation_id_is_replaced() -> None:
    generated = normalise_correlation_id("contains whitespace")

    assert generated.startswith("corr_")
    assert len(generated) == 37


def test_redaction_removes_sensitive_nested_fields() -> None:
    payload = redact(
        {
            "order_id": "order-1",
            "customer": {
                "email": "person@example.com",
                "phone": "0400000000",
                "segment": "VIP",
            },
            "api_token": "secret-value",
        }
    )

    assert payload == {
        "order_id": "order-1",
        "customer": {
            "email": "[REDACTED]",
            "phone": "[REDACTED]",
            "segment": "VIP",
        },
        "api_token": "[REDACTED]",
    }


def test_json_formatter_includes_context_and_correlation_without_pii() -> None:
    formatter = JsonLogFormatter()
    token = bind_correlation_id("incident-2026-0002")
    try:
        record = logging.LogRecord(
            name="promiseguard.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="decision_recorded",
            args=(),
            exc_info=None,
        )
        record.order_id = "order-1"
        record.customer_email = "person@example.com"
        payload = json.loads(formatter.format(record))
    finally:
        reset_correlation_id(token)

    assert payload["correlation_id"] == "incident-2026-0002"
    assert payload["context"]["order_id"] == "order-1"
    assert payload["context"]["customer_email"] == "[REDACTED]"

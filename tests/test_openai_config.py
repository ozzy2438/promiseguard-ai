from __future__ import annotations

from decimal import Decimal

import pytest

from promiseguard.config import Settings


def test_openai_defaults_honor_three_dollar_ceiling() -> None:
    settings = Settings()
    assert settings.openai_enabled is False
    assert settings.openai_model == "gpt-5-nano"
    assert settings.openai_budget_usd == Decimal("3.00")
    assert settings.openai_per_run_limit_usd == Decimal("0.001")


def test_auto_mode_uses_key_presence_without_exposing_value(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-never-printed")
    monkeypatch.setenv("OPENAI_ENABLED", "auto")
    settings = Settings.from_env()
    assert settings.openai_enabled is True
    assert not hasattr(settings, "openai_api_key")


def test_invalid_budget_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(
            openai_budget_usd=Decimal("0.001"),
            openai_per_run_limit_usd=Decimal("0.002"),
        )

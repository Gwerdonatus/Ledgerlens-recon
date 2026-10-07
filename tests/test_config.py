from __future__ import annotations

from decimal import Decimal

import pytest

from ledgerlens_recon.config import Config


def test_config_parses_decimal_tolerance_and_fetch_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMOUNT_TOLERANCE", "0.005")
    monkeypatch.setenv("TIME_TOLERANCE_SECONDS", "30")
    monkeypatch.setenv("STRIPE_FETCH_LIMIT", "250")
    monkeypatch.setenv("DATABASE_FETCH_LIMIT", "750")

    config = Config.from_env()

    assert config.amount_tolerance == Decimal("0.005")
    assert config.time_tolerance_seconds == 30
    assert config.stripe_fetch_limit == 250
    assert config.database_fetch_limit == 750


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("AMOUNT_TOLERANCE", "NaN", "finite, non-negative"),
        ("AMOUNT_TOLERANCE", "-0.01", "finite, non-negative"),
        ("TIME_TOLERANCE_SECONDS", "-1", "non-negative"),
        ("STRIPE_FETCH_LIMIT", "0", "positive integers"),
        ("DATABASE_FETCH_LIMIT", "0", "positive integers"),
    ],
)
def test_config_rejects_unsafe_numeric_values(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, message: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        Config.from_env()

from __future__ import annotations

from datetime import timezone
from decimal import Decimal
from unittest.mock import Mock, call, patch

import pytest

from ledgerlens_recon.data_sources.stripe_client import (
    StripeClient,
    minor_units_to_decimal,
)


def _response(*, data: list[dict], has_more: bool) -> Mock:
    response = Mock()
    response.json.return_value = {"data": data, "has_more": has_more}
    response.raise_for_status.return_value = None
    return response


def _item(transaction_id: str, amount: int = 1234, currency: str = "usd") -> dict:
    return {
        "id": transaction_id,
        "amount": amount,
        "currency": currency,
        "created": 1_700_000_000,
    }


@pytest.mark.parametrize(
    ("amount", "currency", "expected"),
    [
        (1234, "USD", Decimal("12.34")),
        (1234, "JPY", Decimal("1234")),
        (1234, "KWD", Decimal("1.234")),
    ],
)
def test_minor_units_respect_currency_exponent(
    amount: int, currency: str, expected: Decimal
) -> None:
    assert minor_units_to_decimal(amount, currency) == expected


@patch("ledgerlens_recon.data_sources.stripe_client.requests.get")
def test_balance_transactions_follow_stripe_pagination(mock_get: Mock) -> None:
    first_page = [_item(f"txn_{index}") for index in range(100)]
    second_page = [_item(f"txn_{index}") for index in range(100, 125)]
    mock_get.side_effect = [
        _response(data=first_page, has_more=True),
        _response(data=second_page, has_more=False),
    ]

    transactions = StripeClient("sk_test_example").list_balance_transactions(limit=125)

    assert len(transactions) == 125
    assert transactions[0].amount == Decimal("12.34")
    assert transactions[0].created_at.tzinfo == timezone.utc
    assert mock_get.call_args_list == [
        call(
            "https://api.stripe.com/v1/balance_transactions",
            headers={"Authorization": "Bearer sk_test_example"},
            params={"limit": 100},
            timeout=30,
        ),
        call(
            "https://api.stripe.com/v1/balance_transactions",
            headers={"Authorization": "Bearer sk_test_example"},
            params={"limit": 25, "starting_after": "txn_99"},
            timeout=30,
        ),
    ]


def test_balance_transactions_reject_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        StripeClient("sk_test_example").list_balance_transactions(limit=0)

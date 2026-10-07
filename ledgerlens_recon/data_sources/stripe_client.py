from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import requests

from ..reconciliation.models import Transaction
from ..utils.time import parse_iso8601

STRIPE_API_BASE = "https://api.stripe.com/v1"
ZERO_DECIMAL_CURRENCIES = {
    "BIF",
    "CLP",
    "DJF",
    "GNF",
    "JPY",
    "KMF",
    "KRW",
    "MGA",
    "PYG",
    "RWF",
    "UGX",
    "VND",
    "VUV",
    "XAF",
    "XOF",
    "XPF",
}
THREE_DECIMAL_CURRENCIES = {"BHD", "JOD", "KWD", "OMR", "TND"}


@dataclass(frozen=True)
class StripeFetchOptions:
    limit: int = 100
    starting_after: str | None = None


class StripeClient:
    def __init__(self, api_key: str, *, timeout_seconds: int = 30) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def list_balance_transactions(self, *, limit: int = 100) -> list[Transaction]:
        """Fetch up to ``limit`` balance transactions across Stripe pages."""
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

        url = f"{STRIPE_API_BASE}/balance_transactions"
        txs: list[Transaction] = []
        starting_after: str | None = None

        while len(txs) < limit:
            page_limit = min(100, limit - len(txs))
            params: dict[str, int | str] = {"limit": page_limit}
            if starting_after:
                params["starting_after"] = starting_after

            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                params=params,
                timeout=self.timeout_seconds,
            )
            resp.raise_for_status()
            payload = resp.json()
            items = payload.get("data", [])

            for item in items:
                currency = str(item.get("currency", "usd")).upper()
                txs.append(
                    Transaction(
                        transaction_id=str(item.get("id")),
                        amount=minor_units_to_decimal(item.get("amount", 0), currency),
                        currency=currency,
                        created_at=datetime.fromtimestamp(
                            int(item.get("created", 0)), tz=timezone.utc
                        ),
                        source="stripe",
                    )
                )
            if not payload.get("has_more") or not items:
                break
            starting_after = str(items[-1]["id"])

        return txs


def minor_units_to_decimal(amount: int | str, currency: str) -> Decimal:
    normalized_currency = currency.upper()
    exponent = (
        0
        if normalized_currency in ZERO_DECIMAL_CURRENCIES
        else 3 if normalized_currency in THREE_DECIMAL_CURRENCIES else 2
    )
    return Decimal(str(amount)).scaleb(-exponent)


def load_stripe_from_csv(path: str) -> list[Transaction]:
    """Load Stripe-like transactions from CSV for local demo.

    Expected columns:
    transaction_id,amount,currency,created_at
    created_at should be ISO8601 (e.g. 2026-02-23T10:00:00Z)
    """
    out: list[Transaction] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(
                Transaction(
                    transaction_id=str(row["transaction_id"]).strip(),
                    amount=Decimal(row["amount"]),
                    currency=str(row["currency"]).upper().strip(),
                    created_at=parse_iso8601(str(row["created_at"])),
                    source="stripe",
                )
            )
    return out

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

import requests

from ..reconciliation.models import Transaction
from ..utils.time import parse_iso8601


STRIPE_API_BASE = "https://api.stripe.com/v1"


@dataclass(frozen=True)
class StripeFetchOptions:
    limit: int = 100
    starting_after: str | None = None


class StripeClient:
    def __init__(self, api_key: str, *, timeout_seconds: int = 30) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def list_balance_transactions(self, *, limit: int = 100) -> List[Transaction]:
        """Fetch a page of Stripe balance transactions.

        NOTE: This is intentionally small for demo purposes.
        In real use, you’d paginate and filter by date range.
        """
        url = f"{STRIPE_API_BASE}/balance_transactions"
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            params={"limit": limit},
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()

        txs: List[Transaction] = []
        for item in data.get("data", []):
            # Stripe returns amount as integer cents in many endpoints;
            # balance_transactions amount is in cents for most currencies.
            amount = float(item.get("amount", 0)) / 100.0
            currency = str(item.get("currency", "usd")).upper()
            created = datetime.fromtimestamp(int(item.get("created", 0)))
            txs.append(
                Transaction(
                    transaction_id=str(item.get("id")),
                    amount=amount,
                    currency=currency,
                    created_at=created,
                    source="stripe",
                )
            )
        return txs


def load_stripe_from_csv(path: str) -> List[Transaction]:
    """Load Stripe-like transactions from CSV for local demo.

    Expected columns:
    transaction_id,amount,currency,created_at
    created_at should be ISO8601 (e.g. 2026-02-23T10:00:00Z)
    """
    out: List[Transaction] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(
                Transaction(
                    transaction_id=str(row["transaction_id"]).strip(),
                    amount=float(row["amount"]),
                    currency=str(row["currency"]).upper().strip(),
                    created_at=parse_iso8601(str(row["created_at"])),
                    source="stripe",
                )
            )
    return out

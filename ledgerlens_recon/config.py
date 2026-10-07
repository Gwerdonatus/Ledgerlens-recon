from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Config:
    amount_tolerance: Decimal
    time_tolerance_seconds: int
    stripe_fetch_limit: int
    database_fetch_limit: int
    stripe_api_key: str | None
    database_url: str | None

    @staticmethod
    def from_env() -> Config:
        try:
            amount_tol = Decimal(os.getenv("AMOUNT_TOLERANCE", "0.50"))
            time_tol = int(os.getenv("TIME_TOLERANCE_SECONDS", "900"))
            stripe_fetch_limit = int(os.getenv("STRIPE_FETCH_LIMIT", "1000"))
            database_fetch_limit = int(os.getenv("DATABASE_FETCH_LIMIT", "5000"))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Invalid numeric reconciliation configuration.") from exc

        if not amount_tol.is_finite() or amount_tol < 0:
            raise ValueError("AMOUNT_TOLERANCE must be a finite, non-negative decimal.")
        if time_tol < 0:
            raise ValueError("TIME_TOLERANCE_SECONDS must be non-negative.")
        if stripe_fetch_limit <= 0 or database_fetch_limit <= 0:
            raise ValueError("Fetch limits must be positive integers.")
        stripe_key = os.getenv("STRIPE_API_KEY") or None
        db_url = os.getenv("DATABASE_URL") or None
        return Config(
            amount_tolerance=amount_tol,
            time_tolerance_seconds=time_tol,
            stripe_fetch_limit=stripe_fetch_limit,
            database_fetch_limit=database_fetch_limit,
            stripe_api_key=stripe_key,
            database_url=db_url,
        )

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    amount_tolerance: float
    time_tolerance_seconds: int
    stripe_api_key: str | None
    database_url: str | None

    @staticmethod
    def from_env() -> "Config":
        amount_tol = float(os.getenv("AMOUNT_TOLERANCE", "0.50"))
        time_tol = int(os.getenv("TIME_TOLERANCE_SECONDS", "900"))
        stripe_key = os.getenv("STRIPE_API_KEY") or None
        db_url = os.getenv("DATABASE_URL") or None
        return Config(
            amount_tolerance=amount_tol,
            time_tolerance_seconds=time_tol,
            stripe_api_key=stripe_key,
            database_url=db_url,
        )

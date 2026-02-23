from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    amount: float
    currency: str
    created_at: datetime
    source: str  # "stripe" or "internal"


class ReconcileStatus(str, Enum):
    MATCHED = "matched"
    MISSING_IN_STRIPE = "missing_in_stripe"
    MISSING_IN_INTERNAL = "missing_in_internal"
    AMOUNT_MISMATCH = "amount_mismatch"
    TIME_MISMATCH = "time_mismatch"
    INVALID = "invalid"


@dataclass(frozen=True)
class ReconcileRow:
    transaction_id: str
    stripe_amount: Optional[float]
    internal_amount: Optional[float]
    stripe_time: Optional[datetime]
    internal_time: Optional[datetime]
    currency: str
    status: ReconcileStatus
    confidence: float
    notes: str = ""

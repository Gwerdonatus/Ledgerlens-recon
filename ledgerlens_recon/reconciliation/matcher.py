from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Dict, Iterable, List, Tuple

from .models import ReconcileRow, ReconcileStatus, Transaction
from ..utils.time import seconds_between, to_utc
from ..utils.validation import ensure, raise_if_errors, ValidationError


def _round2(x: float | None) -> float | None:
    return None if x is None else float(round(x, 2))


def reconcile(
    stripe: Iterable[Transaction],
    internal: Iterable[Transaction],
    *,
    amount_tolerance: float,
    time_tolerance_seconds: int,
) -> List[ReconcileRow]:
    """Reconcile two transaction streams by transaction_id.

    Idempotent & deterministic:
    - stable ordering by transaction_id
    - no external side effects
    """
    stripe_map: Dict[str, Transaction] = {t.transaction_id: t for t in stripe}
    internal_map: Dict[str, Transaction] = {t.transaction_id: t for t in internal}

    all_ids = sorted(set(stripe_map.keys()) | set(internal_map.keys()))
    rows: List[ReconcileRow] = []

    for tx_id in all_ids:
        s = stripe_map.get(tx_id)
        i = internal_map.get(tx_id)

        if s is None and i is None:
            # logically unreachable
            continue

        # Missing cases
        if s is None:
            rows.append(
                ReconcileRow(
                    transaction_id=tx_id,
                    stripe_amount=None,
                    internal_amount=_round2(i.amount),
                    stripe_time=None,
                    internal_time=to_utc(i.created_at),
                    currency=i.currency,
                    status=ReconcileStatus.MISSING_IN_STRIPE,
                    confidence=0.25,
                    notes="Present in internal only.",
                )
            )
            continue

        if i is None:
            rows.append(
                ReconcileRow(
                    transaction_id=tx_id,
                    stripe_amount=_round2(s.amount),
                    internal_amount=None,
                    stripe_time=to_utc(s.created_at),
                    internal_time=None,
                    currency=s.currency,
                    status=ReconcileStatus.MISSING_IN_INTERNAL,
                    confidence=0.25,
                    notes="Present in Stripe only.",
                )
            )
            continue

        # Validate basics
        errors: List[ValidationError] = []
        ensure(s.currency == i.currency, "currency", "Currency mismatch.", errors)
        raise_if_errors(errors)

        amount_delta = abs(float(s.amount) - float(i.amount))
        time_delta = seconds_between(to_utc(s.created_at), to_utc(i.created_at))

        amount_ok = amount_delta <= amount_tolerance
        time_ok = time_delta <= time_tolerance_seconds

        if amount_ok and time_ok:
            rows.append(
                ReconcileRow(
                    transaction_id=tx_id,
                    stripe_amount=_round2(s.amount),
                    internal_amount=_round2(i.amount),
                    stripe_time=to_utc(s.created_at),
                    internal_time=to_utc(i.created_at),
                    currency=s.currency,
                    status=ReconcileStatus.MATCHED,
                    confidence=1.0,
                    notes="Matched on id; within amount/time tolerance.",
                )
            )
            continue

        # Determine mismatch type (prefer amount mismatch if both)
        if not amount_ok:
            confidence = max(0.0, 0.85 - min(0.85, amount_delta / max(1.0, amount_tolerance)))
            rows.append(
                ReconcileRow(
                    transaction_id=tx_id,
                    stripe_amount=_round2(s.amount),
                    internal_amount=_round2(i.amount),
                    stripe_time=to_utc(s.created_at),
                    internal_time=to_utc(i.created_at),
                    currency=s.currency,
                    status=ReconcileStatus.AMOUNT_MISMATCH,
                    confidence=float(round(confidence, 2)),
                    notes=f"Amount delta={amount_delta:.2f} exceeds tolerance={amount_tolerance:.2f}.",
                )
            )
            continue

        # time mismatch
        confidence = max(0.0, 0.85 - min(0.85, time_delta / max(1.0, float(time_tolerance_seconds))))
        rows.append(
            ReconcileRow(
                transaction_id=tx_id,
                stripe_amount=_round2(s.amount),
                internal_amount=_round2(i.amount),
                stripe_time=to_utc(s.created_at),
                internal_time=to_utc(i.created_at),
                currency=s.currency,
                status=ReconcileStatus.TIME_MISMATCH,
                confidence=float(round(confidence, 2)),
                notes=f"Time delta={time_delta:.0f}s exceeds tolerance={time_tolerance_seconds}s.",
            )
        )

    return rows


def summarize(rows: Iterable[ReconcileRow]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        out[r.status.value] = out.get(r.status.value, 0) + 1
    out["total"] = sum(out.values())
    return out

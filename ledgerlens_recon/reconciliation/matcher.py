from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from ..utils.time import seconds_between, to_utc
from .models import ReconcileRow, ReconcileStatus, Transaction


def _money(value: Decimal | None) -> Decimal | None:
    return value


def _index_unique(transactions: Iterable[Transaction], source: str) -> dict[str, Transaction]:
    indexed: dict[str, Transaction] = {}
    duplicates: set[str] = set()
    for transaction in transactions:
        if transaction.transaction_id in indexed:
            duplicates.add(transaction.transaction_id)
        indexed[transaction.transaction_id] = transaction
    if duplicates:
        duplicate_ids = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplicate transaction IDs in {source}: {duplicate_ids}")
    return indexed


def reconcile(
    stripe: Iterable[Transaction],
    internal: Iterable[Transaction],
    *,
    amount_tolerance: Decimal,
    time_tolerance_seconds: int,
) -> list[ReconcileRow]:
    """Reconcile two transaction streams by transaction_id.

    Idempotent & deterministic:
    - stable ordering by transaction_id
    - no external side effects
    """
    if not amount_tolerance.is_finite() or amount_tolerance < 0:
        raise ValueError("amount_tolerance must be a finite, non-negative decimal")
    if time_tolerance_seconds < 0:
        raise ValueError("time_tolerance_seconds must be non-negative")

    stripe_map = _index_unique(stripe, "Stripe")
    internal_map = _index_unique(internal, "internal")

    all_ids = sorted(set(stripe_map.keys()) | set(internal_map.keys()))
    rows: list[ReconcileRow] = []

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
                    internal_amount=_money(i.amount),
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
                    stripe_amount=_money(s.amount),
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

        if s.currency != i.currency:
            rows.append(
                ReconcileRow(
                    transaction_id=tx_id,
                    stripe_amount=_money(s.amount),
                    internal_amount=_money(i.amount),
                    stripe_time=to_utc(s.created_at),
                    internal_time=to_utc(i.created_at),
                    currency=f"{s.currency}/{i.currency}",
                    status=ReconcileStatus.INVALID,
                    confidence=0.0,
                    notes="Currency mismatch.",
                )
            )
            continue

        amount_delta = abs(s.amount - i.amount)
        time_delta = seconds_between(to_utc(s.created_at), to_utc(i.created_at))

        amount_ok = amount_delta <= amount_tolerance
        time_ok = time_delta <= time_tolerance_seconds

        if amount_ok and time_ok:
            rows.append(
                ReconcileRow(
                    transaction_id=tx_id,
                    stripe_amount=_money(s.amount),
                    internal_amount=_money(i.amount),
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
            denominator = max(Decimal("1"), amount_tolerance)
            penalty = min(Decimal("0.85"), amount_delta / denominator)
            confidence = max(Decimal("0"), Decimal("0.85") - penalty)
            rows.append(
                ReconcileRow(
                    transaction_id=tx_id,
                    stripe_amount=_money(s.amount),
                    internal_amount=_money(i.amount),
                    stripe_time=to_utc(s.created_at),
                    internal_time=to_utc(i.created_at),
                    currency=s.currency,
                    status=ReconcileStatus.AMOUNT_MISMATCH,
                    confidence=float(confidence.quantize(Decimal("0.01"))),
                    notes=(
                        f"Amount delta={amount_delta:f} exceeds " f"tolerance={amount_tolerance:f}."
                    ),
                )
            )
            continue

        # time mismatch
        confidence = max(
            0.0, 0.85 - min(0.85, time_delta / max(1.0, float(time_tolerance_seconds)))
        )
        rows.append(
            ReconcileRow(
                transaction_id=tx_id,
                stripe_amount=_money(s.amount),
                internal_amount=_money(i.amount),
                stripe_time=to_utc(s.created_at),
                internal_time=to_utc(i.created_at),
                currency=s.currency,
                status=ReconcileStatus.TIME_MISMATCH,
                confidence=float(round(confidence, 2)),
                notes=f"Time delta={time_delta:.0f}s exceeds tolerance={time_tolerance_seconds}s.",
            )
        )

    return rows


def summarize(rows: Iterable[ReconcileRow]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r.status.value] = out.get(r.status.value, 0) + 1
    out["total"] = sum(out.values())
    return out

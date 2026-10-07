from __future__ import annotations

from decimal import Decimal

import pytest

from ledgerlens_recon.reconciliation.matcher import reconcile, summarize
from ledgerlens_recon.reconciliation.models import ReconcileStatus, Transaction
from ledgerlens_recon.utils.time import parse_iso8601


def tx(source: str, txid: str, amount: str, ts: str, currency: str = "NGN") -> Transaction:
    return Transaction(
        transaction_id=txid,
        amount=Decimal(amount),
        currency=currency,
        created_at=parse_iso8601(ts),
        source=source,
    )


def test_reconcile_classifies_rows() -> None:
    stripe = [
        tx("stripe", "a", "100.00", "2026-02-22T09:00:00Z"),
        tx("stripe", "b", "200.00", "2026-02-22T09:05:00Z"),
        tx("stripe", "c", "300.00", "2026-02-22T09:10:00Z"),
    ]
    internal = [
        tx("internal", "a", "100.00", "2026-02-22T09:00:10Z"),  # matched
        tx("internal", "b", "205.00", "2026-02-22T09:05:10Z"),
        tx("internal", "x", "50.00", "2026-02-22T09:12:00Z"),
    ]

    rows = reconcile(
        stripe,
        internal,
        amount_tolerance=Decimal("0.50"),
        time_tolerance_seconds=900,
    )
    by_id = {r.transaction_id: r for r in rows}

    assert by_id["a"].status == ReconcileStatus.MATCHED
    assert by_id["b"].status == ReconcileStatus.AMOUNT_MISMATCH
    assert by_id["c"].status == ReconcileStatus.MISSING_IN_INTERNAL
    assert by_id["x"].status == ReconcileStatus.MISSING_IN_STRIPE

    s = summarize(rows)
    assert s["total"] == 4


def test_decimal_amounts_do_not_introduce_binary_float_drift() -> None:
    stripe = [tx("stripe", "precise", "0.30", "2026-02-22T09:00:00Z")]
    internal = [tx("internal", "precise", "0.10", "2026-02-22T09:00:00Z")]

    row = reconcile(
        stripe,
        internal,
        amount_tolerance=Decimal("0.20"),
        time_tolerance_seconds=0,
    )[0]

    assert row.status == ReconcileStatus.MATCHED
    assert row.stripe_amount == Decimal("0.30")
    assert row.internal_amount == Decimal("0.10")


def test_currency_mismatch_is_reported_without_aborting_batch() -> None:
    stripe = [tx("stripe", "currency", "10.00", "2026-02-22T09:00:00Z", "USD")]
    internal = [tx("internal", "currency", "10.00", "2026-02-22T09:00:00Z", "NGN")]

    row = reconcile(
        stripe,
        internal,
        amount_tolerance=Decimal("0"),
        time_tolerance_seconds=0,
    )[0]

    assert row.status == ReconcileStatus.INVALID
    assert row.currency == "USD/NGN"
    assert row.confidence == 0.0


def test_duplicate_transaction_ids_are_rejected() -> None:
    duplicate = tx("stripe", "dup", "10.00", "2026-02-22T09:00:00Z")

    with pytest.raises(ValueError, match="Duplicate transaction IDs in Stripe: dup"):
        reconcile(
            [duplicate, duplicate],
            [],
            amount_tolerance=Decimal("0.50"),
            time_tolerance_seconds=900,
        )


@pytest.mark.parametrize(
    ("amount_tolerance", "time_tolerance"),
    [
        (Decimal("-0.01"), 1),
        (Decimal("NaN"), 1),
        (Decimal("0"), -1),
    ],
)
def test_invalid_tolerances_are_rejected(amount_tolerance: Decimal, time_tolerance: int) -> None:
    with pytest.raises(ValueError):
        reconcile(
            [],
            [],
            amount_tolerance=amount_tolerance,
            time_tolerance_seconds=time_tolerance,
        )

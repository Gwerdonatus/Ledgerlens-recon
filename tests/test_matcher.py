from __future__ import annotations

from ledgerlens_recon.reconciliation.matcher import reconcile, summarize
from ledgerlens_recon.reconciliation.models import Transaction, ReconcileStatus
from ledgerlens_recon.utils.time import parse_iso8601


def tx(source: str, txid: str, amount: float, ts: str, currency: str = "NGN") -> Transaction:
    return Transaction(
        transaction_id=txid,
        amount=amount,
        currency=currency,
        created_at=parse_iso8601(ts),
        source=source,
    )


def test_reconcile_classifies_rows() -> None:
    stripe = [
        tx("stripe", "a", 100.0, "2026-02-22T09:00:00Z"),
        tx("stripe", "b", 200.0, "2026-02-22T09:05:00Z"),
        tx("stripe", "c", 300.0, "2026-02-22T09:10:00Z"),
    ]
    internal = [
        tx("internal", "a", 100.0, "2026-02-22T09:00:10Z"),  # matched
        tx("internal", "b", 205.0, "2026-02-22T09:05:10Z"),  # amount mismatch (tol small)
        tx("internal", "x", 50.0, "2026-02-22T09:12:00Z"),   # missing in stripe
    ]

    rows = reconcile(stripe, internal, amount_tolerance=0.5, time_tolerance_seconds=900)
    by_id = {r.transaction_id: r for r in rows}

    assert by_id["a"].status == ReconcileStatus.MATCHED
    assert by_id["b"].status == ReconcileStatus.AMOUNT_MISMATCH
    assert by_id["c"].status == ReconcileStatus.MISSING_IN_INTERNAL
    assert by_id["x"].status == ReconcileStatus.MISSING_IN_STRIPE

    s = summarize(rows)
    assert s["total"] == 4

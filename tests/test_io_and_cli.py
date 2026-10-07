from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from ledgerlens_recon.data_sources.db_client import load_internal_from_csv
from ledgerlens_recon.data_sources.stripe_client import load_stripe_from_csv
from ledgerlens_recon.main import run_reconcile
from ledgerlens_recon.reconciliation.matcher import reconcile, summarize
from ledgerlens_recon.reconciliation.models import ReconcileStatus
from ledgerlens_recon.reporting.excel_writer import write_report


def _write_csv(path: Path, rows: list[str]) -> None:
    path.write_text(
        "transaction_id,amount,currency,created_at\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def test_csv_loaders_preserve_exact_decimal_values(tmp_path: Path) -> None:
    stripe_path = tmp_path / "stripe.csv"
    internal_path = tmp_path / "internal.csv"
    row = "txn_exact,10.005,usd,2026-02-22T09:00:00Z"
    _write_csv(stripe_path, [row])
    _write_csv(internal_path, [row])

    stripe = load_stripe_from_csv(str(stripe_path))
    internal = load_internal_from_csv(str(internal_path))

    assert stripe[0].amount == Decimal("10.005")
    assert internal[0].amount == Decimal("10.005")
    assert stripe[0].currency == "USD"


def test_excel_report_contains_summary_and_exact_rows(tmp_path: Path) -> None:
    stripe_path = tmp_path / "stripe.csv"
    internal_path = tmp_path / "internal.csv"
    _write_csv(stripe_path, ["txn_1,12.34,usd,2026-02-22T09:00:00Z"])
    _write_csv(internal_path, ["txn_1,12.34,usd,2026-02-22T09:00:00Z"])
    rows = reconcile(
        load_stripe_from_csv(str(stripe_path)),
        load_internal_from_csv(str(internal_path)),
        amount_tolerance=Decimal("0"),
        time_tolerance_seconds=0,
    )
    report_path = tmp_path / "report.xlsx"

    write_report(rows, summarize(rows), str(report_path))

    workbook = load_workbook(report_path, data_only=True)
    assert workbook.sheetnames == ["summary", "reconciliation"]
    details = workbook["reconciliation"]
    assert details["A2"].value == "txn_1"
    assert details["B2"].value == ReconcileStatus.MATCHED.value
    assert details["E2"].value == 12.34


def test_run_reconcile_executes_csv_workflow(tmp_path: Path, monkeypatch) -> None:
    for key in ("STRIPE_API_KEY", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    stripe_path = tmp_path / "stripe.csv"
    internal_path = tmp_path / "internal.csv"
    report_path = tmp_path / "reports" / "result.xlsx"
    _write_csv(stripe_path, ["txn_cli,50.00,ngn,2026-02-22T09:00:00Z"])
    _write_csv(internal_path, ["txn_cli,50.00,ngn,2026-02-22T09:00:00Z"])

    exit_code = run_reconcile(str(stripe_path), str(internal_path), str(report_path))

    assert exit_code == 0
    assert report_path.exists()

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .config import Config
from .data_sources.db_client import DbClient, load_internal_from_csv
from .data_sources.stripe_client import StripeClient, load_stripe_from_csv
from .reconciliation.matcher import reconcile, summarize
from .reporting.excel_writer import write_report
from .utils.logging import setup_logging


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ledgerlens-recon", description="Payment reconciliation CLI.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("reconcile", help="Run reconciliation and write Excel report.")
    r.add_argument("--stripe-csv", default=None, help="Path to Stripe-like CSV (mock mode).")
    r.add_argument("--internal-csv", default=None, help="Path to internal CSV (mock mode).")
    r.add_argument("--out", default="reports/reconciliation_report.xlsx", help="Output Excel path.")
    return p


def run_reconcile(stripe_csv: Optional[str], internal_csv: Optional[str], out_path: str) -> int:
    load_dotenv()
    cfg = Config.from_env()
    log = setup_logging()

    log.info(f"Starting reconcile; out={out_path}")

    stripe_txs = None
    internal_txs = None

    # Stripe source selection
    if cfg.stripe_api_key:
        log.info("Using Stripe API source.")
        stripe_txs = StripeClient(cfg.stripe_api_key).list_balance_transactions(limit=100)
    elif stripe_csv:
        log.info(f"Using Stripe CSV source: {stripe_csv}")
        stripe_txs = load_stripe_from_csv(stripe_csv)
    else:
        raise ValueError("No Stripe source available. Provide STRIPE_API_KEY or --stripe-csv.")

    # Internal source selection
    if cfg.database_url:
        log.info("Using database source.")
        internal_txs = DbClient(cfg.database_url).fetch_transactions(limit=5000)
    elif internal_csv:
        log.info(f"Using internal CSV source: {internal_csv}")
        internal_txs = load_internal_from_csv(internal_csv)
    else:
        raise ValueError("No internal source available. Provide DATABASE_URL or --internal-csv.")

    rows = reconcile(
        stripe_txs,
        internal_txs,
        amount_tolerance=cfg.amount_tolerance,
        time_tolerance_seconds=cfg.time_tolerance_seconds,
    )
    summary = summarize(rows)

    log.info(f"Summary: {summary}")

    out = write_report(rows, summary, out_path)
    log.info(f"Wrote report: {out}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "reconcile":
        return run_reconcile(args.stripe_csv, args.internal_csv, args.out)

    raise ValueError(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())

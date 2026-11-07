# LedgerLens Recon

A small, production-minded **payment reconciliation CLI** that matches transactions between:

- **Stripe** (API or local mock)
- an **internal database** (PostgreSQL via SQLAlchemy *or* local CSV mock)

It generates an **Excel report** with highlighted anomalies and a summary sheet.

> This repository is a **portfolio / demo project**.  
> It’s designed to show how to structure a reconciliation job that’s simple, auditable, and safe to rerun.

---

## Fictional wallet transfer API

The optional Django/DRF + PostgreSQL wallet extension adds atomic transfers, concurrent-safe idempotency, account ownership checks, transaction history and ledger reconciliation. [Setup, demonstration and design notes](docs/wallet.md) · [Recorded verification results](docs/wallet-verification.md).

## Why this exists

Many teams jump straight to orchestration (Airflow/Kafka) for problems that are:
- batch
- deterministic
- moderate volume
- better solved with strong correctness + reporting

This project focuses on **clarity, idempotency, and maintainability**.

---

## Features

- Modular architecture (not a single script)
- Data sources:
  - Stripe API client with bounded cursor pagination (plus a CSV mock mode)
  - DB client via SQLAlchemy (with a mock CSV mode)
- Matching logic:
  - primary match: `transaction_id`
  - exact `Decimal` arithmetic—no binary floating-point money calculations
  - currency-aware Stripe conversion, including zero- and three-decimal currencies
  - validation: currency, amount tolerance, timestamp tolerance, and duplicate IDs
  - categorization into matched, mismatched, invalid, and missing records
- Confidence scoring (0.0–1.0)
- Excel reporting via `openpyxl`:
  - Summary sheet
  - Color-coded rows by status
- Strong production basics:
  - Structured logging (JSON)
  - Config-driven thresholds
  - CLI entry point
  - CI across Python 3.10–3.12 with linting, formatting, package builds, and an 80% coverage gate

---

## Project structure

```
ledgerlens_recon/
├── ledgerlens_recon/
│   ├── data_sources/
│   │   ├── stripe_client.py
│   │   └── db_client.py
│   ├── reconciliation/
│   │   ├── models.py
│   │   └── matcher.py
│   ├── reporting/
│   │   └── excel_writer.py
│   ├── utils/
│   │   ├── logging.py
│   │   └── time.py
│   ├── config.py
│   └── main.py
├── examples/
│   ├── internal_transactions.csv
│   └── stripe_transactions.csv
├── tests/
│   ├── test_config.py
│   ├── test_io_and_cli.py
│   ├── test_matcher.py
│   └── test_stripe_client.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## Quickstart (mock mode)

### 1) Create a venv + install deps

```bash
python -m venv .venv
# Windows:
# .venv\Scripts\activate
# Mac/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run reconciliation using included example CSVs

```bash
python -m ledgerlens_recon.main reconcile \
  --stripe-csv examples/stripe_transactions.csv \
  --internal-csv examples/internal_transactions.csv \
  --out reports/reconciliation_report.xlsx
```

You should see:
- `reports/reconciliation_report.xlsx` (created)
- JSON logs printed to stdout

---

## Using real integrations (optional)

Set environment variables (copy `.env.example` to `.env`):

- `STRIPE_API_KEY` (optional if you use CSV)
- `DATABASE_URL` (Postgres URL for SQLAlchemy)

Then:

```bash
python -m ledgerlens_recon.main reconcile --out reports/report.xlsx
```

The CLI will:
- use Stripe API if `STRIPE_API_KEY` is set
- use DB if `DATABASE_URL` is set
- otherwise fall back to CSV paths if provided

---

## Configuration

Thresholds can be set via env variables:

- `AMOUNT_TOLERANCE` (default: 0.50)
- `TIME_TOLERANCE_SECONDS` (default: 900)
- `STRIPE_FETCH_LIMIT` (default: 1000)
- `DATABASE_FETCH_LIMIT` (default: 5000)

Values are validated at startup. Fetch limits bound each reconciliation run while
Stripe's cursor pagination ensures the configured range is fully traversed.

---

## Development checks

Install the development dependencies and run the same checks enforced by CI:

```bash
pip install -e '.[dev]'
ruff check .
black --check .
pytest --cov=ledgerlens_recon --cov-fail-under=80
python -m build
```

---

## Notes on idempotency

This job is safe to rerun:
- report output is deterministic (stable ordering)
- no external writes are performed besides the report file
- failures are logged and surfaced clearly

---

## License

MIT

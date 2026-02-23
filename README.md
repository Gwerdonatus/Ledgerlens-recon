# LedgerLens Recon

A small, production-minded **payment reconciliation CLI** that matches transactions between:

- **Stripe** (API or local mock)
- an **internal database** (PostgreSQL via SQLAlchemy *or* local CSV mock)

It generates an **Excel report** with highlighted anomalies and a summary sheet.

> This repository is a **portfolio / demo project**.  
> It’s designed to show how to structure a reconciliation job that’s simple, auditable, and safe to rerun.

---

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
  - Stripe API client (with a mock mode)
  - DB client via SQLAlchemy (with a mock CSV mode)
- Matching logic:
  - primary match: `transaction_id`
  - validation: amount tolerance + timestamp tolerance
  - categorization into matched/mismatched/missing
- Confidence scoring (0.0–1.0)
- Excel reporting via `openpyxl`:
  - Summary sheet
  - Color-coded rows by status
- Strong production basics:
  - Structured logging (JSON)
  - Config-driven thresholds
  - CLI entry point
  - Unit tests for core matching logic

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
│   │   ├── time.py
│   │   └── validation.py
│   ├── config.py
│   └── main.py
├── examples/
│   ├── internal_transactions.csv
│   └── stripe_transactions.csv
├── tests/
│   └── test_matcher.py
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

---

## Notes on idempotency

This job is safe to rerun:
- report output is deterministic (stable ordering)
- no external writes are performed besides the report file
- failures are logged and surfaced clearly

---

## License

MIT

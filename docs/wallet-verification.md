# Local verification — 7 November 2026

Environment: Python 3.12.14, Django 5.2.19, Django REST Framework 3.16.1, psycopg 3.3.8 and PostgreSQL 16 in Docker. These are local results; the new GitHub Actions workflow has not been run remotely.

- Wallet suite: **18 tests passed** against PostgreSQL; **98% statement coverage** excluding tests and generated migrations.
- Existing CLI suite: **21 tests passed**, **87.99% statement coverage**.
- Ruff and Black checks passed.
- Django system checks passed and no missing migrations were detected.
- Wheel and source distribution built successfully.
- A temporary development server passed a real HTTP smoke check: POST returned 201, identical retry returned the same status/body, GET returned 200, account history contained the transfer and reconciliation returned no issues.

## Required concurrency demonstration

`python manage.py demo_wallet` produced:

```json
{
  "concurrent_request_statuses": [201, 409],
  "rejection": "insufficient_funds",
  "successful_retries": 10,
  "source_balance": 2000,
  "destination_balance": 8000,
  "reconciliation_issues": []
}
```

Values are GBP minor units. The starting source balance was 10000. Request completion order is intentionally unspecified.

The suite also verified five simultaneous requests with the same key, opposing transfers without deadlock, exceptions after debit and after ledger creation, conflicting reuse of keys, cached business rejection after funding, ownership boundaries, invalid input and detection of a corrupted ledger entry.

## Reproduce

Follow [wallet setup](wallet.md), then run:

```sh
ruff check .
black --check .
pytest --cov=ledgerlens_recon --cov-fail-under=80
coverage run --source=wallet_service manage.py test wallet_service.wallet --noinput
coverage report --fail-under=80
python manage.py makemigrations --check --dry-run
python manage.py demo_wallet
python manage.py reconcile_wallet
python -m build
```

Coverage commands overwrite the local `.coverage` file; each coverage report belongs to the immediately preceding suite. Concurrency tests establish behaviour for the exercised schedules, not a formal proof or load benchmark.

# Wallet service: start here

LedgerLens adds a fictional GBP transfer service to its existing payment reconciliation CLI. It addresses a specific problem: a customer retries a payment after losing the response, while another request may be spending the same balance. The service must return a stable result without applying the transfer twice or allowing either wallet to become negative.

This is a portfolio implementation with executable correctness tests. It does not connect to a bank, card network or payment provider. Opening balances are fixture allocations, not deposits. The existing Stripe/CSV reconciliation pipeline remains independent of the wallet database.

## Documentation map

| Document | Use it to answer |
| --- | --- |
| [API contract](wallet-api.md) | What can a client send, receive and safely retry? |
| [Architecture and invariants](wallet-architecture.md) | Where do guarantees come from, and where do they stop? |
| [Design decisions](decisions/0001-wallet-transfers.md) | Why this transaction, locking and idempotency design? |
| [Local runbook](wallet-operations.md) | How do I run, diagnose and investigate the service? |
| [Verification record](wallet-verification.md) | What was actually tested, on which revision, and what remains unverified? |

## Run the service

Prerequisites: Python 3.10+, Docker with Compose, a running Docker engine and an available localhost port 55432. The recorded local wallet run used Python 3.12 and PostgreSQL 16. Commands assume a POSIX shell and the repository root.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,wallet]'
docker compose -f compose.wallet.yml up -d --wait
python manage.py migrate --noinput
python manage.py seed_wallet
python manage.py runserver 127.0.0.1:8000
```

The seed command prints account IDs, local authentication tokens and current balances. On a fresh database Alice has £100 and Bob has £0. Subsequent runs preserve balances and reuse existing tokens. There is no signup or account-creation API. The database credentials and secret in the default settings are intended for this local environment.

In another terminal, substitute Alice's token from the seed output:

```sh
curl -i http://127.0.0.1:8000/transfers \
  -H 'Authorization: Token <alice-token>' \
  -H 'Idempotency-Key: first-payment' \
  -H 'Content-Type: application/json' \
  -d '{"source":"00000000-0000-0000-0000-000000000001","destination":"00000000-0000-0000-0000-000000000002","amount":8000}'
```

On fresh fixtures this returns 201 and transfers £80. Repeat it unchanged: the response status and JSON body match the original, and no additional entries are created. Change `amount` to `100` while retaining the same key: the response is 409 and balances remain unchanged. GBP is fixed; sending a `currency` field is a validation error.

Use the returned transfer ID with `GET /transfers/{id}`, or inspect Alice's history with `GET /accounts/00000000-0000-0000-0000-000000000001/transfers`. Both require the same authorization header. [Full request, response and retry semantics](wallet-api.md).

## Reproduce the concurrency demonstration

With the database running and migrations applied:

```sh
python manage.py demo_wallet
python manage.py reconcile_wallet
python manage.py test wallet_service.wallet --verbosity 2 --noinput
```

`demo_wallet` creates new users and accounts on every run. It starts two £80 transfer attempts against £100 using separate database connections, then retries the successful request ten times. It verifies one 201, one 409, final balances of £20 and £80, and no reconciliation issues. It invokes the service directly; the test suite separately covers HTTP handling using DRF's client. Records remain available for inspection.

Stop the API with Ctrl-C and the database with:

```sh
docker compose -f compose.wallet.yml stop
```

Use `up -d --wait` to resume. See the [runbook](wallet-operations.md) before removing containers: this Compose configuration has no named data volume or backup workflow.

## Scope of the guarantee

For validated requests routed through the transfer service, one committed result is associated with each authenticated user and idempotency key. Balances, ledger entries, transfer and stored response commit together. Concurrent debits use locked balances rather than a previously read balance.

These guarantees depend on PostgreSQL, the current transaction boundary and all normal transfer writes using the service. Direct ORM/database changes can violate cross-row ledger invariants. Process-kill recovery, failover, large-scale contention and production operation have not been established. See the [architecture](wallet-architecture.md) and [verification gaps](wallet-verification.md) for the exact boundaries.

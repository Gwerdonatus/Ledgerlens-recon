# Fictional wallet transfer service

This extension adds Django REST Framework and PostgreSQL alongside the existing reconciliation CLI. It uses fictional GBP balances and never contacts a payment provider.

## Run locally

From the repository root, using Python 3.10 or newer:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,wallet]'
docker compose -f compose.wallet.yml up -d --wait
python manage.py migrate
python manage.py seed_wallet
python manage.py runserver 127.0.0.1:8000
```

The seed command prints Alice and Bob's account IDs and local demo tokens. Alice starts with £100 (`10000` minor units); Bob starts with zero. Rerunning the command preserves their balances. Keep tokens local. Use `Authorization: Token <token>` for each API request. The settings' database credentials and secret are local demo defaults; deployment is outside this project's scope.

```sh
curl -i http://127.0.0.1:8000/transfers \
  -H 'Authorization: Token <alice-token>' \
  -H 'Idempotency-Key: first-payment' \
  -H 'Content-Type: application/json' \
  -d '{"source":"00000000-0000-0000-0000-000000000001","destination":"00000000-0000-0000-0000-000000000002","amount":8000}'
```

Repeat the exact request with the same key to receive the original JSON body and HTTP status. Change the amount with that key to receive 409. Amounts must be JSON integers, not floats, booleans or strings. GBP is fixed; there is no currency input. Unknown fields are rejected.

| Endpoint | Behaviour |
| --- | --- |
| `POST /transfers` | Authenticated owner debits their account and credits a known destination account |
| `GET /transfers/{uuid}` | Only source and destination owners can read the transfer |
| `GET /accounts` | Lists only the authenticated user's accounts |
| `GET /accounts/{uuid}/transfers` | Owner-only history, newest first |

Lists accept `limit` and `offset`, default to 50 rows and cap at 100. All paths omit trailing slashes. Unknown or inaccessible accounts/transfers return 404. Missing authentication returns 401; invalid inputs return 400. Insufficient funds and destination balance limits return a persisted 409 rejection with a transfer ID. Rejected transfers appear in history and have no ledger entries.

## Reproduce the demonstration

```sh
python manage.py demo_wallet
python manage.py reconcile_wallet
python manage.py test wallet_service.wallet --verbosity 2
```

The demo creates fresh fictional users/accounts each run. It races two distinct £80 withdrawals against £100, verifies exactly one 201 and one 409, then repeats the winning request ten times. Final balances must be £20 and £80. It leaves those records available for inspection.

Tests use a real PostgreSQL test database, separate connections and threads with a start barrier. They exercise HTTP handling through DRF's test client. SQLite is deliberately unsupported because it cannot establish the row-locking guarantee. The test database user needs permission to create databases. `wallet.yml` repeats the suite and demo in CI.

## Configuration and shutdown

Database settings can be overridden with `WALLET_DB_NAME`, `WALLET_DB_USER`, `WALLET_DB_PASSWORD`, `WALLET_DB_HOST` and `WALLET_DB_PORT`. The defaults match `compose.wallet.yml`. `WALLET_SECRET_KEY` overrides the local development secret.

Stop the API with Ctrl-C. To stop the database while retaining its container, run:

```sh
docker compose -f compose.wallet.yml stop
```

The demo is repeatable and intentionally creates new records. See [recorded verification results](wallet-verification.md) for the tested environment and commands.

## Correctness and design

The API validates shape and ownership; `services.py` coordinates the transfer; models and database constraints enforce stored bounds and uniqueness. UUIDs identify accounts and transfers. Account balances and transfer amounts are bounded at 10^12 minor units. A completed transfer has exactly one negative entry for the source and one matching positive entry for the destination. Current balance must equal opening balance plus signed entries.

1. An atomic transaction reserves `(authenticated user, Idempotency-Key)` with a database unique constraint. Concurrent duplicates wait for the first transaction to commit. Django's `get_or_create` retrieves its committed record after a uniqueness conflict.
2. Existing keys compare canonical account IDs and integer amount. An identical request returns the stored result; a changed request returns 409. Keys have no expiration in this version.
3. New requests lock both account rows by UUID order, verify source ownership and check balances while holding the locks. Every transfer uses the same lock order, including opposing transfers.
4. Balance updates, transfer, two entries, and original response commit together. An exception after debit or after ledger creation rolls everything back, including the key reservation. A retry can then try again.
5. Business rejections commit their original result. A previously insufficient request stays rejected after subsequent funding; use a fresh key to make a new attempt. Validation/ownership errors and unexpected exceptions do not reserve a key.

The guarantee is one committed transfer per user/key, even when the client loses the response after commit. It is not an exactly-once network delivery guarantee. Locks have a 10-second wait limit and statements a 20-second limit; infrastructure errors roll back and callers can retry with the same key.

`reconcile_wallet` uses one PostgreSQL repeatable-read, read-only snapshot, compares each transfer with its expected entry pair and recalculates balances. It reports affected account/transfer IDs and exits nonzero on disagreement. A balance mismatch lists related transfers to investigate; that list does not establish which record caused corruption. The existing Stripe/CSV reconciliation CLI remains separately available.

References: [Django row locking](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update), [PostgreSQL lock ordering](https://www.postgresql.org/docs/16/explicit-locking.html), [DRF token authentication](https://www.django-rest-framework.org/api-guide/authentication/#tokenauthentication).

## A bug exposed during implementation

DRF's default serializer silently ignored an unexpected `currency` field. A request with `currency: USD` initially returned 201 and moved GBP. A regression test expected 400 and failed with `201 != 400`. The input serializer now rejects unknown fields before any money moves; the same check also catches misspelled fields. This matters because ignoring a client's currency assumption can produce a valid database transaction with the wrong meaning.

## Limits and next steps

This is a learning service. It has no provider integration, webhooks, worker, reversals, exchange rates, admin UI, deployment configuration or performance benchmark. Tokens have no expiry and there is no public signup or account-creation API. There are no real funds.

Write correctness assumes all normal transfers use this service. Constraints prevent negative balances and duplicate account entries per transfer; cross-row ledger invariants are checked by service logic and reconciliation. Database administrators and direct ORM writes can still alter balances, entries, ownership or opening balances. There are no immutability triggers or restricted writer roles. Reconciliation currently loads the ledger into memory and needs batching for larger datasets. Add hardened database permissions/immutability, fault recovery under process termination, deadlock retry policy and real load tests before treating this as a production design.

For an integration follow-up, add a simulated provider webhook and an outbox/worker, with explicit tests for duplicates, ordering and restart recovery. A Go reimplementation can follow once these invariants are familiar.

# Local wallet runbook

Scope: the Docker/PostgreSQL demo and developer verification. This is not a production deployment or incident-response guarantee. Start with the [quickstart](wallet.md); this document covers configuration and diagnosis.

## Configuration

Settings are read from the process environment in [settings.py](../wallet_service/settings.py). Unlike the existing CLI, the wallet settings do not automatically load `.env`. Export overrides in your shell before running Django commands.

| Variable | Default | Purpose |
| --- | --- | --- |
| `WALLET_DB_NAME` | `ledgerlens` | Database name |
| `WALLET_DB_USER` | `ledgerlens` | Database role |
| `WALLET_DB_PASSWORD` | `ledgerlens-local` | Local database password |
| `WALLET_DB_HOST` | `127.0.0.1` | Database host |
| `WALLET_DB_PORT` | `55432` | Host port, mapped to PostgreSQL 5432 |
| `WALLET_SECRET_KEY` | `local-fictional-wallet-only` | Django local secret |

Changing these variables does not change Compose's configured PostgreSQL role, password or port mapping. Keep both sides aligned. The role in this disposable setup can create the test database; that is not a recommended production privilege model. Django allows `localhost`, `127.0.0.1` and `testserver` hosts; there is no environment override for that list.

## Startup and validation

```sh
docker compose -f compose.wallet.yml up -d --wait
docker compose -f compose.wallet.yml ps
python manage.py check
python manage.py migrate --noinput
python manage.py seed_wallet
python manage.py reconcile_wallet
python manage.py runserver 127.0.0.1:8000
```

The Compose healthcheck establishes database availability only. `check` validates Django configuration; it does not prove data consistency. `reconcile_wallet` prints `{"issues": []}` and exits 0 when its checks agree. There is no application health endpoint.

Fixture tokens are credentials. Use them locally and do not commit seed output or paste tokens into issue/PR logs. Token generation and [DRF authentication](https://www.django-rest-framework.org/api-guide/authentication/#tokenauthentication) are independent of Django session login; fixture users have unusable passwords. Real remote token transport would require HTTPS and a token lifecycle design.

## Diagnose common symptoms

| Symptom | First checks | Recovery boundary |
| --- | --- | --- |
| Docker connection error | Docker engine is running; current Docker context is correct | Start the engine, then retry Compose |
| Port 55432 already allocated | Identify the listener/container; compare intended database host/port | Use the intended existing database or explicitly align a different mapping and settings; do not remove an unrelated container |
| PostgreSQL authentication error | Exported environment matches database credentials | Correct credentials; changing Compose environment does not reset an already initialized database role |
| Missing tables | `python manage.py showmigrations wallet` | Apply migrations before seeding/serving |
| Test database creation denied | Role has `CREATEDB` on a disposable local instance | Use an appropriate local test role, not a shared production database |
| 401 response | Correct fixture token and `Authorization: Token ...` header | Rerun seed to inspect/reuse local credentials |
| 404 for another account's history | Requester owns that account | Expected access boundary; do not broaden querysets to bypass it |
| Repeated insufficient-funds 409 after funding | Same key is returning the original rejection | Use a new key only for a deliberate new attempt |
| Timeout or 500 | Server traceback, database availability, lock contention | Retry the unchanged request/key; do not infer rollback merely from the response |

The lock timeout is 10 seconds and statement timeout 20 seconds. There is no automatic service retry, mapped 503 response, metrics dashboard or alerting. Server/database logs are currently needed to distinguish infrastructure failures.

## Investigate reconciliation discrepancies

Capture the checker output and command exit status:

```sh
python manage.py reconcile_wallet > wallet-reconciliation.json
```

Discrepancies produce JSON on stdout and a `CommandError` on stderr with nonzero exit status. Database connection/query failures can also exit nonzero; an absent or incomplete report is not evidence of consistency. The output file contains account/transfer identifiers; keep it in the local investigation context.

1. Confirm the expected database and revision. Record when the report was produced.
2. If investigating a real defect in this demo, pause transfer writes while preserving current records. The command itself does not pause writers.
3. For `transfer_entries`, compare the transfer's source/destination/amount/status with its signed entries. For `account_balance`, compare opening balance, summed entries and stored balance. Related IDs are investigation candidates, not proven causes. For `transfer_owner`, examine whether ownership was edited.
4. Inspect the affected records without modifying them, for example with the Django shell:

```python
from wallet_service.wallet.models import Account, LedgerEntry, Transfer
transfer_id = "<affected-transfer-uuid>"
Transfer.objects.filter(pk=transfer_id).values()
LedgerEntry.objects.filter(transfer_id=transfer_id).values("account_id", "amount")
Account.objects.filter(entries__transfer_id=transfer_id).distinct().values(
    "id", "opening_balance", "balance"
)
```

5. Establish the responsible code path or direct write before designing a correction. Reconciliation does not provide an authoritative repair amount or a compensating-transfer API. Do not edit records merely to make the report pass.
6. After a reviewed correction, rerun reconciliation and preserve both reports and the correction rationale. A clean report establishes the implemented invariants at that snapshot; it does not establish external settlement or absence of historical tampering.

## Shutdown and data lifecycle

```sh
# Stop containers while retaining them and their attached data.
docker compose -f compose.wallet.yml stop
# Resume the same Compose environment.
docker compose -f compose.wallet.yml up -d --wait
```

There is no explicit named volume in the current Compose file. Do not rely on `down` followed by `up` to reconnect the same anonymous database volume. Do not use volume deletion as a routine troubleshooting step. No backup/restore procedure is implemented or verified here.

`seed_wallet` preserves existing fixture balances; it is not a reset command. `demo_wallet` creates new users/accounts on each run and checks reconciliation across the whole wallet database, so unrelated existing drift also causes the demo to fail. Run deliberately destructive/corruption experiments only in the disposable test database. The Django suite creates `test_ledgerlens` by default and removes it afterwards.

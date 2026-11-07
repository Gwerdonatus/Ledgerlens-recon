# Wallet verification record

Recorded: 7 November 2026. Implementation baseline: [`e69531194b8b836a01c0e7fd6b840c628bcf0919`](https://github.com/Gwerdonatus/Ledgerlens-recon/commit/e69531194b8b836a01c0e7fd6b840c628bcf0919). Subsequent documentation-only revisions do not change the behaviour measured below.

## Results and provenance

| Check | Recorded result | Evidence boundary |
| --- | --- | --- |
| Local wallet suite | 18 passed; 98% statement coverage (250/255 statements) | Python 3.12.14, Django 5.2.19, DRF 3.16.1, psycopg 3.3.8, PostgreSQL 16 in Docker; tests and generated migrations omitted from coverage |
| Local existing CLI suite | 21 passed; 87.99% statement coverage (315/358 statements) | Independent reconciliation tests; does not establish wallet behaviour |
| Local static/configuration checks | Ruff, Black, Django system check and migration drift check passed | Configuration/format checks, not runtime correctness proofs |
| Local packaging | Wheel and source distribution built | Does not establish production deployment readiness |
| Local real HTTP smoke check | POST 201; identical retry; GET 200; history contained transfer; reconciliation clean | Temporary development server; one recorded manual/scripted smoke run, not a committed HTTP smoke-test harness |
| GitHub CLI workflow | Completed successfully on implementation baseline | [CI run 42319590110](https://github.com/Gwerdonatus/Ledgerlens-recon/actions/runs/42319590110), Python 3.10–3.12 matrix |
| GitHub wallet workflow | Completed successfully on implementation baseline | [Wallet run 42319590114](https://github.com/Gwerdonatus/Ledgerlens-recon/actions/runs/42319590114), Python 3.12/PostgreSQL 16 |

The workflows are [CI](../.github/workflows/ci.yml) and [wallet correctness](../.github/workflows/wallet.yml). Test totals refer to this baseline; neither totals nor coverage percentages are a throughput, reliability or production-traffic claim. Dependency ranges and Docker tags are not fully locked, so later installations may resolve newer patch versions. The environment above records the local run, not a claim about every version resolved in CI.

## Requirement-to-test map

Tests live in [WalletTests](../wallet_service/wallet/tests.py). The suite uses Django `TransactionTestCase`, PostgreSQL transactions and fresh database connections in concurrent threads. Start barriers align request starts but do not force a particular lock acquisition schedule. DRF's `APIClient` exercises request handling in process; the server socket is covered only by the separately recorded smoke check.

| Requirement | Test method(s) | Assertion or observation |
| --- | --- | --- |
| Sequential replay | `test_success_and_ten_retries_return_original_response` | Same status/body ten times, one transfer, two entries, expected balances |
| Simultaneous replay | `test_simultaneous_same_key_moves_money_once` | Five same-key requests agree; one transfer and one debit |
| Competing withdrawals | `test_concurrent_overspending_then_ten_retries` | One 201/one 409, then winning-key retries leave balances unchanged |
| Rollback after debit | `test_failure_after_debit_rolls_everything_back_then_retry_succeeds` | Injected credit-save exception; original balances, no transfer/entries/key, subsequent same-key retry succeeds |
| Failure storing result | `test_failure_persisting_response_also_rolls_back` | Exception after ledger creation; original balances and no transfer |
| Conflicting reuse | `test_conflicting_key_rejected` | Changed amount/destination returns 409; no further money movement |
| Stable rejection | `test_rejected_request_remains_rejected_after_funding` | Previously insufficient request remains rejected with the same body after fixture funding |
| Key scope | `test_key_is_scoped_to_authenticated_user` | Same textual key used independently by two users |
| Access boundaries | `test_ownership_and_unauthenticated_access` | Missing credentials denied; unrelated user cannot debit/read; destination owner can read |
| Input contract | `test_invalid_inputs`, `test_unknown_fields_are_rejected` | Invalid amounts/UUIDs/keys, same-account transfer and unknown fields rejected without reservations |
| Destination capacity | `test_destination_limit` | Destination-full rejection; balances unchanged |
| Database backstop | `test_database_rejects_negative_balance` | Direct negative-balance update raises integrity error |
| Drift detection | `test_reconciliation_identifies_bad_pair_and_affected_transfer` | Altered credit entry produces transfer discrepancy and related transfer ID in balance issue |
| Opposing transfers | `test_opposing_transfers_do_not_deadlock` | A→B and B→A complete within test bounds, conserve balances and reconcile |
| Fixture rerun | `test_seed_rerun_preserves_spent_balance` | Seed does not reset spent balance or rotate existing token |
| Audit command | `test_reconciliation_command_exits_nonzero_on_discrepancy` | Clean JSON report, then nonzero command failure after deliberate corruption |
| Demonstration command | `test_demo_command_leaves_inspectable_correct_records` | Ten successful replays, expected final balances and clean reconciliation |

Tests that directly change opening/current balances or ledger entries do so to construct fixtures or simulate corruption in a disposable test database; those writes are not supported API operations.

## Concurrency demonstration

`python manage.py demo_wallet` creates fresh £100/£0 accounts, races distinct £80 requests and retries the winner ten times. The observed outcome was one completed transfer and one persisted insufficient-funds rejection, ending at £20/£80 with no audit issues.

The following is a **summary of the recorded outcome**, not the command's literal output schema:

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

The actual output includes `fictional`, a `requests` array with each key/status/result, generated UUIDs and timestamps, and the final balances/retry/audit fields. Which key wins is intentionally unspecified. The command calls the service directly rather than sending network requests.

## Reproduce

Follow [setup](wallet.md). The database role must be able to create the disposable test database; the default Compose role can. With the virtual environment active:

```sh
ruff check .
black --check .
pytest --cov=ledgerlens_recon --cov-fail-under=80
coverage run --source=wallet_service manage.py test wallet_service.wallet --noinput
coverage report --fail-under=80
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py demo_wallet
python manage.py reconcile_wallet
python -m build
```

`pytest` covers the existing CLI; wallet tests run through `manage.py test`. Coverage commands overwrite `.coverage`; interpret each report against its immediately preceding suite. Repeated demonstration runs add new fictional users/accounts and do not reset existing fixtures.

For a manual HTTP check, start the development server and follow the [POST/retry example](wallet.md), then read the returned ID and account history using the [API contract](wallet-api.md). Do not include fixture tokens in saved evidence.

## What remains unverified

- Process termination, host restart, database failover and connection loss at the commit boundary. Exception injection establishes rollback for the exercised code paths; it is not a process-crash test.
- Real network delivery failures and automatic client retry/backoff behaviour. The API has no packaged client or retry loop.
- Lock-timeout/deadlock error response mapping and broad/high-contention schedules. Two threads and five duplicates do not establish load capacity, fairness or a latency objective.
- Arbitrary direct database writes, concurrent account ownership changes, incomplete idempotency rows, or coordinated tampering. The application has no normal API for these writes.
- Reconciliation during a forced concurrent commit, all possible corruption classes, and large-ledger resource bounds. The snapshot design is implemented; not every premise has a dedicated adversarial test.
- Authentication expiry/rotation, abuse resistance, remote deployment, external settlement, provider events and backup restoration.

These gaps constrain the claim to the implementation and scenarios above. Prioritized acceptance evidence for follow-up work is in [ADR 0001](decisions/0001-wallet-transfers.md).

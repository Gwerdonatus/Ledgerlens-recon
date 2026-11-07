# ADR 0001: transactional wallet transfers in one PostgreSQL database

- Status: implemented for the fictional wallet demo
- Decision date: 7 November 2026
- Implementation baseline: `e69531194b8b836a01c0e7fd6b840c628bcf0919`
- Scope: transfers within LedgerLens; excludes provider settlement and real funds

## Context

A transfer request may be repeated, race another withdrawal or fail after one write. We need to explain and test what happens to balances and the client's result in each case. The existing project is a Python reconciliation CLI; the extension should be small enough to inspect without hiding correctness behind queues or multiple services.

Requirements are integer monetary amounts, source ownership, bounded nonnegative balances, equal debit/credit entries for completed transfers, atomic failure and stable replay of both completed and business-rejected requests.

## Decision and alternatives

| Decision | Reason | Alternative and tradeoff |
| --- | --- | --- |
| Django/DRF service in the same repository, one PostgreSQL database | Reuses Python knowledge and gives all transfer state one commit boundary | A separate service or Go rewrite adds integration/language work before these invariants are understood |
| Integer GBP minor units, fixed currency | Exact arithmetic and a narrow input contract | Decimal is also appropriate for monetary domains; multiple currencies require explicit units, conversion and balancing rules |
| Lock both account rows in UUID order | A readable serialization point for funds and destination capacity checks | Optimistic version checks or conditional updates can work, but need conflict/retry logic spanning both accounts |
| Reserve a database-unique user/key before account locks | Handles simultaneous duplicates and coordinates replay with commit | An in-memory cache cannot coordinate independent processes or roll back atomically with money records |
| Persist the original response in the transfer transaction | A retry recovers the same outcome after a lost response | Reconstructing from mutable current state risks response drift and loses the original rejection reason |
| Persist business rejections | A key represents one evaluated intent, including rejection | Retrying the same key after funding could otherwise unexpectedly turn a rejected operation into a debit |
| Keep keys without expiry for this version | Avoids reopening an old intent after deletion | Bounded retention needs an explicit client replay horizon and archival/tombstone policy |
| Store current balance and signed ledger entries | Fast balance checks plus an independent recomputation path | Deriving balance on every write changes the contention/query model; stored balances require reconciliation |
| Separate read-only reconciliation | Detects broken pairs and balance drift without altering evidence | Automatic repair needs provenance, authorization and compensating-entry rules that are not yet defined |

The database enforces row bounds and key uniqueness. Service code enforces cross-row ledger relationships. That split is deliberate for a small demonstration, but database permissions and immutable history remain necessary follow-ups before a stronger audit claim.

## Consequences

Correctness is localized to one transaction and a small set of source files. Hot accounts serialize transfers and may time out under contention. Keys and responses grow without bound. The ledger is an internal transfer journal with fixture allocations, not a complete financial ledger or settlement system. Tests are tied to PostgreSQL because the concurrency mechanism depends on its row locks.

There is no automatic retry loop: callers reuse the same key after an ambiguous outcome. Unexpected failures currently return generic server errors. Direct database edits can invalidate the assumptions, and reconciliation cannot prove the absence of coordinated tampering.

## Implementation learning: ignored currency

The initial DRF serializer ignored unknown request fields. A request containing `currency: USD` returned 201 while moving GBP. `test_unknown_fields_are_rejected` expected 400 and failed with `201 != 400`. The serializer now rejects unknown fields before creating a reservation. The lesson is to make unsupported financial intent explicit at the API boundary; a database-correct operation can still have the wrong customer meaning.

## Follow-ups and acceptance evidence

These are proposed work, not implemented features or scheduled commitments.

| Priority | Change | Evidence needed before claiming completion |
| --- | --- | --- |
| 1 | Immutable journal and restricted writers | Direct entry update/delete rejected for the application role; controlled corrections preserve history |
| 1 | Recovery and contention policy | Kill/restart and lost-response tests around commit; bounded retries for retryable errors; measured hot-account contention |
| 1 | Operational visibility and recovery | Correlation identifiers without token leakage, error/lock/reconciliation metrics, and a verified backup restore |
| 2 | API hardening | Error taxonomy, versioning, token lifecycle, rate limiting and explicit ownership-change semantics |
| 2 | Bounded audit and history queries | Dataset-scale evidence that memory/query cost is bounded and audits preserve a consistent view |
| 2 | Key retention | Documented replay horizon and tests proving old requests cannot silently execute again |
| 3 | Simulated provider/outbox worker | Duplicate, out-of-order and restart delivery tests; no coupling of external calls to held account locks |

Revisit this decision if we add a second database/provider, change isolation or locking, permit ownership changes, expire keys or permit additional transfer writers. Each changes a premise of the current proof of behaviour.

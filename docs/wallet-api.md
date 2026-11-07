# Wallet API contract

Implementation: [routes](../wallet_service/urls.py), [views and serializers](../wallet_service/wallet/api.py), [transfer service](../wallet_service/wallet/services.py). Local base URL: `http://127.0.0.1:8000`. Paths have no trailing slash. The API has no version prefix; treat it as an evolving demo contract.

## Authentication and access

Every endpoint requires `Authorization: Token <token>`. Obtain fixture tokens with `python manage.py seed_wallet`. Tokens identify the requester server-side; clients cannot submit a user or owner field. Missing or invalid credentials return 401. Tokens do not expire automatically in this implementation.

| Endpoint | Access rule |
| --- | --- |
| `POST /transfers` | Requester must own the source; destination may belong to another user |
| `GET /transfers/{id}` | Requester must own the source or destination |
| `GET /accounts` | Returns only requester's accounts |
| `GET /accounts/{id}/transfers` | Requester must own that account |

Unknown and inaccessible resources both return 404. A sender must already know the destination UUID; there is no public directory or payee verification flow. Possessing a destination UUID does not grant read access to that account.

## Create a transfer

`POST /transfers` with `Content-Type: application/json` and `Idempotency-Key`.

| Input | Contract |
| --- | --- |
| `Idempotency-Key` header | Required; 1–128 ASCII characters with codes 33–126; spaces and control characters rejected |
| `source` | Required account UUID |
| `destination` | Required different account UUID |
| `amount` | Required JSON integer, inclusive range 1–1,000,000,000,000, in GBP minor units |

`8000` means £80. Strings, floats (including `8000.0`), booleans, null, unknown fields and a `currency` field are rejected. UUIDs are normalized before comparison for idempotency. There is no memo, client reference or external provider ID.

Example body:

```json
{
  "source": "00000000-0000-0000-0000-000000000001",
  "destination": "00000000-0000-0000-0000-000000000002",
  "amount": 8000
}
```

Illustrative 201 body; generated IDs and timestamps vary:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "source": "00000000-0000-0000-0000-000000000001",
  "destination": "00000000-0000-0000-0000-000000000002",
  "amount": 8000,
  "currency": "GBP",
  "status": "completed",
  "created_at": "2026-11-07T00:00:00+00:00"
}
```

A business rejection returns 409 with the same transfer fields, `status: rejected`, and an `error` value of `insufficient_funds` or `destination_balance_limit`. It creates a rejected transfer and a stored response, with no balance changes or ledger entries. If both balance checks would fail, insufficient funds takes precedence.

## Retry and conflict semantics

Key scope is `(authenticated user, key)`. Keys currently have no expiry or cleanup policy. The same key may be used independently by another authenticated user.

| Situation | Result | Client action |
| --- | --- | --- |
| Same user/key and normalized source, destination and amount | Original POST status and JSON body, including a prior 409 business rejection | Treat as the original outcome |
| Same user/key, changed valid payload | 409 with `detail` conflict message; no new transfer | Correct the accidental reuse; a genuinely new intent needs a new key |
| Invalid body or key | 400; does not reserve a new key | Correct the input |
| New key, missing/inaccessible source or missing destination | 404; reservation rolls back | Correct account references/access |
| Original result is unknown because of timeout/disconnection/5xx | May have committed, or may have rolled back | Retry the identical request with the same key |

Input validation occurs before idempotency lookup. Reusing an existing key with an invalid body returns 400 rather than the stored result or a conflict. An identical valid replay returns the stored result before rechecking current balances. A rejected request remains rejected after later funding; a new attempt requires a new key.

The replay guarantee covers status and JSON body, not all HTTP headers, response byte formatting or latency. Do not generate a new key merely because a response was lost: that would express another transfer intent.

## Error bodies

Examples reflect the current framework/service implementation; there is no common application error envelope or stable error-code taxonomy for every failure.

| Case | Status | Representative JSON |
| --- | --- | --- |
| Missing key | 400 | `{"Idempotency-Key":"Provide 1–128 printable ASCII characters without spaces."}` |
| Float amount | 400 | `{"amount":["Use an integer number of minor units."]}` |
| Unknown currency field | 400 | `{"currency":"Unknown field."}` |
| Unavailable account | 404 | `{"detail":"Account unavailable."}` |
| Valid payload conflicts with stored key | 409 | `{"detail":"This Idempotency-Key was already used for a different request."}` |

Malformed JSON is a 400. An unsupported media type may return 415. Unexpected database/application errors are not mapped to a dedicated retryable status or JSON envelope; the development server can return a generic 500. A 5xx alone cannot tell a client whether commit succeeded.

## Read a transfer

`GET /transfers/{id}` returns 200 with `id`, `source`, `destination`, `amount`, `currency`, `status` and `created_at`. It returns the transfer representation, not the stored POST response. In particular, a rejected transfer's GET representation does **not** include the POST `error` reason. Repeat the original POST/key to recover that original response.

Parse timestamps as offset-aware ISO 8601 values. POST replay preserves the stored timestamp string; GET serialization may format an equivalent instant differently.

## List accounts and history

`GET /accounts` returns objects with `id`, `balance` and `currency`, ordered by account UUID. `GET /accounts/{id}/transfers` returns the transfer representation above, including completed and rejected transfers, ordered by descending `created_at`, then descending ID.

Both use `limit`/`offset` pagination: default 50, maximum limit 100. Example envelope:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {"id": "00000000-0000-0000-0000-000000000001", "balance": 2000, "currency": "GBP"}
  ]
}
```

`next` and `previous` are URLs or null. Offset pagination is not a stable snapshot across requests; concurrent inserts can shift history pages. There is no ledger-entry endpoint, filtering, cursor pagination or total-balance API.

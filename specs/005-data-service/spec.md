# Spec: Data Service API

**Intake ID:** 0005-data-service
**Pod:** claim-runner
**Pod spec number:** claim-runner/005
**Status:** Ready for allocation
**Constitution references:** Technology Stack, Service Independence, Data Layer, Central Startup
**Source:** `intake/0005-data-service.md`

---

## Goal

Implement the Data Service as a FastAPI service on port 8083. It loads all four
JSON data files into memory at startup and exposes them over HTTP/REST. The three
adjudication services — Claims Manager, Benefits Determiner, and Pricer — call
this service for every data access instead of reading files from disk. Claims
Manager writes new claim records through this service.

The Data Service is an internal service. It is not exposed to external callers.

---

## Out of Scope

- Accumulator write-back to `members.json` — that file remains read-only at
  runtime; the Data Service loads and serves it unchanged (constitution: Data
  Layer)
- Any query, filter, or search capability beyond the specific lookups listed
  below
- Authentication or authorisation
- Any persistent store other than `claims.json` — no database, cache, or message
  broker is introduced (constitution: Data Layer)
- Institutional claims

---

## Functional Requirements

### FR-1 — Member lookup

`GET /members/{member_id}` returns the full member record for the given ID.
Returns `404` if the member is not found.

### FR-2 — Plan lookup

`GET /plans/{plan_id}` returns the full plan record for the given ID.
Returns `404` if the plan is not found.

### FR-3 — Fee schedule lookup

`GET /fee-schedules/{procedure_code}` returns the fee schedule entry for the
given CPT code, covering both `in_network` and `out_of_network` blocks.
Returns `404` if the procedure code is not found.

### FR-4 — Claim read

`GET /claims/{claim_id}` returns the stored adjudication record for the given
claim ID. Returns `404` if not found.

### FR-5 — Claim write

`POST /claims` stores a new adjudication result. The request body must conform
to the claim ledger schema in `architecture/data-model.md §5`.

Returns `201` with the stored record on success. Returns `409 CONFLICT` if
`claim_id` is already present in the store.

After storing the record in memory, the service writes the updated claim
list back to `claims.json` synchronously before returning `201`. If the file
write fails, the service returns `500` and does not retain the record in memory.

### FR-6 — Health check

`GET /health` returns `200` with a JSON body reporting the count of records
loaded for each collection:

```json
{
  "status": "UP",
  "members": 200,
  "plans": 5,
  "fee_schedules": 25,
  "claims": 150
}
```

`claims` reflects the current in-memory count and increases as records are
written.

---

## Domain Model

### GET /members/{member_id} — Response

Full member record as defined in `architecture/data-model.md §3`. Sample:

```json
{
  "member_id": "MBR-10042",
  "first_name": "Jane",
  "last_name": "Smith",
  "date_of_birth": "1985-04-12",
  "gender": "F",
  "contact": { "email": "jane.smith@email.com", "phone": "555-123-4567", "address": "123 Main St, Springfield, IL 62701" },
  "enrollment": { "plan_id": "PLN-GOLD-001", "effective_date": "2025-01-01", "termination_date": null },
  "accumulators": {
    "plan_year": "2025",
    "individual_deductible": { "limit": 500.00, "used": 125.00, "met": false },
    "family_deductible": null,
    "individual_oop_max": { "limit": 4000.00, "used": 155.00, "met": false },
    "family_oop_max": null
  },
  "authorizations": [
    { "auth_id": "AUTH-00321", "procedure_code": "42820", "authorized_date": "2025-08-01", "expiration_date": "2025-11-01" }
  ]
}
```

### GET /plans/{plan_id} — Response

Full plan record as defined in `architecture/data-model.md §2`.

### GET /fee-schedules/{procedure_code} — Response

Full fee schedule entry as defined in `architecture/data-model.md §4`.

### GET /claims/{claim_id} — Response

Full claim ledger record as defined in `architecture/data-model.md §5`.

### POST /claims — Request

Full claim ledger record as defined in `architecture/data-model.md §5`. The
`claim_id` field must be present and non-empty.

### POST /claims — Response

| HTTP Status | Condition |
|---|---|
| `201` | Record stored successfully; body is the stored record |
| `409` | `claim_id` already exists in the store |
| `422` | Request body is missing required fields |
| `500` | File write to `claims.json` failed; record not retained |

---

## Integration

### Called by

All three adjudication services. No external callers.

### Data files loaded at startup

| File | Access | Purpose |
|---|---|---|
| `members.json` | Read — loaded once at startup | Member records served via `GET /members/{member_id}` |
| `plans.json` | Read — loaded once at startup | Plan records served via `GET /plans/{plan_id}` |
| `fee_schedules.json` | Read — loaded once at startup | Fee schedule records served via `GET /fee-schedules/{procedure_code}` |
| `claims.json` | Read at startup; written after each `POST /claims` | Claim ledger; bootstraps in-memory store; persisted on every write |

`DATA_DIR` environment variable controls the data directory path; default is
`./data`. The Data Service is the only service that reads from or writes to disk.

---

## Non-functional Requirements

- **Language / framework:** Python 3.11+, FastAPI (constitution: Technology Stack)
- **Startup:** Service must be independently startable; it has no upstream HTTP
  dependencies (it reads only from the local filesystem)
- **`/health` gate:** `start.sh` uses `/health` to gate downstream service
  startups; endpoint must return `200` when all four files are loaded
- **In-memory store:** All reference data (members, plans, fee_schedules) is
  loaded once at startup and held in memory for the lifetime of the process;
  there is no hot-reload mechanism
- **Synchronous write:** `POST /claims` persists to `claims.json` before
  returning; no async or deferred write
- **`claims.json` bootstrap:** If `claims.json` does not exist on startup, the
  service creates it as an empty array (`[]`) and starts normally

---

## Edge Cases

| Case | Expected behavior |
|---|---|
| `GET /members/{member_id}` — ID not found | `404` with `{ "detail": "member not found" }` |
| `GET /plans/{plan_id}` — ID not found | `404` with `{ "detail": "plan not found" }` |
| `GET /fee-schedules/{procedure_code}` — code not found | `404` with `{ "detail": "procedure code not found" }` |
| `GET /claims/{claim_id}` — ID not found | `404` with `{ "detail": "claim not found" }` |
| `POST /claims` — `claim_id` already present | `409` with `{ "detail": "claim already exists" }` |
| `POST /claims` — file write fails (disk full, permission error) | `500`; record not added to in-memory store |
| `claims.json` does not exist on startup | Create empty file; log at INFO level; continue normally |
| Reference file (`members.json`, `plans.json`, or `fee_schedules.json`) missing on startup | Log error at CRITICAL level; exit with non-zero status code |

---

## Constraints

- The Data Service is the only service that reads from disk. No other service
  may use `DATA_DIR` or read JSON files directly. (Constitution: Data Layer,
  Decision 0009)
- `claims.json` is the only file any service may write to, and only through this
  service's `POST /claims` endpoint. (Constitution: Data Layer)
- No external database, cache, or message broker is introduced. (Constitution:
  Data Layer)
- This service does not implement any adjudication logic. (Constitution:
  Adjudication Flow)
- This spec covers the Data Service only. Changes to any adjudication service
  contract triggered by introducing this service are tracked within each
  respective spec (0001, 0002, 0003). (Constitution: Spec Scope)

---

## Acceptance Criteria

1. `GET /members/{member_id}` with a valid ID returns `200` with the full member
   record matching the schema in `architecture/data-model.md §3`.
2. `GET /members/{member_id}` with an unknown ID returns `404`.
3. `GET /plans/{plan_id}` with a valid ID returns `200` with the full plan
   record.
4. `GET /plans/{plan_id}` with an unknown ID returns `404`.
5. `GET /fee-schedules/{procedure_code}` with a valid CPT code returns `200`
   with the fee schedule entry including both `in_network` and `out_of_network`
   blocks.
6. `GET /fee-schedules/{procedure_code}` with an unknown code returns `404`.
7. `GET /claims/{claim_id}` with a valid ID returns `200` with the full claim
   ledger record.
8. `GET /claims/{claim_id}` with an unknown ID returns `404`.
9. `POST /claims` with a valid, new claim body returns `201` and the claim is
   subsequently retrievable via `GET /claims/{claim_id}`.
10. After a successful `POST /claims`, the claim appears in `claims.json` on disk
    (verifiable by restarting the service and calling `GET /claims/{claim_id}`).
11. `POST /claims` with a `claim_id` that already exists returns `409`.
12. `GET /health` returns `200` with correct record counts for all four
    collections once all files are loaded.
13. If `claims.json` is absent at startup, the service starts normally and
    `GET /health` returns `"claims": 0`.
14. If any reference file is absent at startup, the service exits with a non-zero
    status code (verified by observing that `start.sh` detects the health check
    failure and does not proceed).

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

## Clarifications

### Session 2026-09-01

- Q: Do the three adjudication services (001–003) need to be updated to call the Data Service before spec 005 can be marked complete? → A: No — spec 005 ships independently. Specs 001–003 will be updated in separate follow-on specs that are blocked on 005 landing first.
- Q: Should `.specify/memory/data-model.md` be created as part of spec 005, or is it a prerequisite from another repository? → A: External prerequisite — distributed from the control pod. Available at `.specify/memory/data-model.md` in this repository; all spec path references updated accordingly.
- Q: When multiple adjudication services submit claims concurrently via `POST /claims`, how should the Data Service protect the in-memory claim store from concurrent write corruption? → A: `asyncio.Lock` on the `async def` POST handler guards the in-memory store. (threading.Lock is incorrect for async FastAPI endpoints — see research.md Decision 1. No file write.)
- Q: What startup position should the Data Service occupy in `start.sh`, and is updating `start.sh` in scope for spec 005? → A: Yes, in scope — Data Service starts first; `start.sh` is updated as part of this spec so that Benefits Determiner and Pricer are gated behind the Data Service `/health` returning 200.
- Q: Beyond the two log levels already specified (INFO for missing `claims.json`, CRITICAL for missing reference files), what request-level events should the Data Service log? → A: Log every `POST /claims` outcome (claim ID + success/failure) and every `404` response at INFO level.

### Session 2026-09-02

- Q: Should the Data Service write claim records back to `claims.json` after each `POST /claims`, or operate as a fully in-memory store with all four JSON files read-only at startup? → A: Fully in-memory — all four files are loaded at startup and never written to at runtime. Each restart returns to the seed state. This departs from the Pod-Local Constitution principle that `claims.json` is the durable claim ledger; a decision on record is required (Decision 0010 placeholder).

---

## Out of Scope

- Accumulator write-back to `members.json` — that file remains read-only at
  runtime; the Data Service loads and serves it unchanged (constitution: Data
  Layer)
- Any query, filter, or search capability beyond the specific lookups listed
  below
- Authentication or authorisation
- Any persistent store — the service is intentionally ephemeral; no database,
  cache, message broker, or runtime file writes are introduced
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

`POST /claims` stores a new adjudication result in the in-memory claim store.
The request body must conform to the claim ledger schema in
`.specify/memory/data-model.md §5`.

Returns `201` with the stored record on success. Returns `409 CONFLICT` if
`claim_id` is already present in the store.

The record is stored in memory only. No write to `claims.json` or any other
file occurs. The in-memory store update is protected by a `asyncio.Lock`
to prevent race conditions when multiple adjudication services submit claims
simultaneously.

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

Full member record as defined in `.specify/memory/data-model.md §3`. Sample:

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

Full plan record as defined in `.specify/memory/data-model.md §2`.

### GET /fee-schedules/{procedure_code} — Response

Full fee schedule entry as defined in `.specify/memory/data-model.md §4`.

### GET /claims/{claim_id} — Response

Full claim ledger record as defined in `.specify/memory/data-model.md §5`.

### POST /claims — Request

Full claim ledger record as defined in `.specify/memory/data-model.md §5`. The
`claim_id` field must be present and non-empty.

### POST /claims — Response

| HTTP Status | Condition |
|---|---|
| `201` | Record stored in memory successfully; body is the stored record |
| `409` | `claim_id` already exists in the store |
| `422` | Request body is missing required fields |

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
| `claims.json` | Read at startup only | Claim ledger; bootstraps in-memory store; never written to at runtime |

`DATA_DIR` environment variable controls the data directory path; default is
`./data`. The Data Service is the only service that reads from disk. No service
writes to disk at runtime.

---

## Non-functional Requirements

- **Language / framework:** Python 3.11+, FastAPI (constitution: Technology Stack)
- **Startup:** Service must be independently startable; it has no upstream HTTP
  dependencies (it reads only from the local filesystem)
- **`/health` gate:** `start.sh` uses `/health` to gate downstream service
  startups; endpoint must return `200` when all four files are loaded
- **`start.sh` update in scope:** This spec delivers an updated `start.sh` that
  starts the Data Service first and gates all three adjudication services
  (Benefits Determiner, Pricer, Claims Manager) on the Data Service `/health`
  returning `200` before proceeding. The prior startup order (Benefits
  Determiner → Pricer → Claims Manager) is preserved after that gate.
- **Fully in-memory store:** All four collections (members, plans,
  fee_schedules, claims) are loaded from the JSON seed files once at startup
  and held in memory for the lifetime of the process. No data is written to
  disk at runtime. Restarting the service returns it to the seed state.
  There is no hot-reload mechanism.
- **Concurrent write safety:** A `asyncio.Lock` serializes all in-memory
  store writes for `POST /claims`; no two requests may modify the claims
  collection simultaneously
- **Observability:** In addition to startup/shutdown logging (constitution
  minimum), the service logs at INFO level: every `POST /claims` outcome
  (claim ID, HTTP status, and success/failure reason) and every `404` response
  (resource type and requested ID)
- **`claims.json` bootstrap:** If `claims.json` does not exist on startup, the
  service initializes the in-memory claims store as an empty collection and
  starts normally (no file is created on disk)

---

## Edge Cases

| Case | Expected behavior |
|---|---|
| `GET /members/{member_id}` — ID not found | `404` with `{ "detail": "member not found" }` |
| `GET /plans/{plan_id}` — ID not found | `404` with `{ "detail": "plan not found" }` |
| `GET /fee-schedules/{procedure_code}` — code not found | `404` with `{ "detail": "procedure code not found" }` |
| `GET /claims/{claim_id}` — ID not found | `404` with `{ "detail": "claim not found" }` |
| `POST /claims` — `claim_id` already present | `409` with `{ "detail": "claim already exists" }` |
| `claims.json` does not exist on startup | Initialize empty in-memory claims store; log at INFO level; continue normally |
| Reference file (`members.json`, `plans.json`, or `fee_schedules.json`) missing on startup | Log error at CRITICAL level; exit with non-zero status code |

---

## Constraints

- The Data Service is the only service that reads from disk. No other service
  may use `DATA_DIR` or read JSON files directly. (Constitution: Data Layer,
  Decision 0009)
- No service writes to disk at runtime. All four JSON files are read-only seed
  data. This departs from the Pod-Local Constitution principle that `claims.json`
  is the durable claim ledger; Decision 0010 (pending) records the rationale:
  idempotent restarts simplify practicum testing and the claim ledger is
  ephemeral by design for this implementation. (Clarified 2026-09-02)
- No external database, cache, or message broker is introduced. (Constitution:
  Data Layer)
- This service does not implement any adjudication logic. (Constitution:
  Adjudication Flow)
- This spec covers the Data Service only. Changes to any adjudication service
  contract triggered by introducing this service are tracked within each
  respective spec (0001, 0002, 0003), delivered as follow-on specs blocked on
  this spec landing first. Spec 005 ships independently of those follow-on
  updates. (Constitution: Spec Scope; Clarified 2026-09-01)

---

## Acceptance Criteria

1. `GET /members/{member_id}` with a valid ID returns `200` with the full member
   record matching the schema in `.specify/memory/data-model.md §3`.
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
10. After restarting the service, a claim written in the previous session is NOT
    retrievable via `GET /claims/{claim_id}` — confirming that the store is
    in-memory only and returns to seed state on restart.
11. `POST /claims` with a `claim_id` that already exists returns `409`.
12. `GET /health` returns `200` with correct record counts for all four
    collections once all files are loaded.
13. If `claims.json` is absent at startup, the service starts normally and
    `GET /health` returns `"claims": 0`.
14. If any reference file is absent at startup, the service exits with a non-zero
    status code (verified by observing that `start.sh` detects the health check
    failure and does not proceed).

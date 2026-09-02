# HTTP Contract: Data Service

**Base URL**: `http://localhost:8083` (default; `PORT` env var overrides)  
**Date**: 2026-09-02 | **Spec**: [../spec.md](../spec.md)

Internal service — not exposed to external callers.

---

## GET /health

Returns service status and in-memory record counts.

**Response 200**
```json
{
  "status": "UP",
  "members": 200,
  "plans": 5,
  "fee_schedules": 25,
  "claims": 150
}
```
`claims` reflects the current in-memory count and increments with each successful `POST /claims`.

---

## GET /members/{member_id}

Returns the full member record for the given ID.

**Path parameter**: `member_id` — e.g. `MBR-10042`

**Response 200** — full member record per `.specify/memory/data-model.md §3`

**Response 404**
```json
{ "detail": "member not found" }
```

---

## GET /plans/{plan_id}

Returns the full plan record for the given ID.

**Path parameter**: `plan_id` — e.g. `PLN-GOLD-001`

**Response 200** — full plan record per `.specify/memory/data-model.md §2`

**Response 404**
```json
{ "detail": "plan not found" }
```

---

## GET /fee-schedules/{procedure_code}

Returns the fee schedule entry for the given CPT code, covering both
`in_network` and `out_of_network` blocks.

**Path parameter**: `procedure_code` — e.g. `99213`

**Response 200** — full fee schedule entry per `.specify/memory/data-model.md §4`

**Response 404**
```json
{ "detail": "procedure code not found" }
```

---

## GET /claims/{claim_id}

Returns the stored adjudication record for the given claim ID.

**Path parameter**: `claim_id` — e.g. `CLM-20250901-001`

**Response 200** — full claim ledger record per `.specify/memory/data-model.md §5`

**Response 404**
```json
{ "detail": "claim not found" }
```

---

## POST /claims

Stores a new adjudication result in the in-memory claim store.

**Request body** — full claim ledger record per `.specify/memory/data-model.md §5`.
`claim_id` must be present and non-empty.

**Response 201** — stored record (same shape as request body)

**Response 409**
```json
{ "detail": "claim already exists" }
```

**Response 422** — FastAPI default validation error; returned when required
fields are missing from the request body.

---

## Error notes

- All 404 responses use `{ "detail": "<resource> not found" }` where
  `<resource>` is one of `member`, `plan`, `procedure code`, `claim`.
- The service logs every `POST /claims` outcome (claim ID + HTTP status) and
  every 404 response at INFO level.
- If a reference file (`members.json`, `plans.json`, `fee_schedules.json`) is
  absent at startup, the service exits with a non-zero status code and does not
  accept requests. `start.sh` detects the failed `/health` check and halts.

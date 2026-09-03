# Spec: Claim Correction and Re-adjudication — Data Service

**Intake ID:** 0009-claim-re-adjudication
**Pod:** claim-runner
**Pod spec number:** claim-runner/010
**Status:** Allocated
**Constitution references:** Technology Stack, Data Layer, Spec Scope
**Source:** control pod session 2026-09-03
**Decomposed from:** pods/claim-runner/specs/0009-claim-re-adjudication/spec.md

---

## Goal

Add a `PUT /claims/{claim_id}` endpoint to the Data Service that replaces an
existing claim ledger entry with a new record. This is the provider side of the
re-adjudication feature; the Claims Manager orchestration (allow_resubmit flag
and re-adjudication flow) is specified separately in claim-runner/012.

---

## Out of Scope

- Re-adjudication logic — that is Claims Manager's responsibility
  (claim-runner/012)
- Audit trail or history of superseded claim versions
- Reversal of accumulator state from the original adjudication
- Any change to Claims Manager, Benefits Determiner, or Pricer

---

## Functional Requirements

### FR-1 — PUT endpoint to replace a claim record

`PUT /claims/{claim_id}` replaces the stored claim record for the given ID with
the request body. The existing in-memory entry is overwritten atomically.

Returns `200` with the replaced record on success. Returns `404` if `claim_id`
is not found — callers should use `POST /claims` to create new records. Returns
`422` if the request body is missing required fields or if the `claim_id` in the
body does not match the path parameter.

### FR-2 — Health check

`GET /health` on the Data Service continues to return `200`.

---

## Domain Model

### PUT /claims/{claim_id} — Request

Full claim ledger record (same schema as `POST /claims`). The `claim_id` in the
request body must match the path parameter.

### PUT /claims/{claim_id} — Response body (200)

```json
{
  "claim_id": "CLM-20250901-001",
  "member_id": "MBR-10042",
  "status": "PAID",
  "adjudicated_at": "2025-09-02T10:15:00Z",
  "totals": { "..." },
  "denial_reasons": [],
  "errors": [],
  "line_detail": [ { "..." } ]
}
```

The response body is the new stored record, identical to what
`GET /claims/{claim_id}` would return after a successful PUT.

### PUT /claims/{claim_id} — Status codes

| HTTP Status | Condition |
|---|---|
| `200` | Record replaced; body is the new stored record |
| `404` | `claim_id` not found in the in-memory store |
| `422` | Request body is missing required fields or body `claim_id` does not match path |

---

## Non-functional Requirements

- **Language / framework:** Python 3.11+, FastAPI (constitution: Technology Stack)
- **In-memory only:** The PUT operation replaces the in-memory record; no disk
  write occurs (constitution: Data Layer, Decision 0010)
- **Additive change only:** No existing Data Service routes are modified

---

## Edge Cases

| Case | Expected behaviour |
|---|---|
| `claim_id` not found | `404`; caller should use POST for new records |
| Body `claim_id` does not match path | `422` |
| Request body missing required fields | `422` |

---

## Constraints

- Data Service only. Claims Manager orchestration is specified in
  claim-runner/012.
- In-memory only; `claims.json` is not modified at runtime.
  (Constitution: Data Layer, Decision 0010)

---

## Acceptance Criteria

1. `PUT /claims/CLM-20250901-001` with a valid claim body returns `200` with the
   new record; a subsequent `GET /claims/CLM-20250901-001` returns the replaced
   record.

2. `PUT /claims/CLM-DOES-NOT-EXIST` with a valid claim body returns `404`.

3. `PUT /claims/CLM-20250901-001` with a body where `claim_id` is set to a
   different value returns `422`.

4. `GET /health` returns `200` after the new endpoint is deployed.

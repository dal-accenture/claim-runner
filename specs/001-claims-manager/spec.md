# Spec: Claims Manager API

**Intake ID:** 0001-claims-manager  
**Pod:** claim-runner  
**Pod spec number:** claim-runner/001  
**Status:** Ready for allocation  
**Constitution references:** Technology Stack, Adjudication Flow, Data Layer, Spec Scope  
**Source:** `intake/0001-claims-manager.md`

---

## Goal

Implement the Claims Manager as a FastAPI service on port 8080. It is the sole external entry point for claim adjudication. Callers submit one or more professional claims (CMS-1500 / 837P) in a single batch request. For each claim, the service validates the payload, orchestrates calls to the Benefits Determiner and Pricer, composes the adjudication result, writes it to the claim ledger (`claims.json`), and returns the full set of results in submission order.

---

## Out of Scope

- EDI 837P / 837I parsing or format validation
- Prior authorization initiation or tracking
- Payment disbursement
- EOB / 835 ERA generation
- Appeals handling
- Authentication or authorization
- Institutional claims (CMS-1450 / UB-04 / 837I) — permanent exclusion per constitution

---

## Functional Requirements

### FR-1 — Batch claim submission

`POST /claims/batch` accepts a JSON body containing a `claims` array of one or more claim objects. Each claim is adjudicated independently. The response returns one result per claim in the same order as submitted.

A validation failure on one claim does not abort the batch — the service continues adjudicating the remaining claims and returns all results together. Each entry in `results` has a `status` field; callers must check `status` to determine how to handle the entry.

### FR-2 — Per-claim field validation

Before invoking any downstream service, validate each claim for:

| Field | Rule |
|---|---|
| `claim_id` | Non-empty string; unique within the batch; not already present in `claims.json` |
| `member_id` | Non-empty string |
| `provider_id` | Non-empty string |
| `date_of_service` | Valid date, `YYYY-MM-DD` format |
| `claim_lines` | At least one entry |
| `claim_lines[].line_number` | Positive integer; unique within the claim |
| `claim_lines[].procedure_code` | Non-empty string |
| `claim_lines[].units` | Positive integer |
| `claim_lines[].billed_amount` | Positive number |

A claim failing any validation rule returns a per-claim result with `status: "VALIDATION_ERROR"` and an `errors` array containing at least one descriptive message identifying the offending field. The claim is not written to the Data Service.

### FR-3 — Member existence check

Before calling Benefits Determiner, call Data Service `GET /members/{member_id}`. If the Data Service returns 404, the claim is immediately denied with `denial_reason: NOT_ELIGIBLE`. The Pricer is not called. If the Data Service returns 5xx, the batch returns `503 SERVICE_UNAVAILABLE` (same as FR-4's downstream-unavailable rule).

### FR-4 — Orchestration sequence

For each claim that passes validation and member check:

1. Call `POST /benefits/determine` with a JSON body containing `member_id`, `provider_id`, `procedure_codes` (array of all procedure codes in the claim), and `date_of_service`.
2. If all lines are denied by Benefits Determiner, skip the Pricer. Set claim status to `DENIED`.
3. If at least one line is covered, call `POST /price` with `member_id`, `plan_id` (from the Benefits Determiner response), `network_status` (from the Benefits Determiner response), and only the covered claim lines.
4. Merge Pricer line detail with denied lines from Benefits Determiner into a single `line_detail` array, preserving the original claim line order. Denied lines are constructed with all financial fields set to `0.00`, `line_status: "DENIED"`, and `denial_reason` copied from the Benefits Determiner `line_determinations` entry.
5. Determine final status: `PAID` (all lines paid), `DENIED` (all lines denied), `PARTIALLY_PAID` (mix).
6. Sum `totals` across all lines.
7. Call Data Service `POST /claims` to persist the adjudication result.
8. Return the result.

`plan_id` and `network_status` must come from the Benefits Determiner response and must not be re-derived by Claims Manager (constitution: Adjudication Flow).

### FR-5 — Claim retrieval

`GET /claims/{claim_id}` calls Data Service `GET /claims/{claim_id}` and returns the stored adjudication result. Returns `404` if the Data Service returns `404`.

### FR-6 — Health check

`GET /health` returns `200` with `{ "status": "UP" }` when the service is running and able to accept requests.

---

## Domain Model

### Request shape — POST /claims/batch

```json
{
  "claims": [
    {
      "claim_id": "CLM-20250901-001",
      "member_id": "MBR-10042",
      "provider_id": "PRV-90210",
      "date_of_service": "2025-09-01",
      "claim_lines": [
        {
          "line_number": 1,
          "procedure_code": "99213",
          "diagnosis_codes": ["Z00.00"],
          "units": 1,
          "billed_amount": 250.00
        }
      ]
    }
  ]
}
```

`diagnosis_codes` is accepted but not evaluated in this implementation.

### Response shape — POST /claims/batch

```json
{
  "results": [
    {
      "claim_id": "CLM-20250901-001",
      "status": "PAID",
      "adjudicated_at": "2025-09-01T14:30:01Z",
      "totals": {
        "billed_amount": 250.00,
        "allowed_amount": 115.00,
        "member_liability": 30.00,
        "payer_liability": 85.00
      },
      "denial_reasons": [],
      "line_detail": [
        {
          "line_number": 1,
          "procedure_code": "99213",
          "billed_amount": 250.00,
          "allowed_amount": 115.00,
          "deductible_applied": 0.00,
          "copay_applied": 30.00,
          "coinsurance_applied": 0.00,
          "member_liability": 30.00,
          "payer_liability": 85.00,
          "adjustment_reason_code": "CO-45",
          "denial_reason": null,
          "line_status": "PAID"
        }
      ]
    }
  ]
}
```

A denied line (from Benefits Determiner) has all financial fields set to `0.00` and `denial_reason` populated:

```json
{
  "line_number": 2,
  "procedure_code": "42820",
  "billed_amount": 4200.00,
  "allowed_amount": 0.00,
  "deductible_applied": 0.00,
  "copay_applied": 0.00,
  "coinsurance_applied": 0.00,
  "member_liability": 0.00,
  "payer_liability": 0.00,
  "adjustment_reason_code": null,
  "denial_reason": "AUTH_REQUIRED_NOT_ON_FILE",
  "line_status": "DENIED"
}
```

A validation-error or conflict result has a minimal envelope — fields that don't apply are `null` or empty:

```json
{
  "claim_id": "CLM-20250901-002",
  "status": "VALIDATION_ERROR",
  "adjudicated_at": null,
  "totals": null,
  "denial_reasons": [],
  "errors": ["claim_lines: at least one entry required"],
  "line_detail": []
}
```

For a duplicate `claim_id` already in the Data Service ledger, `status` is `"CONFLICT"` and `errors` contains one entry: `"claim_id already exists"`.

The response shape for `GET /claims/{claim_id}` is identical to a single adjudicated entry in the `results` array (never an error entry).

### Claim status lifecycle

| Condition | Status |
|---|---|
| All lines paid | `PAID` |
| All lines denied | `DENIED` |
| Mix of paid and denied lines | `PARTIALLY_PAID` |

### Denial reasons (claim-level, set by Claims Manager)

| Code | Trigger |
|---|---|
| `NOT_ELIGIBLE` | Member not found in Data Service (`GET /members/{id}` returned 404) |
| `SERVICE_UNAVAILABLE` | Benefits Determiner or Pricer returned 5xx |

Line-level denial reasons (`NOT_COVERED`, `AUTH_REQUIRED_NOT_ON_FILE`, etc.) are passed through from the Benefits Determiner response.

---

## Integration

### Downstream: Benefits Determiner

```
POST http://${BENEFITS_DETERMINER_URL}/benefits/determine
Content-Type: application/json

{
  "member_id": "MBR-10042",
  "provider_id": "PRV-90210",
  "procedure_codes": ["99213", "42820"],
  "date_of_service": "2025-09-01"
}
```

`BENEFITS_DETERMINER_URL` defaults to `http://localhost:8081`.

### Downstream: Pricer

```
POST http://${PRICER_URL}/price
{
  "claim_id": "...",
  "member_id": "...",
  "plan_id": "...",       ← from Benefits Determiner response
  "network_status": "...", ← from Benefits Determiner response
  "claim_lines": [...]    ← covered lines only
}
```

`PRICER_URL` defaults to `http://localhost:8082`.

### Data Service

All data access goes through the Data Service (constitution: Data Layer). Claims Manager accesses no files in `data/` directly.

| Operation | Data Service call |
|---|---|
| Member existence check | `GET /members/{member_id}` |
| Persist adjudicated claim | `POST /claims` |
| Retrieve adjudicated claim | `GET /claims/{claim_id}` |

`DATA_SERVICE_URL` environment variable controls the Data Service base URL; default is `http://localhost:8083`.

### Architecture note

`exposed-api.md` in `pods/claim-runner/architecture/` documents `POST /claims` (singular). This spec supersedes that with `POST /claims/batch`. That document should be updated at implementation time.

---

## Non-functional Requirements

- **Language / framework:** Python 3.11+, FastAPI (constitution: Technology Stack)
- **Startup:** Service must be independently startable without Benefits Determiner or Pricer running
- **`/health` gate:** `start.sh` uses `/health` to sequence startup; endpoint must return 200 when data files are loaded
- **Batch ordering:** Results must be returned in the same order claims were submitted
- **Atomicity per claim:** A claim that fails validation or member check is excluded from the ledger; no partial writes

---

## Edge Cases

| Case | Expected behavior |
|---|---|
| Batch of one claim | Behaves identically to a multi-claim batch |
| One claim in batch fails validation | That claim returns a 400 result; others proceed normally |
| Duplicate `claim_id` within the same batch | Second occurrence returns `status: "VALIDATION_ERROR"` with error `"claim_id duplicate within batch"`; first proceeds normally |
| `claim_id` already persisted in Data Service | Returns `status: "CONFLICT"`; claim not re-adjudicated |
| Benefits Determiner returns 5xx | Entire batch request returns `503 SERVICE_UNAVAILABLE`; no claims written to ledger |
| Pricer returns 5xx | Entire batch request returns `503 SERVICE_UNAVAILABLE`; no claims written to ledger |
| All lines of a claim are denied by Benefits Determiner | Pricer not called; claim written to ledger as DENIED |
| Exactly one line covered, rest denied | Pricer called with covered line only; result is PARTIALLY_PAID |
| Data Service unreachable on member check | Same 503 behavior as Benefits Determiner / Pricer 5xx — no claims written |

---

## Constraints

- Claims Manager is the sole orchestrator. Benefits Determiner and Pricer do not call each other or call Claims Manager. (Constitution: Adjudication Flow)
- `plan_id` and `network_status` are forwarded from the Benefits Determiner response, not re-derived. (Constitution: Adjudication Flow)
- Claims Manager accesses no files in `data/` directly. All data access (member lookup, claim persistence, claim retrieval) is via HTTP calls to the Data Service. (Constitution: Data Layer)
- No spec may add institutional claim support. (Constitution: Claim Type)
- This spec covers Claims Manager only. Any change to Benefits Determiner or Pricer contracts triggered by this work requires a separate spec. (Constitution: Spec Scope, Decision 0001)

---

## Clarifications

### Session 2026-09-03

- Q: Should Claims Manager call Benefits Determiner via GET with CSV query params or POST with a JSON body and array `procedure_codes`? → A: POST with JSON body, `procedure_codes` as array — per the spec 002 contract, which is the authoritative interface definition.
- Q: Should Claims Manager access `members.json` and `claims.json` directly or via Data Service HTTP calls? → A: Via Data Service HTTP calls (`GET /members/{id}`, `POST /claims`, `GET /claims/{id}`) — constitution v1.1 Data Layer principle governs; direct file access is not permitted for any service except the Data Service.
- Q: What does a denied line entry look like in the merged `line_detail` array? → A: All financial fields set to `0.00`, `line_status: "DENIED"`, `denial_reason` copied from the Benefits Determiner response, `adjustment_reason_code: null`; `billed_amount` carries the original submitted amount.
- Q: What does a per-claim validation error or conflict result look like in the `results` array? → A: `{"claim_id": "...", "status": "VALIDATION_ERROR", "adjudicated_at": null, "totals": null, "denial_reasons": [], "errors": ["..."], "line_detail": []}`. Conflict results use `status: "CONFLICT"`. `adjudicated_at` is set by Claims Manager at adjudication time as a UTC ISO 8601 string; null for non-adjudicated results.

---

## Acceptance Criteria

1. A batch containing one valid in-network claim returns a single result with status `PAID` and a correct `line_detail` entry including `copay_applied`, `deductible_applied`, and `adjustment_reason_code`.
2. A batch containing multiple claims returns one result per claim in submission order.
3. A claim with an unknown `member_id` is denied with `NOT_ELIGIBLE` and the Pricer is not called (verified by absence of Pricer call in logs or mock).
4. A claim with one covered and one non-covered procedure returns status `PARTIALLY_PAID` with per-line `line_status` values of `PAID` and `DENIED` respectively.
5. A fully denied claim (all lines denied by Benefits Determiner) returns status `DENIED` and the Pricer is not called.
6. Every successfully adjudicated claim is retrievable via `GET /claims/{claim_id}` and returns the same shape as the original POST response entry.
7. `GET /claims/{claim_id}` returns `404` for an unknown `claim_id`.
8. A claim with a missing required field returns a per-claim result with `status: "VALIDATION_ERROR"` and an `errors` entry naming the offending field.
9. A batch where one claim fails validation still processes and returns results for all other claims.
10. A `claim_id` submitted a second time (already persisted in the Data Service) returns a per-claim result with `status: "CONFLICT"`.
11. `GET /health` returns `200` with `{ "status": "UP" }`.
12. When Benefits Determiner is unreachable, the batch returns `503` and no claims are persisted to the Data Service.

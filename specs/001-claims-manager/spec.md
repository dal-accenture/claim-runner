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

A validation failure on one claim does not abort the batch — the service continues adjudicating the remaining claims and returns all results together.

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

A claim failing any validation rule returns a per-claim `400` result with at least one descriptive error message identifying the offending field. The claim is not written to the ledger.

### FR-3 — Member existence check

Before calling Benefits Determiner, verify `member_id` exists in `members.json`. If not found, the claim is immediately denied with `denial_reason: NOT_ELIGIBLE`. The Pricer is not called.

### FR-4 — Orchestration sequence

For each claim that passes validation and member check:

1. Call `GET /benefits/determine` with `member_id`, `provider_id`, `procedure_codes` (CSV of all procedure codes in the claim), and `date_of_service`.
2. If all lines are denied by Benefits Determiner, skip the Pricer. Set claim status to `DENIED`.
3. If at least one line is covered, call `POST /price` with `member_id`, `plan_id` (from the Benefits Determiner response), `network_status` (from the Benefits Determiner response), and only the covered claim lines.
4. Merge Pricer line detail with denied lines from Benefits Determiner into a single `line_detail` array.
5. Determine final status: `PAID` (all lines paid), `DENIED` (all lines denied), `PARTIALLY_PAID` (mix).
6. Sum `totals` across all lines.
7. Write the adjudication result to `claims.json`.
8. Return the result.

`plan_id` and `network_status` must come from the Benefits Determiner response and must not be re-derived by Claims Manager (constitution: Adjudication Flow).

### FR-5 — Claim retrieval

`GET /claims/{claim_id}` returns the stored adjudication result for a previously adjudicated claim. The result is read from `claims.json`. Returns `404` if not found.

### FR-6 — Health check

`GET /health` returns `200` with `{ "status": "UP", "members_loaded": <count> }` when the service is running and `members.json` is loaded.

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
          "line_status": "PAID"
        }
      ]
    }
  ]
}
```

The response shape for `GET /claims/{claim_id}` is identical to a single entry in the `results` array.

### Claim status lifecycle

| Condition | Status |
|---|---|
| All lines paid | `PAID` |
| All lines denied | `DENIED` |
| Mix of paid and denied lines | `PARTIALLY_PAID` |

### Denial reasons (claim-level, set by Claims Manager)

| Code | Trigger |
|---|---|
| `NOT_ELIGIBLE` | Member not found in `members.json` |
| `SERVICE_UNAVAILABLE` | Benefits Determiner or Pricer returned 5xx |

Line-level denial reasons (`NOT_COVERED`, `AUTH_REQUIRED_NOT_ON_FILE`, etc.) are passed through from the Benefits Determiner response.

---

## Integration

### Downstream: Benefits Determiner

```
GET http://${BENEFITS_DETERMINER_URL}/benefits/determine
  ?member_id=MBR-10042
  &provider_id=PRV-90210
  &procedure_codes=99213,42820
  &date_of_service=2025-09-01
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

### Data files loaded at startup

| File | Access | Purpose |
|---|---|---|
| `members.json` | Read | Member existence check |
| `claims.json` | Read + Write | Ledger — loaded at startup; appended after each adjudication |

`DATA_DIR` environment variable controls the data directory path; default is `./data`.

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
| Duplicate `claim_id` within the same batch | Second occurrence returns `400 DUPLICATE_CLAIM_ID`; first proceeds normally |
| `claim_id` already present in `claims.json` | Returns `409 CONFLICT`; claim not re-adjudicated |
| Benefits Determiner returns 5xx | Entire batch request returns `503 SERVICE_UNAVAILABLE`; no claims written to ledger |
| Pricer returns 5xx | Entire batch request returns `503 SERVICE_UNAVAILABLE`; no claims written to ledger |
| All lines of a claim are denied by Benefits Determiner | Pricer not called; claim written to ledger as DENIED |
| Exactly one line covered, rest denied | Pricer called with covered line only; result is PARTIALLY_PAID |
| `claims.json` does not exist on startup | Service creates an empty ledger file (`[]`) and starts normally |

---

## Constraints

- Claims Manager is the sole orchestrator. Benefits Determiner and Pricer do not call each other or call Claims Manager. (Constitution: Adjudication Flow)
- `plan_id` and `network_status` are forwarded from the Benefits Determiner response, not re-derived. (Constitution: Adjudication Flow)
- `claims.json` is the only data file this service writes to. `members.json` is read-only. (Constitution: Data Layer)
- No spec may add institutional claim support. (Constitution: Claim Type)
- This spec covers Claims Manager only. Any change to Benefits Determiner or Pricer contracts triggered by this work requires a separate spec. (Constitution: Spec Scope, Decision 0001)

---

## Acceptance Criteria

1. A batch containing one valid in-network claim returns a single result with status `PAID` and a correct `line_detail` entry including `copay_applied`, `deductible_applied`, and `adjustment_reason_code`.
2. A batch containing multiple claims returns one result per claim in submission order.
3. A claim with an unknown `member_id` is denied with `NOT_ELIGIBLE` and the Pricer is not called (verified by absence of Pricer call in logs or mock).
4. A claim with one covered and one non-covered procedure returns status `PARTIALLY_PAID` with per-line `line_status` values of `PAID` and `DENIED` respectively.
5. A fully denied claim (all lines denied by Benefits Determiner) returns status `DENIED` and the Pricer is not called.
6. Every successfully adjudicated claim is retrievable via `GET /claims/{claim_id}` and returns the same shape as the original POST response entry.
7. `GET /claims/{claim_id}` returns `404` for an unknown `claim_id`.
8. A claim with a missing required field returns a per-claim `400` result with a descriptive message naming the offending field.
9. A batch where one claim fails validation still processes and returns results for all other claims.
10. A `claim_id` submitted a second time (already in the ledger) returns `409 CONFLICT`.
11. `GET /health` returns `200` with `members_loaded` equal to the count of records in `members.json`.
12. When Benefits Determiner is unreachable, the batch returns `503` and no claims are written to `claims.json`.

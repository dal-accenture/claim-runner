# Data Model: Claims Manager

**Spec**: 001-claims-manager

---

## Entities

### ClaimLine (request)

Represents a single service line within a submitted claim.

| Field | Type | Validation |
|---|---|---|
| `line_number` | `int` | Positive integer; unique within the claim |
| `procedure_code` | `str` | Non-empty string |
| `diagnosis_codes` | `list[str]` | Optional; accepted but not evaluated |
| `units` | `int` | Positive integer |
| `billed_amount` | `Decimal` | Positive number |

### ClaimRequest (item in batch)

One professional claim submitted for adjudication.

| Field | Type | Validation |
|---|---|---|
| `claim_id` | `str` | Non-empty; unique within the batch; not already in Data Service |
| `member_id` | `str` | Non-empty string |
| `provider_id` | `str` | Non-empty string |
| `date_of_service` | `date` | Valid date, `YYYY-MM-DD` format |
| `claim_lines` | `list[ClaimLine]` | At least one entry |

### BatchRequest

Top-level request body for `POST /claims/batch`.

| Field | Type | Validation |
|---|---|---|
| `claims` | `list[ClaimRequest]` | At least one entry |

---

### LineDetailEntry (per-line result)

Present in every AdjudicationResult regardless of line status.

| Field | Type | Notes |
|---|---|---|
| `line_number` | `int` | From original claim |
| `procedure_code` | `str` | From original claim |
| `billed_amount` | `Decimal` | `billed_amount × units` from original claim |
| `allowed_amount` | `Decimal` | From Pricer; `0.00` for denied lines |
| `contractual_adjustment` | `Decimal` | From Pricer; `0.00` for denied lines |
| `deductible_applied` | `Decimal` | From Pricer; `0.00` for denied lines |
| `copay_applied` | `Decimal` | From Pricer; `0.00` for denied lines |
| `coinsurance_applied` | `Decimal` | From Pricer; `0.00` for denied lines |
| `member_liability` | `Decimal` | From Pricer; `0.00` for denied lines |
| `payer_liability` | `Decimal` | From Pricer; `0.00` for denied lines |
| `adjustment_reason_code` | `str \| null` | From Pricer; `null` for denied lines |
| `denial_reason` | `str \| null` | From BD `line_determinations`; `null` for paid lines |
| `line_status` | `"PAID" \| "DENIED"` | |

### ClaimTotals

Summed financials across all lines in a claim. `null` for non-adjudicated results (VALIDATION_ERROR, CONFLICT).

| Field | Type | Notes |
|---|---|---|
| `billed_amount` | `Decimal` | Sum of all lines' `billed_amount × units` |
| `allowed_amount` | `Decimal` | Sum across all lines; `0.00` for fully-denied claims |
| `member_liability` | `Decimal` | Sum across all lines |
| `payer_liability` | `Decimal` | Sum across all lines |

### AdjudicationResult (per-claim result in batch response)

| Field | Type | Notes |
|---|---|---|
| `claim_id` | `str` | From original claim |
| `status` | `str` | `PAID`, `DENIED`, `PARTIALLY_PAID`, `VALIDATION_ERROR`, `CONFLICT` |
| `adjudicated_at` | `datetime \| null` | UTC ISO 8601; set by Claims Manager; `null` for non-adjudicated results |
| `totals` | `ClaimTotals \| null` | `null` for VALIDATION_ERROR, CONFLICT |
| `denial_reasons` | `list[str]` | Claim-level denial codes (`NOT_ELIGIBLE`, `SERVICE_UNAVAILABLE`); empty for success |
| `errors` | `list[str]` | Field-level error messages for VALIDATION_ERROR / CONFLICT; empty for adjudicated results |
| `line_detail` | `list[LineDetailEntry]` | Empty for VALIDATION_ERROR, CONFLICT, NOT_ELIGIBLE denials |

### BatchResponse

| Field | Type | Notes |
|---|---|---|
| `results` | `list[AdjudicationResult]` | One per submitted claim, in submission order |

---

## Status Lifecycle

```
Submitted claim
    │
    ├─── Validation fails ──────────────► VALIDATION_ERROR (not written to Data Service)
    │
    ├─── claim_id already in DS ────────► CONFLICT (not written to Data Service)
    │
    ├─── Member not found (DS 404) ─────► DENIED / NOT_ELIGIBLE (written to Data Service)
    │
    └─── Adjudication proceeds
             │
             ├─── All lines denied (BD) ──► DENIED (written to Data Service)
             │
             ├─── Some lines denied ──────► PARTIALLY_PAID (written to Data Service)
             │
             └─── All lines paid ─────────► PAID (written to Data Service)
```

Any downstream 5xx at any point → batch-level 503, no claims written.

---

## Claim-Level Denial Reason Codes

| Code | Trigger |
|---|---|
| `NOT_ELIGIBLE` | Data Service returns 404 on `GET /members/{id}` |
| `SERVICE_UNAVAILABLE` | BD, Pricer, or Data Service returns 5xx |

Line-level denial reason codes (`NOT_COVERED`, `AUTH_REQUIRED_NOT_ON_FILE`, `PLAN_TERMINATED`) come from Benefits Determiner `line_determinations` and are passed through unchanged.

---

## Relationships

```
BatchRequest
  └── 1..* ClaimRequest
              └── 1..* ClaimLine

BatchResponse
  └── 1..* AdjudicationResult  (1:1 with ClaimRequest, same order)
              └── 0..* LineDetailEntry  (1:1 with ClaimLine for adjudicated results)
```

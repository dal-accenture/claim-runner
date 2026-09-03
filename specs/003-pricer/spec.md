# Spec: Pricer API

**Intake ID:** 0003-pricer  
**Pod:** claim-runner  
**Pod spec number:** claim-runner/003  
**Status:** Ready for allocation  
**Constitution references:** Technology Stack, Service Independence, Data Layer, Adjudication Flow, Spec Scope  
**Source:** `intake/0003-pricer.md`

---

## Goal

Implement the Pricer as a FastAPI service on port 8082. Given a member, a plan, a network status, and a list of covered procedure codes, it calculates the allowed amount for each line, applies the member's cost-sharing obligations in the prescribed order (deductible, copay, coinsurance), enforces the out-of-pocket maximum, and returns a complete per-line financial breakdown plus claim-level totals. The service also returns an accumulator snapshot showing before/after balances for informational and audit purposes; it does not write back to `members.json`.

---

## Clarifications

### Session 2026-09-02

- Q: Should the Pricer load `members.json`, `fee_schedules.json`, and `plans.json` directly from disk at startup, or call the Data Service via HTTP for those lookups? → A: HTTP calls to Data Service — `GET /members/{member_id}`, `GET /plans/{plan_id}`, `GET /fee-schedules/{procedure_code}`; configured via `DATA_SERVICE_URL` env var. Constitution v1.1 prohibits direct file access by adjudication services.
- Q: When a single claim has multiple lines, should deductible consumption from earlier lines be tracked in a running counter (so later lines see the reduced remaining deductible), or should each line read `individual_deductible.used` from the seeded record independently? → A: Running counter — `deductible_used_this_claim` accumulates across lines exactly as `oop_used_this_claim` does; each subsequent line sees the reduced remaining deductible.
- Q: When pricing a multi-unit line (`units: 2`), should the allowed amount be `fee_schedule_rate × units`, or is `units` informational only and `billed_amount` already reflects quantity? → A: Multiply by units — both `billed_amount` and `fee_schedule_rate` are per-unit; line totals are `× units`. `allowed_amount = min(billed_amount, fee_schedule_rate) × units`.
- Q: If the Data Service is unreachable when the Pricer calls `GET /members/{id}`, `GET /plans/{id}`, or `GET /fee-schedules/{code}` mid-request, what should the service return to Claims Manager? → A: `503 Service Unavailable` with `{"detail": "Data Service unavailable"}` — explicit connectivity signal, consistent with Benefits Determiner.

---

## Out of Scope

- Coverage or eligibility determination — that is Benefits Determiner's responsibility
- Coordination of Benefits (COB) across multiple plans
- Pharmacy or DME pricing
- Accumulator write-back to `members.json` — read-only (constitution: Data Layer)
- Payment disbursement
- Institutional claims

---

## Functional Requirements

### FR-1 — Allowed amount calculation (per line)

Call `GET /fee-schedules/{procedure_code}` on the Data Service. If the response is `404`, return `422` with the unrecognized code identified in the error body. Select `in_network.allowed_amount` or `out_of_network.allowed_amount` based on `network_status`.

Both `billed_amount` and `fee_schedule_rate` are per-unit; multiply by `units` to get line totals:
- `line_billed = billed_amount × units`
- `line_fee_schedule_rate = fee_schedule_rate × units`
- `allowed_amount = min(line_billed, line_fee_schedule_rate)`
- `contractual_adjustment = line_billed - allowed_amount` (reason code: `CO-45`)

### FR-2 — Cost-sharing application (per line)

Apply in the following order. Two running counters accumulate across all lines in the request:
- `oop_used_this_claim` — tracks total member liability applied so far (for OOP cap enforcement)
- `deductible_used_this_claim` — tracks total deductible applied so far (so later lines see the reduced remaining deductible)

**Step 1 — OOP max pre-check**  
If `member.individual_oop_max.met = true` (or accumulated `oop_used` already meets the limit), set `member_liability = 0.00` and `payer_liability = allowed_amount` for this line. Skip remaining steps.

**Step 2 — Copay (before deductible)**  
If `fee_schedules.copay_applies_before_deductible = true` for this code and network status, apply the copay. Advance `oop_used_this_claim` by `copay_applied`.

**Step 3 — Deductible**  
`remaining_deductible = individual_deductible.limit - (individual_deductible.used + deductible_used_this_claim)`.  
`balance_after_copay = allowed_amount - copay_applied`.  
`deductible_applied = min(balance_after_copay, max(0, remaining_deductible))`.  
Advance `deductible_used_this_claim` by `deductible_applied`.  
Advance `oop_used_this_claim` by `deductible_applied`.

**Step 4 — Copay (after deductible)**  
If `copay_applies_before_deductible = false`, apply the copay now. Advance `oop_used_this_claim`.

**Step 5 — Coinsurance**  
`coinsurance_base = allowed_amount - copay_applied - deductible_applied`.  
`coinsurance_applied = coinsurance_base × coinsurance_pct`.  
Advance `oop_used_this_claim`.

**Step 6 — OOP max enforcement**  
`oop_available = individual_oop_max.limit - (individual_oop_max.used + oop_used_this_claim_before_this_line)`.  
If `member_liability_this_line > oop_available`, cap member liability at `oop_available`; payer absorbs the remainder.  
Add final member liability to `oop_used_this_claim`.

**Step 7 — Payer liability**  
`payer_liability = allowed_amount - member_liability`.

### FR-3 — Claim-level totals

Sum `billed_amount`, `allowed_amount`, `member_liability`, and `payer_liability` across all lines.

### FR-4 — Accumulator snapshot

Include an `accumulator_snapshot` in the response with before/after values for deductible and OOP. "Before" values come directly from `members.json`. "After" values are the projected balances if this claim's charges were applied. These are informational only and are not persisted.

### FR-5 — Health check

`GET /health` returns `200` when the service is running. No Data Service reachability check is required at startup — the service starts independently and fails individual requests if the Data Service is unavailable.

---

## Domain Model

### Endpoint

```
POST /price
```

### Request

```json
{
  "claim_id": "CLM-20250901-001",
  "member_id": "MBR-10042",
  "plan_id": "PLN-GOLD-001",
  "network_status": "IN_NETWORK",
  "claim_lines": [
    {
      "line_number": 1,
      "procedure_code": "99213",
      "units": 1,
      "billed_amount": 250.00
    }
  ]
}
```

### Request field rules

| Field | Required | Validation |
|---|---|---|
| `claim_id` | Yes | Non-empty string |
| `member_id` | Yes | Must exist in `members.json` |
| `plan_id` | Yes | Must exist in `plans.json` |
| `network_status` | Yes | `IN_NETWORK` or `OUT_OF_NETWORK` |
| `claim_lines` | Yes | At least one line |
| `claim_lines[].procedure_code` | Yes | Must exist in `fee_schedules.json`; returns `422` if not found |
| `claim_lines[].units` | Yes | Positive integer; line totals are `per-unit value × units` |
| `claim_lines[].billed_amount` | Yes | Positive number; per-unit charged amount |

### Response

```json
{
  "claim_id": "CLM-20250901-001",
  "totals": {
    "billed_amount": 250.00,
    "allowed_amount": 115.00,
    "member_liability": 30.00,
    "payer_liability": 85.00
  },
  "accumulator_snapshot": {
    "individual_deductible_used_before": 125.00,
    "individual_deductible_used_after":  125.00,
    "individual_oop_used_before": 155.00,
    "individual_oop_used_after":  185.00
  },
  "line_detail": [
    {
      "line_number": 1,
      "procedure_code": "99213",
      "billed_amount": 250.00,
      "allowed_amount": 115.00,
      "contractual_adjustment": 135.00,
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
```

### Adjustment reason codes

| Code | When applied |
|---|---|
| `CO-45` | Billed amount exceeds fee schedule allowed amount (contractual obligation) |
| `PR-1` | Deductible amount applied |
| `PR-2` | Coinsurance amount applied |
| `PR-3` | Copay amount applied |

`CO-96` (non-covered charge) is applied by Claims Manager for denied lines; the Pricer does not use it.

---

## Worked examples

### In-network GP office visit — copay before deductible, coinsurance 0%

| Item | Value |
|---|---|
| Billed amount | $250.00 |
| Allowed amount (fee schedule 99213 in-network) | $115.00 |
| Contractual adjustment (`CO-45`) | $135.00 |
| Copay (before deductible) | $30.00 |
| Deductible applied | $0.00 (copay-only rule; coinsurance 0%) |
| Coinsurance (0%) | $0.00 |
| **Member liability** | **$30.00** |
| **Payer liability** | **$85.00** |

### In-network surgical procedure — deductible partially met, coinsurance 10%

| Item | Value |
|---|---|
| Billed amount | $4,200.00 |
| Allowed amount (fee schedule 42820 in-network) | $2,800.00 |
| Contractual adjustment | $1,400.00 |
| Copay | $0.00 |
| Remaining deductible | $375.00 |
| Deductible applied | $375.00 |
| Balance after deductible | $2,425.00 |
| Coinsurance (10%) | $242.50 |
| **Member liability** | **$617.50** |
| **Payer liability** | **$2,182.50** |

---

## Integration

### Called by

Claims Manager only. Called with covered claim lines only (lines denied by Benefits Determiner are excluded from the Pricer request).

### Data Service calls

| Endpoint | When called | Fields used |
|---|---|---|
| `GET /members/{member_id}` | FR-2 accumulator lookup | `accumulators.individual_deductible`, `accumulators.individual_oop_max` |
| `GET /plans/{plan_id}` | FR-2 plan validation | `plan_id` (existence check only; cost-sharing rules come from fee schedules) |
| `GET /fee-schedules/{procedure_code}` | FR-1 allowed amount | `in_network`, `out_of_network`, `copay_applies_before_deductible` |

`DATA_SERVICE_URL` environment variable sets the Data Service base URL; default is `http://localhost:8083`.

---

## Non-functional Requirements

- **Language / framework:** Python 3.11+, FastAPI (constitution: Technology Stack)
- **Startup:** Service must be independently startable without Claims Manager or Benefits Determiner running
- **`/health` gate:** Must return `200` when the service is running; does not require Data Service to be reachable at startup
- **Data access:** All member, plan, and fee schedule lookups via HTTP calls to Data Service (`DATA_SERVICE_URL`); no direct file access (constitution v1.1: Data Layer)
- **Data Service error handling:** Any connection error or unexpected HTTP status from the Data Service returns `503 Service Unavailable` with `{"detail": "Data Service unavailable"}` to the caller
- **Pure read:** No writes to any data file (constitution: Data Layer)
- **Multi-line OOP enforcement:** The OOP cap must be enforced across lines within a single request, not just per-line independently

---

## Edge Cases

| Case | Expected behavior |
|---|---|
| Member's deductible already fully met | `deductible_applied = 0.00`; coinsurance applied to full allowed amount |
| Multi-line claim, deductible consumed on line 1 | Line 2 sees reduced remaining deductible via `deductible_used_this_claim` running counter |
| Member's OOP max already met (`met: true` in `members.json`) | `member_liability = 0.00` for all lines; payer absorbs 100% |
| OOP max hit partway through a multi-line claim | Line that crosses the threshold is capped; all subsequent lines have `member_liability = 0.00` |
| Out-of-network procedure | Uses `out_of_network.allowed_amount` and `out_of_network.coinsurance_pct` |
| Billed amount below allowed amount | `allowed_amount = billed_amount`; contractual adjustment = $0.00 |
| Procedure code not in `fee_schedules.json` | Returns `422` with the unrecognized code identified in the error body |
| `member_id` not in `members.json` | Returns `404` |
| `plan_id` not in `plans.json` | Returns `404` |
| Data Service unreachable during any lookup | `503 Service Unavailable` with `{"detail": "Data Service unavailable"}` |

---

## Constraints

- This service does not call Claims Manager or Benefits Determiner. (Constitution: Adjudication Flow)
- Accumulator write-back to `members.json` is explicitly out of scope. (Constitution: Data Layer)
- No data file writes permitted. (Constitution: Data Layer)
- No spec may add institutional claim support. (Constitution: Claim Type)
- This spec covers Pricer only. Changes to Claims Manager or Benefits Determiner contracts are a separate spec. (Constitution: Spec Scope, Decision 0001)

---

## Acceptance Criteria

1. A covered in-network GP office visit with a copay-before-deductible rule returns the copay amount as member liability and `allowed_amount - copay` as payer liability.
2. A covered in-network surgical procedure with coinsurance returns correct deductible and coinsurance splits; payer liability equals `allowed_amount - member_liability`.
3. When a member's deductible is already met (`met: true`), no deductible is applied and coinsurance is calculated on the full allowed amount.
4. When a member's OOP maximum is already met (`met: true`), member liability is `$0.00` and payer liability equals the full allowed amount.
5. On a multi-line claim where the OOP max is hit partway through, the line crossing the threshold has member liability capped at the remaining OOP headroom, and all subsequent lines have `member_liability = 0.00`.
6. An out-of-network procedure uses the `out_of_network` allowed amount and coinsurance rate from `fee_schedules.json`.
7. A procedure code not present in `fee_schedules.json` returns `422` with the unrecognized code identified in the error response.
8. `accumulator_snapshot.individual_deductible_used_before` matches the `used` value seeded in `members.json`; `_after` reflects the projected balance after this claim's deductible charges.
9. `totals.member_liability + totals.payer_liability = totals.allowed_amount` for every response.
10. `CO-45` adjustment reason code is present on any line where `billed_amount > allowed_amount`.
11. `GET /health` returns `200` when the service is running.
12. A Data Service connection error during a pricing request returns `503 Service Unavailable` with `{"detail": "Data Service unavailable"}`.

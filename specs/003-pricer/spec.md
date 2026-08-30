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

Look up `procedure_code` in `fee_schedules.json`. Select `in_network.allowed_amount` or `out_of_network.allowed_amount` based on `network_status`. The allowed amount is `min(billed_amount, fee_schedule_rate)`. The contractual adjustment is `billed_amount - allowed_amount` (reason code: `CO-45`).

### FR-2 — Cost-sharing application (per line)

Apply in the following order. A running `oop_used_this_claim` counter accumulates member liability across lines to enforce the OOP cap correctly on multi-line claims.

**Step 1 — OOP max pre-check**  
If `member.individual_oop_max.met = true` (or accumulated `oop_used` already meets the limit), set `member_liability = 0.00` and `payer_liability = allowed_amount` for this line. Skip remaining steps.

**Step 2 — Copay (before deductible)**  
If `fee_schedules.copay_applies_before_deductible = true` for this code and network status, apply the copay. Advance `oop_used_this_claim` by `copay_applied`.

**Step 3 — Deductible**  
`remaining_deductible = individual_deductible.limit - individual_deductible.used`.  
`balance_after_copay = allowed_amount - copay_applied`.  
`deductible_applied = min(balance_after_copay, remaining_deductible)`.  
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

`GET /health` returns `200` when the service is running and data files are loaded.

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
| `claim_lines[].units` | Yes | Positive integer |
| `claim_lines[].billed_amount` | Yes | Positive number |

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

### Data files loaded at startup

| File | Access | Fields used |
|---|---|---|
| `fee_schedules.json` | Read | `procedure_code`, `in_network`, `out_of_network`, `copay_applies_before_deductible` |
| `members.json` | Read | `member_id`, `accumulators.individual_deductible`, `accumulators.individual_oop_max` |
| `plans.json` | Read | `plan_id` — used to validate the incoming `plan_id`; cost-sharing rules come from `fee_schedules.json` |

`DATA_DIR` environment variable controls the data directory path; default is `./data`.

---

## Non-functional Requirements

- **Language / framework:** Python 3.11+, FastAPI (constitution: Technology Stack)
- **Startup:** Service must be independently startable without Claims Manager or Benefits Determiner running
- **`/health` gate:** Must return `200` when all three data files are successfully loaded
- **Pure read:** No writes to any data file (constitution: Data Layer)
- **Multi-line OOP enforcement:** The OOP cap must be enforced across lines within a single request, not just per-line independently

---

## Edge Cases

| Case | Expected behavior |
|---|---|
| Member's deductible already fully met | `deductible_applied = 0.00`; coinsurance applied to full allowed amount |
| Member's OOP max already met (`met: true` in `members.json`) | `member_liability = 0.00` for all lines; payer absorbs 100% |
| OOP max hit partway through a multi-line claim | Line that crosses the threshold is capped; all subsequent lines have `member_liability = 0.00` |
| Out-of-network procedure | Uses `out_of_network.allowed_amount` and `out_of_network.coinsurance_pct` |
| Billed amount below allowed amount | `allowed_amount = billed_amount`; contractual adjustment = $0.00 |
| Procedure code not in `fee_schedules.json` | Returns `422` with the unrecognized code identified in the error body |
| `member_id` not in `members.json` | Returns `404` |
| `plan_id` not in `plans.json` | Returns `404` |

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
11. `GET /health` returns `200` when all three data files are loaded.

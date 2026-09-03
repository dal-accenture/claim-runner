# Contract: POST /price

**Service**: Pricer (port 8082)  
**Caller**: Claims Manager  
**Spec**: 003-pricer

---

## Request

```
POST /price
Content-Type: application/json
```

```json
{
  "claim_id":      "string",        // required
  "member_id":     "string",        // required
  "plan_id":       "string",        // required
  "network_status": "IN_NETWORK",   // required; IN_NETWORK | OUT_OF_NETWORK
  "claim_lines": [
    {
      "line_number":     1,
      "procedure_code":  "99213",   // required; must exist in fee schedules
      "units":           1,         // required; positive integer; billed_amount is per-unit
      "billed_amount":   250.00     // required; positive; per-unit charged amount
    }
  ]
}
```

---

## Response — 200 OK: In-network GP visit (copay before deductible, 0% coinsurance)

```json
{
  "claim_id": "CLM-20250901-001",
  "totals": {
    "billed_amount":   250.00,
    "allowed_amount":  115.00,
    "member_liability": 30.00,
    "payer_liability":  85.00
  },
  "accumulator_snapshot": {
    "individual_deductible_used_before": 125.00,
    "individual_deductible_used_after":  125.00,
    "individual_oop_used_before":        155.00,
    "individual_oop_used_after":         185.00
  },
  "line_detail": [
    {
      "line_number":            1,
      "procedure_code":         "99213",
      "billed_amount":          250.00,
      "allowed_amount":         115.00,
      "contractual_adjustment": 135.00,
      "deductible_applied":       0.00,
      "copay_applied":           30.00,
      "coinsurance_applied":      0.00,
      "member_liability":        30.00,
      "payer_liability":         85.00,
      "adjustment_reason_code": "CO-45",
      "line_status":            "PAID"
    }
  ]
}
```

## Response — 200 OK: Surgical procedure (deductible partially met, 10% coinsurance)

```json
{
  "claim_id": "CLM-20250901-002",
  "totals": {
    "billed_amount":    4200.00,
    "allowed_amount":   2800.00,
    "member_liability":  617.50,
    "payer_liability":  2182.50
  },
  "accumulator_snapshot": {
    "individual_deductible_used_before": 125.00,
    "individual_deductible_used_after":  500.00,
    "individual_oop_used_before":        155.00,
    "individual_oop_used_after":         772.50
  },
  "line_detail": [
    {
      "line_number":            1,
      "procedure_code":         "42820",
      "billed_amount":          4200.00,
      "allowed_amount":         2800.00,
      "contractual_adjustment": 1400.00,
      "deductible_applied":      375.00,
      "copay_applied":             0.00,
      "coinsurance_applied":     242.50,
      "member_liability":        617.50,
      "payer_liability":        2182.50,
      "adjustment_reason_code": "CO-45",
      "line_status":            "PAID"
    }
  ]
}
```

## Response — 200 OK: OOP max already met

```json
{
  "claim_id": "CLM-20250901-003",
  "totals": {
    "billed_amount":   250.00,
    "allowed_amount":  115.00,
    "member_liability":  0.00,
    "payer_liability": 115.00
  },
  "accumulator_snapshot": {
    "individual_deductible_used_before": 250.00,
    "individual_deductible_used_after":  250.00,
    "individual_oop_used_before":       2000.00,
    "individual_oop_used_after":        2000.00
  },
  "line_detail": [
    {
      "line_number":            1,
      "procedure_code":         "99213",
      "billed_amount":          250.00,
      "allowed_amount":         115.00,
      "contractual_adjustment": 135.00,
      "deductible_applied":       0.00,
      "copay_applied":            0.00,
      "coinsurance_applied":      0.00,
      "member_liability":         0.00,
      "payer_liability":         115.00,
      "adjustment_reason_code": "CO-45",
      "line_status":            "PAID"
    }
  ]
}
```

---

## Error Responses

| Status | Condition | Body |
|---|---|---|
| `404 Not Found` | `member_id` not found in Data Service | `{"detail": "Member {member_id} not found"}` |
| `404 Not Found` | `plan_id` not found in Data Service | `{"detail": "Plan {plan_id} not found"}` |
| `422 Unprocessable Entity` | Procedure code not in fee schedules | `{"detail": "Procedure code {code} not found in fee schedules"}` |
| `422 Unprocessable Entity` | Missing or malformed required field | FastAPI default validation error |
| `503 Service Unavailable` | Data Service unreachable | `{"detail": "Data Service unavailable"}` |

---

## Health Endpoint

```
GET /health
→ 200 OK
→ {"status": "ok"}
```

---

## Invariants (verified by tests)

- `member_liability + payer_liability == allowed_amount` for every line
- `totals.member_liability == sum of line member_liabilities`
- `totals.payer_liability == sum of line payer_liabilities`
- `accumulator_snapshot._after == _before + this_claim_applied`

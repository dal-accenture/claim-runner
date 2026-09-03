# Contract: POST /claims/batch

**Service**: Claims Manager (port 8080)  
**Spec**: 001-claims-manager

---

## Request

```
POST /claims/batch
Content-Type: application/json
```

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

`diagnosis_codes` is optional and accepted but not evaluated.

---

## Response — 200 OK: All claims processed (success or per-claim failure)

The top-level HTTP status is always `200` when the batch itself is processed (regardless of individual claim outcomes). Per-claim failures appear inline in `results`.

### All lines paid

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
      "errors": [],
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
          "denial_reason": null,
          "line_status": "PAID"
        }
      ]
    }
  ]
}
```

### Mixed (one paid, one denied)

```json
{
  "results": [
    {
      "claim_id": "CLM-20250901-002",
      "status": "PARTIALLY_PAID",
      "adjudicated_at": "2025-09-01T14:30:05Z",
      "totals": {
        "billed_amount": 4450.00,
        "allowed_amount": 115.00,
        "member_liability": 30.00,
        "payer_liability": 85.00
      },
      "denial_reasons": [],
      "errors": [],
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
          "denial_reason": null,
          "line_status": "PAID"
        },
        {
          "line_number": 2,
          "procedure_code": "42820",
          "billed_amount": 4200.00,
          "allowed_amount": 0.00,
          "contractual_adjustment": 0.00,
          "deductible_applied": 0.00,
          "copay_applied": 0.00,
          "coinsurance_applied": 0.00,
          "member_liability": 0.00,
          "payer_liability": 0.00,
          "adjustment_reason_code": null,
          "denial_reason": "AUTH_REQUIRED_NOT_ON_FILE",
          "line_status": "DENIED"
        }
      ]
    }
  ]
}
```

### Validation error (per-claim)

```json
{
  "results": [
    {
      "claim_id": "CLM-20250901-003",
      "status": "VALIDATION_ERROR",
      "adjudicated_at": null,
      "totals": null,
      "denial_reasons": [],
      "errors": ["claim_lines: at least one entry required"],
      "line_detail": []
    }
  ]
}
```

### Conflict (claim_id already exists in Data Service)

```json
{
  "results": [
    {
      "claim_id": "CLM-20250901-001",
      "status": "CONFLICT",
      "adjudicated_at": null,
      "totals": null,
      "denial_reasons": [],
      "errors": ["claim_id already exists"],
      "line_detail": []
    }
  ]
}
```

---

## Response — 503 Service Unavailable: Downstream 5xx

Returned when Benefits Determiner, Pricer, or Data Service returns 5xx for any claim. No claims are written to the Data Service.

```json
{"detail": "Service unavailable"}
```

---

## Validation Rules (FR-2)

| Field | Rule |
|---|---|
| `claim_id` | Non-empty string; unique within the batch |
| `member_id` | Non-empty string |
| `provider_id` | Non-empty string |
| `date_of_service` | Valid date, `YYYY-MM-DD` |
| `claim_lines` | At least one entry |
| `claim_lines[].line_number` | Positive integer; unique within the claim |
| `claim_lines[].procedure_code` | Non-empty string |
| `claim_lines[].units` | Positive integer |
| `claim_lines[].billed_amount` | Positive number |

---

## Health Endpoint

```
GET /health
→ 200 OK
→ {"status": "UP"}
```

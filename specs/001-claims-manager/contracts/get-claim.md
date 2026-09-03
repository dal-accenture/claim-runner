# Contract: GET /claims/{claim_id}

**Service**: Claims Manager (port 8080)  
**Spec**: 001-claims-manager

---

## Request

```
GET /claims/{claim_id}
```

`claim_id` is a path parameter (string).

---

## Response — 200 OK: Claim found

Returns the stored adjudication result. Identical in shape to a successfully adjudicated entry from `POST /claims/batch` `results`. Only previously adjudicated claims (PAID, DENIED, PARTIALLY_PAID) are retrievable — VALIDATION_ERROR and CONFLICT results are not stored.

```json
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
```

---

## Response — 404 Not Found

Returned when the Data Service has no record for `claim_id`.

```json
{"detail": "Claim CLM-UNKNOWN not found"}
```

---

## Error Responses

| Status | Condition |
|---|---|
| `404 Not Found` | `claim_id` not in Data Service |
| `503 Service Unavailable` | Data Service unreachable or returned 5xx |

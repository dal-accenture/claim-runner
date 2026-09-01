# Exposed API — Claim Runner Pod

The only interface this pod exposes to external callers is the Claims Manager API on port 8080. The Benefits Determiner, Pricer, and Data Service are internal services; they are not intended to be called directly by external systems in the practicum configuration.

**This API accepts professional claims only** — physician and outpatient services billed on a CMS-1500 form (electronic: 837P). Institutional claims (hospital/facility services, CMS-1450 / UB-04 / 837I) are not supported.

## Claims Manager API

**Base URL:** `http://localhost:8080`  
**Protocol:** HTTP/REST, JSON payloads  
**Authentication:** None (practicum configuration)

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/claims/batch` | Submit one or more claims for adjudication |
| `GET` | `/claims/{claim_id}` | Retrieve a previously adjudicated claim result |
| `GET` | `/health` | Liveness check |

### POST /claims/batch

Submits a batch of one or more claims. Each claim is adjudicated independently. Claims Manager validates each payload, calls Benefits Determiner and Pricer in sequence for each covered claim, composes the adjudication results, writes each to the claim ledger, and returns all results in submission order.

A validation failure on one claim does not abort the batch — the remaining claims are adjudicated and all results are returned together.

**Request**

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

Required fields: `claim_id`, `member_id`, `provider_id`, `date_of_service`, at least one entry in `claim_lines`. Each line requires `line_number`, `procedure_code`, `units`, `billed_amount`.

`diagnosis_codes` is accepted but not evaluated.

**Response**

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

Results are returned in the same order claims were submitted. A per-claim `status` of `400` indicates a validation failure for that claim; the other claims in the batch are unaffected.

**Claim Status Values**

| Status | Condition |
|---|---|
| `PAID` | All lines covered and priced |
| `DENIED` | All lines denied |
| `PARTIALLY_PAID` | Mix of paid and denied lines |

**HTTP Status Codes**

| Code | Condition |
|---|---|
| `200` | Batch processed; per-claim status in `results[].status` |
| `400` | Per-claim validation failure (missing or invalid fields); other claims in batch proceed |
| `409` | `claim_id` already exists in the claim ledger; claim not re-adjudicated |
| `503` | Benefits Determiner, Pricer, or Data Service unreachable |

### GET /claims/{claim_id}

Returns the adjudication result for a previously submitted claim. The response shape is identical to a single entry in `POST /claims/batch` `results`. Results persist across Claims Manager restarts via the Data Service.

| Code | Condition |
|---|---|
| `200` | Claim found |
| `404` | Claim not found |

### GET /health

Returns `200` with `{ "status": "UP" }` when the service is running. Used by `start.sh` to gate startup sequencing.

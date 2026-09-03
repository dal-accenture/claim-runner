# Quickstart: Claims Manager

**Spec**: 001-claims-manager  
**Service port**: 8080

---

## Prerequisites

All upstream services must be healthy before these scenarios can run:

| Service | Port | Required by |
|---|---|---|
| Data Service | 8083 | Member lookup, claim storage/retrieval |
| Benefits Determiner | 8081 | All adjudication scenarios |
| Pricer | 8082 | Scenarios with covered lines |

Start the full system:

```sh
./start.sh
```

Or start Claims Manager in isolation (for health-only verification):

```sh
uvicorn claims_manager.main:app --port 8080
```

---

## Scenario 1 — Single in-network claim, PAID

A GP visit with copay-only cost-sharing (coinsurance 0%, copay $30).

**Seed member**: `MBR-10042` (ensure deductible not met; use any member with an active Gold plan)

```powershell
Invoke-RestMethod -Method POST -Uri "http://localhost:8080/claims/batch" `
  -ContentType "application/json" `
  -Body '{
    "claims": [{
      "claim_id": "CLM-QS-001",
      "member_id": "MBR-10042",
      "provider_id": "PRV-90210",
      "date_of_service": "2025-09-01",
      "claim_lines": [{
        "line_number": 1,
        "procedure_code": "99213",
        "units": 1,
        "billed_amount": 250.00
      }]
    }]
  }' | ConvertTo-Json -Depth 10
```

**Expected**:
- `results[0].status == "PAID"`
- `results[0].line_detail[0].line_status == "PAID"`
- `results[0].line_detail[0].copay_applied == 30.00`
- `results[0].line_detail[0].allowed_amount == 115.00`
- `results[0].totals.member_liability == 30.00`

---

## Scenario 2 — Batch with two claims in submission order

Verifies that results are returned in the same order as submitted.

```powershell
Invoke-RestMethod -Method POST -Uri "http://localhost:8080/claims/batch" `
  -ContentType "application/json" `
  -Body '{
    "claims": [
      {
        "claim_id": "CLM-QS-002A",
        "member_id": "MBR-10042",
        "provider_id": "PRV-90210",
        "date_of_service": "2025-09-01",
        "claim_lines": [{"line_number": 1, "procedure_code": "99213", "units": 1, "billed_amount": 250.00}]
      },
      {
        "claim_id": "CLM-QS-002B",
        "member_id": "MBR-10043",
        "provider_id": "PRV-90210",
        "date_of_service": "2025-09-01",
        "claim_lines": [{"line_number": 1, "procedure_code": "99213", "units": 1, "billed_amount": 250.00}]
      }
    ]
  }' | ConvertTo-Json -Depth 10
```

**Expected**:
- `results[0].claim_id == "CLM-QS-002A"`
- `results[1].claim_id == "CLM-QS-002B"`
- Both with `status == "PAID"` (assuming both members are valid and covered)

---

## Scenario 3 — Unknown member, NOT_ELIGIBLE denial

```powershell
Invoke-RestMethod -Method POST -Uri "http://localhost:8080/claims/batch" `
  -ContentType "application/json" `
  -Body '{
    "claims": [{
      "claim_id": "CLM-QS-003",
      "member_id": "MBR-UNKNOWN-99999",
      "provider_id": "PRV-90210",
      "date_of_service": "2025-09-01",
      "claim_lines": [{"line_number": 1, "procedure_code": "99213", "units": 1, "billed_amount": 250.00}]
    }]
  }' | ConvertTo-Json -Depth 10
```

**Expected**:
- `results[0].status == "DENIED"`
- `results[0].denial_reasons` contains `"NOT_ELIGIBLE"`
- `results[0].line_detail == []`

---

## Scenario 4 — Mixed batch: valid + validation failure

One valid claim and one missing `claim_lines`. Both results returned; only the valid claim is adjudicated.

```powershell
Invoke-RestMethod -Method POST -Uri "http://localhost:8080/claims/batch" `
  -ContentType "application/json" `
  -Body '{
    "claims": [
      {
        "claim_id": "CLM-QS-004A",
        "member_id": "MBR-10042",
        "provider_id": "PRV-90210",
        "date_of_service": "2025-09-01",
        "claim_lines": [{"line_number": 1, "procedure_code": "99213", "units": 1, "billed_amount": 250.00}]
      },
      {
        "claim_id": "CLM-QS-004B",
        "member_id": "MBR-10043",
        "provider_id": "PRV-90210",
        "date_of_service": "2025-09-01",
        "claim_lines": []
      }
    ]
  }' | ConvertTo-Json -Depth 10
```

**Expected**:
- `results[0].status == "PAID"` (CLM-QS-004A adjudicated normally)
- `results[1].status == "VALIDATION_ERROR"` (CLM-QS-004B has empty claim_lines)
- `results[1].errors` contains a message mentioning `claim_lines`

---

## Scenario 5 — Claim retrieval via GET

Submit a claim then retrieve it by ID.

```powershell
# First: submit (reuse CLM-QS-001 or pick a new ID)
$batch = Invoke-RestMethod -Method POST -Uri "http://localhost:8080/claims/batch" `
  -ContentType "application/json" `
  -Body '{
    "claims": [{
      "claim_id": "CLM-QS-005",
      "member_id": "MBR-10042",
      "provider_id": "PRV-90210",
      "date_of_service": "2025-09-01",
      "claim_lines": [{"line_number": 1, "procedure_code": "99213", "units": 1, "billed_amount": 250.00}]
    }]
  }'

# Then: retrieve
Invoke-RestMethod -Uri "http://localhost:8080/claims/CLM-QS-005" | ConvertTo-Json -Depth 10
```

**Expected**:
- `status == "PAID"`
- Response shape identical to `results[0]` from the batch call

```powershell
# Unknown claim_id returns 404
try {
  Invoke-RestMethod -Uri "http://localhost:8080/claims/CLM-NOTEXIST"
} catch {
  $_.Exception.Response.StatusCode.Value__  # expect 404
}
```

---

## Scenario 6 — Duplicate claim_id (CONFLICT)

Submit the same `claim_id` a second time.

```powershell
# Assumes CLM-QS-005 was submitted in Scenario 5
Invoke-RestMethod -Method POST -Uri "http://localhost:8080/claims/batch" `
  -ContentType "application/json" `
  -Body '{
    "claims": [{
      "claim_id": "CLM-QS-005",
      "member_id": "MBR-10042",
      "provider_id": "PRV-90210",
      "date_of_service": "2025-09-01",
      "claim_lines": [{"line_number": 1, "procedure_code": "99213", "units": 1, "billed_amount": 250.00}]
    }]
  }' | ConvertTo-Json -Depth 10
```

**Expected**:
- `results[0].status == "CONFLICT"`
- `results[0].errors[0] == "claim_id already exists"`

---

## Scenario 7 — Health check

```powershell
Invoke-RestMethod -Uri "http://localhost:8080/health"
```

**Expected**: `{"status": "UP"}`

---

## Scenario 8 — PARTIALLY_PAID (one covered, one denied)

**Requires** a member with a plan that covers `99213` but not `42820` (or a procedure that requires auth). Check Benefits Determiner seed data for a member with a plan that has an excluded procedure.

```powershell
Invoke-RestMethod -Method POST -Uri "http://localhost:8080/claims/batch" `
  -ContentType "application/json" `
  -Body '{
    "claims": [{
      "claim_id": "CLM-QS-008",
      "member_id": "MBR-10087",
      "provider_id": "PRV-90210",
      "date_of_service": "2025-09-01",
      "claim_lines": [
        {"line_number": 1, "procedure_code": "99213", "units": 1, "billed_amount": 250.00},
        {"line_number": 2, "procedure_code": "42820", "units": 1, "billed_amount": 4200.00}
      ]
    }]
  }' | ConvertTo-Json -Depth 10
```

**Expected**:
- `results[0].status == "PARTIALLY_PAID"`
- `results[0].line_detail[0].line_status == "PAID"`
- `results[0].line_detail[1].line_status == "DENIED"`
- `results[0].line_detail[1].denial_reason` is non-null

---

## Reference

- Full request/response shapes: `specs/001-claims-manager/contracts/`
- Entity definitions: `specs/001-claims-manager/data-model.md`
- Benefits Determiner contract: `specs/002-benefits-determiner/contracts/post-benefits-determine.md`
- Pricer contract: `specs/003-pricer/contracts/post-price.md`

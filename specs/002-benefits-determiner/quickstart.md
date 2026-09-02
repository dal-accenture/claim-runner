# Quickstart: Benefits Determiner

**Spec**: 002-benefits-determiner

Validation scenarios for proving `POST /benefits/determine` works end-to-end. Each scenario requires the seed data (`data/`) and the Data Service (port 8083) to be running, unless stated otherwise.

---

## Prerequisites

```powershell
# 1. Seed data must exist
ls data/members.json data/plans.json   # should exist from spec 004

# 2. Start Data Service (if not already running)
cd data_service
pip install -r requirements.txt
$env:DATA_DIR = "..\data"
uvicorn main:app --port 8083
cd ..

# 3. Start Benefits Determiner
cd benefits_determiner
pip install -r requirements.txt
$env:DATA_SERVICE_URL = "http://localhost:8083"
uvicorn main:app --port 8081
cd ..
```

---

## Scenario 1 — Health check

```powershell
Invoke-RestMethod http://localhost:8081/health
# Expected: HTTP 200, body: {"status": "ok"}
```

---

## Scenario 2 — Eligible member, in-network, covered procedure, no auth required

Use any Gold PPO member (MBR-10001 through MBR-10040) with a GP procedure code (e.g., `99213`) and an in-network provider (e.g., `PRV-10001`).

```powershell
$body = @{
    member_id       = "MBR-10001"
    provider_id     = "PRV-10001"
    procedure_codes = @("99213")
    date_of_service = "2025-06-01"
} | ConvertTo-Json

Invoke-RestMethod -Method POST -Uri http://localhost:8081/benefits/determine `
    -ContentType "application/json" -Body $body
```

**Expected:**
```json
{
  "eligible": true,
  "network_status": "IN_NETWORK",
  "overall_covered": true,
  "line_determinations": [
    { "procedure_code": "99213", "covered": true, "requires_auth": false, "auth_on_file": null, "denial_reason": null }
  ],
  "denial_reason": null
}
```

---

## Scenario 3 — Out-of-network provider

Use any Silver PPO member with a GP code and provider `PRV-10001` (not in Silver's network `PRV-10005`–`PRV-10020`).

```powershell
$body = @{
    member_id       = "MBR-10041"
    provider_id     = "PRV-10001"
    procedure_codes = @("99213")
    date_of_service = "2025-06-01"
} | ConvertTo-Json

Invoke-RestMethod -Method POST -Uri http://localhost:8081/benefits/determine `
    -ContentType "application/json" -Body $body
```

**Expected:** `eligible: true`, `network_status: "OUT_OF_NETWORK"`, `overall_covered: true`, `denial_reason: null`.

---

## Scenario 4 — Member not found (NOT_ELIGIBLE)

```powershell
$body = @{
    member_id       = "MBR-99999"
    provider_id     = "PRV-10001"
    procedure_codes = @("99213")
    date_of_service = "2025-06-01"
} | ConvertTo-Json

Invoke-RestMethod -Method POST -Uri http://localhost:8081/benefits/determine `
    -ContentType "application/json" -Body $body
```

**Expected:** `eligible: false`, `denial_reason: "NOT_ELIGIBLE"`, `line_determinations: []`.

---

## Scenario 5 — Excluded procedure code (NOT_COVERED)

Silver PPO excludes surgical ENT codes (`42820`). Use any Silver PPO member.

```powershell
$body = @{
    member_id       = "MBR-10041"
    provider_id     = "PRV-10005"
    procedure_codes = @("42820")
    date_of_service = "2025-06-01"
} | ConvertTo-Json

Invoke-RestMethod -Method POST -Uri http://localhost:8081/benefits/determine `
    -ContentType "application/json" -Body $body
```

**Expected:** `eligible: true`, `overall_covered: false`, line: `covered: false`, `denial_reason: "NOT_COVERED"`.

---

## Scenario 6 — Auth required, no auth on file (AUTH_REQUIRED_NOT_ON_FILE)

Gold PPO covers `42820` but requires auth. Use a Gold member who has no authorization for `42820`.

```powershell
$body = @{
    member_id       = "MBR-10029"   # Gold member with no 42820 auth; adjust ID if needed
    provider_id     = "PRV-10001"
    procedure_codes = @("42820")
    date_of_service = "2025-06-01"
} | ConvertTo-Json

Invoke-RestMethod -Method POST -Uri http://localhost:8081/benefits/determine `
    -ContentType "application/json" -Body $body
```

**Expected:** `eligible: true`, `overall_covered: false`, line: `covered: false`, `requires_auth: true`, `denial_reason: "AUTH_REQUIRED_NOT_ON_FILE"`.

---

## Scenario 7 — Auth on file, valid date range

Gold member with a valid authorization for `42820`. Check `data/members.json` for a member with `authorizations[].procedure_code == "42820"` and a non-expired date.

```powershell
$body = @{
    member_id       = "MBR-10001"   # adjust to a Gold member with 42820 auth
    provider_id     = "PRV-10001"
    procedure_codes = @("42820")
    date_of_service = "2025-06-01"  # must fall within auth authorized_date/expiration_date
} | ConvertTo-Json

Invoke-RestMethod -Method POST -Uri http://localhost:8081/benefits/determine `
    -ContentType "application/json" -Body $body
```

**Expected:** `covered: true`, `auth_on_file: "<auth_id>"`, `denial_reason: null`.

---

## Scenario 8 — Missing required field (422)

```powershell
$body = '{"member_id": "MBR-10001", "provider_id": "PRV-10001", "procedure_codes": ["99213"]}'
# date_of_service missing

try {
    Invoke-RestMethod -Method POST -Uri http://localhost:8081/benefits/determine `
        -ContentType "application/json" -Body $body
} catch {
    $_.Exception.Response.StatusCode   # Expected: 422
}
```

---

## Scenario 9 — Data Service unavailable (503)

Stop the Data Service, then call the Benefits Determiner.

```powershell
# Stop data service first, then:
$body = @{
    member_id       = "MBR-10001"
    provider_id     = "PRV-10001"
    procedure_codes = @("99213")
    date_of_service = "2025-06-01"
} | ConvertTo-Json

try {
    Invoke-RestMethod -Method POST -Uri http://localhost:8081/benefits/determine `
        -ContentType "application/json" -Body $body
} catch {
    $_.Exception.Response.StatusCode          # Expected: 503
    # Body: {"detail": "Data Service unavailable"}
}
```

---

## Running the Test Suite

```powershell
cd benefits_determiner
pip install -r requirements.txt
pip install pytest respx

pytest tests/ -v
```

Tests use `respx` to mock Data Service calls — no live Data Service required.

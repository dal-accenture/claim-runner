# Quickstart: Pricer

**Spec**: 003-pricer

Validation scenarios for proving `POST /price` works end-to-end. Each scenario requires the seed data (`data/`) and the Data Service (port 8083) to be running.

---

## Prerequisites

```powershell
# 1. Seed data must exist
ls data/members.json data/fee_schedules.json data/plans.json

# 2. Start Data Service (if not already running)
cd C:\Users\daniel.a.lasaga\docs\projects\uhg\claim-runner
$env:DATA_DIR = "./data"
uvicorn data_service.main:app --port 8083

# 3. Start Pricer (separate terminal, repo root)
cd C:\Users\daniel.a.lasaga\docs\projects\uhg\claim-runner
$env:DATA_SERVICE_URL = "http://localhost:8083"
uvicorn pricer.main:app --port 8082
```

---

## Scenario 1 — Health check

```powershell
Invoke-RestMethod http://localhost:8082/health
# Expected: HTTP 200, body: {"status": "ok"}
```

---

## Scenario 2 — In-network GP visit (copay before deductible, 0% coinsurance)

Member on Gold PPO (`PLN-GOLD-001`), procedure `99213` in-network. Fee schedule: allowed $115, copay $30 (before deductible), coinsurance 0%.

```powershell
$body = @{
    claim_id       = "CLM-TEST-001"
    member_id      = "MBR-10001"
    plan_id        = "PLN-GOLD-001"
    network_status = "IN_NETWORK"
    claim_lines    = @(@{ line_number=1; procedure_code="99213"; units=1; billed_amount=250.00 })
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method POST -Uri http://localhost:8082/price -ContentType "application/json" -Body $body
```

**Expected:** `totals.member_liability = 30.00`, `totals.payer_liability = 85.00`, `line_detail[0].copay_applied = 30.00`, `deductible_applied = 0.00`.

---

## Scenario 3 — Surgical procedure (deductible partially met, 10% coinsurance)

Member with remaining deductible of $375 (`individual_deductible.used = 125.00`, limit $500). Procedure `42820` in-network: allowed $2800, no copay, 10% coinsurance.

```powershell
# Find a Gold PPO member whose individual_deductible.used = 125.00
# Use MBR-10001 if that matches the seed data, or inspect data/members.json

$body = @{
    claim_id       = "CLM-TEST-002"
    member_id      = "MBR-10001"
    plan_id        = "PLN-GOLD-001"
    network_status = "IN_NETWORK"
    claim_lines    = @(@{ line_number=1; procedure_code="42820"; units=1; billed_amount=4200.00 })
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method POST -Uri http://localhost:8082/price -ContentType "application/json" -Body $body
```

**Expected:** `deductible_applied` equals the member's remaining deductible; `coinsurance_applied = (2800 - deductible_applied) × 0.10`; `member_liability + payer_liability = 2800.00`.

---

## Scenario 4 — OOP max already met

Find a member in `data/members.json` whose `individual_oop_max.met = true`.

```powershell
$body = @{
    claim_id       = "CLM-TEST-003"
    member_id      = "MBR-10XXX"   # replace with a member whose oop_max.met = true
    plan_id        = "PLN-GOLD-001"
    network_status = "IN_NETWORK"
    claim_lines    = @(@{ line_number=1; procedure_code="99213"; units=1; billed_amount=250.00 })
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method POST -Uri http://localhost:8082/price -ContentType "application/json" -Body $body
```

**Expected:** `totals.member_liability = 0.00`, `totals.payer_liability = allowed_amount`.

---

## Scenario 5 — Out-of-network procedure

```powershell
$body = @{
    claim_id       = "CLM-TEST-004"
    member_id      = "MBR-10001"
    plan_id        = "PLN-GOLD-001"
    network_status = "OUT_OF_NETWORK"
    claim_lines    = @(@{ line_number=1; procedure_code="99213"; units=1; billed_amount=250.00 })
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method POST -Uri http://localhost:8082/price -ContentType "application/json" -Body $body
```

**Expected:** `allowed_amount = min(250.00, 84.00) = 84.00` (OON fee schedule rate); `coinsurance_applied = 84.00 × 0.40 = 33.60`.

---

## Scenario 6 — Unknown procedure code → 422

```powershell
$body = @{
    claim_id       = "CLM-TEST-005"
    member_id      = "MBR-10001"
    plan_id        = "PLN-GOLD-001"
    network_status = "IN_NETWORK"
    claim_lines    = @(@{ line_number=1; procedure_code="00000"; units=1; billed_amount=100.00 })
} | ConvertTo-Json -Depth 5

try {
    Invoke-RestMethod -Method POST -Uri http://localhost:8082/price -ContentType "application/json" -Body $body
} catch {
    $_.Exception.Response.StatusCode  # Expected: 422
}
```

---

## Scenario 7 — Member not found → 404

```powershell
$body = @{
    claim_id       = "CLM-TEST-006"
    member_id      = "MBR-99999"
    plan_id        = "PLN-GOLD-001"
    network_status = "IN_NETWORK"
    claim_lines    = @(@{ line_number=1; procedure_code="99213"; units=1; billed_amount=250.00 })
} | ConvertTo-Json -Depth 5

try {
    Invoke-RestMethod -Method POST -Uri http://localhost:8082/price -ContentType "application/json" -Body $body
} catch {
    $_.Exception.Response.StatusCode  # Expected: 404
}
```

---

## Scenario 8 — Financial invariant spot check

For any successful response, verify:
```powershell
$r = Invoke-RestMethod -Method POST -Uri http://localhost:8082/price -ContentType "application/json" -Body $body
$r.totals.member_liability + $r.totals.payer_liability -eq $r.totals.allowed_amount  # must be True
```

---

## Running the Test Suite

```powershell
cd C:\Users\daniel.a.lasaga\docs\projects\uhg\claim-runner
pip install pytest respx
pytest pricer/tests/ -v
# No live Data Service required — respx mocks all httpx calls
```

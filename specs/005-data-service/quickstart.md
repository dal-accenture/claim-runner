# Quickstart Validation Guide: Data Service

**Date**: 2026-09-02 | **Spec**: [spec.md](spec.md)

---

## Prerequisites

- Python 3.11+ installed
- Seed data generated (spec 004 complete): `data/members.json`,
  `data/plans.json`, `data/fee_schedules.json`, `data/claims.json` present
- Working directory: repository root

---

## Start the service

```bash
cd data_service
pip install -r requirements.txt
uvicorn main:app --port 8083
```

Or via `start.sh` (starts Data Service first, then adjudication services):

```bash
./start.sh
```

Expected startup output (stdout):
```
INFO: Data Service starting on port 8083
INFO: Loaded members=200, plans=5, fee_schedules=25, claims=150
INFO: Uvicorn running on http://0.0.0.0:8083
```

---

## Validation scenarios

### 1. Health check

```bash
curl http://localhost:8083/health
```

Expected:
```json
{ "status": "UP", "members": 200, "plans": 5, "fee_schedules": 25, "claims": 150 }
```

**AC-12**

---

### 2. Member lookup — found

```bash
curl http://localhost:8083/members/MBR-10001
```

Expected: `200` with full member record including `enrollment`, `accumulators`,
and `authorizations` arrays. Schema: `.specify/memory/data-model.md §3`.

**AC-1**

---

### 3. Member lookup — not found

```bash
curl http://localhost:8083/members/MBR-99999
```

Expected: `404` `{ "detail": "member not found" }`

**AC-2**

---

### 4. Plan lookup — found

```bash
curl http://localhost:8083/plans/PLN-GOLD-001
```

Expected: `200` with full plan record including `covered_procedure_codes` and
`network_provider_ids`. Schema: `.specify/memory/data-model.md §2`.

**AC-3**

---

### 5. Plan lookup — not found

```bash
curl http://localhost:8083/plans/PLN-DOES-NOT-EXIST
```

Expected: `404` `{ "detail": "plan not found" }`

**AC-4**

---

### 6. Fee schedule lookup — found

```bash
curl http://localhost:8083/fee-schedules/99213
```

Expected: `200` with entry containing both `in_network` and `out_of_network`
blocks. Schema: `.specify/memory/data-model.md §4`.

**AC-5**

---

### 7. Fee schedule lookup — not found

```bash
curl http://localhost:8083/fee-schedules/00000
```

Expected: `404` `{ "detail": "procedure code not found" }`

**AC-6**

---

### 8. Claim read — pre-seeded record found

Pick any `claim_id` from `data/claims.json`, e.g. `CLM-20250101-001`:

```bash
curl http://localhost:8083/claims/CLM-20250101-001
```

Expected: `200` with full claim ledger record. Schema:
`.specify/memory/data-model.md §5`.

**AC-7**

---

### 9. Claim read — not found

```bash
curl http://localhost:8083/claims/CLM-DOES-NOT-EXIST
```

Expected: `404` `{ "detail": "claim not found" }`

**AC-8**

---

### 10. Claim write — success

```bash
curl -X POST http://localhost:8083/claims \
  -H "Content-Type: application/json" \
  -d '{
    "claim_id": "CLM-20260902-TEST",
    "member_id": "MBR-10001",
    "provider_id": "PRV-10001",
    "date_of_service": "2026-09-02",
    "received_at": "2026-09-02T10:00:00Z",
    "adjudicated_at": "2026-09-02T10:00:01Z",
    "status": "PAID",
    "totals": { "billed_amount": 250.00, "allowed_amount": 115.00, "member_liability": 30.00, "payer_liability": 85.00 },
    "denial_reasons": [],
    "line_detail": [{ "line_number": 1, "procedure_code": "99213", "billed_amount": 250.00, "allowed_amount": 115.00, "deductible_applied": 0.00, "copay_applied": 30.00, "coinsurance_applied": 0.00, "member_liability": 30.00, "payer_liability": 85.00, "adjustment_reason_code": "CO-45", "line_status": "PAID" }]
  }'
```

Expected: `201` with the stored record body.

Then verify retrieval:

```bash
curl http://localhost:8083/claims/CLM-20260902-TEST
```

Expected: `200` with the same record.

**AC-9**

---

### 11. Claim write — duplicate

Repeat the POST from scenario 10 without restarting the service:

```bash
curl -X POST http://localhost:8083/claims \
  -H "Content-Type: application/json" \
  -d '{ "claim_id": "CLM-20260902-TEST", ... }'
```

Expected: `409` `{ "detail": "claim already exists" }`

**AC-11**

---

### 12. In-memory-only confirmation

After a successful `POST /claims` (scenario 10), restart the service:

```bash
# Ctrl-C, then restart
uvicorn main:app --port 8083
```

Then:

```bash
curl http://localhost:8083/claims/CLM-20260902-TEST
```

Expected: `404` — the claim written in the previous session is gone, confirming
the store is in-memory only.

**AC-10**

---

### 13. Missing reference file at startup

Remove or rename a reference file, then start the service:

```bash
mv data/members.json data/members.json.bak
uvicorn main:app --port 8083
```

Expected: service exits with a non-zero status code; CRITICAL log line emitted.
Restore the file afterwards: `mv data/members.json.bak data/members.json`.

**AC-14**

---

### 14. Missing claims.json at startup

```bash
mv data/claims.json data/claims.json.bak
uvicorn main:app --port 8083
```

Expected: service starts normally; `/health` returns `"claims": 0`; INFO log
line notes the missing file.

```bash
curl http://localhost:8083/health
# → { "status": "UP", "members": 200, "plans": 5, "fee_schedules": 25, "claims": 0 }
```

Restore: `mv data/claims.json.bak data/claims.json`

**AC-13**

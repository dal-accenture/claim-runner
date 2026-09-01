# Inter-Service Contracts — Claim Runner Pod

These contracts define the HTTP interfaces between the four internal services.
Claims Manager is the sole orchestrator of the adjudication flow. Claims Manager,
Benefits Determiner, and Pricer all call the Data Service for data access; no
service reads JSON files from disk directly.

A change to any request or response shape here requires coordinated updates in
both the calling service and the implementing service.

---

## Claims Manager → Benefits Determiner

**Method:** `GET`
**Path:** `/benefits/determine`
**Caller env var:** `BENEFITS_DETERMINER_URL` (default `http://localhost:8081`)

### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `member_id` | string | Yes | Member identifier |
| `provider_id` | string | Yes | Rendering provider identifier |
| `procedure_codes` | string (CSV) | Yes | Comma-separated procedure codes from all claim lines |
| `date_of_service` | string (YYYY-MM-DD) | Yes | Date of service |

### Response

```json
{
  "member_id": "MBR-10042",
  "plan_id": "PLN-GOLD-001",
  "eligible": true,
  "network_status": "IN_NETWORK",
  "overall_covered": true,
  "line_determinations": [
    {
      "procedure_code": "99213",
      "covered": true,
      "requires_auth": false,
      "auth_on_file": null,
      "denial_reason": null
    }
  ]
}
```

`network_status` values: `IN_NETWORK`, `OUT_OF_NETWORK`

`denial_reason` values (present when `covered: false`):

| Code | Meaning |
|---|---|
| `NOT_COVERED` | Procedure not a covered benefit |
| `NOT_ELIGIBLE` | Member not eligible on date of service |
| `AUTH_REQUIRED_NOT_ON_FILE` | Auth required but absent or expired |
| `PLAN_TERMINATED` | Plan not active on date of service |

**Contract rule:** If `eligible` is `false` or `overall_covered` is `false` for all
lines, Claims Manager must not call Pricer. It must return a `DENIED` result to
the external caller using the appropriate denial codes.

---

## Claims Manager → Pricer

**Method:** `POST`
**Path:** `/price`
**Caller env var:** `PRICER_URL` (default `http://localhost:8082`)

### Request

```json
{
  "claim_id": "CLM-20240901-001",
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

`plan_id` and `network_status` are taken from the Benefits Determiner response
and forwarded here. Claims Manager must not independently re-derive them.

### Response

```json
{
  "claim_id": "CLM-20240901-001",
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

**Contract rule:** Claims Manager surfaces `accumulator_snapshot` in the
adjudication result returned to the external caller. It does not write these
values back to any data file or to the Data Service.

---

## Claims Manager → Data Service

**Caller env var:** `DATA_SERVICE_URL` (default `http://localhost:8083`)

### Member existence check

```
GET /members/{member_id}
```

Used by Claims Manager to verify member existence before calling downstream
services. Returns the full member record (`200`) or `404`.

### Claim write

```
POST /claims
Content-Type: application/json

{ <full claim ledger record — see architecture/data-model.md §5> }
```

Called after each successful adjudication. Returns `201` with the stored record.
Returns `409` if `claim_id` already exists (Claims Manager should surface this
as a duplicate-claim error rather than re-adjudicating).

### Claim read

```
GET /claims/{claim_id}
```

Called by `GET /claims/{claim_id}` on the Claims Manager public API. Returns the
stored record (`200`) or `404`.

---

## Benefits Determiner → Data Service

**Caller env var:** `DATA_SERVICE_URL` (default `http://localhost:8083`)

### Member lookup

```
GET /members/{member_id}
```

Returns the full member record including `enrollment` and `authorizations`.
Returns `404` if the member is not found.

### Plan lookup

```
GET /plans/{plan_id}
```

`plan_id` is taken from the member's active `enrollment.plan_id`. Returns the
full plan record including `covered_procedure_codes`, `excluded_procedure_codes`,
and `network_provider_ids`. Returns `404` if the plan is not found.

---

## Pricer → Data Service

**Caller env var:** `DATA_SERVICE_URL` (default `http://localhost:8083`)

### Member lookup (accumulators)

```
GET /members/{member_id}
```

Returns the full member record. Pricer reads `accumulators.individual_deductible`
and `accumulators.individual_oop_max`. Returns `404` if the member is not found;
Pricer returns `404` to its caller in this case.

### Plan lookup (validation)

```
GET /plans/{plan_id}
```

Used to validate that the `plan_id` passed in the request exists. Returns `404`
if the plan is not found; Pricer returns `404` to its caller.

### Fee schedule lookup

```
GET /fee-schedules/{procedure_code}
```

Returns the fee schedule entry for the given CPT code, covering both
`in_network` and `out_of_network` blocks. Returns `404` if the code is not
found; Pricer returns `422` to Claims Manager with the unrecognized code
identified.

---

## Health Endpoints

All four services expose `GET /health` on their respective ports. These are used
exclusively by `start.sh` for startup sequencing.

| Service | Port | Health path |
|---|---|---|
| Data Service | 8083 | `/health` |
| Benefits Determiner | 8081 | `/health` |
| Pricer | 8082 | `/health` |
| Claims Manager | 8080 | `/health` |

# Spec: Benefits Determiner API

**Intake ID:** 0002-benefits-determiner  
**Pod:** claim-runner  
**Pod spec number:** claim-runner/002  
**Status:** Ready for allocation  
**Constitution references:** Technology Stack, Service Independence, Data Layer, Spec Scope  
**Source:** `intake/0002-benefits-determiner.md`

---

## Goal

Implement the Benefits Determiner as a FastAPI service on port 8081. Given a member, a provider, a set of procedure codes, and a date of service, it determines whether the member is eligible, whether each procedure code is covered or excluded under the member's active plan, what the provider's network status is, and whether any required prior authorizations are on file. It returns a structured per-line determination that Claims Manager uses to decide whether to proceed to pricing.

---

## Clarifications

### Session 2026-09-02

- Q: Should Benefits Determiner call the Data Service via HTTP to look up members and plans, or load those files directly from disk at startup? → A: HTTP calls to Data Service — `GET /members/{member_id}` and `GET /plans/{plan_id}`; configured via `DATA_SERVICE_URL` env var. Constitution v1.1 prohibits direct file access by adjudication services.
- Q: Should the determination endpoint use `GET /benefits/determine` with query parameters, or `POST /benefits/determine` with a JSON request body? → A: POST with JSON body — `{"member_id": "...", "provider_id": "...", "procedure_codes": ["99213", "42820"], "date_of_service": "YYYY-MM-DD"}`. More robust than CSV query params and consistent with the Claims Manager call pattern.
- Q: Should a terminated enrollment return `PLAN_TERMINATED` specifically, or should `NOT_ELIGIBLE` cover both "member not found" and "enrollment not active"? → A: Two distinct codes — `NOT_ELIGIBLE` when the member record is not found; `PLAN_TERMINATED` when the member exists but enrollment termination date precedes the date of service.
- Q: If the Data Service is unreachable when Benefits Determiner calls `GET /members/{id}` or `GET /plans/{id}` mid-request, what should the service return to Claims Manager? → A: Return `503 Service Unavailable` with `{"detail": "Data Service unavailable"}` so Claims Manager gets a clear downstream-connectivity signal rather than an ambiguous `500`.

---

## Out of Scope

- Clinical or medical necessity review
- Diagnosis code evaluation
- Referral validation (not applicable to PPO plans; deferred if HMO plans are added)
- Provider credentialing — providers are trusted as submitted (constitution note)
- Any pricing or cost-sharing calculation
- Institutional claims

---

## Functional Requirements

### FR-1 — Member eligibility check (claim-level)

Call `GET /members/{member_id}` on the Data Service. If the response is `404`, return immediately with `eligible: false` and `denial_reason: NOT_ELIGIBLE`. If the call fails due to a connection error or non-404/non-200 response, return `503 Service Unavailable` with `{"detail": "Data Service unavailable"}`.

Check the member's `enrollment` record: `effective_date <= date_of_service` and (`termination_date` is null OR `termination_date >= date_of_service`). If the enrollment's `termination_date` is set and precedes `date_of_service`, return immediately with `eligible: false` and `denial_reason: PLAN_TERMINATED`. If no active enrollment is found for any other reason, return `eligible: false` and `denial_reason: NOT_ELIGIBLE`.

### FR-2 — Network status determination (claim-level)

Call `GET /plans/{plan_id}` on the Data Service using the `plan_id` from the member's active enrollment. Check whether `provider_id` is present in `plan.network_provider_ids`. Set `network_status` to `IN_NETWORK` or `OUT_OF_NETWORK`. Out-of-network status is not a denial; it affects pricing only. If the call fails due to a connection error or unexpected status, return `503 Service Unavailable` with `{"detail": "Data Service unavailable"}`.

### FR-3 — Per-procedure-code determination (line-level)

For each procedure code in the request, apply in order:

1. **Exclusion check** — if the code is in `plan.excluded_procedure_codes`, set `covered: false`, `denial_reason: NOT_COVERED`. Skip remaining checks for this code.
2. **Coverage check** — if the code is not in `plan.covered_procedure_codes`, set `covered: false`, `denial_reason: NOT_COVERED`.
3. **Authorization check** — if the covered entry has `requires_auth: true`, search `member.authorizations` for a record where `procedure_code` matches AND `authorized_date <= date_of_service <= expiration_date`. If found, set `covered: true`, `auth_on_file: <auth_id>`. If not found, set `covered: false`, `denial_reason: AUTH_REQUIRED_NOT_ON_FILE`.

### FR-4 — Roll-up

Set `overall_covered: true` only if every `line_determination` entry has `covered: true`.

### FR-5 — Health check

`GET /health` returns `200` when the service is running. No Data Service reachability check is required at startup — the service starts independently and fails individual requests if the Data Service is unavailable.

---

## Domain Model

### Endpoint

```
POST /benefits/determine
Content-Type: application/json

{
  "member_id":       "string",        // required
  "provider_id":     "string",        // required
  "procedure_codes": ["string", ...], // required; one or more CPT codes
  "date_of_service": "YYYY-MM-DD"     // required
}
```

All four fields are required. Missing any returns `422` (FastAPI default validation error) with a message identifying the missing field.

### Response — all lines covered

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

### Response — mixed (one covered, one denied)

```json
{
  "member_id": "MBR-10087",
  "plan_id": "PLN-SILVER-002",
  "eligible": true,
  "network_status": "OUT_OF_NETWORK",
  "overall_covered": false,
  "line_determinations": [
    {
      "procedure_code": "99213",
      "covered": true,
      "requires_auth": false,
      "auth_on_file": null,
      "denial_reason": null
    },
    {
      "procedure_code": "42820",
      "covered": false,
      "requires_auth": true,
      "auth_on_file": null,
      "denial_reason": "AUTH_REQUIRED_NOT_ON_FILE"
    }
  ]
}
```

### Response — member not eligible

```json
{
  "member_id": "MBR-10099",
  "plan_id": null,
  "eligible": false,
  "network_status": null,
  "overall_covered": false,
  "line_determinations": [],
  "denial_reason": "NOT_ELIGIBLE"
}
```

### Denial reason codes

| Code | Scope | Trigger |
|---|---|---|
| `NOT_ELIGIBLE` | Claim | Member not found, or no active enrollment on date of service |
| `PLAN_TERMINATED` | Claim | Plan termination date precedes the date of service |
| `NOT_COVERED` | Line | Procedure excluded by or absent from the plan's covered list |
| `AUTH_REQUIRED_NOT_ON_FILE` | Line | Procedure requires auth; no valid (non-expired) auth found |

---

## Integration

### Called by

Claims Manager only. This service is not intended to be called directly by external callers in the practicum configuration.

### Data Service calls

| Endpoint | When called | Fields used |
|---|---|---|
| `GET /members/{member_id}` | FR-1 eligibility check | `enrollment`, `authorizations` |
| `GET /plans/{plan_id}` | FR-2 network status + FR-3 coverage | `network_provider_ids`, `covered_procedure_codes`, `excluded_procedure_codes` |

`DATA_SERVICE_URL` environment variable sets the Data Service base URL; default is `http://localhost:8083`.

---

## Non-functional Requirements

- **Language / framework:** Python 3.11+, FastAPI (constitution: Technology Stack)
- **Startup:** Service must be independently startable without Claims Manager or Pricer running
- **`/health` gate:** Must return `200` when the service is running; does not require Data Service to be reachable at startup
- **Data access:** All member and plan lookups via HTTP calls to Data Service (`DATA_SERVICE_URL`); no direct file access (constitution v1.1: Data Layer)
- **Pure read:** No writes to any data file (constitution: Data Layer)
- **Data Service error handling:** Any connection error or unexpected HTTP status from the Data Service returns `503 Service Unavailable` with `{"detail": "Data Service unavailable"}` to the caller; it does not return `500`.

---

## Edge Cases

| Case | Expected behavior |
|---|---|
| `member_id` not found in `members.json` | Return `eligible: false`, `denial_reason: NOT_ELIGIBLE`, empty `line_determinations` |
| Member enrollment terminated before date of service | `eligible: false`, `denial_reason: PLAN_TERMINATED` |
| Procedure code in both `covered_procedure_codes` and `excluded_procedure_codes` | Exclusion takes precedence; `covered: false`, `denial_reason: NOT_COVERED` |
| Authorization present but expired on date of service | `covered: false`, `denial_reason: AUTH_REQUIRED_NOT_ON_FILE` |
| Provider not in `network_provider_ids` | `network_status: OUT_OF_NETWORK`; not a denial |
| Single procedure code submitted (CSV of one) | Parsed and evaluated normally |
| Multiple procedure codes, all denied | `overall_covered: false`; all line entries have `covered: false` |
| Missing any required request body field | `422` (FastAPI validation error) naming the missing field |
| Data Service unreachable during `GET /members/{id}` or `GET /plans/{id}` | `503 Service Unavailable` with `{"detail": "Data Service unavailable"}` |

---

## Constraints

- This service does not call Claims Manager or Pricer. (Constitution: Adjudication Flow)
- No data file writes permitted. (Constitution: Data Layer)
- No spec may add institutional claim support. (Constitution: Claim Type)
- This spec covers Benefits Determiner only. Changes to Claims Manager contracts or Pricer are a separate spec. (Constitution: Spec Scope, Decision 0001)

---

## Acceptance Criteria

1. A member with an active enrollment, a covered procedure code, and no auth requirement returns `eligible: true`, `overall_covered: true`, and `covered: true` on the line determination.
2. A member whose enrollment terminated before the date of service returns `eligible: false`, `denial_reason: PLAN_TERMINATED`, and an empty `line_determinations` array.
3. A procedure code present in `excluded_procedure_codes` returns `covered: false`, `denial_reason: NOT_COVERED`, even if the same code also appears in `covered_procedure_codes`.
4. A procedure requiring authorization with a valid, non-expired auth on file returns `covered: true` with `auth_on_file` populated with the `auth_id`.
5. A procedure requiring authorization with no auth on file returns `covered: false`, `denial_reason: AUTH_REQUIRED_NOT_ON_FILE`.
6. A procedure requiring authorization with an expired auth (expiration date before date of service) returns `covered: false`, `denial_reason: AUTH_REQUIRED_NOT_ON_FILE`.
7. A provider whose ID is not in `network_provider_ids` returns `network_status: OUT_OF_NETWORK` and does not trigger a denial.
8. A request with one covered and one non-covered code returns `overall_covered: false` with per-line determinations reflecting each code's individual result.
9. A request with all covered codes returns `overall_covered: true`.
10. Missing any required request body field returns `422` with a message identifying the missing field.
11. `GET /health` returns `200` when the service is running.
12. A Data Service connection error during a determination request returns `503 Service Unavailable` with `{"detail": "Data Service unavailable"}`.

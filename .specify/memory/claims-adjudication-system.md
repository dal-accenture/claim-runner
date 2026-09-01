# Claims Adjudication System — Architectural Document

**Version:** 1.2  
**Status:** Draft  
**Domain:** Commercial Health Insurance  
**Claim type:** Professional claims only (CMS-1500 / 837P)  
**Scope:** Claims Submission, Benefits Determination, Pricing & Payment Calculation

---

## 1. Overview

This document describes the architecture for a lightweight, runnable claims adjudication demo built for use in a course practicum. It covers four services: a central data layer, claim intake and orchestration, benefits determination, and pricing and payment calculation. Each capability is encapsulated in its own API service. Reference data (plan definitions, member records) is stored in JSON files loaded at startup by the Data Service and served over HTTP to the other services — no external database is required or intended.

**This system processes professional claims only.** A professional claim is a claim for physician and outpatient services submitted on a CMS-1500 form (or its electronic equivalent, the 837P transaction). Institutional claims (hospital and facility services submitted on a CMS-1450 / UB-04 form, or electronically as an 837I transaction) are out of scope for this system.

The system is designed for clarity and hands-on runnability. It is not intended to cover front-end EDI intake validation, clinical review, fraud detection, payment disbursement, or appeals — these are out of scope.

The engineering pods responsible for this system are listed in `registry/pods.yaml`.

---

## 2. Scope

### In Scope

| Capability | Service |
|---|---|
| Centralised in-memory data access (members, plans, fee schedules, claim ledger) | Data Service API |
| Professional claim (CMS-1500) submission and orchestration | Claims Manager API |
| Benefits determination (coverage, authorization, network status) | Benefits Determiner API |
| Pricing, cost-sharing, and payment calculation | Pricer API |

### Out of Scope

- Institutional claims (CMS-1450 / UB-04 / 837I) — this system is professional claims only
- Front-end EDI intake and format validation (837P parsing)
- Prior authorization workflows
- Clinical / medical necessity review
- Fraud, waste, and abuse detection
- Payment disbursement (EFT / check issuance)
- EOB and 835 ERA generation
- Appeals and grievances

---

## 3. System Architecture

### 3.1 High-Level Diagram

```
                        ┌─────────────────────────────┐
                        │        External Caller        │
                        │  (provider system / test      │
                        │   client / integration test)  │
                        └────────────┬────────────────┘
                                     │  POST /claims/batch
                                     ▼
                        ┌─────────────────────────────┐
                        │      Claims Manager API       │
                        │  - Accepts claim payload      │
                        │  - Orchestrates adjudication  │
                        │  - Returns adjudication result│
                        └────────┬──────────┬──────────┘
                                 │          │
               ┌─────────────────┘          └─────────────────┐
               │                                               │
               ▼                                               ▼
┌──────────────────────────┐              ┌──────────────────────────┐
│   Benefits Determiner API │              │        Pricer API         │
│  - Coverage check        │              │  - Allowed amount calc    │
│  - Network status        │              │  - Deductible / OOP logic │
│  - Authorization check   │              │  - Coinsurance / copay    │
└──────────────┬───────────┘              └──────────────┬───────────┘
               │                                         │
               └───────────────────┬─────────────────────┘
                                   │  (also: Claims Manager)
                                   ▼
                        ┌─────────────────────────────┐
                        │       Data Service API        │
                        │  - GET /members/{id}          │
                        │  - GET /plans/{id}            │
                        │  - GET /fee-schedules/{code}  │
                        │  - GET /claims/{id}           │
                        │  - POST /claims               │
                        │                               │
                        │  Loads from disk (in-memory): │
                        │    members.json               │
                        │    plans.json                 │
                        │    fee_schedules.json         │
                        │    claims.json (r/w)          │
                        └─────────────────────────────┘
```

### 3.2 Service Interaction Flow

```
Caller
  │
  │  1. POST /claims/batch  { claims: [...] }
  ▼
Claims Manager
  │
  │  2. GET /members/{member_id}  (existence check)
  ▼
Data Service
  │  Returns: member record | 404 → deny with NOT_ELIGIBLE
  │
  └──► back to Claims Manager
         │
         │  3. GET /benefits/determine  { member_id, provider_id, procedure_codes, date_of_service }
         ▼
       Benefits Determiner
         │  (calls Data Service for member + plan records)
         │  Returns: { eligible, plan_id, network_status, overall_covered, line_determinations[] }
         │
         └──► back to Claims Manager
                │
                │  4. POST /price  { member_id, plan_id, network_status, claim_lines (covered only) }
                ▼
              Pricer
                │  (calls Data Service for member, plan, and fee schedule records)
                │  Returns: { totals, accumulator_snapshot, line_detail[] }
                │
                └──► back to Claims Manager
                       │
                       │  5. POST /claims  { adjudication result }
                       ▼
                     Data Service
                       │  Persists to claims.json; returns 201
                       │
                       └──► back to Claims Manager
                              │
                              │  6. Return full batch result
                              ▼
                           Caller
                             Returns: { results: [ { claim_id, status, totals,
                                         denial_reasons[], line_detail[] } ] }
```

---

## 4. Services

### 4.1 Data Service API

**Role:** The single source of truth for all runtime data. Loads the four JSON data files into memory at startup and exposes them via HTTP/REST. All three adjudication services call the Data Service for data access; none reads from disk directly. Claims Manager writes new claim records through this service.

**Base URL:** `http://localhost:8083`

#### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/members/{member_id}` | Look up a member record |
| `GET` | `/plans/{plan_id}` | Look up a plan record |
| `GET` | `/fee-schedules/{procedure_code}` | Look up a fee schedule entry |
| `GET` | `/claims/{claim_id}` | Retrieve a stored claim record |
| `POST` | `/claims` | Store a new adjudication result |
| `GET` | `/health` | Health check with record counts |

#### Responsibilities

- Load `members.json`, `plans.json`, `fee_schedules.json`, and `claims.json` at startup into in-memory maps keyed by their primary identifier
- Serve all lookup requests from in-memory maps
- On `POST /claims`: validate the claim body, store in memory, persist the updated claims list to `claims.json`, return `201`
- Return `409` if a `claim_id` already exists
- Return `404` for any lookup that finds no matching record
- Report record counts on `GET /health`; this is what `start.sh` polls before starting downstream services

#### Data Files Owned

| File | Access |
|---|---|
| `members.json` | Read at startup; held in memory; never written |
| `plans.json` | Read at startup; held in memory; never written |
| `fee_schedules.json` | Read at startup; held in memory; never written |
| `claims.json` | Read at startup; written after every successful `POST /claims` |

---

### 4.2 Claims Manager API

**Role:** Entry point and orchestrator. Accepts a batch of claims, invokes the Benefits Determiner and Pricer in sequence for each claim, composes the adjudication results, and returns them to the caller.

**Base URL:** `http://localhost:8080`

#### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/claims/batch` | Submit one or more claims for adjudication |
| `GET` | `/claims/{claim_id}` | Retrieve a previously adjudicated claim result |
| `GET` | `/health` | Health check |

#### POST /claims/batch — Request Payload

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

#### POST /claims/batch — Response Payload

```json
{
  "results": [
    {
      "claim_id": "CLM-20250901-001",
      "status": "PAID",
      "adjudicated_at": "2025-09-01T14:32:00Z",
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

#### Responsibilities

- Validate required fields on each incoming claim
- Call `GET /members/{member_id}` on the Data Service to verify member existence before downstream calls
- Call Benefits Determiner; halt and return a denied result if coverage fails
- Call Pricer with benefits context; compose final adjudication result
- Write adjudication results via `POST /claims` on the Data Service; proxy `GET /claims/{claim_id}` to the Data Service

#### Data Accessed via Data Service

| Endpoint | Purpose |
|---|---|
| `GET /members/{member_id}` | Member existence check before invoking downstream services |
| `POST /claims` | Write adjudication result to claim ledger |
| `GET /claims/{claim_id}` | Read a stored adjudication result |

---

### 4.3 Benefits Determiner API

**Role:** Determines whether a claim is covered under the member's plan, identifies network status of the provider, and flags whether a required authorization is on file.

**Base URL:** `http://localhost:8081`

#### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/benefits/determine` | Evaluate benefits for a claim |
| `GET` | `/health` | Health check |

#### GET /benefits/determine — Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `member_id` | string | Yes | Member identifier |
| `provider_id` | string | Yes | Rendering provider identifier |
| `procedure_codes` | string (CSV) | Yes | Comma-separated procedure codes |
| `date_of_service` | date | Yes | Date of service (YYYY-MM-DD) |

#### GET /benefits/determine — Response Payload

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

#### Possible `denial_reason` Values

| Code | Description |
|---|---|
| `NOT_COVERED` | Service is not a covered benefit under the plan |
| `NOT_ELIGIBLE` | Member was not eligible on the date of service |
| `AUTH_REQUIRED_NOT_ON_FILE` | Prior authorization required but not present |
| `PLAN_TERMINATED` | Plan was not active on the date of service |

#### Responsibilities

- Call the Data Service for member and plan records on each request
- Look up the member's active plan on the date of service
- Check whether each procedure code is listed as a covered benefit
- Determine in-network vs. out-of-network status by matching `provider_id` against the plan's network provider list
- Check whether any procedure code requires prior authorization; if so, verify presence in the member's auth records
- Return a structured per-line determination; any `covered: false` result includes a `denial_reason`

#### Data Accessed via Data Service

| Endpoint | Purpose |
|---|---|
| `GET /members/{member_id}` | Member eligibility, plan enrollment, and authorization records |
| `GET /plans/{plan_id}` | Benefit coverage rules, network provider lists, authorization requirements |

---

### 4.4 Pricer API

**Role:** Calculates the allowed amount for each claim line, applies the member's cost-sharing obligations (deductible, copay, coinsurance), respects the out-of-pocket maximum, and returns payer vs. member liability.

**Base URL:** `http://localhost:8082`

#### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/price` | Price a claim |
| `GET` | `/health` | Health check |

#### POST /price — Request Payload

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

#### POST /price — Response Payload

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

#### Pricing Logic

1. **Allowed amount** — call `GET /fee-schedules/{procedure_code}` on the Data Service; select the in-network or out-of-network rate based on `network_status`; billed amount is capped at the allowed amount
2. **Deductible** — apply any remaining deductible balance from the member's YTD accumulator, obtained via `GET /members/{member_id}` on the Data Service
3. **Copay** — apply fixed copay from the fee schedule record (after deductible is met, or before deductible if `copay_applies_before_deductible` is true for this procedure)
4. **Coinsurance** — apply member coinsurance percentage to the remaining allowed amount after deductible and copay
5. **Out-of-pocket maximum** — cap total member liability so that YTD OOP + current liability does not exceed the plan's OOP max
6. **Payer liability** — allowed amount minus total member liability

#### Responsibilities

- Call the Data Service for member, plan, and fee schedule records on each request
- Apply pricing logic per line item in order (allowed amount → deductible → copay → coinsurance → OOP max)
- Accumulator balances are read from the Data Service and not written back; the Pricer returns an informational `accumulator_snapshot` only

#### Data Accessed via Data Service

| Endpoint | Purpose |
|---|---|
| `GET /members/{member_id}` | Accumulator limits and current balances (deductible, OOP max) |
| `GET /plans/{plan_id}` | Plan existence validation |
| `GET /fee-schedules/{procedure_code}` | Allowed amounts, copays, and coinsurance rates by procedure code and network status |

---

## 5. Data Files (JSON)

All reference data is stored as JSON files in the `data/` directory of the pod repository. The **Data Service** is the sole process that reads from or writes to these files; the three adjudication services access all data through the Data Service's HTTP API. The canonical schemas and sample records for each file are in `architecture/data-model.md`.

| File | Loaded by | Writable | Purpose |
|---|---|---|---|
| `plans.json` | Data Service | No | Covered and excluded procedure codes; network provider IDs; plan type and dates |
| `members.json` | Data Service | No | Member registration, plan enrollment, accumulator limits and balances, authorizations |
| `fee_schedules.json` | Data Service | No | Allowed amounts, copays, and coinsurance by procedure code and network status |
| `claims.json` | Data Service | Yes — written via `POST /claims` | Durable ledger of all submitted and adjudicated claims; backing store for `GET /claims/{claim_id}` |

**Key design notes (v1.2):**

- The Data Service is the only service that holds a reference to the `data/` directory. Adjudication services have no `DATA_DIR` variable and no filesystem dependency.
- Cost-sharing rules (copay, coinsurance, `copay_applies_before_deductible`) are in `fee_schedules.json`, not `plans.json`.
- Deductible and OOP maximum limits are carried in `members.json` under `accumulators`. These are seeded manually and not updated at runtime — a known practicum limitation.
- `claims.json` is the only writable file. The Data Service writes it synchronously after each successful `POST /claims`.

---

## 6. Inter-Service Communication

All services communicate over HTTP/REST using JSON payloads. For this mock implementation, services are co-located and addressed by localhost ports. In a production deployment, service URLs would be externalized to environment variables or a service registry.

| Caller | Callee | Protocol | Auth |
|---|---|---|---|
| Claims Manager | Benefits Determiner | HTTP GET | None (mock) |
| Claims Manager | Pricer | HTTP POST | None (mock) |
| Claims Manager | Data Service | HTTP GET / POST | None (mock) |
| Benefits Determiner | Data Service | HTTP GET | None (mock) |
| Pricer | Data Service | HTTP GET | None (mock) |

Service URLs are configured via environment variables:

| Variable | Default |
|---|---|
| `BENEFITS_DETERMINER_URL` | `http://localhost:8081` |
| `PRICER_URL` | `http://localhost:8082` |
| `DATA_SERVICE_URL` | `http://localhost:8083` |

---

## 7. Error Handling

Each service returns standard HTTP status codes. The Claims Manager is responsible for translating downstream errors into a coherent response to the caller.

| Scenario | HTTP Status | Behavior |
|---|---|---|
| Member not found | 404 | Claims Manager returns `DENIED` with reason `NOT_ELIGIBLE` |
| Benefits Determiner unavailable | 503 | Claims Manager returns 503 to caller with `SERVICE_UNAVAILABLE` |
| Pricer unavailable | 503 | Claims Manager returns 503 to caller with `SERVICE_UNAVAILABLE` |
| Invalid claim payload | 400 | Claims Manager returns 400 with field-level validation errors |
| Procedure code not in fee schedule | 422 | Pricer returns 422; Claims Manager denies the affected line with `NOT_PRICED` |

---

## 8. Assumptions & Constraints

- **Professional claims only.** The system accepts CMS-1500 / 837P professional claims. Institutional claims (CMS-1450 / UB-04 / 837I) are not supported and are not a future scope item for this practicum.
- **JSON mock data by design.** All reference data is loaded from JSON files at service startup and held in memory. This is the intended data layer for the practicum, not a placeholder for a future database.
- **Synchronous orchestration.** The Claims Manager calls Benefits Determiner and Pricer sequentially and blocks until both respond. Asynchronous or event-driven processing is out of scope.
- **Single member / single plan.** Each claim is adjudicated against one member and one active plan. COB (coordination of benefits across multiple plans) is noted in the Pricer design but simplified to single-plan logic in this iteration.
- **Accumulators are read-only.** Deductible and OOP accumulator balances are seeded in `members.json` and read at adjudication time. Neither the Pricer nor any other service writes back to `members.json`. Subsequent claims in the same session see the same starting balances. The claim ledger (`claims.json`) provides the audit trail to reconstruct true YTD balances when needed.
- **No authentication or authorization.** API endpoints are unauthenticated in this mock implementation. OAuth 2.0 / API key enforcement would be added before any production deployment.
- **Procedure codes only.** Diagnosis codes are accepted on the claim but are not evaluated in this iteration. Clinical necessity logic is out of scope.

---

## 9. Possible Extensions

These are scoped extensions that stay within the practicum's runnable-demo constraint:

- Asynchronous processing via a lightweight in-process queue to illustrate event-driven patterns
- Prior authorization workflow as a standalone Authorization Manager service
- Fraud, waste, and abuse (FWA) detection layer between Claims Manager and Benefits Determiner
- 835 ERA and EOB generation service downstream of Claims Manager
- API gateway with OAuth 2.0 and rate limiting (using a local mock identity provider)
- Full COB logic for members with dual coverage

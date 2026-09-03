# Spec: Member Claims History — Claims Manager

**Intake ID:** 0006-member-claims-history
**Pod:** claim-runner
**Pod spec number:** claim-runner/008
**Status:** Allocated
**Constitution references:** Technology Stack, Data Layer, Spec Scope, Adjudication Flow
**Source:** control pod session 2026-09-03
**Decomposed from:** pods/claim-runner/specs/0006-member-claims-history/spec.md
**Blocked on:** claim-runner/006 — Data Service must expose GET /claims?member_id=
before this spec can be implemented.

---

## Goal

Add a `GET /claims?member_id={member_id}` route to Claims Manager (port 8080)
that delegates to the Data Service query added in claim-runner/006, sorts the
results by `adjudicated_at` descending, and returns them in the standardised
response shape.

**This spec cannot be implemented until claim-runner/006 is merged.** The Data
Service must expose `GET /claims?member_id=` before the Claims Manager proxy
can call it.

---

## Out of Scope

- Pagination or cursor-based scrolling
- Filtering by status, date range, or procedure code
- Any change to the Data Service, Benefits Determiner, or Pricer
- Any change to the adjudication flow or the POST /claims/batch path

---

## Functional Requirements

### FR-1 — Member claims history route

`GET /claims?member_id={member_id}` on Claims Manager (port 8080) calls
`GET /claims?member_id={member_id}` on the Data Service (claim-runner/006) and
assembles the response. It sorts the returned records in reverse chronological
order by `adjudicated_at` (most recent first) before returning.

The `member_id` query parameter is required. Omitting it returns `422`.

### FR-2 — Response shape

The top-level response is an object with `member_id` (echoed from the query
parameter) and `results` (array). Each entry in `results` has exactly the same
shape as a single item in `POST /claims/batch results` and as
`GET /claims/{claim_id}`.

An unknown `member_id` or a member with no adjudicated claims returns `200` with
an empty `results` array, not `404`.

### FR-3 — Health check

`GET /health` on Claims Manager continues to return `200`.

---

## Domain Model

### GET /claims?member_id={id} — Request

| Parameter | Type | Required | Description |
|---|---|---|---|
| `member_id` | query string | Yes | Member identifier to retrieve history for |

### GET /claims?member_id={id} — Response

```json
{
  "member_id": "MBR-10042",
  "results": [
    {
      "claim_id": "CLM-20250901-002",
      "status": "PAID",
      "adjudicated_at": "2025-09-01T14:31:00Z",
      "totals": {
        "billed_amount": 250.00,
        "allowed_amount": 115.00,
        "member_liability": 30.00,
        "payer_liability": 85.00
      },
      "denial_reasons": [],
      "errors": [],
      "line_detail": [ { "..." } ]
    },
    {
      "claim_id": "CLM-20250901-001",
      "status": "DENIED",
      "adjudicated_at": "2025-09-01T14:30:00Z",
      "totals": { "billed_amount": 250.00, "allowed_amount": 0.00, "member_liability": 0.00, "payer_liability": 0.00 },
      "denial_reasons": [{ "code": "NOT_COVERED" }],
      "errors": [],
      "line_detail": [ { "..." } ]
    }
  ]
}
```

Results are sorted by `adjudicated_at` descending (most recent first). Each entry
in `results` is structurally identical to a `GET /claims/{claim_id}` response.
The Data Service response uses `records`; Claims Manager renames the array to
`results`.

### GET /claims?member_id={id} — Empty result

```json
{
  "member_id": "MBR-UNKNOWN",
  "results": []
}
```

### Status codes

| HTTP Status | Condition |
|---|---|
| `200` | Query executed; `results` sorted by `adjudicated_at` desc |
| `422` | `member_id` query parameter is missing |
| `503` | Data Service returned `5xx` or was unreachable |

---

## Integration

### Claims Manager → Data Service (member query) — NEW

```
GET http://${DATA_SERVICE_URL}/claims?member_id={member_id}
```

`DATA_SERVICE_URL` defaults to `http://localhost:8083`.

**Provided by claim-runner/006 — this spec is blocked until that PR is merged.**

If the Data Service returns `5xx` or is unreachable, Claims Manager returns `503`.

### Existing routes unchanged

`POST /claims/batch`, `GET /claims/{claim_id}`, and `GET /health` on Claims Manager
are not modified. The new route is additive.

---

## Non-functional Requirements

- **Language / framework:** Python 3.11+, FastAPI (constitution: Technology Stack)
- **Additive change only:** No existing Claims Manager routes are modified
- **Sort order:** Most-recently-adjudicated first; ties in `adjudicated_at` may be
  returned in any stable order
- **No direct data access:** All data flows through the Data Service.
  (Constitution: Data Layer)

---

## Edge Cases

| Case | Expected behaviour |
|---|---|
| `member_id` omitted from query | `422` |
| `member_id` matches no claims | `200` with `results: []`; not `404` |
| `member_id` identifies a known member with no claims | `200` with `results: []` |
| Single claim on file for the member | `results` array with one entry |
| Data Service returns `5xx` | Claims Manager returns `503` |
| Data Service unreachable | Claims Manager returns `503` |

---

## Constraints

- Claims Manager only. Data Service query endpoint is specified in
  claim-runner/006.
- This spec is blocked on claim-runner/006. Do not begin implementation until
  the Data Service PR is merged.
- No direct file access by Claims Manager. (Constitution: Data Layer)
- Claims Manager remains the sole external entry point.
  (Constitution: Adjudication Flow)

---

## Acceptance Criteria

1. Two claims for the same member are retrievable together in reverse-chronological
   order.

   ```
   Setup: submit CLM-20250901-001 (for MBR-10042) at T=14:30, then
          CLM-20250901-002 (for MBR-10042) at T=14:31.

   GET /claims?member_id=MBR-10042
   → 200
   {
     "member_id": "MBR-10042",
     "results": [
       { "claim_id": "CLM-20250901-002", "adjudicated_at": "...14:31...", ... },
       { "claim_id": "CLM-20250901-001", "adjudicated_at": "...14:30...", ... }
     ]
   }
   ```

2. An unknown `member_id` returns an empty `results` array, not a `404`.

   ```
   GET /claims?member_id=MBR-UNKNOWN
   → 200 { "member_id": "MBR-UNKNOWN", "results": [] }
   ```

3. A known member with no adjudicated claims returns an empty `results` array.

   ```
   GET /claims?member_id=MBR-10001
   → 200 { "member_id": "MBR-10001", "results": [] }
   ```

4. Each entry in `results` has the same shape as `GET /claims/{claim_id}`.

5. Omitting `member_id` returns `422`.

6. `GET /health` returns `200 { "status": "UP" }` after the new route is
   deployed.

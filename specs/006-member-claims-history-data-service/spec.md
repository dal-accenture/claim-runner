# Spec: Member Claims History — Data Service

**Intake ID:** 0006-member-claims-history
**Pod:** claim-runner
**Pod spec number:** claim-runner/006
**Status:** Allocated
**Constitution references:** Technology Stack, Data Layer, Spec Scope
**Source:** control pod session 2026-09-03
**Decomposed from:** pods/claim-runner/specs/0006-member-claims-history/spec.md

---

## Goal

Add a member query endpoint to the Data Service. `GET /claims?member_id={member_id}`
scans the in-memory claims store and returns every claim record whose `member_id`
matches the query parameter. This is the provider side of the member claims history
feature; the Claims Manager proxy that consumes this endpoint is specified separately
in claim-runner/008.

---

## Out of Scope

- Sorting — the Data Service returns records in unspecified order; the caller sorts
- Pagination or cursor-based scrolling
- Filtering by status, date range, or procedure code
- Any change to Claims Manager, Benefits Determiner, or Pricer
- Any change to the adjudication flow or the POST /claims/batch path

---

## Functional Requirements

### FR-1 — Member claims query

`GET /claims?member_id={member_id}` on the Data Service (port 8083) scans the
in-memory claims store and returns every claim record whose `member_id` matches
the query parameter.

If no records match, the service returns `200` with an empty `records` array. A
`member_id` parameter that matches no member is not an error at this layer — the
store does not validate member existence for query requests.

The `member_id` query parameter is required. Omitting it returns `422`.

### FR-2 — Health check

`GET /health` on the Data Service continues to return `200`.

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
  "records": [
    { "<full claim ledger record>" },
    { "<full claim ledger record>" }
  ]
}
```

The Data Service response uses `records`. The order of records in the array is
unspecified; the Data Service does not sort. Callers are responsible for any
ordering they require.

### GET /claims?member_id={id} — Empty result

```json
{
  "member_id": "MBR-UNKNOWN",
  "records": []
}
```

### Status codes

| HTTP Status | Condition |
|---|---|
| `200` | Query executed; `records` contains zero or more matching records |
| `422` | `member_id` query parameter is missing |

---

## Non-functional Requirements

- **Language / framework:** Python 3.11+, FastAPI (constitution: Technology Stack)
- **Additive change only:** No existing Data Service routes are modified
- **In-memory only:** The query scans the in-memory store; no disk access
  (constitution: Data Layer, Decision 0010)

---

## Edge Cases

| Case | Expected behaviour |
|---|---|
| `member_id` omitted from query | `422` |
| `member_id` matches no claims | `200` with `records: []` |
| `member_id` identifies a known member with no claims | `200` with `records: []` |
| Single claim on file for the member | `records` array with one entry |

---

## Constraints

- Data Service only. Claims Manager proxy is specified in claim-runner/008.
- No direct file access. (Constitution: Data Layer)
- No sorting — the Data Service returns records in unspecified order.

---

## Acceptance Criteria

1. `GET /claims?member_id=MBR-10042` returns `200` with a `records` array
   containing all claims for that member.

2. `GET /claims?member_id=MBR-UNKNOWN` returns `200` with `records: []`
   (not `404`).

3. `GET /claims` (no `member_id` parameter) returns `422`.

4. `GET /health` returns `200` after the new query path is deployed.

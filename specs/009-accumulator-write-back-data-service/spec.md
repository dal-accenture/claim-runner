# Spec: Live Accumulator Write-back — Data Service

**Intake ID:** 0008-accumulator-write-back
**Pod:** claim-runner
**Pod spec number:** claim-runner/009
**Status:** Allocated
**Constitution references:** Technology Stack, Data Layer, Spec Scope
**Source:** control pod session 2026-09-03
**Decomposed from:** pods/claim-runner/specs/0008-accumulator-write-back/spec.md

---

## Goal

Add an accumulator delta endpoint to the Data Service so that Claims Manager can
apply year-to-date spending deltas after each successful adjudication. This is
the provider side of the accumulator write-back feature; the Claims Manager
orchestration is specified separately in claim-runner/011.

---

## Out of Scope

- Writing accumulator state to `members.json` on disk — the data layer remains
  in-memory only (constitution: Data Layer, Decision 0010)
- Family deductible or family OOP max accumulators
- Accumulator reset at plan year rollover
- Any change to Claims Manager, Benefits Determiner, or Pricer

---

## Functional Requirements

### FR-1 — Accumulator delta endpoint

`PATCH /members/{member_id}/accumulators` applies additive delta values to the
member's in-memory accumulator record.

Request body:

```json
{
  "individual_deductible_delta": 375.00,
  "individual_oop_delta": 405.00
}
```

Both fields are required. Both must be non-negative numbers. A negative delta
returns `422`. A delta of `0.00` is accepted and is a no-op for that accumulator.

The service applies each delta atomically to the in-memory record:

```
individual_deductible.used = individual_deductible.used + individual_deductible_delta
individual_oop_max.used    = individual_oop_max.used    + individual_oop_delta
```

After applying, the service recomputes `met` for each accumulator:

```
individual_deductible.met = (individual_deductible.used >= individual_deductible.limit)
individual_oop_max.met    = (individual_oop_max.used    >= individual_oop_max.limit)
```

`used` is clamped to at most `limit` for `individual_oop_max` (the member cannot
exceed the OOP ceiling). `individual_deductible.used` may exceed
`individual_deductible.limit` by the delta amount if the deductible was nearly
met; it is not clamped.

Returns `200` with the full updated member record on success. Returns `404` if
the member is not found. Returns `422` if either delta is negative.

### FR-2 — Health check

`GET /health` on the Data Service continues to return `200`.

---

## Domain Model

### PATCH /members/{member_id}/accumulators — Request

```json
{
  "individual_deductible_delta": 375.00,
  "individual_oop_delta": 405.00
}
```

| Field | Type | Required | Constraint |
|---|---|---|---|
| `individual_deductible_delta` | number | Yes | >= 0 |
| `individual_oop_delta` | number | Yes | >= 0 |

### PATCH /members/{member_id}/accumulators — Response

```json
{
  "member_id": "MBR-10043",
  "first_name": "...",
  "last_name": "...",
  "accumulators": {
    "plan_year": "2025",
    "individual_deductible": { "limit": 500.00, "used": 500.00, "met": true },
    "family_deductible": null,
    "individual_oop_max": { "limit": 4000.00, "used": 530.00, "met": false },
    "family_oop_max": null
  }
}
```

Full member record is returned so callers can verify the resulting accumulator
state.

### PATCH /members/{member_id}/accumulators — Status codes

| HTTP Status | Condition |
|---|---|
| `200` | Deltas applied; full updated member record in body |
| `404` | Member not found |
| `422` | Either delta is negative |

---

## Non-functional Requirements

- **Language / framework:** Python 3.11+, FastAPI (constitution: Technology Stack)
- **In-memory only:** Accumulator state lives in the in-memory store; no disk
  writes (constitution: Data Layer, Decision 0010)
- **Atomicity:** The delta and `met` recomputation are applied in a single
  in-memory operation per PATCH request; concurrent requests to the same member
  are not expected in the practicum configuration
- **Additive change only:** No existing Data Service routes are modified

---

## Edge Cases

| Case | Expected behaviour |
|---|---|
| Zero delta for one field | `200`; that accumulator's `used` is unchanged |
| Claim that fully meets the deductible | `used` equals `limit`; `met` flips to `true` |
| Claim where OOP max is reached | `used` clamped to `limit`; `met` flips to `true` |
| Negative delta submitted | `422` |
| Member not found | `404` |

---

## Constraints

- Data Service only. Claims Manager orchestration is specified in
  claim-runner/011.
- Accumulator state is in-memory only; `members.json` is not written at runtime.
  (Constitution: Data Layer, Decision 0010)

---

## Acceptance Criteria

1. `PATCH /members/MBR-10043/accumulators` with valid positive deltas returns
   `200` with the full updated member record reflecting the new `used` values.

2. When the delta pushes `individual_oop_max.used` to or beyond `limit`, `used`
   is clamped to `limit` and `met` is `true`.

3. When the delta pushes `individual_deductible.used` to or beyond `limit`, `met`
   flips to `true`; `used` is not clamped.

4. `PATCH` with a negative delta returns `422`.

5. `PATCH` for an unknown member returns `404`.

6. Two sequential PATCH calls for the same member accumulate correctly — the
   second call applies its delta to the result of the first.

7. `GET /health` returns `200` after the new endpoint is deployed.

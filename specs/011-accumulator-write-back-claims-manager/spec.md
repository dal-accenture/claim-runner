# Spec: Live Accumulator Write-back — Claims Manager

**Intake ID:** 0008-accumulator-write-back
**Pod:** claim-runner
**Pod spec number:** claim-runner/011
**Status:** Allocated
**Constitution references:** Technology Stack, Data Layer, Spec Scope, Adjudication Flow
**Source:** control pod session 2026-09-03
**Decomposed from:** pods/claim-runner/specs/0008-accumulator-write-back/spec.md
**Blocked on:** claim-runner/009 — Data Service must expose
PATCH /members/{member_id}/accumulators before this spec can be implemented.

---

## Goal

Wire accumulator write-back into Claims Manager's adjudication flow. After the
Pricer returns a successful adjudication result, Claims Manager computes the
accumulator deltas and calls `PATCH /members/{member_id}/accumulators` on the
Data Service (claim-runner/009) before writing the claim to the ledger.

**This spec cannot be implemented until claim-runner/009 is merged.** The Data
Service must expose `PATCH /members/{member_id}/accumulators` before Claims
Manager can call it.

---

## Out of Scope

- Writing accumulator state to `members.json` on disk (constitution: Data Layer,
  Decision 0010)
- Family deductible or family OOP max accumulators
- Accumulator reset at plan year rollover
- Any change to the Data Service, Benefits Determiner, or Pricer

---

## Functional Requirements

### FR-1 — Write-back in the adjudication flow

After the Pricer returns and before writing the claim to the ledger, Claims Manager
computes the accumulator deltas from the Pricer response and calls the Data Service.

Compute deltas:

```
deductible_delta = accumulator_snapshot.individual_deductible_used_after
                 - accumulator_snapshot.individual_deductible_used_before
oop_delta        = accumulator_snapshot.individual_oop_used_after
                 - accumulator_snapshot.individual_oop_used_before
```

Call `PATCH /members/{member_id}/accumulators` with these deltas (claim-runner/009).

If the PATCH returns `503` or the Data Service is unreachable, Claims Manager
returns `503` to the caller and does not write the claim to the ledger.

If the PATCH returns `404` (member no longer in the Data Service), Claims Manager
returns `503` with a descriptive error and does not write the claim.

### FR-2 — Write-back only on successful adjudications

Accumulator write-back occurs only when the claim produces a `PAID` or
`PARTIALLY_PAID` status. `DENIED`, `VALIDATION_ERROR`, and `CONFLICT` outcomes
do not trigger a PATCH call.

A `DENIED` claim has no Pricer response and no deltas to apply. A
`VALIDATION_ERROR` or `CONFLICT` claim never reaches the Pricer.

### FR-3 — Health check

`GET /health` on Claims Manager continues to return `200`.

---

## Integration

### Claims Manager → Data Service (accumulator write-back) — NEW

```
PATCH http://${DATA_SERVICE_URL}/members/{member_id}/accumulators
Content-Type: application/json

{
  "individual_deductible_delta": <number>,
  "individual_oop_delta": <number>
}
```

`DATA_SERVICE_URL` defaults to `http://localhost:8083`.

**Provided by claim-runner/009 — this spec is blocked until that PR is merged.**

Called after the Pricer returns, before `POST /claims` writes the ledger entry.
If this call fails, the ledger write is aborted and the batch returns `503`.

### Updated: Claims Manager → Data Service inter-service contract

`architecture/inter-service-contracts.md` must be updated to document the new
PATCH endpoint in the Claims Manager → Data Service section.

---

## Non-functional Requirements

- **Language / framework:** Python 3.11+, FastAPI (constitution: Technology Stack)
- **In-memory only:** Accumulator state lives in the Data Service in-memory store;
  no disk writes (constitution: Data Layer, Decision 0010)
- **Additive to adjudication flow:** The PATCH call and delta computation are
  inserted after the Pricer returns. No existing adjudication behaviour changes.
- **No direct data access:** All data flows through the Data Service.
  (Constitution: Data Layer)

---

## Edge Cases

| Case | Expected behaviour |
|---|---|
| Copay-only claim (no deductible applied) | `deductible_delta = 0`; PATCH still called; `individual_deductible.used` unchanged |
| Claim that fully meets the deductible | `used` equals `limit`; `met` flips to `true` |
| Claim where OOP max is reached mid-claim | Pricer caps member liability; delta reflects capped amount; `individual_oop_max.met` flips to `true` |
| DENIED claim | No PATCH call; accumulators unchanged |
| VALIDATION_ERROR claim | No PATCH call; accumulators unchanged |
| Data Service returns `404` on PATCH | Claims Manager returns `503`; claim not written to ledger |
| Data Service unreachable during PATCH | Claims Manager returns `503`; claim not written to ledger |
| Two claims for same member submitted sequentially | Second claim reads the updated accumulator; running totals accumulate correctly |

---

## Constraints

- Claims Manager only. Data Service PATCH endpoint is specified in
  claim-runner/009.
- This spec is blocked on claim-runner/009. Do not begin implementation until
  the Data Service PR is merged.
- Accumulator state is in-memory only. (Constitution: Data Layer, Decision 0010)
- No direct file access by Claims Manager. (Constitution: Data Layer)
- Claims Manager is the sole orchestrator; it initiates the PATCH call. Benefits
  Determiner and Pricer do not call the Data Service PATCH endpoint.
  (Constitution: Adjudication Flow)

---

## Acceptance Criteria

1. After a PAID claim where only a copay applies (no deductible), the member's OOP
   accumulator increases by the copay amount; the deductible accumulator is
   unchanged.

   ```
   Setup: MBR-10042 individual_deductible = { used: 125.00, limit: 500.00, met: false }
                    individual_oop_max    = { used: 155.00, limit: 4000.00, met: false }

   POST /claims/batch { claim for MBR-10042, procedure 99213, billed 250.00 }
   → PAID, deductible_applied: 0.00, copay_applied: 30.00

   GET /members/MBR-10042 (via Data Service)
   → individual_deductible = { used: 125.00, met: false }  (unchanged)
     individual_oop_max    = { used: 185.00, met: false }  (155.00 + 30.00)
   ```

2. After a PAID claim where deductible is applied, the deductible accumulator
   increases correctly and `met` flips when the limit is reached.

   ```
   Setup: MBR-10043 individual_deductible = { used: 125.00, limit: 500.00, met: false }

   POST /claims/batch { claim for MBR-10043, procedure 42820, billed 5000.00 }
   → deductible_applied: 375.00

   GET /members/MBR-10043 → individual_deductible = { used: 500.00, met: true }
   ```

3. When the OOP max is reached, `met` flips to `true` and `used` is clamped to
   `limit`.

   ```
   Setup: MBR-10044 individual_oop_max = { used: 1950.00, limit: 2000.00, met: false }

   POST /claims/batch { claim for MBR-10044 with gross member_liability 75.00 }
   → Pricer caps member_liability to 50.00; oop_delta: 50.00

   GET /members/MBR-10044 → individual_oop_max = { used: 2000.00, met: true }
   ```

4. A DENIED claim does not update accumulators.

5. A VALIDATION_ERROR claim does not update accumulators.

6. Two sequential claims for the same member accumulate correctly.

   ```
   Setup: MBR-10042 individual_oop_max.used = 155.00
   First claim:  copay 30.00  → oop.used = 185.00
   Second claim: copay 40.00  → oop.used = 225.00
   GET /members/MBR-10042 → individual_oop_max.used = 225.00
   ```

7. `GET /health` on Claims Manager returns `200 { "status": "UP" }`.

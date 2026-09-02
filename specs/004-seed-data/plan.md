# Implementation Plan: Seed Data Generation

**Spec**: specs/004-seed-data/spec.md  
**Branch**: control-pod/architecture-speckit-memory  
**Date**: 2026-09-02

---

## Technical Context

| Item | Value |
|---|---|
| Language | Python 3.11+ |
| Dependencies | stdlib only — no pip packages |
| Entry point | `scripts/generate_seed_data.py` |
| Output directory | `data/` (repository root) |
| Random seed | `random.seed(42)` — fixed for reproducible committed files |
| Accumulator strategy | Claims-first organic — `used` derived from paid claim sums |
| Data model reference | `.specify/memory/data-model.md` v1.1 |
| Test location | `scripts/tests/test_seed_data.py` |

---

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| `GET /health` required | N/A | Script, not a service |
| Integration test before spec complete | ✅ PASS | pytest runs script as subprocess, validates output |
| No hardcoded ports or file paths | ✅ PASS | Output path taken from argument (default `./data`) |
| Env vars for configuration | ✅ PASS | `DATA_DIR` env var controls output directory |
| No external runtime dependencies | ✅ PASS | stdlib only |
| Startup/shutdown logged to stdout | N/A | Script, not a service |
| POSIX-compatible | ✅ PASS | Python 3.11+ stdlib |
| JSON files are the data layer | ✅ PASS | Script produces the four canonical seed files |
| Professional claims only | ✅ PASS | No 837I / institutional claim records |

No constitution departures required.

---

## Source Structure

```
scripts/
  generate_seed_data.py        # single-file generation script
scripts/tests/
  __init__.py
  test_seed_data.py            # integration tests
data/
  plans.json                   # 5 records (committed output)
  fee_schedules.json           # 25 records (committed output)
  members.json                 # 200 records (committed output)
  claims.json                  # ≥150 records (committed output)
```

Single-file script decision: the script has no callers and no shared utilities. Internal module structure would add navigation overhead with no benefit. Top-level functions per generation phase are sufficient.

---

## Generation Architecture

The script executes five phases in strict dependency order:

```
generate_plans()
  → generate_fee_schedules()
    → generate_members(plans)
      → generate_claims(members, plans, fee_schedules)
        → reconcile_accumulators(members, claims)
          → write_files(data_dir, plans, fee_schedules, members, claims)
```

### Phase descriptions

| Phase | Function | Output |
|---|---|---|
| 1 | `generate_plans()` | 5 plan dicts per FR-2 coverage matrix |
| 2 | `generate_fee_schedules()` | 25 fee schedule dicts per FR-3 rate table |
| 3 | `generate_members(plans)` | 200 member dicts per FR-4; accumulators zero-initialized |
| 4 | `generate_claims(members, plans, fee_schedules)` | ≥150 pre-adjudicated claim dicts per FR-5 volume table |
| 5 | `reconcile_accumulators(members, claims)` | Updates each member's `used` by summing `member_liability` across their paid claims; sets `met` flag |
| 6 | `write_files(...)` | Writes all four JSON files to `data_dir` |

Members reference `plan_id` (from plans). Claims reference `member_id` (from members) and `procedure_code` (from fee schedules). Accumulator reconciliation runs after all claims are finalized so it can sum the complete paid claim set.

---

## Pricing Logic (inline in script)

The script implements the same cost-sharing formulas as spec 0003-pricer. Pre-seeded claims must match exactly because the Data Service (spec 005) loads them without re-adjudicating.

**In-network, copay-applicable (`copay_applies_before_deductible: true`):**
- `copay_applied = copay`; `deductible_applied = 0`; `coinsurance_applied = 0`
- `member_liability = copay`
- Copay applies regardless of whether deductible is met

**In-network, coinsurance (`copay_applies_before_deductible: false`, `copay = 0`):**
- `coinsurance_applied = round(allowed_amount * coinsurance_pct, 2)`
- `member_liability = coinsurance_applied`

**Out-of-network:**
- `coinsurance_applied = round(oon_allowed_amount * 0.40, 2)`
- `member_liability = coinsurance_applied`
- OON `copay_applies_before_deductible` is always `false`; OON copay is always `$0.00`

**OOP max already met (at time of claim):**
- `member_liability = 0.00`; `payer_liability = allowed_amount`

**Always:** `payer_liability = round(allowed_amount - member_liability, 2)`

---

## Timestamps on Pre-Seeded Claims

The data model requires `received_at` and `adjudicated_at` (ISO 8601). For seed data:
- `received_at` = `date_of_service` + `T09:00:00Z`
- `adjudicated_at` = `date_of_service` + `T09:01:00Z`

These values are realistic enough for practicum use and simple to generate deterministically.

---

## Integration Test Strategy

`scripts/tests/test_seed_data.py` runs the script as a subprocess against a temp output directory, then validates:

| Check | AC |
|---|---|
| Record counts: 5 plans, 25 fee schedules, 200 members, ≥150 claims | AC-1, AC-2, AC-3, AC-5 |
| Every claim satisfies `member_liability + payer_liability == allowed_amount` | AC-6 |
| Every claim's `allowed_amount` matches the fee schedule for that code and network status | AC-7 |
| Every member's `met` flag is `true` iff `used >= limit` | AC-4 |
| Accumulator `used` reconciles against paid claim sums | AC-8 |
| At least one member per plan has PAID, DENIED, PARTIALLY_PAID outcomes | AC-9 |
| No claim references a missing `member_id` | AC-10 |
| No claim references a missing `procedure_code` | AC-11 |
| Script runs to completion without error | AC-12 |
| Spot-check ≥3 scenario coverage categories from the checklist | AC-13 |
| Script run twice produces byte-identical output (reproducibility) | FR-6 random seed |

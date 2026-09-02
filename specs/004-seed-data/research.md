# Research: Seed Data Generation

**Date**: 2026-09-02 | **Spec**: [spec.md](spec.md)

---

## Decision 1: Accumulator computation — claims-first organic

**Decision**: Generate claims organically (realistic cost-sharing for each member), then compute accumulator `used` values by summing `member_liability` across that member's paid claims. Set `met = True` when `used >= limit`.

**Rationale**: The spec's 20/50/20/10% distribution table is a target shape, not a hard constraint on exact bucket counts. Claims-first avoids a reverse-calculation problem (setting accumulator targets first and then generating claims to match), which is complex and error-prone when OOP max caps member liability. The organic approach guarantees mathematical consistency by construction: `used` is always exactly the sum of paid claims.

**Alternatives considered**: Bucket-first (assign each member to a state bucket, then generate claims to fill it). Rejected because hitting exact counts (40/100/40/20) requires reverse-calculating how many claims at what amounts reach the target — fragile under rounding and OOP max edge cases.

---

## Decision 2: Fixed random seed

**Decision**: `random.seed(42)` at the top of the script.

**Rationale**: Generated files are committed to source control. Without a fixed seed, every run produces different member IDs, accumulator values, and claim amounts — making git diffs unreadable and making the committed baseline unstable. Seed 42 is conventional and carries no special significance.

**Alternatives considered**: CLI `--seed` argument defaulting to 42. Rejected as unnecessary complexity for a practicum script with a single intended use.

---

## Decision 3: Pricing logic inline in script

**Decision**: Implement cost-sharing formulas directly in `generate_seed_data.py` rather than calling the Pricer service.

**Rationale**: The spec requires stdlib only (no pip dependencies). The Pricer is a running HTTP service, not a library, so importing or calling it from the generation script is not possible without adding `httpx` or `requests`. The pricing rules are fully specified in the fee schedule (copay, coinsurance_pct, copay_applies_before_deductible) and can be implemented in ~30 lines.

**Alternatives considered**: Extract pricing logic to a shared module. Rejected — the generation script has no callers and the Pricer service implements its own copy. Premature abstraction.

---

## Decision 4: Single-file script, no internal module structure

**Decision**: `generate_seed_data.py` is a single file with top-level functions per generation phase.

**Rationale**: The script has no callers, no shared utilities, and no tests that need to import individual functions. A flat function-per-phase structure is readable and navigable without any module overhead.

**Alternatives considered**: `scripts/seed/` package with `plans.py`, `members.py`, etc. Rejected — adds import plumbing that serves no practicum purpose.

---

## Decision 5: OON `copay_applies_before_deductible` always `false`

**Decision**: All 25 fee schedule records have `out_of_network.copay_applies_before_deductible: false` and `out_of_network.copay: 0.00`.

**Rationale**: Out-of-network reimbursement in this system is coinsurance-only (40% of OON allowed amount). There is no OON copay. Setting `copay_applies_before_deductible: false` is the correct and consistent value; the spec's fee schedule table omits the OON column because it is always the same.

---

## Decision 6: Timestamps on pre-seeded claims

**Decision**: `received_at = date_of_service + "T09:00:00Z"`, `adjudicated_at = date_of_service + "T09:01:00Z"` for all pre-seeded claims.

**Rationale**: The data model requires both fields (ISO 8601). The spec does not prescribe realistic intraday variation for seed data. A fixed offset is simple, deterministic, and sufficient for the practicum — no adjudication logic depends on the time component.

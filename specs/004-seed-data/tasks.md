# Tasks: Seed Data Generation

**Input**: Design documents from `specs/004-seed-data/`

**Sources**: spec.md (FR-1–FR-6 + scenario checklist), plan.md, research.md, quickstart.md

**Tests**: Included — constitution mandates integration tests (non-negotiable:
"The primary success path must have an integration test before a spec is marked
complete"). Tests run the script as a subprocess against a temp directory.

**Organization**: Three derived user stories in delivery order.

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files or independent data domains)
- **[Story]**: Derived user story this task belongs to (US1 / US2 / US3)
- All tasks include exact file paths

---

## Phase 1: Setup

**Purpose**: Create the script entry point and test fixture scaffolding.

- [x] T001 Create `scripts/generate_seed_data.py` with: `random.seed(42)` at top; `DATA_DIR` env var read (default `./data`); `main()` calling all generation functions in dependency order (`generate_plans` → `generate_fee_schedules` → `generate_members` → `generate_claims` → `reconcile_accumulators` → `write_files`); stdout summary at completion listing record counts and output path
- [x] T002 Create `scripts/tests/__init__.py` (empty) and `scripts/tests/test_seed_data.py` with a `seed_data` pytest fixture that: runs `python scripts/generate_seed_data.py` as a subprocess with `DATA_DIR` set to a `tmp_path` directory; asserts subprocess exits with code 0; loads and returns all four output JSON files as parsed dicts

---

## Phase 2: Foundational

**Purpose**: Static reference data — no upstream dependencies; both functions can be
implemented in parallel.

**⚠️ CRITICAL**: Members and claims cannot be generated until plans and fee schedules exist.

- [x] T003 [P] Implement `generate_fee_schedules()` in `scripts/generate_seed_data.py` — return a list of 25 dicts from the FR-3 rate table; each record: `procedure_code`, `in_network` block (`allowed_amount`, `copay`, `copay_applies_before_deductible`, `coinsurance_pct`), `out_of_network` block (`allowed_amount`, `copay: 0.00`, `copay_applies_before_deductible: false`, `coinsurance_pct: 0.40`); schema per `.specify/memory/data-model.md §4`
- [x] T004 [P] Implement `generate_plans()` in `scripts/generate_seed_data.py` — return a list of 5 plan dicts from FR-2; each record: `plan_id`, `plan_name`, `plan_type`, `effective_date: "2025-01-01"`, `termination_date: "2025-12-31"`, `covered_procedure_codes` list (each entry: `procedure_code`, `requires_auth: bool`), `excluded_procedure_codes` list (each entry: `procedure_code`, `exclusion_reason`), `network_provider_ids` list; schema per `.specify/memory/data-model.md §2`

**Checkpoint**: Plans and fee schedules are complete — member and claim generation can begin.

---

## Phase 3: US1 — Member Enrollment Data (P1) 🎯 MVP

**Goal**: `members.json` with 200 members, correct plan distribution, realistic demographics,
zero-initialized accumulators, and authorizations for Gold/Premier plans — loadable by the
Data Service at startup.

**Independent Test**: Run the script; assert `members.json` contains exactly 200 records;
all `plan_id` values reference a valid plan; accumulator `met` flags are all `false` (pre-reconciliation);
no required fields are missing.

- [x] T005 [US1] Implement `generate_members(plans, fee_schedules)` in `scripts/generate_seed_data.py` — 200 member dicts, IDs `MBR-10001` through `MBR-10200`; plan distribution 40/55/50/30/25 per FR-4; age-band and gender demographics per FR-4 tables (18–29: 30, 30–44: 60, 45–59: 70, 60+: 40; ~50% M / ~45% F / ~5% X); single enrollment record per member (`effective_date: "2025-01-01"`, `termination_date: null`); `family_deductible: null`, `family_oop_max: null`; accumulator `used: 0.00`, `met: false` for both `individual_deductible` and `individual_oop_max`; limits from plan deductible/OOP max values per FR-2; schema per `.specify/memory/data-model.md §3`
- [x] T006 [US1] Add authorization generation inside `generate_members()` in `scripts/generate_seed_data.py` — for 12 of 40 Gold members: add authorization records for a random subset of surgical ENT codes (`42820`, `42821`, `30140`, `30520`, `31240`); for 15 of 30 Premier members: add authorizations for a random subset of all 11 ENT codes; distribute authorization dates so ~half are active (2025-06-01 through 2025-12-31) and ~half are expired (2025-01-01 through 2025-05-31) to cover the auth-expired denial path
- [x] T007 [US1] Integration test in `scripts/tests/test_seed_data.py` — using the `seed_data` fixture: assert `len(members) == 200`; assert all `member_id` values are unique; assert all `plan_id` values appear in the plans output; assert accumulator `met == False` for all members; assert no member is missing `enrollment`, `accumulators`, or `authorizations` keys

**Checkpoint**: `members.json` valid and loadable. Data Service can start with plans, fee schedules, and members.

---

## Phase 4: US2 — Claims History & Financial Consistency (P2)

**Goal**: `claims.json` with ≥150 pre-adjudicated claims covering all 7 volume categories;
accumulator `used` values in `members.json` reconciled against paid claim sums;
all financial invariants hold.

**Independent Test**: Run the script; load `claims.json` — assert ≥150 records, every claim
satisfies `member_liability + payer_liability == allowed_amount`, no orphan `member_id` or
`procedure_code`. Then load `members.json` — for each member, sum `member_liability` across
their paid claims and assert it equals their recorded `used` values (within 0.01).

- [x] T008 [US2] Implement `_compute_line_pricing(fee_entry, network_status, member_oop_remaining)` helper in `scripts/generate_seed_data.py` — returns dict with `copay_applied`, `deductible_applied`, `coinsurance_applied`, `member_liability`, `payer_liability` per plan.md pricing logic: (a) in-net copay-applicable: `member_liability = copay`; (b) in-net coinsurance: `member_liability = round(allowed * coinsurance_pct, 2)`; (c) OON: `member_liability = round(oon_allowed * 0.40, 2)`; (d) OOP max reached: `member_liability = 0.00`; always: `payer_liability = round(allowed - member_liability, 2)`
- [x] T009 [US2] Implement `generate_claims(members, plans, fee_schedules)` in `scripts/generate_seed_data.py` — produce all 7 claim categories from FR-5: 70 paid in-net GP visits, 30 paid in-net ENT diagnostic, 10 paid in-net ENT surgical (with valid auth), 10 partially paid mixed lines, 10 denied excluded by plan, 10 denied auth-required not on file, 10 paid OON; date range 2025-01-01 through 2025-08-31; claim IDs `CLM-YYYYMMDD-NNN`; `received_at = date_of_service + "T09:00:00Z"`; `adjudicated_at = date_of_service + "T09:01:00Z"`; every claim and line satisfies `member_liability + payer_liability == allowed_amount`; denied claims: `totals.payer_liability = 0.00`, `member_liability = 0.00`, `allowed_amount = 0.00`; schema per `.specify/memory/data-model.md §5`
- [x] T010 [US2] Implement `reconcile_accumulators(members, claims)` in `scripts/generate_seed_data.py` — for each member: sum `member_liability` across their paid claims (`status == "PAID"` or `status == "PARTIALLY_PAID"`); update `accumulators.individual_deductible.used` and `accumulators.individual_oop_max.used` to reflect these sums (split: deductible portion up to `limit`, remainder to OOP); set `met = True` when `used >= limit`; mutates members in-place
- [x] T011 [US2] Integration test in `scripts/tests/test_seed_data.py` — assert `len(claims) >= 150`; for every claim, `round(member_liability + payer_liability, 2) == round(allowed_amount, 2)`; all `claim_id` values unique; all `member_id` values in members; all `line_detail[*].procedure_code` values in fee schedules (AC-6, AC-10, AC-11)
- [x] T012 [US2] Integration test in `scripts/tests/test_seed_data.py` — accumulator reconciliation: for each member with paid claims, assert `sum(c.totals.member_liability for c in their paid claims) ≈ member.accumulators.individual_deductible.used + member.accumulators.individual_oop_max.used` (tolerance 0.01); assert `met == True` iff `used >= limit` for all members (AC-4, AC-8)

**Checkpoint**: All four files generated, financially consistent, and accumulator-reconciled. Core acceptance criteria satisfied.

---

## Phase 5: End-to-End Validation

- [x] T013 [P] Integration test in `scripts/tests/test_seed_data.py` — reproducibility: run the script twice against two separate `tmp_path` directories; read each output file pair and assert contents are equal; confirms `random.seed(42)` produces stable committed files (FR-6)
- [x] T014 [P] Integration test in `scripts/tests/test_seed_data.py` — scenario coverage checklist: count claims by category and assert minimums from spec.md checklist: ≥20 in-net GP copay-only (ded not met), ≥5 ENT surgical with auth, ≥5 auth-required denials, ≥5 excluded denials, ≥5 OON claims, ≥3 OOP-max-met claims, ≥5 multi-line claims, ≥60 members with zero claims (AC-13)
- [x] T015 Start the Data Service with the generated seed data (`DATA_DIR=./data uvicorn main:app --port 8083` from `data_service/`) and confirm `GET /health` returns `{"status": "UP", "members": 200, "plans": 5, "fee_schedules": 25, "claims": <N>}` — this completes T027 deferred from `specs/005-data-service/tasks.md`

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — T003 and T004 parallelizable
- **Phase 3 (US1)**: Depends on Phase 2 (plans needed to assign member `plan_id` and limits)
- **Phase 4 (US2)**: Depends on Phase 3 (claims reference member IDs; reconciliation mutates members)
- **Phase 5 (End-to-End Validation)**: Depends on all user story phases complete

### User story dependencies

- **US1 (P1)**: Depends on Foundational (plans)
- **US2 (P2)**: Depends on US1 (members must exist before claims)
- **US3 (P3)**: Depends on US2 (claims must exist before scenario coverage can be validated)

### Within each user story

- T005 (generate_members) before T006 (add authorizations) before T007 (test)
- T008 (pricing helper) before T009 (generate_claims) before T010 (reconcile) before T011/T012 (tests)
- T013 and T014 parallelizable (both read-only validation against completed output)

---

## Parallel Opportunities

### Phase 2 (Foundational) — maximum parallelism

```
Parallel group:
  T003  generate_fee_schedules()   → scripts/generate_seed_data.py
  T004  generate_plans()           → scripts/generate_seed_data.py
```

Note: Both write to the same file but implement non-overlapping functions. In practice, implement sequentially in one editing session or carefully merge if parallelized across sessions.

### Phase 5 (End-to-End Validation) — parallel tests

```
Parallel group:
  T013  Reproducibility test        → scripts/tests/test_seed_data.py
  T014  Scenario coverage test      → scripts/tests/test_seed_data.py
```

---

## Implementation Strategy

### MVP (Phases 1–3 + T007)

1. Phase 1: Create script skeleton and test fixture
2. Phase 2: Implement plans + fee schedules
3. Phase 3: Implement members + authorization distribution
4. Validate: `members.json` loads cleanly into Data Service; T007 integration test passes

### Incremental delivery

1. Phases 1–3 → MVP: Data Service can start with plans, fee schedules, members
2. Phase 4: Claims + reconciliation → full financial dataset; Data Service loads all four files
3. Phase 5: Reproducibility + scenario coverage → spec complete; T027 from spec 005 unblocked

### Validation order

Run tests after each phase rather than at the end:
- After Phase 2: manually inspect a plan and fee schedule record for schema correctness
- After Phase 3: run T007 (`pytest scripts/tests/test_seed_data.py::test_members`)
- After Phase 4: run T011 + T012 (`pytest scripts/tests/test_seed_data.py -k "financial or accumulator"`)
- After Phase 5: `pytest scripts/tests/test_seed_data.py -v` — all tests green

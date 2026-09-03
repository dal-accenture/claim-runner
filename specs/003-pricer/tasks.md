# Tasks: Pricer

**Input**: Design documents from `specs/003-pricer/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/post-price.md, quickstart.md

**Organization**: Tasks grouped by user story. Each story is independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Setup

**Purpose**: Create the `pricer/` service directory and declare dependencies.

- [x] T001 Create `pricer/` directory with subdirectory `tests/` per plan.md Project Structure
- [x] T002 Create `pricer/requirements.txt` with: `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`

**Checkpoint**: `pip install -r pricer/requirements.txt` installs without error.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pydantic models, HTTP client with error hierarchy, and app skeleton — all three user stories depend on these.

⚠️ No user story work can begin until this phase is complete.

- [x] T003 Create `pricer/models.py` with all Pydantic models (`ClaimLine`, `PriceRequest`, `LineDetail`, `ClaimTotals`, `AccumulatorSnapshot`, `PriceResponse`) and exception classes (`DataServiceError`, `MemberNotFoundError`, `PlanNotFoundError`) exactly as specified in `specs/003-pricer/data-model.md`
- [x] T004 Create `pricer/data_client.py` — synchronous `httpx.Client` wrapper with `get_member(client, base_url, member_id)`, `get_plan(client, base_url, plan_id)`, `get_fee_schedule(client, base_url, procedure_code)`; raises `DataServiceError` on connection/timeout errors or unexpected status codes; raises `MemberNotFoundError` on 404 from `/members/{id}`; raises `PlanNotFoundError` on 404 from `/plans/{id}`; returns `None` on 404 from `/fee-schedules/{code}` (Pricer converts this to 422 inline)
- [x] T005 [P] Create `pricer/tests/__init__.py` (empty file)
- [x] T006 Create `pricer/main.py` — FastAPI app with: lifespan context manager opening/closing `httpx.Client` on `app.state`; exception handlers mapping `DataServiceError` → 503, `MemberNotFoundError` → 404, `PlanNotFoundError` → 404; reads `DATA_SERVICE_URL` env var (default `http://localhost:8083`) and `PORT` env var (default `8082`); logs `"Pricer listening on port {PORT}, DATA_SERVICE_URL={DATA_SERVICE_URL}"` on startup; `GET /health` returns `200 {"status": "ok"}`

**Checkpoint**: `python -c "from pricer.main import app"` runs without import errors. `GET /health` returns 200.

---

## Phase 3: User Story 1 — Allowed Amount Calculation + API Wiring (FR-1)

**Goal**: `POST /price` fetches member, plan, and fee schedules from the Data Service, computes the allowed amount for each line (scaled by units, capped at fee schedule rate), assembles a partial response (line `billed_amount`, `allowed_amount`, `contractual_adjustment` populated; cost-sharing fields zeroed), and returns correct 503/404/422 error responses.

**Independent Test**: POST with a valid member and in-network procedure — response has `line_detail[0].allowed_amount = min(billed_amount, fee_schedule_rate)` and `contractual_adjustment = billed_amount - allowed_amount`.

**Acceptance criteria covered**: AC-6 (OON rate selection), AC-7 (422 on unknown code), AC-10 (CO-45).

- [x] T007 [US1] Create `pricer/pricing.py` with `compute_allowed(line: ClaimLine, fee_schedule: dict, network_status: str) -> tuple[Decimal, Decimal]` — selects `in_network` or `out_of_network` block based on `network_status`; `line_billed = line.billed_amount * line.units`; `fee_rate = fee_schedule_block["allowed_amount"] * line.units`; returns `(min(line_billed, fee_rate), line_billed - min(line_billed, fee_rate))`
- [x] T008 [US1] Wire FR-1 into `POST /price` in `pricer/main.py` — call `data_client.get_member()` (raises `MemberNotFoundError` if 404); call `data_client.get_plan()` (raises `PlanNotFoundError` if 404); fetch fee schedule per unique procedure code using `data_client.get_fee_schedule()` (return 422 inline if `None`); call `compute_allowed()` per line; assemble partial `PriceResponse` with `line_detail` (cost-sharing fields = 0), zeroed `ClaimTotals`, empty `AccumulatorSnapshot` (zeros) — will be completed in US2/US3
- [x] T009 [US1] Write unit tests for allowed amount in `pricer/tests/test_pricing.py` — test: in-network uses `in_network.allowed_amount`, OON uses `out_of_network.allowed_amount`, `min(billed, fee_rate)` applied when billed exceeds fee rate, `units=2` doubles both billed and fee rate totals, `CO-45` present when billed > allowed, `contractual_adjustment=0` when billed <= fee rate

**Checkpoint**: `pytest pricer/tests/test_pricing.py -k allowed` passes. POST with unknown procedure code returns 422.

---

## Phase 4: User Story 2 — Cost-Sharing Algorithm (FR-2)

**Goal**: For each line, apply the 7-step cost-sharing algorithm (OOP pre-check → copay before deductible → deductible → copay after deductible → coinsurance → OOP cap → payer liability) using two running counters (`deductible_used_this_claim`, `oop_used_this_claim`) that accumulate across all lines in the request.

**Independent Test**: `pytest pricer/tests/test_pricing.py -k cost_sharing` covers all deductible/copay/coinsurance/OOP permutations.

**Acceptance criteria covered**: AC-1, AC-2, AC-3, AC-4, AC-5.

- [x] T010 [US2] Add `apply_cost_sharing(allowed_amount: Decimal, fs_block: dict, accumulators: dict, deductible_used_so_far: Decimal, oop_used_so_far: Decimal) -> tuple[LineDetail_cost_fields, Decimal, Decimal]` to `pricer/pricing.py` — implements FR-2 Steps 1–7 exactly; returns `(deductible_applied, copay_applied, coinsurance_applied, member_liability, payer_liability, new_deductible_used, new_oop_used)` where `new_*` values are passed to the next line's call
- [x] T011 [US2] Wire FR-2 into `POST /price` in `pricer/main.py` — initialize `deductible_used = Decimal("0")` and `oop_used = Decimal("0")` before the line loop; call `apply_cost_sharing()` per line passing accumulated counters; update counters with returned values; update `line_detail` entries with cost-sharing fields
- [x] T012 [US2] Write unit tests for cost-sharing in `pricer/tests/test_pricing.py` — test: copay-only (0% coinsurance, deductible untouched); deductible partially met; deductible fully met (coinsurance on full allowed); OOP already met (`individual_oop_max.met=true` → member_liability=0); OOP hit partway through multi-line claim (second line member_liability=0); OON coinsurance 40%; `member_liability + payer_liability == allowed_amount` invariant for every case

**Checkpoint**: `pytest pricer/tests/test_pricing.py -k cost_sharing` all pass. Multi-line claim with running counter test passes.

---

## Phase 5: User Story 3 — Claim Totals + Accumulator Snapshot (FR-3, FR-4)

**Goal**: Sum per-line financials into `ClaimTotals` and produce an `AccumulatorSnapshot` with before/after deductible and OOP values. Complete the `PriceResponse`.

**Independent Test**: POST response has `totals.member_liability + totals.payer_liability == totals.allowed_amount` and `accumulator_snapshot._after == _before + this_claim_applied`.

**Acceptance criteria covered**: AC-8, AC-9.

- [x] T013 [US3] Add `compute_totals(line_details: list) -> ClaimTotals` and `compute_snapshot(accumulators: dict, deductible_used_this_claim: Decimal, oop_used_this_claim: Decimal) -> AccumulatorSnapshot` to `pricer/pricing.py` — totals sum `billed_amount`, `allowed_amount`, `member_liability`, `payer_liability` across lines; snapshot sets `_before` from seeded values and `_after = _before + this_claim_applied`
- [x] T014 [US3] Wire FR-3 + FR-4 into `POST /price` in `pricer/main.py` — after line loop completes, call `compute_totals()` and `compute_snapshot()` with final counter values; assemble and return the complete `PriceResponse`
- [x] T015 [US3] Write unit tests for totals and snapshot in `pricer/tests/test_pricing.py` — test: totals sum correctly across two lines; `member_liability + payer_liability == allowed_amount` per line and in totals; snapshot `_after` equals `_before + this_claim_deductible`; snapshot `_after` equals `_before + this_claim_oop`

**Checkpoint**: `pytest pricer/tests/test_pricing.py` all pass. Full POST /price response matches shape in `contracts/post-price.md`.

---

## Phase 6: End-to-End Validation

**Purpose**: Integration tests against all 12 acceptance criteria; quickstart validation against live seed data.

- [x] T016 Write integration tests in `pricer/tests/test_api.py` using FastAPI `TestClient` + `respx` — cover: AC-1 (GP copay, member_liability=copay), AC-2 (surgical, deductible+coinsurance), AC-3 (deductible already met), AC-4 (OOP already met, member_liability=0), AC-5 (OOP hit mid multi-line claim), AC-6 (OON uses out_of_network rate), AC-7 (unknown procedure code → 422), AC-8 (accumulator_snapshot _before/_after correct), AC-9 (totals invariant), AC-10 (CO-45 on contractual adjustment), AC-11 (GET /health → 200), AC-12 (Data Service unreachable → 503); also test member not found → 404, plan not found → 404
- [x] T017 Run `pytest pricer/tests/ -v` and verify all tests pass (no live Data Service required)
- [x] T018 Start Pricer against live seed data (`DATA_SERVICE_URL=http://localhost:8083`) from repo root and run `quickstart.md` Scenarios 1–5 manually, verifying expected responses

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1
- **US1 (Phase 3)**: Depends on Phase 2 — `pricing.py`, `data_client.py`, and `main.py` skeleton must exist
- **US2 (Phase 4)**: Depends on Phase 3 — needs allowed amount computed before cost-sharing can be applied; needs fee schedule block available in `pricing.py`
- **US3 (Phase 5)**: Depends on Phase 4 — running counters must be finalized before snapshot and totals
- **End-to-End Validation (Phase 6)**: Depends on Phase 5 — all pricing logic must be complete

### Parallel Opportunities

- T005 (`tests/__init__.py`) can run in parallel with T003–T004
- T007 (`pricing.py` kernel) can run in parallel with T008 (`main.py` wiring in US1) — different coordination points but both write different sections; write T007 first, then T008
- Within Phase 5: T013 (`pricing.py`) can run in parallel with T014 (`main.py`) after T013 is done

---

## Parallel Example: Phase 4 (US2)

```
# T010 (apply_cost_sharing in pricing.py) completes first
# Then in parallel:
Task T011: Wire FR-2 into main.py   (main.py)
Task T012: Unit tests for cost-sharing (tests/test_pricing.py)
```

---

## Implementation Strategy

### MVP (US1 only — Phases 1–3)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational — models, data_client, app skeleton, health
3. Complete Phase 3: US1 — allowed amount, 503/404/422 error handling
4. **STOP and VALIDATE**: POST with known member returns correct `allowed_amount`; unknown code returns 422; Data Service down returns 503
5. This MVP proves the full Data Service integration works before adding business logic

### Incremental Delivery

1. Phases 1–3 → Allowed amount (MVP)
2. Phase 4 → Add cost-sharing (core value)
3. Phase 5 → Add totals + snapshot (complete response)
4. Phase 6 → Full test coverage, quickstart validation

---

## Notes

- `billed_amount` and fee schedule `allowed_amount` are per-unit; multiply by `units` for line totals — see research.md Decision 4
- Two running counters per request: `deductible_used_this_claim` and `oop_used_this_claim` — see research.md Decision 3
- Fetch fee schedules once per unique procedure code, cache in a dict for the request — see research.md Decision 5
- `DataServiceError` → 503; `MemberNotFoundError` → 404; `PlanNotFoundError` → 404; procedure code 404 → 422 inline
- Constitution requires integration test before spec is marked complete — T016/T017 satisfy this

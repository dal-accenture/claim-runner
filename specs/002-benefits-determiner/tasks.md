# Tasks: Benefits Determiner

**Input**: Design documents from `specs/002-benefits-determiner/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/post-benefits-determine.md, quickstart.md

**Organization**: Tasks grouped by user story. Each story is independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Setup

**Purpose**: Create the `benefits_determiner/` service directory and declare dependencies.

- [x] T001 Create `benefits_determiner/` directory with subdirectory `tests/` per plan.md Project Structure
- [x] T002 Create `benefits_determiner/requirements.txt` with: `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`

**Checkpoint**: `pip install -r benefits_determiner/requirements.txt` installs without error.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure that all three user stories depend on — Pydantic models, HTTP client, app skeleton with error handler.

⚠️ No user story work can begin until this phase is complete.

- [x] T003 Create `benefits_determiner/models.py` with `DetermineRequest`, `LineDetermination`, `DetermineResponse`, and `DataServiceError` exactly as specified in `specs/002-benefits-determiner/data-model.md`
- [x] T004 Create `benefits_determiner/data_client.py` — synchronous `httpx.Client` wrapper with `get_member(client, base_url, member_id) -> dict` and `get_plan(client, base_url, plan_id) -> dict`; raises `DataServiceError` on `httpx.ConnectError`, timeout, or any non-200/non-404 response; returns `None` on 404
- [x] T005 [P] Create `benefits_determiner/tests/__init__.py` (empty file)
- [x] T006 Create `benefits_determiner/main.py` — FastAPI app with: lifespan context manager that opens/closes `httpx.Client` on `app.state`; FastAPI exception handler mapping `DataServiceError` → `503 {"detail": "Data Service unavailable"}`; reads `DATA_SERVICE_URL` env var (default `http://localhost:8083`) and `PORT` env var (default `8081`); logs `"Benefits Determiner listening on port {PORT}, DATA_SERVICE_URL={DATA_SERVICE_URL}"` to stdout on startup

**Checkpoint**: `python -c "from benefits_determiner.main import app"` runs without import errors.

---

## Phase 3: User Story 1 — Member Eligibility + Health Endpoint (FR-1, FR-5)

**Goal**: `GET /health` returns 200; `POST /benefits/determine` returns early with `NOT_ELIGIBLE` or `PLAN_TERMINATED` when the member is ineligible; returns 503 when the Data Service is unreachable.

**Independent Test**: Run `pytest benefits_determiner/tests/test_determination.py -k eligibility` against the unit tests; call `GET /health` and verify 200.

**Acceptance criteria covered**: AC-2, AC-10, AC-11, AC-12.

- [x] T007 [US1] Implement `GET /health` in `benefits_determiner/main.py` — returns `200 {"status": "ok"}`
- [x] T008 [US1] Create `benefits_determiner/determination.py` with `check_eligibility(enrollment: dict, date_of_service: date) -> tuple[bool, str | None]` — returns `(False, "PLAN_TERMINATED")` if `termination_date` is set and precedes `date_of_service`; `(True, None)` otherwise
- [x] T009 [US1] Wire FR-1 into `POST /benefits/determine` in `benefits_determiner/main.py` — call `data_client.get_member()`; return `NOT_ELIGIBLE` early-return response if member is `None` (404); call `check_eligibility()`; return `PLAN_TERMINATED` early-return response if not eligible; both early returns use the shape in `contracts/post-benefits-determine.md`
- [x] T010 [US1] Write unit tests for eligibility in `benefits_determiner/tests/test_determination.py` — test active enrollment passes, terminated enrollment returns PLAN_TERMINATED, termination_date null is treated as active

**Checkpoint**: `pytest benefits_determiner/tests/test_determination.py -k eligibility` — all tests pass. Manual `GET /health` returns 200.

---

## Phase 4: User Story 2 — Network Status (FR-2)

**Goal**: After a member is confirmed eligible, `POST /benefits/determine` calls the Data Service for the plan and sets `network_status` to `IN_NETWORK` or `OUT_OF_NETWORK` based on whether `provider_id` is in `plan.network_provider_ids`. Out-of-network is not a denial.

**Independent Test**: POST with an eligible member and a provider not in the plan network — response must have `network_status: "OUT_OF_NETWORK"`, `eligible: true`, and no denial.

**Acceptance criteria covered**: AC-7.

- [x] T011 [US2] Add `check_network(plan: dict, provider_id: str) -> str` to `benefits_determiner/determination.py` — returns `"IN_NETWORK"` if `provider_id` in `plan["network_provider_ids"]`, else `"OUT_OF_NETWORK"`
- [x] T012 [US2] Wire FR-2 into `POST /benefits/determine` in `benefits_determiner/main.py` — after eligibility confirmed, call `data_client.get_plan()` using `enrollment["plan_id"]`; call `check_network()`; set `network_status` on the response (placeholder `line_determinations: []` and `overall_covered: false` until US3)

**Checkpoint**: POST with an eligible member and out-of-network provider returns `network_status: "OUT_OF_NETWORK"` with no denial_reason.

---

## Phase 5: User Story 3 — Procedure Code Determination + Roll-Up (FR-3, FR-4)

**Goal**: For each procedure code, apply exclusion → coverage → authorization checks in order and produce a `LineDetermination`. Set `overall_covered: true` only when all lines are covered.

**Independent Test**: `pytest benefits_determiner/tests/test_determination.py -k procedure` covers all line-level denial paths.

**Acceptance criteria covered**: AC-1, AC-3, AC-4, AC-5, AC-6, AC-8, AC-9.

- [x] T013 [US3] Add `evaluate_line(code: str, plan: dict, authorizations: list, date_of_service: date) -> LineDetermination` to `benefits_determiner/determination.py` implementing the three-step check in FR-3 order: (1) exclusion — if `code` matches any `entry["code"]` in `plan["excluded_procedure_codes"]`, return `covered: false, denial_reason: NOT_COVERED`; (2) coverage — if `code` not in any `entry["code"]` in `plan["covered_procedure_codes"]`, return `covered: false, denial_reason: NOT_COVERED`; (3) auth — if matching covered entry has `requires_auth: true`, search `authorizations` for `auth.procedure_code == code AND auth.authorized_date <= date_of_service <= auth.expiration_date`; if found, return `covered: true, auth_on_file: auth["auth_id"]`; if not found, return `covered: false, denial_reason: AUTH_REQUIRED_NOT_ON_FILE`
- [x] T014 [US3] Add `compute_overall_covered(line_determinations: list[LineDetermination]) -> bool` to `benefits_determiner/determination.py` — returns `True` only if every entry has `covered: true`
- [x] T015 [US3] Wire FR-3 + FR-4 into `POST /benefits/determine` in `benefits_determiner/main.py` — iterate `request.procedure_codes`, call `evaluate_line()` for each, collect results, call `compute_overall_covered()`, assemble and return the full `DetermineResponse`
- [x] T016 [US3] Write unit tests for procedure determination in `benefits_determiner/tests/test_determination.py` — test excluded code → NOT_COVERED, absent code → NOT_COVERED, exclusion takes precedence over coverage, code with auth + valid auth → covered with auth_on_file, code with auth + no auth → AUTH_REQUIRED_NOT_ON_FILE, code with auth + expired auth → AUTH_REQUIRED_NOT_ON_FILE, code without auth requirement → covered

**Checkpoint**: `pytest benefits_determiner/tests/test_determination.py` — all tests pass. Full determination smoke test via curl/PowerShell against live Data Service.

---

## Phase 6: End-to-End Validation

**Purpose**: Integration test coverage for all 12 acceptance criteria; quickstart validation against live seed data.

- [x] T017 Write integration tests in `benefits_determiner/tests/test_api.py` using FastAPI `TestClient` + `respx` to mock `httpx` Data Service calls — cover: AC-1 (eligible, covered, no auth), AC-2 (PLAN_TERMINATED), AC-3 (excluded procedure), AC-4 (auth on file, valid), AC-5 (auth required, not on file), AC-6 (expired auth → AUTH_REQUIRED_NOT_ON_FILE), AC-7 (OON provider, not a denial), AC-8 (mixed lines, overall_covered false), AC-9 (all lines covered, overall_covered true), AC-10 (missing field → 422), AC-11 (GET /health → 200), AC-12 (Data Service unreachable → 503)
- [x] T018 Run `pytest benefits_determiner/tests/ -v` and verify all tests pass (no live Data Service required)
- [ ] T019 Start Benefits Determiner against live seed data (`DATA_SERVICE_URL=http://localhost:8083`) and run `quickstart.md` Scenarios 1–5 manually, verifying expected responses

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1
- **US1 (Phase 3)**: Depends on Phase 2 — `determination.py` and `main.py` skeleton must exist
- **US2 (Phase 4)**: Depends on Phase 3 — needs eligibility gate already wired in `main.py`
- **US3 (Phase 5)**: Depends on Phase 4 — needs plan object already fetched and available
- **End-to-End Validation (Phase 6)**: Depends on Phase 5 — all determination logic must be complete

### Parallel Opportunities

- T005 (tests `__init__.py`) can run in parallel with T003–T004
- Within Phase 3: T008 (determination.py) can run in parallel with T007 (health endpoint) — different files
- Within Phase 5: T013 and T014 both go in `determination.py` — write sequentially; T015 (`main.py`) can follow T013/T014 in parallel with T016 (test file — different file)

---

## Parallel Example: Phase 5

```
# Launch in parallel:
Task T013: evaluate_line() in benefits_determiner/determination.py
Task T014: compute_overall_covered() in benefits_determiner/determination.py

# Then wire both into main.py:
Task T015: Wire FR-3 + FR-4 into main.py (depends on T013, T014)

# In parallel with T015:
Task T016: Write unit tests in tests/test_determination.py (different file)
```

---

## Implementation Strategy

### MVP (US1 only — Phases 1–3)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational — models, data_client, app skeleton
3. Complete Phase 3: US1 — health + eligibility
4. **STOP and VALIDATE**: `GET /health` returns 200; POST with unknown member returns NOT_ELIGIBLE; POST with terminated member returns PLAN_TERMINATED; POST with Data Service down returns 503
5. This MVP exercises the full lifecycle of the service

### Incremental Delivery

1. Phases 1–3 → Eligibility-aware service (MVP)
2. Phase 4 → Add network status
3. Phase 5 → Add procedure-level determination (full feature)
4. Phase 6 → Full test coverage, quickstart validation

---

## Notes

- `"code"` key (not `"procedure_code"`) when iterating `plan.covered_procedure_codes` and `plan.excluded_procedure_codes` — see research.md Decision 4
- Parse dates as `datetime.date` objects before comparing — see research.md Decision 5
- `httpx.Client` lives on `app.state.http_client` (lifespan) — see research.md Decision 6
- Tests use `respx` — no live Data Service required for test suite
- Constitution requires integration test before spec is marked complete — T017/T018 satisfy this

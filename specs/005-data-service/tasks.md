# Tasks: Data Service API

**Input**: Design documents from `specs/005-data-service/`

**Sources**: spec.md (FR-1–FR-6 → derived user stories), plan.md, data-model.md,
contracts/http.md, research.md

**Tests**: Included — constitution mandates integration tests (non-negotiable:
"The primary success path must have an integration test before a spec is marked
complete"). No separate test framework setup task needed; pytest + httpx are the
only dependencies.

**Organization**: Three derived user stories in delivery order.

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (touches different files, no in-flight dependencies)
- **[Story]**: Derived user story this task belongs to (US1 / US2 / US3)
- All tasks include exact file paths

---

## Phase 1: Setup

**Purpose**: Project initialization — directory structure and dependencies.

- [ ] T001 Create `data_service/main.py` with an empty FastAPI app stub (no routes) and `data_service/requirements.txt`
- [ ] T002 Add `fastapi` and `uvicorn[standard]` to `data_service/requirements.txt`
- [ ] T003 [P] Create `data_service/tests/conftest.py` with: (a) `TestClient` fixture wrapping the FastAPI app; (b) `tmp_data_dir` fixture writing minimal valid JSON seed files (1 member, 1 plan, 1 fee schedule, 1 claim) to a temp directory and setting `DATA_DIR` env var

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Data loading and lifecycle infrastructure that every route handler depends on.

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [ ] T004 Declare four module-level dict stores (`_members`, `_plans`, `_fee_schedules`, `_claims`) and one `asyncio.Lock` (`_lock`) at the top of `data_service/main.py`
- [ ] T005 Implement the FastAPI `lifespan` context manager in `data_service/main.py`: load `members.json` → `_members` (keyed by `member_id`), `plans.json` → `_plans` (keyed by `plan_id`), `fee_schedules.json` → `_fee_schedules` (keyed by `procedure_code`), `claims.json` → `_claims` (keyed by `claim_id`); read `DATA_DIR` env var (default `./data`)
- [ ] T006 Add startup error handling in the lifespan hook in `data_service/main.py`: if `members.json`, `plans.json`, or `fee_schedules.json` is absent, log at CRITICAL level and call `sys.exit(1)`; if `claims.json` is absent, log at INFO level and initialize `_claims = {}`
- [ ] T007 Emit stdout startup log in the lifespan hook in `data_service/main.py`: port (from `PORT` env var, default `8083`) and record counts for all four collections
- [ ] T008 Emit stdout shutdown log in the lifespan hook in `data_service/main.py`: `"Data Service shutting down"`

**Checkpoint**: Data loading, startup/shutdown logging, and `asyncio.Lock` are in place — route handlers can now be added.

---

## Phase 3: US1 — Service Bootstrap & Health Check (P1) 🎯 MVP

**Goal**: Service starts independently with no upstream HTTP dependencies, `/health`
returns correct counts, and `start.sh` is updated to gate all adjudication services
on this endpoint.

**Independent Test**: `curl http://localhost:8083/health` returns `200` with
`members`, `plans`, `fee_schedules`, and `claims` counts matching the seed files.
Service starts successfully when `claims.json` is absent. Service exits non-zero
when a reference file is absent.

- [ ] T009 [US1] Implement `GET /health` in `data_service/main.py`: return `{"status": "UP", "members": len(_members), "plans": len(_plans), "fee_schedules": len(_fee_schedules), "claims": len(_claims)}`
- [ ] T010 [US1] Update `start.sh`: add Data Service as the first service started (`cd data_service && uvicorn main:app --port ${PORT:-8083} &`), poll `GET http://localhost:${PORT:-8083}/health` until HTTP 200 before proceeding to Benefits Determiner; preserve existing Benefits Determiner → Pricer → Claims Manager startup order after this gate
- [ ] T011 [US1] Integration test — `GET /health` success: assert `200`, `status == "UP"`, and counts match the sizes of the fixture JSON files in `data_service/tests/test_health.py`
- [ ] T012 [US1] Integration test — missing reference file: start a subprocess with `members.json` absent from `DATA_DIR`; assert process exits with non-zero status code in `data_service/tests/test_health.py`
- [ ] T013 [US1] Integration test — missing `claims.json`: use `tmp_data_dir` fixture without `claims.json`; assert service starts normally and `GET /health` returns `"claims": 0` in `data_service/tests/test_health.py`

**Checkpoint**: `/health` endpoint live; `start.sh` gates adjudication services; three health integration tests green. Service is MVP-shippable.

---

## Phase 4: US2 — Reference Data Reads (P2)

**Goal**: `GET /members/{member_id}`, `GET /plans/{plan_id}`, and
`GET /fee-schedules/{procedure_code}` each return the full seed record on hit
and `404` on miss.

**Independent Test**: curl each endpoint with a key present in the fixture data
(expect `200` + full record) and with an unknown key (expect `404` +
`{ "detail": "<resource> not found" }`).

- [ ] T014 [P] [US2] Implement `GET /members/{member_id}` in `data_service/main.py`: return `_members[member_id]` or raise `HTTPException(404, detail="member not found")`
- [ ] T015 [P] [US2] Implement `GET /plans/{plan_id}` in `data_service/main.py`: return `_plans[plan_id]` or raise `HTTPException(404, detail="plan not found")`
- [ ] T016 [P] [US2] Implement `GET /fee-schedules/{procedure_code}` in `data_service/main.py`: return `_fee_schedules[procedure_code]` or raise `HTTPException(404, detail="procedure code not found")`
- [ ] T017 [P] [US2] Integration tests for `GET /members/{member_id}` in `data_service/tests/test_members.py`: assert `200` with full member record for a known fixture ID; assert `404` with correct detail for an unknown ID
- [ ] T018 [P] [US2] Integration tests for `GET /plans/{plan_id}` in `data_service/tests/test_plans.py`: assert `200` with full plan record for a known fixture ID; assert `404` with correct detail for an unknown ID
- [ ] T019 [P] [US2] Integration tests for `GET /fee-schedules/{procedure_code}` in `data_service/tests/test_fee_schedules.py`: assert `200` with entry containing both `in_network` and `out_of_network` blocks for a known code; assert `404` for an unknown code

**Checkpoint**: All three reference data endpoints functional and integration-tested independently.

---

## Phase 5: US3 — Claim Store Operations (P3)

**Goal**: `GET /claims/{claim_id}` returns stored claims; `POST /claims` appends to
the in-memory store under `asyncio.Lock`; no disk write occurs; restart confirms
the in-memory-only design; INFO logging emitted on write outcomes and 404s.

**Independent Test**: POST a new claim (expect `201`); GET it back (expect `200`);
POST the same claim again (expect `409`); restart the service; GET the posted
claim (expect `404` — confirming in-memory-only).

- [ ] T020 [US3] Implement `GET /claims/{claim_id}` in `data_service/main.py`: return `_claims[claim_id]` or raise `HTTPException(404, detail="claim not found")`
- [ ] T021 [US3] Implement `POST /claims` as `async def` in `data_service/main.py`: validate `claim_id` is present; raise `409` if already in `_claims`; `async with _lock: _claims[body["claim_id"]] = body`; return `201` with stored record
- [ ] T022 [US3] Add INFO-level logging in `data_service/main.py`: log claim ID + HTTP status after every `POST /claims` outcome; log resource type + requested ID for every `404` response (members, plans, fee schedules, claims)
- [ ] T023 [US3] Integration tests for `GET /claims/{claim_id}` in `data_service/tests/test_claims.py`: assert `200` with full claim record for a pre-seeded fixture ID; assert `404` for an unknown ID
- [ ] T024 [US3] Integration tests for `POST /claims` in `data_service/tests/test_claims.py`: valid new claim returns `201` and is subsequently retrievable via `GET`; duplicate `claim_id` returns `409`; missing required field returns `422`
- [ ] T025 [US3] Integration test — in-memory-only confirmation in `data_service/tests/test_claims.py`: POST a claim, restart the app (re-create `TestClient`), assert `GET /claims/{claim_id}` returns `404` (claim not persisted across restart)
- [ ] T026 [US3] Concurrency smoke test in `data_service/tests/test_claims.py`: use `asyncio.gather` to POST two distinct claims simultaneously via `httpx.AsyncClient`; assert both return `201` and both are subsequently retrievable

**Checkpoint**: Full claim store (read + write) functional; asyncio.Lock correctness smoke-tested; in-memory-only behavior verified; all integration tests green.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T027 [P] Run all 14 validation scenarios from `specs/005-data-service/quickstart.md` against the live service started with real seed data from `data/`; record any discrepancy
- [ ] T028 Verify `PORT` env var is respected: start service with `PORT=9999`, confirm it binds on `9999` and `/health` returns `200` at that port

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — blocks all user stories
- **Phase 3 (US1)**: Depends on Phase 2
- **Phase 4 (US2)**: Depends on Phase 2 — can start in parallel with US1 after Phase 2
- **Phase 5 (US3)**: Depends on Phase 2 — can start in parallel with US1 and US2 after Phase 2
- **Phase 6 (Polish)**: Depends on all user story phases complete

### User story dependencies

- **US1 (P1)**: Independently completable after Foundational
- **US2 (P2)**: Independently completable after Foundational; no dependency on US1
- **US3 (P3)**: Independently completable after Foundational; no dependency on US1 or US2

### Within each user story

- Implementation tasks (T00x) before integration test tasks only where the test
  exercises a live endpoint; `conftest.py` fixtures are setup-phase and always
  available
- T014 / T015 / T016 are all parallelizable (same file, non-overlapping route
  handlers); similarly T017 / T018 / T019 are parallelizable (separate test files)
- T021 (POST /claims) depends on T020 (GET /claims) being present so the round-trip test works

---

## Parallel Examples

### Phase 4 (US2) — maximum parallelism

```
Parallel group A (implementation — different route handlers, same file):
  T014  GET /members/{member_id}     → data_service/main.py
  T015  GET /plans/{plan_id}         → data_service/main.py
  T016  GET /fee-schedules/{code}    → data_service/main.py

Parallel group B (tests — different test files):
  T017  test_members.py
  T018  test_plans.py
  T019  test_fee_schedules.py
```

### Across stories (after Foundational complete)

```
Developer A: Phase 3 (US1) — health + start.sh
Developer B: Phase 4 (US2) — reference reads
Developer C: Phase 5 (US3) — claim operations
```

---

## Implementation Strategy

### MVP (US1 only — Phases 1–3)

1. Phase 1: Setup → Phase 2: Foundational → Phase 3: US1
2. **Validate**: `start.sh` starts Data Service first; `/health` returns correct counts; three integration tests pass
3. The system can now boot end-to-end (adjudication services gate on this)

### Incremental delivery

1. Phases 1–3 → MVP: health check and startup gate working
2. Phase 4 → Reference reads: adjudication services can query members, plans, fee schedules
3. Phase 5 → Claim operations: full adjudication round-trip possible through Data Service
4. Phase 6 → Polish: quickstart validated, PORT env var confirmed

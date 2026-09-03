# Tasks: Claims Manager

**Input**: Design documents from `specs/001-claims-manager/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/post-claims-batch.md, contracts/get-claim.md, quickstart.md

**Organization**: Tasks grouped by user story. Each story is independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Setup

**Purpose**: Create the `claims_manager/` service directory and declare dependencies.

- [x] T001 Create `claims_manager/` directory with subdirectory `tests/` per plan.md Project Structure
- [x] T002 Create `claims_manager/requirements.txt` with: `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`, `pytest`, `respx`

**Checkpoint**: `pip install -r claims_manager/requirements.txt` installs without error.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pydantic models, HTTP data client, pure adjudication functions, and app skeleton — all user stories depend on these.

⚠️ No user story work can begin until this phase is complete.

- [x] T003 Create `claims_manager/__init__.py` (empty package marker)
- [x] T004 [P] Create `claims_manager/tests/__init__.py` (empty package marker)
- [x] T005 Create `claims_manager/models.py` with:
  - `Money = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]` for JSON-safe Decimal serialization
  - Request models: `ClaimLine` (line_number, procedure_code, diagnosis_codes: list[str] optional, units, billed_amount: Decimal), `ClaimRequest` (claim_id, member_id, provider_id, date_of_service: date, claim_lines: list[ClaimLine]), `BatchRequest` (claims: list[ClaimRequest])
  - Response models: `LineDetailEntry` (all 13 fields per data-model.md using Money for financial fields), `ClaimTotals` (billed_amount, allowed_amount, member_liability, payer_liability, all Money), `AdjudicationResult` (claim_id, status: str, adjudicated_at: Optional[str], totals: Optional[ClaimTotals], denial_reasons: list[str], errors: list[str], line_detail: list[LineDetailEntry]), `BatchResponse` (results: list[AdjudicationResult])
  - Exception classes: `DataServiceError(Exception)`, `BenefitsDeterminerError(Exception)`, `PricerError(Exception)`
- [x] T006 Create `claims_manager/data_client.py` with five synchronous `httpx.Client` wrapper functions:
  - `get_member(client, base_url, member_id) -> dict` — calls `GET /members/{id}`; raises `DataServiceError` on connection/timeout/5xx; raises inline (returns None) on 404 — caller handles NOT_ELIGIBLE
  - `get_claim(client, base_url, claim_id) -> dict | None` — calls `GET /claims/{id}`; returns None on 404; raises `DataServiceError` on 5xx
  - `post_claim(client, base_url, result: dict) -> None` — calls `POST /claims`; raises `DataServiceError` on 5xx
  - `determine_benefits(client, base_url, payload: dict) -> dict` — calls `POST /benefits/determine`; raises `BenefitsDeterminerError` on connection/timeout/5xx
  - `price_claim(client, base_url, payload: dict) -> dict` — calls `POST /price`; raises `PricerError` on connection/timeout/5xx
- [x] T007 Create `claims_manager/adjudication.py` with four pure functions:
  - `validate_claim(claim: ClaimRequest, seen_ids: set[str]) -> list[str]` — checks all FR-2 rules; returns list of error messages (empty = valid); checks claim_id not in seen_ids (duplicate-within-batch)
  - `build_denied_line(claim_line: ClaimLine, denial_reason: str) -> dict` — returns a LineDetailEntry dict with billed_amount=claim_line.billed_amount*claim_line.units, all financial fields 0.00, line_status="DENIED", adjustment_reason_code=None
  - `compute_claim_totals(line_details: list[dict]) -> dict` — sums billed_amount, allowed_amount, member_liability, payer_liability across all lines
  - `determine_claim_status(line_details: list[dict]) -> str` — returns "PAID" if all line_status=="PAID", "DENIED" if all "DENIED", else "PARTIALLY_PAID"
- [x] T008 Create `claims_manager/main.py` — FastAPI app with:
  - Lifespan context manager opening/closing `httpx.Client` on `app.state`
  - Reads env vars `DATA_SERVICE_URL` (default `http://localhost:8083`), `BENEFITS_DETERMINER_URL` (default `http://localhost:8081`), `PRICER_URL` (default `http://localhost:8082`), `PORT` (default `8080`)
  - Logs `"Claims Manager listening on port {PORT}, DATA_SERVICE_URL={DATA_SERVICE_URL}, BENEFITS_DETERMINER_URL={BENEFITS_DETERMINER_URL}, PRICER_URL={PRICER_URL}"` on startup
  - Exception handlers: `DataServiceError → 503`, `BenefitsDeterminerError → 503`, `PricerError → 503` (all return `{"detail": "Service unavailable"}`)
  - `GET /health` returns `{"status": "UP"}`

**Checkpoint**: `python -c "from claims_manager.main import app"` runs without import errors. `GET /health` returns 200.

---

## Phase 3: User Story 1 — Batch Claim Adjudication (FR-1 through FR-4)

**Goal**: `POST /claims/batch` validates each claim, orchestrates Benefits Determiner and Pricer, merges results, writes adjudicated claims to the Data Service, and returns all results in submission order.

**Independent Test**: POST with one valid in-network claim → response has `results[0].status == "PAID"` with correct `line_detail` and `totals`. All exception paths (unknown member, BD 5xx, validation failure) return the correct per-claim or batch result.

**Acceptance criteria covered**: AC-1 through AC-5, AC-8 through AC-12.

- [x] T009 [US1] Wire `POST /claims/batch` in `claims_manager/main.py` — implement the full per-claim processing loop per plan.md Processing Flow:
  1. Iterate claims in submission order; maintain `seen_ids: set[str]` and `results: list`
  2. For each claim: call `adjudication.validate_claim()`; if errors → append VALIDATION_ERROR result and continue
  3. Check `data_client.get_claim()` for existing claim_id; if found (not None) → append CONFLICT result and continue
  4. Call `data_client.get_member()`; if None (404) → append DENIED/NOT_ELIGIBLE result and continue
  5. Call `data_client.determine_benefits()` (raises `BenefitsDeterminerError` on 5xx)
  6. If BD response `overall_covered == False` and all lines denied → build denied result (no Pricer call)
  7. Otherwise: extract covered lines (where `line_determinations[].covered == True`); call `data_client.price_claim()` with covered lines (raises `PricerError` on 5xx)
  8. Merge Pricer `line_detail` with denied lines from BD `line_determinations` using `adjudication.build_denied_line()`, preserving original claim line order
  9. Call `adjudication.compute_claim_totals()` and `adjudication.determine_claim_status()`; set `adjudicated_at` to UTC ISO 8601 string
  10. Append AdjudicationResult to results list
  11. After loop: call `data_client.post_claim()` for each adjudicated result (PAID, DENIED, PARTIALLY_PAID only)
  12. Return `BatchResponse(results=results)`
  - Exception handlers on `DataServiceError`, `BenefitsDeterminerError`, `PricerError` bubble up to the FastAPI exception handler → 503 (no claims written)
- [x] T010 [P] [US1] Write unit tests for pure functions in `claims_manager/tests/test_adjudication.py` covering:
  - `validate_claim`: missing claim_id, empty claim_lines, negative units, negative billed_amount, duplicate line_number within claim, duplicate claim_id in seen_ids, valid claim returns empty errors
  - `build_denied_line`: financial fields all 0.00, billed_amount = billed*units, line_status="DENIED", denial_reason populated
  - `compute_claim_totals`: sum across two lines (one paid one denied), invariant member+payer == allowed
  - `determine_claim_status`: all paid→PAID, all denied→DENIED, mix→PARTIALLY_PAID
- [x] T011 [US1] Write integration tests for `POST /claims/batch` in `claims_manager/tests/test_api.py` using FastAPI `TestClient` + `respx` mocking all three downstream services; cover:
  - AC-1: one valid in-network claim → PAID, correct line_detail fields (copay_applied, deductible_applied, adjustment_reason_code)
  - AC-2: two-claim batch → results in submission order, both claim_ids present
  - AC-3: unknown member_id → DENIED/NOT_ELIGIBLE, no Pricer mock needed (verifiable by mock not being called)
  - AC-4: one covered + one denied line → PARTIALLY_PAID, per-line line_status values
  - AC-5: all lines denied by BD → DENIED, no Pricer mock needed
  - AC-8: missing required field (empty claim_lines) → VALIDATION_ERROR with errors entry
  - AC-9: batch with one VALIDATION_ERROR + one valid claim → both results returned
  - AC-10: duplicate claim_id (get_claim mock returns 200) → CONFLICT result
  - AC-11: GET /health → 200, `{"status": "UP"}`
  - AC-12: BD mock raises ConnectError → batch returns HTTP 503

**Checkpoint**: `pytest claims_manager/tests/ -v -k "not retrieval"` all pass (no live upstream required).

---

## Phase 4: User Story 2 — Claim Retrieval (FR-5)

**Goal**: `GET /claims/{claim_id}` calls Data Service and returns the stored adjudication result. Returns 404 if not found.

**Independent Test**: Mock `get_claim()` returning a stored result → GET returns 200 with same shape. Mock returning None → GET returns 404.

**Acceptance criteria covered**: AC-6, AC-7.

- [x] T012 [US2] Wire `GET /claims/{claim_id}` in `claims_manager/main.py` — call `data_client.get_claim()`; if None → `raise HTTPException(404, detail=f"Claim {claim_id} not found")`; else return result dict directly (FastAPI serializes it)
- [x] T013 [US2] Add retrieval integration tests to `claims_manager/tests/test_api.py` covering:
  - AC-6: `get_claim` mock returns stored result → GET 200 with same shape as POST batch result entry
  - AC-7: `get_claim` mock returns None → GET 404 with detail message

**Checkpoint**: `pytest claims_manager/tests/ -v` all pass.

---

## Phase 5: End-to-End Validation

**Purpose**: Full test suite confirmation, start.sh update, and live quickstart validation.

- [x] T014 Run `pytest claims_manager/tests/ -v` from repo root and confirm all tests pass (no live upstream required for test suite)
- [x] T015 Update `start.sh` — uncomment the Pricer section (step 3: `cd pricer && uvicorn ...`) and the Claims Manager section (step 4: `cd claims_manager && uvicorn ...` + `wait_for_health` call); leave Benefits Determiner (step 2) commented as a TODO until spec 002 is implemented
- [x] T016 Start Claims Manager with live upstream services (Data Service + Pricer; BD mocked or stubbed) and validate quickstart.md Scenarios 1–7 manually

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 complete
- **US1 (Phase 3)**: Depends on Phase 2 — models, data_client, adjudication.py, and main.py skeleton must exist
- **US2 (Phase 4)**: Depends on Phase 2 (main.py skeleton); can begin after T008 completes, independent of Phase 3
- **End-to-End Validation (Phase 5)**: Depends on Phase 3 and Phase 4 complete

### Parallel Opportunities

- T004 (`tests/__init__.py`) can run in parallel with T003–T008
- T010 (unit tests for adjudication.py) can begin as soon as T007 completes — runs in parallel with T009 (main.py wiring)
- T012 (GET /claims/{id} wiring) and T013 (retrieval tests) are independent of T009–T011 once Phase 2 is done

---

## Parallel Example: Phase 3 (US1)

```
# T009 (POST /claims/batch wiring in main.py) runs first
# Then in parallel:
Task T010: Unit tests for adjudication.py       (tests/test_adjudication.py)
Task T011: Integration tests for batch endpoint  (tests/test_api.py)
```

---

## Implementation Strategy

### MVP (Phase 1–2 + POST /claims/batch health + validation only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational — models, data_client, adjudication.py, app skeleton, health
3. Complete T009: Wire POST /claims/batch with at least validation (VALIDATION_ERROR path) working
4. **STOP and VALIDATE**: POST with valid payload calls BD mock and returns results; invalid payload returns VALIDATION_ERROR
5. This MVP proves the integration skeleton works before adding all adjudication edge cases

### Incremental Delivery

1. Phases 1–2 → Skeleton + health (MVP foundation)
2. Phase 3 → Full batch adjudication with all 10 ACs
3. Phase 4 → Claim retrieval (2 ACs)
4. Phase 5 → Full validation, start.sh, quickstart

---

## Notes

- `Money` type alias for `Decimal` (same pattern as Pricer) prevents Pydantic v2 serializing Decimal as strings in JSON
- `date_of_service` in ClaimRequest is a `date` type; Pydantic parses `"YYYY-MM-DD"` strings automatically
- `diagnosis_codes` is accepted but not forwarded to BD or Pricer; strip it from the BD payload
- BD `line_determinations` is indexed by `procedure_code` — build a lookup dict by procedure_code to match with original claim lines during merge
- `post_claim` is called once per adjudicated result after the entire loop completes; if DS raises `DataServiceError` during write, the batch 503 exception handler fires — the caller gets 503 even though adjudication succeeded (acceptable for practicum)
- Constitution requires integration test before spec complete — T011/T013 satisfy this
- `start.sh` update (T015) is part of this spec per research.md Decision 7; uncomment only Pricer + Claims Manager steps

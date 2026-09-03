# Implementation Plan: Claims Manager

**Branch**: `001-claims-manager` | **Date**: 2026-09-03 | **Spec**: `specs/001-claims-manager/spec.md`

**Input**: Feature specification from `/specs/001-claims-manager/spec.md`

---

## Summary

Implement Claims Manager as a FastAPI service on port 8080. It is the sole external entry point for adjudication: it accepts `POST /claims/batch`, validates each claim, orchestrates Benefits Determiner (POST) and Pricer (POST) for each valid claim, merges results, writes adjudicated claims to the Data Service, and returns all results in submission order. `GET /claims/{claim_id}` retrieves stored results from the Data Service. All data access goes through the Data Service via HTTP (constitution v1.1 Data Layer).

---

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`

**Storage**: Data Service (port 8083) via HTTP — no direct file access

**Testing**: `pytest`, `respx` (httpx mocking), FastAPI `TestClient`

**Target Platform**: Single machine, POSIX shell

**Project Type**: web-service

**Performance Goals**: Practicum — no throughput targets

**Constraints**: Independently startable without Benefits Determiner or Pricer; must not import from `benefits_determiner/` or `pricer/`

**Scale/Scope**: Practicum — small seed dataset, no concurrency requirements

---

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| `/health` endpoint required (non-negotiable) | ✓ PASS | FR-6 defines `GET /health → 200 {"status": "UP"}` |
| Integration test before spec complete (non-negotiable) | ✓ PASS | Tasks phase includes `TestClient` + `respx` integration tests |
| Env vars, no hardcoded values | ✓ PASS | `BENEFITS_DETERMINER_URL`, `PRICER_URL`, `DATA_SERVICE_URL`, `PORT` all env-configurable |
| No external runtime dependencies | ✓ PASS | httpx only; no DB/broker |
| Startup + shutdown logged | ✓ PASS | Startup logs port and all upstream URLs |
| Professional claims only (permanent) | ✓ PASS | No institutional claim support |
| Python + FastAPI only | ✓ PASS | |
| Each service has its own requirements.txt | ✓ PASS | `claims_manager/requirements.txt` |
| Independently startable | ✓ PASS | Service starts without BD/Pricer running |
| No cross-service imports | ✓ PASS | All coupling is HTTP only |
| Data Service is sole file accessor | ✓ PASS | All data via HTTP; no `DATA_DIR` or file I/O in Claims Manager |
| Claims Manager is sole orchestrator | ✓ PASS | BD and Pricer do not call each other |
| `plan_id`/`network_status` forwarded from BD | ✓ PASS | Not re-derived in Claims Manager |
| `start.sh` wires Claims Manager | ✓ PASS | Step 4 in `start.sh` already stubbed; will be uncommented at implementation |

All gates pass. No violations to justify.

---

## Project Structure

### Documentation (this feature)

```text
specs/001-claims-manager/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── post-claims-batch.md
│   └── get-claim.md
└── tasks.md             # /speckit-tasks output (not yet created)
```

### Source Code

```text
claims_manager/
├── __init__.py
├── requirements.txt
├── models.py            # Pydantic request/response models, exception classes
├── data_client.py       # httpx wrappers: Data Service, Benefits Determiner, Pricer
├── adjudication.py      # Pure functions: validate_claim, build_denied_line, compute_totals, build_result
└── main.py              # FastAPI app, lifespan, exception handlers, routes

claims_manager/tests/
├── __init__.py
├── test_adjudication.py # Unit tests for pure functions
└── test_api.py          # Integration tests (TestClient + respx)
```

---

## Key Design Decisions (from research.md)

| # | Decision | Reference |
|---|---|---|
| 1 | Sync `httpx.Client` in lifespan | research.md Decision 1 |
| 2 | Abort entire batch on any downstream 5xx | research.md Decision 2 |
| 3 | Check `GET /claims/{id}` before adjudicating (dedup) | research.md Decision 3 |
| 4 | Pass through `contractual_adjustment` from Pricer | research.md Decision 4 |
| 5 | `totals: null` for VALIDATION_ERROR/CONFLICT; billed only for DENIED | research.md Decision 5 |
| 6 | `POST /claims` sends full AdjudicationResult JSON | research.md Decision 6 |
| 7 | Uncomment Pricer + Claims Manager in `start.sh` | research.md Decision 7 |
| 8 | `adjudicated_at` UTC ISO 8601 with `Z` suffix | research.md Decision 8 |
| 9 | Process claims sequentially in submission order | research.md Decision 9 |
| 10 | `diagnosis_codes` accepted, not evaluated or forwarded | research.md Decision 10 |

---

## Per-Claim Processing Flow

```
for claim in batch:
    1. Validate fields (FR-2) → VALIDATION_ERROR if fails
    2. Check batch-local claim_id uniqueness → VALIDATION_ERROR if duplicate
    3. Call DS GET /claims/{id} → CONFLICT if 200; abort batch if 5xx
    4. Call DS GET /members/{id} → DENIED/NOT_ELIGIBLE if 404; abort batch if 5xx
    5. Call BD POST /benefits/determine → abort batch if 5xx
    6. If all lines denied → DENIED (skip Pricer)
    7. Call Pricer POST /price (covered lines only) → abort batch if 5xx
    8. Merge BD denied lines + Pricer line_detail → line_detail array
    9. Compute totals, determine status (PAID/DENIED/PARTIALLY_PAID)
    10. Record result in-memory

after all claims processed:
    11. Call DS POST /claims for each adjudicated result
    12. Return BatchResponse with all results in submission order
```

Note: VALIDATION_ERROR and CONFLICT results are recorded but never written to the Data Service (steps 1–3 short-circuit before step 11).

---

## Complexity Tracking

No constitution violations. No complexity tracking entry required.

# Implementation Plan: Data Service API

**Branch**: `005-data-service` | **Date**: 2026-09-02 | **Spec**: [spec.md](spec.md)

**Input**: `specs/005-data-service/spec.md`

## Summary

Implement the Data Service as a FastAPI service on port 8083. All four JSON seed
files are loaded into memory at startup via FastAPI's lifespan hook and held for
the lifetime of the process. Five GET endpoints serve members, plans, fee
schedules, claims, and health status. One POST endpoint (`async def`) appends new claim records
to the in-memory claims store under an `asyncio.Lock` (no disk write). No data is written to disk at runtime — restarting returns the service
to seed state. `start.sh` is updated to start the Data Service first and gate the
three adjudication services on its `/health` returning 200.

---

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `fastapi`, `uvicorn[standard]`

**Storage**: In-memory only — four `dict[str, dict]` stores keyed by primary key,
populated at startup from JSON seed files. No runtime writes to disk.

**Testing**: `pytest`, `httpx` (ASGI TestClient for FastAPI)

**Target Platform**: Single-machine practicum (Windows / Linux)

**Project Type**: Internal web service

**Performance Goals**: No explicit latency targets; sub-100ms expected for all
endpoints at practicum data scale (200 members, 25 fee schedules, 5 plans,
150+ claims).

**Constraints**:
- No external runtime dependencies
- Independently startable — no upstream HTTP dependencies at startup
- `DATA_DIR` env var controls the data directory (default `./data`)
- `PORT` env var controls the listening port (default `8083`)
- `/health` must return `200` when all four files are loaded

**Scale/Scope**: 200 members, 25 fee schedules, 5 plans, 150+ claims — all
comfortably held in a single Python process.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| `GET /health` returns 200 (non-negotiable) | ✅ PASS | FR-6 defines endpoint and response shape |
| Tests must not hardcode port numbers or file paths (non-negotiable) | ✅ PASS | Tests use ASGI `TestClient` (no real port); data path injected via `DATA_DIR` in test fixtures |
| Services read configuration from env vars (non-negotiable) | ✅ PASS | `DATA_DIR` (default `./data`), `PORT` (default `8083`) |
| No external runtime dependency (non-negotiable) | ✅ PASS | In-memory only; no DB, broker, or remote API |
| Startup logged to stdout (non-negotiable) | ✅ PASS | Lifespan startup emits port and per-collection record counts |
| Python 3.11+, FastAPI (pod-local) | ✅ PASS | Constitution: Technology Stack |
| Own `requirements.txt` at `data_service/requirements.txt` (pod-local) | ✅ PASS | Constitution: Technology Stack |
| Service independently startable (pod-local) | ✅ PASS | Lifespan reads files only; no upstream service required |
| `DATA_DIR` env var, default `./data` (pod-local) | ✅ PASS | Constitution: Data Layer |
| `claims.json` durability (pod-local, strong default) | ⚠️ DEPARTURE | Decision 0010 pending — in-memory only by design; see Complexity Tracking |
| `start.sh` starts Data Service first, gates others on `/health` (pod-local) | ✅ PASS | Clarified 2026-09-01 — in scope for this spec |

### Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Departs from `claims.json` write-back principle | Idempotent restarts simplify repeated practicum test runs; every restart returns to the exact seed state | Write-back would require a manual reset step before each test run; accumulator balances are already acknowledged as non-persistent, making the claim ledger a partial truth anyway |

---

## Project Structure

### Documentation (this feature)

```text
specs/005-data-service/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   └── http.md          ← Phase 1 output
└── tasks.md             ← Phase 2 output (/speckit-tasks — not created here)
```

### Source Code

```text
data_service/
├── main.py              ← FastAPI app, lifespan hook, all six route handlers
└── requirements.txt     ← fastapi, uvicorn[standard]

data_service/tests/
├── conftest.py          ← TestClient fixture; temp DATA_DIR with minimal JSON fixtures
├── test_members.py      ← GET /members/{member_id} — found / not found
├── test_plans.py        ← GET /plans/{plan_id} — found / not found
├── test_fee_schedules.py ← GET /fee-schedules/{code} — found / not found
├── test_claims.py       ← GET /claims/{id}; POST /claims happy path, 409, 422;
│                           concurrency smoke test (two concurrent POSTs)
└── test_health.py       ← counts match fixture; missing reference file exits non-zero

start.sh                 ← updated — Data Service starts first, gated by /health;
                            existing order (Benefits Determiner → Pricer →
                            Claims Manager) preserved after that gate
```

**Structure Decision**: Single-file service (`main.py`). The Data Service has no
business logic — only load-and-serve behaviour. Six route handlers and one
lifespan hook fit cleanly in one file. A multi-module layout would add navigation
cost with no structural benefit at this scope.

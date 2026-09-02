# Research: Benefits Determiner

**Spec**: 002-benefits-determiner | **Date**: 2026-09-02

---

## Decision 1 — HTTP client library

**Decision**: Use `httpx` with a synchronous `httpx.Client`.

**Rationale**: FastAPI supports both sync and async handlers; at practicum scale a synchronous handler is simpler to test and reason about. `httpx` is the idiomatic choice over `requests` because its mock library (`respx`) integrates cleanly with pytest and supports both sync and async. `urllib` (stdlib) was considered but mocking it in tests requires more ceremony.

**Alternatives considered**:
- `requests` — widely used but `respx` targets `httpx`; switching later would require changing test infrastructure
- `urllib.request` (stdlib) — no external dependency, but verbose and harder to mock cleanly in tests

---

## Decision 2 — Mocking Data Service calls in tests

**Decision**: Use `respx` to intercept `httpx` calls during tests.

**Rationale**: Tests must not require a live Data Service running (`PASS` on independent-startable principle). `respx` lets tests define canned responses for `GET /members/{id}` and `GET /plans/{id}` at the route level, giving full control over 200, 404, and connectivity failure scenarios. The FastAPI `TestClient` from `httpx` is compatible.

**Alternatives considered**:
- `unittest.mock.patch` on `httpx.Client.get` — works but is fragile (patches a method, not a URL pattern); `respx` is more expressive and URL-aware
- Spinning up a real Data Service in a subprocess for tests — would work but adds a startup dependency and slows test runs

---

## Decision 3 — Error propagation for Data Service failures

**Decision**: `data_client.py` raises a custom `DataServiceError` exception for all connectivity problems (connection refused, timeout, non-200 non-404 responses). `main.py` registers a FastAPI exception handler that converts `DataServiceError` → `503 Service Unavailable` with `{"detail": "Data Service unavailable"}`.

**Rationale**: Keeping the 503 mapping in one place (the exception handler in `main.py`) avoids repeating error-handling code in every route. The Data Service error is a connectivity concern, not a business-logic concern; separating it from `determination.py` keeps the determination logic pure and testable without HTTP mocking.

**Alternatives considered**:
- Letting `httpx.ConnectError` propagate to FastAPI's default handler — would return `500`, which is indistinguishable from a bug in the determination logic
- Catching the exception inline in the route handler — duplicates the try/except for every endpoint; worse when more endpoints are added

---

## Decision 4 — Plan field name: `code` not `procedure_code`

**Decision**: When iterating `plan.covered_procedure_codes` and `plan.excluded_procedure_codes`, access the `"code"` key, not `"procedure_code"`.

**Rationale**: The data model schema (`.specify/memory/data-model.md`) defines both arrays as objects with `"code"`, `"description"`, and optionally `"requires_auth"` or `"exclusion_reason"`. The spec's FR-3 prose is ambiguous (uses "procedure code" as a concept without specifying the key name). The seed data in `data/plans.json` uses `"code"` throughout, confirmed by `generate_seed_data.py`. Using `"procedure_code"` would silently fail to match any code, producing incorrect NOT_COVERED denials for all procedures.

**Alternatives considered**: None — this is a correctness constraint, not a design choice.

---

## Decision 5 — Authorization date comparison

**Decision**: Parse `authorized_date`, `expiration_date`, and `date_of_service` as `datetime.date` objects before comparing.

**Rationale**: ISO 8601 date strings (`YYYY-MM-DD`) sort lexicographically, so string comparison would work for simple range checks. However, parsing to `datetime.date` makes intent explicit, avoids edge cases with malformed strings, and matches the Pydantic model's `date` type used in the request body.

**Logic**: Auth is valid when `auth.authorized_date <= date_of_service <= auth.expiration_date`.

---

## Decision 6 — `httpx.Client` lifecycle

**Decision**: Create the `httpx.Client` once at application startup (module-level or via FastAPI lifespan), reuse it across requests.

**Rationale**: Creating a new client per request adds TCP handshake overhead (even at practicum scale) and makes tests less predictable when `respx` intercepts at the client level. A shared client is the `httpx` recommended pattern.

**How**: Use FastAPI's `lifespan` context manager to open the client on startup and close it on shutdown. Store it on `app.state.http_client`.

---

## Decision 7 — Startup log format

**Decision**: Log to stdout on startup: `"Benefits Determiner listening on port {PORT}, DATA_SERVICE_URL={DATA_SERVICE_URL}"`.

**Rationale**: Constitution requires at minimum: port and data files loaded. Since this service has no data files, the equivalent is the Data Service URL (where all data comes from). One line is sufficient.

# Research: Pricer

**Spec**: 003-pricer | **Date**: 2026-09-02

---

## Decision 1 — HTTP client and mocking (same as Benefits Determiner)

**Decision**: Use `httpx` with a synchronous `httpx.Client`; mock with `respx` in tests.

**Rationale**: Consistent with Benefits Determiner (spec 002). FastAPI `TestClient` is built on `httpx`, so `respx` integrates natively. No async needed at practicum scale. The shared pattern means the same test infrastructure approach applies to both services.

**Alternatives considered**: Same as spec 002 — `requests` lacks `respx` integration; `urllib` is verbose.

---

## Decision 2 — Pricing logic isolation

**Decision**: All cost-sharing logic lives in `pricing.py` as a pure function `price_claim(member: dict, fee_schedule_map: dict, request: PriceRequest) -> PriceResponse`. `main.py` handles HTTP concerns only.

**Rationale**: The seven-step cost-sharing algorithm (FR-2) has enough complexity and branching to warrant thorough unit testing without HTTP overhead. Isolating it in `pricing.py` allows `test_pricing.py` to test every deductible/copay/coinsurance/OOP permutation by passing plain dicts — no `respx` setup required.

**Alternatives considered**: Inline pricing in the route handler — simpler but makes the pricing logic untestable in isolation.

---

## Decision 3 — Running counters across lines

**Decision**: Initialize `deductible_used_this_claim = 0.0` and `oop_used_this_claim = 0.0` before iterating lines. Pass them by reference (or thread them through the loop) so each line receives the accumulated values from prior lines.

**Rationale**: Clarification Q2 confirmed that deductible must track across lines the same way OOP does. Without this, a 2-line claim could apply the full remaining deductible to both lines, overcharging the member.

**Implementation note**: In Python, use a mutable accumulator object or return updated counters from each line's pricing function; don't rely on closure mutation.

---

## Decision 4 — Units-based line totals

**Decision**: `billed_amount` and `fee_schedule_rate` are per-unit. All line calculations use `× units`:
- `line_billed = billed_amount × units`
- `line_fee_schedule_rate = fee_schedule_rate × units`
- `allowed_amount = min(line_billed, line_fee_schedule_rate)`
- All downstream cost-sharing math operates on `allowed_amount` (the scaled total).

**Rationale**: Clarification Q3 confirmed this. The `units` field exists as a distinct value, implying the Pricer is responsible for scaling.

---

## Decision 5 — Data Service call pattern

**Decision**: Fetch member and plan once per request (before iterating lines). Fetch fee schedule once per unique procedure code (cache in a dict for the request lifetime if the same code appears on multiple lines).

**Rationale**: Member and plan are needed for every line; fetching once avoids N+1 calls. Fee schedules are per-procedure-code; a request with two lines for the same code should not make two identical `GET /fee-schedules/{code}` calls.

---

## Decision 6 — Error responses

| Condition | Status | Body |
|---|---|---|
| Data Service unreachable | 503 | `{"detail": "Data Service unavailable"}` |
| `member_id` not found (404 from Data Service) | 404 | `{"detail": "Member {member_id} not found"}` |
| `plan_id` not found (404 from Data Service) | 404 | `{"detail": "Plan {plan_id} not found"}` |
| `procedure_code` not found (404 from Data Service) | 422 | `{"detail": "Procedure code {code} not found in fee schedules"}` |
| Missing/invalid request field | 422 | FastAPI default validation error |

Note: procedure code not found maps to 422 (not 404) per spec FR-1 — it is a client input error, not a resource-not-found at the claim level.

**Implementation**: `DataServiceError` → 503 via exception handler (same as Benefits Determiner). `MemberNotFoundError` and `PlanNotFoundError` → 404 via separate handlers. Procedure code 404 is handled inline in `pricing.py` / `main.py` before pricing begins.

---

## Decision 7 — Accumulator snapshot

**Decision**: Compute `_after` values as `seeded_value + this_claim_applied`. Do not cap `_after` at the limit — show the true projected value so the snapshot accurately reflects what would have been written back if accumulators were updated.

**Rationale**: The snapshot is informational only. Capping at the limit would mask OOP-exceeded scenarios; showing the uncapped value makes the snapshot a faithful projection.

---

## Decision 8 — Startup log format

**Decision**: `"Pricer listening on port {PORT}, DATA_SERVICE_URL={DATA_SERVICE_URL}"` — same format as Benefits Determiner.

**Rationale**: Consistency; constitution requires port and data source at minimum.

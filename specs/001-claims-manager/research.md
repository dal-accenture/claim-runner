# Research: Claims Manager

**Spec**: 001-claims-manager  
**Branch**: 001-claims-manager (target; current branch: 003-pricer)

---

## Decision 1 — HTTP client type

**Decision**: Synchronous `httpx.Client`, opened in FastAPI lifespan, stored on `app.state`.

**Rationale**: Consistent with Pricer (spec 003). FastAPI synchronous route handlers work fine with a sync httpx client. The practicum is single-machine and does not require async concurrency benefits.

**Alternatives considered**: `httpx.AsyncClient` with async route handlers — adds complexity (async/await throughout) for no observable benefit in a practicum context.

---

## Decision 2 — Batch abort on downstream 5xx

**Decision**: If any downstream service (Data Service, Benefits Determiner, Pricer) returns 5xx for any claim in the batch, abort the entire batch immediately and return HTTP 503 with no claims written to the Data Service.

**Rationale**: Spec edge cases table states "entire batch request returns `503 SERVICE_UNAVAILABLE`; no claims written to ledger" for BD or Pricer 5xx. This extends to Data Service 5xx per clarification Q2. The safest interpretation is fail-fast on the first encountered 5xx.

**Alternatives considered**: Per-claim 503 result — rejected; spec is explicit that 5xx from a downstream is a batch-level failure, not a per-claim failure.

---

## Decision 3 — Claim deduplication check before adjudication

**Decision**: Before adjudicating a claim, call `GET /claims/{claim_id}` on the Data Service. If 200 → record `status: "CONFLICT"` and skip adjudication for that claim. If 404 → proceed. If 5xx → abort entire batch.

**Rationale**: Checking first avoids calling Benefits Determiner and Pricer for a claim that will be rejected anyway. Consistent with the spec's intent that duplicate claims are not re-adjudicated.

**Alternatives considered**: Attempt `POST /claims` at the end and handle 409 — would waste downstream calls. No check at all — would require `POST /claims` to return 409 and Claims Manager to retroactively convert a result to CONFLICT.

---

## Decision 4 — `contractual_adjustment` in `line_detail`

**Decision**: Include `contractual_adjustment` in the Claims Manager `line_detail` response, passed through from the Pricer.

**Rationale**: The Pricer response includes `contractual_adjustment` per line. Omitting it in the Claims Manager response would discard information callers may need for remittance reconciliation. The spec's response example omits it but does not say it is excluded. For denied lines, `contractual_adjustment` is `0.00`.

**Alternatives considered**: Omit it — rejected; the spec example is illustrative, not exhaustive for the PAID case.

---

## Decision 5 — `totals` field for non-adjudicated results

**Decision**:
- `VALIDATION_ERROR` and `CONFLICT` results: `totals: null`
- `DENIED` claims (all lines denied by BD): `billed_amount` = sum of submitted `billed_amount × units` per line; `allowed_amount`, `member_liability`, `payer_liability` all `0.00`

**Rationale**: Totals are only meaningful after cost-sharing is applied. For validation failures no pricing has occurred. For fully-denied claims, billed amounts are still reported to inform the caller of what was submitted; financial totals are zero because no payment flows.

---

## Decision 6 — Data Service claim persistence payload

**Decision**: `POST /claims` sends the full AdjudicationResult JSON (the same shape returned in the batch response for a successfully adjudicated claim). The Data Service is expected to accept this payload and return `201 Created` on success, `409 Conflict` if `claim_id` already exists (treated as CONFLICT per Decision 3).

**Rationale**: The Data Service API is defined in spec 005 (not yet complete). This decision records what Claims Manager will send so spec 005 can define a compatible endpoint. The payload reuses the response model — no separate storage model needed.

**Note**: Spec 001 implementation must coordinate with spec 005 implementation to ensure `POST /claims` accepts this payload.

---

## Decision 7 — `start.sh` uncommenting

**Decision**: As part of spec 001 implementation, uncomment the Pricer section (step 3) and the Claims Manager section (step 4) in `start.sh`. The Benefits Determiner section (step 2) remains commented until spec 002 is implemented.

**Rationale**: `start.sh` already has all four sections stubbed with TODO comments. Spec 001 implementation is the correct time to wire Claims Manager into the central startup script.

---

## Decision 8 — `adjudicated_at` format

**Decision**: UTC ISO 8601 datetime string with `Z` suffix, e.g. `"2025-09-01T14:30:01Z"`. Set by Claims Manager using `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")` at the point the adjudication result is assembled. `null` for non-adjudicated results (VALIDATION_ERROR, CONFLICT).

---

## Decision 9 — Batch request ordering

**Decision**: Claims are processed in submission order. Results are returned in the same order. Validation and deduplication checks happen per-claim as the list is iterated; no reordering.

---

## Decision 10 — `diagnosis_codes` handling

**Decision**: `diagnosis_codes` is accepted in the request model but ignored during adjudication. It is not passed to Benefits Determiner or Pricer, and is not stored in the Data Service.

**Rationale**: Spec explicitly states "accepted but not evaluated in this implementation."

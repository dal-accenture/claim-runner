# Data Model: Pricer

**Spec**: 003-pricer | **Date**: 2026-09-02

Pydantic models for `pricer/models.py`. Backing data schemas (members, fee schedules) are in `.specify/memory/data-model.md`.

---

## Request Models

### `ClaimLine`

```python
from pydantic import BaseModel
from decimal import Decimal

class ClaimLine(BaseModel):
    line_number: int           # 1-based; preserved in response
    procedure_code: str        # CPT code — must exist in fee schedules
    units: int                 # Positive integer; billed_amount and fee schedule rate are per-unit
    billed_amount: Decimal     # Per-unit charged amount; positive
```

### `PriceRequest`

```python
class PriceRequest(BaseModel):
    claim_id: str
    member_id: str
    plan_id: str
    network_status: str        # IN_NETWORK | OUT_OF_NETWORK
    claim_lines: list[ClaimLine]  # At least one line required
```

**Validation rules:**
- All fields required; missing any returns `422`
- `network_status` must be `"IN_NETWORK"` or `"OUT_OF_NETWORK"` — use a Pydantic `Literal` or validator
- `claim_lines` must be non-empty
- `units` must be positive; `billed_amount` must be positive

---

## Response Models

### `LineDetail`

```python
class LineDetail(BaseModel):
    line_number: int
    procedure_code: str
    billed_amount: Decimal         # line_billed = per_unit × units
    allowed_amount: Decimal        # min(line_billed, fee_schedule_rate × units)
    contractual_adjustment: Decimal  # line_billed - allowed_amount
    deductible_applied: Decimal
    copay_applied: Decimal
    coinsurance_applied: Decimal
    member_liability: Decimal      # deductible + copay + coinsurance (after OOP cap)
    payer_liability: Decimal       # allowed_amount - member_liability
    adjustment_reason_code: str    # "CO-45" if contractual_adjustment > 0, else null or omitted
    line_status: str               # "PAID"
```

### `ClaimTotals`

```python
class ClaimTotals(BaseModel):
    billed_amount: Decimal
    allowed_amount: Decimal
    member_liability: Decimal
    payer_liability: Decimal
```

### `AccumulatorSnapshot`

```python
class AccumulatorSnapshot(BaseModel):
    individual_deductible_used_before: Decimal  # seeded value from members.json
    individual_deductible_used_after: Decimal   # before + deductible_used_this_claim
    individual_oop_used_before: Decimal         # seeded value from members.json
    individual_oop_used_after: Decimal          # before + oop_used_this_claim
```

### `PriceResponse`

```python
class PriceResponse(BaseModel):
    claim_id: str
    totals: ClaimTotals
    accumulator_snapshot: AccumulatorSnapshot
    line_detail: list[LineDetail]
```

---

## Internal Exception Models

```python
class DataServiceError(Exception):
    """Raised by data_client.py on connectivity failure or unexpected status."""
    pass

class MemberNotFoundError(Exception):
    member_id: str

class PlanNotFoundError(Exception):
    plan_id: str
```

Exception handlers in `main.py`:
- `DataServiceError` → `503 {"detail": "Data Service unavailable"}`
- `MemberNotFoundError` → `404 {"detail": "Member {member_id} not found"}`
- `PlanNotFoundError` → `404 {"detail": "Plan {plan_id} not found"}`

Procedure code not found is handled inline: `422 {"detail": "Procedure code {code} not found in fee schedules"}`.

---

## Cost-Sharing Algorithm Inputs (from Data Service)

### From `GET /members/{member_id}` → 200

```json
{
  "accumulators": {
    "individual_deductible": { "limit": 250.00, "used": 125.00, "met": false },
    "individual_oop_max":    { "limit": 2000.00, "used": 155.00, "met": false }
  }
}
```

### From `GET /fee-schedules/{procedure_code}` → 200

```json
{
  "in_network": {
    "allowed_amount": 115.00,
    "copay": 30.00,
    "copay_applies_before_deductible": true,
    "coinsurance_pct": 0.00
  },
  "out_of_network": {
    "allowed_amount": 84.00,
    "copay": 0.00,
    "copay_applies_before_deductible": false,
    "coinsurance_pct": 0.40
  }
}
```

Select `in_network` or `out_of_network` block based on `request.network_status`.

---

## Invariants

- `member_liability + payer_liability == allowed_amount` for every `LineDetail`
- `totals.member_liability == sum(ld.member_liability for ld in line_detail)`
- `totals.payer_liability == sum(ld.payer_liability for ld in line_detail)`
- `accumulator_snapshot.individual_deductible_used_after == before + deductible_used_this_claim`
- `accumulator_snapshot.individual_oop_used_after == before + oop_used_this_claim`

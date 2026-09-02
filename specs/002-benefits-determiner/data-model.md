# Data Model: Benefits Determiner

**Spec**: 002-benefits-determiner | **Date**: 2026-09-02

This document defines the Pydantic models used by `benefits_determiner/models.py`. The backing data schemas (members, plans) are in `.specify/memory/data-model.md`; this document covers only the API request/response shapes.

---

## Request Model — `DetermineRequest`

```python
from pydantic import BaseModel
from datetime import date

class DetermineRequest(BaseModel):
    member_id: str
    provider_id: str
    procedure_codes: list[str]   # one or more CPT codes; e.g. ["99213", "42820"]
    date_of_service: date        # parsed from "YYYY-MM-DD"; FastAPI returns 422 if malformed
```

**Validation rules:**
- All four fields required — FastAPI returns `422` if any is missing or `procedure_codes` is empty
- `procedure_codes` must be a non-empty list; FastAPI enforces the list type
- `date_of_service` parsed by Pydantic as `datetime.date`

---

## Response Models

### `LineDetermination`

One entry per procedure code submitted.

```python
class LineDetermination(BaseModel):
    procedure_code: str
    covered: bool
    requires_auth: bool            # true if the covered entry has requires_auth: true
    auth_on_file: str | None       # auth_id if a valid auth was found; null otherwise
    denial_reason: str | None      # NOT_COVERED | AUTH_REQUIRED_NOT_ON_FILE | null
```

### `DetermineResponse`

Returned from `POST /benefits/determine` on a successful determination.

```python
class DetermineResponse(BaseModel):
    member_id: str
    plan_id: str | None            # null when member not found (NOT_ELIGIBLE early return)
    eligible: bool
    network_status: str | None     # IN_NETWORK | OUT_OF_NETWORK; null on early return
    overall_covered: bool          # true only when ALL line_determinations have covered: true
    line_determinations: list[LineDetermination]  # empty on NOT_ELIGIBLE / PLAN_TERMINATED
    denial_reason: str | None      # NOT_ELIGIBLE | PLAN_TERMINATED; null if eligible
```

---

## Denial Reason Codes

| Code | Scope | Source |
|---|---|---|
| `NOT_ELIGIBLE` | claim-level | Member not found (Data Service returns 404 for member_id) |
| `PLAN_TERMINATED` | claim-level | Member exists; `enrollment.termination_date < date_of_service` |
| `NOT_COVERED` | line-level | Code in `excluded_procedure_codes` or absent from `covered_procedure_codes` |
| `AUTH_REQUIRED_NOT_ON_FILE` | line-level | Code needs auth (`requires_auth: true`) but no valid auth found |

---

## Data Service Response Shapes (read-only reference)

The Data Service returns raw JSON from the seed files. Benefits Determiner reads these fields:

### From `GET /members/{member_id}` → 200

```json
{
  "enrollment": {
    "plan_id": "string",
    "effective_date": "YYYY-MM-DD",
    "termination_date": "YYYY-MM-DD | null"
  },
  "authorizations": [
    {
      "auth_id": "string",
      "procedure_code": "string",
      "authorized_date": "YYYY-MM-DD",
      "expiration_date": "YYYY-MM-DD"
    }
  ]
}
```

### From `GET /plans/{plan_id}` → 200

```json
{
  "network_provider_ids": ["string"],
  "covered_procedure_codes": [
    { "code": "string", "requires_auth": true | false }
  ],
  "excluded_procedure_codes": [
    { "code": "string" }
  ]
}
```

**Critical**: The field name is `"code"` (not `"procedure_code"`) in both `covered_procedure_codes` and `excluded_procedure_codes` objects. See research.md Decision 4.

---

## Internal Exception

```python
class DataServiceError(Exception):
    """Raised by data_client.py when the Data Service is unreachable or returns an unexpected status."""
    pass
```

`main.py` registers a FastAPI exception handler: `DataServiceError` → `503 {"detail": "Data Service unavailable"}`.

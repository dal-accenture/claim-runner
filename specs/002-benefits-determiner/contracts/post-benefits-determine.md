# Contract: POST /benefits/determine

**Service**: Benefits Determiner (port 8081)  
**Caller**: Claims Manager  
**Spec**: 002-benefits-determiner

---

## Request

```
POST /benefits/determine
Content-Type: application/json
```

```json
{
  "member_id":       "string",        // required
  "provider_id":     "string",        // required
  "procedure_codes": ["string", ...], // required; one or more CPT codes
  "date_of_service": "YYYY-MM-DD"     // required; ISO 8601 date
}
```

---

## Response — 200 OK: All lines covered

```json
{
  "member_id": "MBR-10042",
  "plan_id": "PLN-GOLD-001",
  "eligible": true,
  "network_status": "IN_NETWORK",
  "overall_covered": true,
  "line_determinations": [
    {
      "procedure_code": "99213",
      "covered": true,
      "requires_auth": false,
      "auth_on_file": null,
      "denial_reason": null
    }
  ],
  "denial_reason": null
}
```

## Response — 200 OK: Mixed (one covered, one denied)

```json
{
  "member_id": "MBR-10087",
  "plan_id": "PLN-SILVER-002",
  "eligible": true,
  "network_status": "OUT_OF_NETWORK",
  "overall_covered": false,
  "line_determinations": [
    {
      "procedure_code": "99213",
      "covered": true,
      "requires_auth": false,
      "auth_on_file": null,
      "denial_reason": null
    },
    {
      "procedure_code": "42820",
      "covered": false,
      "requires_auth": true,
      "auth_on_file": null,
      "denial_reason": "AUTH_REQUIRED_NOT_ON_FILE"
    }
  ],
  "denial_reason": null
}
```

## Response — 200 OK: Member not eligible (not found)

```json
{
  "member_id": "MBR-99999",
  "plan_id": null,
  "eligible": false,
  "network_status": null,
  "overall_covered": false,
  "line_determinations": [],
  "denial_reason": "NOT_ELIGIBLE"
}
```

## Response — 200 OK: Plan terminated

```json
{
  "member_id": "MBR-10099",
  "plan_id": null,
  "eligible": false,
  "network_status": null,
  "overall_covered": false,
  "line_determinations": [],
  "denial_reason": "PLAN_TERMINATED"
}
```

---

## Error Responses

| Status | Condition | Body |
|---|---|---|
| `422 Unprocessable Entity` | Missing or malformed required field | FastAPI default validation error with field names |
| `503 Service Unavailable` | Data Service unreachable or returned unexpected status | `{"detail": "Data Service unavailable"}` |

---

## Health Endpoint

```
GET /health
→ 200 OK
→ {"status": "ok"}
```

No body schema requirement; any 200 response satisfies the constitution.

---

## Denial Reason Codes

| Code | Scope | Trigger |
|---|---|---|
| `NOT_ELIGIBLE` | claim | Member not found in Data Service |
| `PLAN_TERMINATED` | claim | Member enrollment `termination_date` precedes `date_of_service` |
| `NOT_COVERED` | line | Procedure in `excluded_procedure_codes` or absent from `covered_procedure_codes` |
| `AUTH_REQUIRED_NOT_ON_FILE` | line | Procedure needs auth; no valid non-expired auth found in member record |

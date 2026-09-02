# Data Model: Data Service

**Date**: 2026-09-02 | **Spec**: [spec.md](spec.md)

---

## Source schemas

All four JSON seed file schemas are defined in
`.specify/memory/data-model.md` (v1.1, distributed from the control pod).
This document records the **in-memory store structures** used by the Data
Service at runtime — not the JSON shapes, which are unchanged.

---

## In-memory stores

The Data Service maintains four module-level dicts populated at startup:

| Store | Python type | Key | Value | Source file |
|---|---|---|---|---|
| `_members` | `dict[str, dict]` | `member_id` | Full member record (dict) | `members.json` |
| `_plans` | `dict[str, dict]` | `plan_id` | Full plan record (dict) | `plans.json` |
| `_fee_schedules` | `dict[str, dict]` | `procedure_code` | Full fee schedule entry (dict) | `fee_schedules.json` |
| `_claims` | `dict[str, dict]` | `claim_id` | Full claim ledger record (dict) | `claims.json` |

Values are raw Python dicts parsed from JSON — no Pydantic model layer in the
store. The seed data from spec 004 is trusted input; re-validating it on every
read would add overhead with no benefit.

---

## Startup loading sequence

```
lifespan start
  ├── Load members.json   → _members   (keyed by member_id)
  ├── Load plans.json     → _plans     (keyed by plan_id)
  ├── Load fee_schedules.json → _fee_schedules (keyed by procedure_code)
  ├── Load claims.json    → _claims    (keyed by claim_id)
  │     └── if missing: initialize _claims = {}; log INFO
  └── Log startup: port, len(_members), len(_plans),
                   len(_fee_schedules), len(_claims)
```

If `members.json`, `plans.json`, or `fee_schedules.json` is missing:
log CRITICAL and `sys.exit(1)`.

---

## Write path — POST /claims

```
POST /claims
  ├── Validate body (FastAPI / Pydantic at request boundary)
  ├── Check claim_id not in _claims → 409 if present
  ├── async with _lock:
  │     _claims[claim_id] = record
  └── Return 201 with stored record
```

`_lock` is a module-level `asyncio.Lock`. The critical section is the dict
mutation only — validation happens before acquiring the lock.

---

## Seed data volumes (from spec 004)

| Collection | Count at startup |
|---|---|
| `_members` | 200 |
| `_plans` | 5 |
| `_fee_schedules` | 25 |
| `_claims` | ≥ 150 (pre-seeded) |

All counts reported in the `/health` response and the startup log.

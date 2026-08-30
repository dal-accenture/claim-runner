# Spec: Seed Data Generation

**Intake ID:** 0004-seed-data  
**Pod:** claim-runner  
**Pod spec number:** claim-runner/004  
**Status:** Ready for allocation  
**Constitution references:** Data Layer, Technology Stack  
**Source:** `intake/0004-seed-data.md`

---

## Goal

Produce four fully populated JSON seed files — `plans.json`, `fee_schedules.json`, `members.json`, and `claims.json` — committed to the `data/` directory of the pod repository. These files are the complete data layer for the practicum system. They must be loadable directly by the three services at startup, internally consistent, and cover every adjudication scenario the integration test suite needs to exercise.

The implementation is a one-time generation script (`scripts/generate_seed_data.py`) that writes the four files. The script is committed to the repository; the generated files are also committed (they are not generated at service startup).

---

## Out of Scope

- Runtime data generation or seeding at service startup
- Database population
- Accumulator write-back simulation beyond what is described below
- Data for institutional claims (837I / CMS-1450)

---

## Functional Requirements

### FR-1 — Procedure code vocabulary

The following CPT codes form the complete vocabulary across all plans and fee schedules. Every plan must take a position on each code: covered, covered with authorization required, or excluded.

**General Practice (GP) — 14 codes**

| CPT | Description |
|---|---|
| `99202` | Office visit, new patient, straightforward complexity |
| `99203` | Office visit, new patient, low complexity |
| `99204` | Office visit, new patient, moderate complexity |
| `99205` | Office visit, new patient, high complexity |
| `99211` | Office visit, established patient, minimal |
| `99212` | Office visit, established patient, straightforward |
| `99213` | Office visit, established patient, low complexity |
| `99214` | Office visit, established patient, moderate complexity |
| `99215` | Office visit, established patient, high complexity |
| `99395` | Preventive visit, established patient, 18–39 years |
| `99396` | Preventive visit, established patient, 40–64 years |
| `93000` | ECG with interpretation |
| `85025` | CBC with differential |
| `80053` | Comprehensive metabolic panel |

**ENT — 11 codes**

| CPT | Description |
|---|---|
| `92504` | Binocular microscopy of the ear |
| `92551` | Screening test, pure tone, air only |
| `92552` | Pure tone audiometry, air only |
| `92557` | Comprehensive audiometry |
| `69210` | Removal of impacted cerumen |
| `31575` | Laryngoscopy, flexible, diagnostic |
| `42820` | Tonsillectomy/adenoidectomy, patient ≤12 |
| `42821` | Tonsillectomy/adenoidectomy, patient >12 |
| `30140` | Submucous resection of turbinate |
| `30520` | Septoplasty |
| `31240` | Nasal/sinus endoscopy, surgical |

### FR-2 — plans.json (5 records)

| Plan ID | Name | Type | Deductible | OOP Max |
|---|---|---|---|---|
| `PLN-GOLD-001` | Gold PPO | PPO | $250 | $2,000 |
| `PLN-SILVER-002` | Silver PPO | PPO | $750 | $4,500 |
| `PLN-BRONZE-003` | Bronze HDHP | HDHP | $1,500 | $7,000 |
| `PLN-PREMIER-004` | Premier HMO | HMO | $0 | $1,500 |
| `PLN-BASIC-005` | Basic EPO | EPO | $1,000 | $5,000 |

Plan year: `2025`. Effective date: `2025-01-01`. Termination date: `2025-12-31`.

**Coverage matrix (ENT codes — all plans cover all 14 GP codes unless noted):**

| CPT | GOLD | SILVER | BRONZE | PREMIER | BASIC |
|---|---|---|---|---|---|
| `92504`–`69210` (diagnostic ENT) | Covered | Covered | Covered | Covered (auth) | Covered |
| `31575` (laryngoscopy) | Covered | Covered | Covered | Covered (auth) | Excluded |
| `42820`, `42821`, `30140`, `30520`, `31240` (surgical ENT) | Covered (auth) | Excluded | Excluded | Covered (auth) | Excluded |
| `99395`, `99396` (preventive) | Covered | Covered | Covered | Covered | Excluded |
| `93000`, `85025`, `80053` (diagnostic lab/ECG) | Covered | Covered | Covered | Covered | Excluded |
| Basic EPO GP: `99202`–`99215` | — | — | — | — | Covered |

Exclusion reason for Silver/Bronze surgical ENT: `"Requires specialist rider"`.  
Exclusion reason for Basic EPO non-core codes: `"Not covered under Basic EPO benefit"`.

**Network provider IDs:**

| Plan | In-network provider IDs |
|---|---|
| `PLN-GOLD-001` | `PRV-10001` through `PRV-10015` |
| `PLN-SILVER-002` | `PRV-10005` through `PRV-10020` |
| `PLN-BRONZE-003` | `PRV-10010` through `PRV-10025` |
| `PLN-PREMIER-004` | `PRV-20001` through `PRV-20010` |
| `PLN-BASIC-005` | `PRV-30001` through `PRV-30012` |

### FR-3 — fee_schedules.json (25 records)

One record per procedure code (14 GP + 11 ENT). Out-of-network rates are 65–75% of in-network allowed amounts.

**GP rates:**

| CPT | In-Net Allowed | OON Allowed | In-Net Copay | Pre-Ded? | In-Net Coins | OON Coins |
|---|---|---|---|---|---|---|
| `99202` | $95.00 | $70.00 | $25.00 | Yes | 0% | 40% |
| `99203` | $130.00 | $95.00 | $25.00 | Yes | 0% | 40% |
| `99204` | $185.00 | $135.00 | $40.00 | Yes | 0% | 40% |
| `99205` | $250.00 | $185.00 | $40.00 | Yes | 0% | 40% |
| `99211` | $45.00 | $33.00 | $15.00 | Yes | 0% | 40% |
| `99212` | $80.00 | $58.00 | $25.00 | Yes | 0% | 40% |
| `99213` | $115.00 | $84.00 | $30.00 | Yes | 0% | 40% |
| `99214` | $170.00 | $124.00 | $40.00 | Yes | 0% | 40% |
| `99215` | $230.00 | $168.00 | $40.00 | Yes | 0% | 40% |
| `99395` | $185.00 | $135.00 | $0.00 | Yes | 0% | 40% |
| `99396` | $220.00 | $161.00 | $0.00 | Yes | 0% | 40% |
| `93000` | $75.00 | $55.00 | $0.00 | No | 10% | 40% |
| `85025` | $22.00 | $16.00 | $0.00 | No | 10% | 40% |
| `80053` | $28.00 | $20.00 | $0.00 | No | 10% | 40% |

**ENT rates:**

| CPT | In-Net Allowed | OON Allowed | In-Net Copay | Pre-Ded? | In-Net Coins | OON Coins |
|---|---|---|---|---|---|---|
| `92504` | $95.00 | $69.00 | $50.00 | Yes | 0% | 40% |
| `92551` | $35.00 | $26.00 | $50.00 | Yes | 0% | 40% |
| `92552` | $55.00 | $40.00 | $50.00 | Yes | 0% | 40% |
| `92557` | $95.00 | $69.00 | $50.00 | Yes | 0% | 40% |
| `69210` | $65.00 | $47.00 | $50.00 | Yes | 0% | 40% |
| `31575` | $285.00 | $208.00 | $75.00 | No | 10% | 40% |
| `42820` | $2,800.00 | $2,044.00 | $0.00 | No | 10% | 40% |
| `42821` | $3,200.00 | $2,336.00 | $0.00 | No | 10% | 40% |
| `30140` | $3,400.00 | $2,482.00 | $0.00 | No | 10% | 40% |
| `30520` | $4,100.00 | $2,993.00 | $0.00 | No | 10% | 40% |
| `31240` | $3,800.00 | $2,774.00 | $0.00 | No | 10% | 40% |

### FR-4 — members.json (200 records)

**Distribution:**

| Plan | Count |
|---|---|
| `PLN-GOLD-001` | 40 |
| `PLN-SILVER-002` | 55 |
| `PLN-BRONZE-003` | 50 |
| `PLN-PREMIER-004` | 30 |
| `PLN-BASIC-005` | 25 |

Member IDs: `MBR-10001` through `MBR-10200`.

**Demographics:**

| Age band | % | Count |
|---|---|---|
| 18–29 | 15% | 30 |
| 30–44 | 30% | 60 |
| 45–59 | 35% | 70 |
| 60+ | 20% | 40 |

Gender: approximately 50% M / 45% F / 5% X.

Enrollment: single active enrollment per member. `effective_date: 2025-01-01`, `termination_date: null`.

`family_deductible` and `family_oop_max` are `null` for all 200 members (individual coverage).

**Accumulator seeding (mid-year snapshot):**

| State | % | Count |
|---|---|---|
| Untouched (`used = 0.00`, `met = false`) | 20% | 40 |
| Partially used (1%–80% of limit) | 50% | 100 |
| Deductible met, OOP partially used | 20% | 40 |
| OOP max met (both `met = true`) | 10% | 20 |

The `met` flag must be `true` if and only if `used >= limit`.

**Authorizations** (relevant for Gold and Premier plans only):

| Plan | Members with auths | Codes |
|---|---|---|
| `PLN-GOLD-001` | 12 of 40 | Subset of `42820`, `42821`, `30140`, `30520`, `31240` |
| `PLN-PREMIER-004` | 15 of 30 | Subset of all 11 ENT codes |

Authorization dates should be distributed so that some are active and some are expired (to exercise the auth-expired denial path).

### FR-5 — claims.json (≥150 records, pre-seeded for 140 members)

Claims are pre-adjudicated (status already set). Dates span `2025-01-01` through `2025-08-31`. Claim ID format: `CLM-YYYYMMDD-NNN`.

**Volume by category:**

| Category | Count |
|---|---|
| Paid, in-network GP visit | 70 |
| Paid, in-network ENT diagnostic | 30 |
| Paid, in-network ENT surgical (with valid auth) | 10 |
| Partially paid (mixed lines) | 10 |
| Denied — not covered (excluded by plan) | 10 |
| Denied — auth required, not on file | 10 |
| Paid, out-of-network | 10 |
| **Total** | **150** |

**Financial consistency rules:**

- `allowed_amount` must match the fee schedule for the procedure code and network status
- `member_liability + payer_liability = allowed_amount` for every claim and every line
- `deductible_applied`, `copay_applied`, and `coinsurance_applied` must follow the pricing logic in spec `0003-pricer`
- Accumulator `used` values in `members.json` must be consistent with the sum of cost-sharing across that member's paid claims in `claims.json` — pre-seeding simulates the write-back that the runtime deliberately defers

### FR-6 — Generation script

The script lives at `scripts/generate_seed_data.py`. It writes all four files to `data/`. The script must be re-runnable (idempotent — it overwrites existing files). It requires Python 3.11+ and no dependencies outside the standard library.

---

## Domain Model

Output file schemas are defined in `architecture/data-model.md`. This spec references those schemas and does not repeat them. All generated records must conform exactly to the v1.1 schemas.

---

## Integration

This spec does not produce any API service. The output files (`data/plans.json`, `data/fee_schedules.json`, `data/members.json`, `data/claims.json`) are consumed by the three services defined in specs `0001-claims-manager`, `0002-benefits-determiner`, and `0003-pricer`.

**Dependency:** This spec should be implemented before or in parallel with the three service specs. The services must have loadable data files to run against.

---

## Scenario coverage checklist

The dataset must cover the following scenarios so integration tests can exercise every adjudication path using seed data alone:

| Scenario | At least N |
|---|---|
| In-network GP visit, copay only (deductible not met) | 20 claims |
| In-network GP visit, deductible fully met | 10 claims |
| In-network GP preventive, $0 copay / $0 cost-sharing | 5 claims |
| In-network ENT diagnostic with specialist copay | 10 claims |
| In-network ENT surgical with auth, coinsurance applies | 5 claims |
| ENT surgical denied — auth required, not on file | 5 claims |
| ENT surgical denied — excluded by plan | 5 claims |
| Out-of-network visit, coinsurance applies | 5 claims |
| OOP max already met, payer absorbs 100% | 3 claims |
| Multi-line claim, all lines paid | 5 claims |
| Multi-line claim, partially paid | 5 claims |
| Member with no claim history | 60 members |

---

## Constraints

- All four output files must conform to the v1.1 schemas in `architecture/data-model.md`. (Constitution: Data Layer)
- The generation script is POSIX-compatible Python; no package manifest is added to the repository root. (Constitution: Technology Stack, AGENTS.md §2)
- No application code in this repository. The script lives in `scripts/` in the pod repository, not in the control pod. (AGENTS.md §2)
- This spec covers the data layer only. Changes to any service API triggered by the data design are a separate spec. (Constitution: Spec Scope, Decision 0001)

---

## Acceptance Criteria

1. `plans.json` contains exactly 5 records; each has a non-empty `covered_procedure_codes` array and a non-empty `network_provider_ids` array.
2. `fee_schedules.json` contains exactly 25 records (14 GP + 11 ENT); every procedure code in the coverage matrix has a matching entry.
3. `members.json` contains exactly 200 records; each references a valid `plan_id` from `plans.json`.
4. Every member's accumulator `met` flag is `true` if and only if `used >= limit`.
5. `claims.json` contains at least 150 pre-seeded records; every claim references a valid `member_id` from `members.json`.
6. Every pre-seeded claim satisfies `totals.member_liability + totals.payer_liability = totals.allowed_amount`.
7. Every pre-seeded claim's `allowed_amount` matches the fee schedule rate for that procedure code and network status.
8. Pre-seeded member accumulator `used` values in `members.json` are reconcilable against the sum of cost-sharing in that member's paid claims in `claims.json`.
9. At least one member per plan has claims covering each applicable outcome type (PAID, DENIED, PARTIALLY_PAID).
10. No claim in `claims.json` references a `member_id` absent from `members.json`.
11. No claim references a procedure code absent from `fee_schedules.json`.
12. The generation script runs to completion with `python scripts/generate_seed_data.py` and overwrites existing output files without error.
13. Every scenario in the scenario coverage checklist is satisfied by at least the minimum number of claims specified.

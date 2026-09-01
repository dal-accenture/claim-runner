# Claims Adjudication — Data Model

**Version:** 1.1  
**Status:** Active  
**Change from v1.0:** Added claim ledger (`claims.json`); removed provider registry, accumulator write-back, and plan-year rollover; documented provider trust assumption.

---

## 1. Overview

This document defines the data model for the four JSON mock files loaded by the Data Service at startup and served over HTTP to the adjudication services:

| File | Owned / Loaded By | Purpose |
|---|---|---|
| `plans.json` | Data Service | Plan definitions, covered/excluded procedure codes, network provider lists, cost-sharing rules |
| `members.json` | Data Service | Member registration, plan enrollment, accumulators, authorizations |
| `fee_schedules.json` | Data Service | Allowed amounts, copays, and coinsurance by procedure code and network status |
| `claims.json` | Data Service (read/write) | Durable ledger of all submitted and adjudicated claims |

### Key Assumptions

- **Provider trust.** All providers are assumed to be valid and credentialed. Provider IDs are accepted as submitted; no provider registry or credential check is performed. Network status (in-network vs. out-of-network) is still determined by whether the `provider_id` appears in the plan's `network_provider_ids` list.
- **Accumulators are read-only.** Deductible and OOP accumulator balances in `members.json` are seeded manually and read at adjudication time. They are not updated after each claim. This is a known mock limitation.
- **Single active enrollment per member.** Each member has one active plan enrollment at any given time.

---

## 2. Plan Definition — `plans.json`

A plan defines what services are covered, which procedure codes are accepted or excluded, and which providers are in-network.

### Schema

```json
{
  "plan_id": "string",              // Unique plan identifier. E.g. "PLN-GOLD-001"
  "plan_name": "string",            // Human-readable name. E.g. "Gold PPO"
  "plan_year": "string",            // Coverage year. E.g. "2025"
  "plan_type": "string",            // PPO | HMO | EPO | HDHP
  "effective_date": "date",         // Plan available from. E.g. "2025-01-01"
  "termination_date": "date",       // Plan expires after. E.g. "2025-12-31"

  "network_provider_ids": [         // Provider IDs considered in-network for this plan.
    "string"                        // Any provider_id NOT in this list is out-of-network.
  ],

  "covered_procedure_codes": [      // Procedure codes covered by the plan
    {
      "code": "string",             // CPT code. E.g. "99213"
      "description": "string",      // Human-readable. E.g. "Office visit, established patient"
      "requires_auth": "boolean"    // Whether prior authorization is required
    }
  ],

  "excluded_procedure_codes": [     // Procedure codes explicitly NOT covered by the plan
    {
      "code": "string",             // CPT code. E.g. "99281"
      "description": "string",
      "exclusion_reason": "string"  // E.g. "Cosmetic", "Requires ER rider"
    }
  ]
}
```

### Sample Record

```json
{
  "plan_id": "PLN-GOLD-001",
  "plan_name": "Gold PPO",
  "plan_year": "2025",
  "plan_type": "PPO",
  "effective_date": "2025-01-01",
  "termination_date": "2025-12-31",

  "network_provider_ids": ["PRV-90210", "PRV-10001", "PRV-10002"],

  "covered_procedure_codes": [
    { "code": "99203", "description": "Office visit, new patient — GP",               "requires_auth": false },
    { "code": "99213", "description": "Office visit, established patient — GP",        "requires_auth": false },
    { "code": "99214", "description": "Office visit, established patient, complex — GP","requires_auth": false },
    { "code": "92504", "description": "Binocular microscopy — ENT",                    "requires_auth": false },
    { "code": "42820", "description": "Tonsillectomy — ENT",                           "requires_auth": true  },
    { "code": "30140", "description": "Submucous resection, turbinate — ENT",          "requires_auth": true  }
  ],

  "excluded_procedure_codes": [
    { "code": "99281", "description": "Emergency dept visit, minimal",  "exclusion_reason": "Not covered; requires ER rider" },
    { "code": "21210", "description": "Graft, bone nasal area",         "exclusion_reason": "Cosmetic" }
  ]
}
```

---

## 3. Member Registration — `members.json`

A member record ties an individual to a plan and carries their current accumulator balances (seeded manually; not updated at runtime in this implementation).

### Schema

```json
{
  "member_id": "string",            // Unique member identifier. E.g. "MBR-10042"
  "first_name": "string",
  "last_name": "string",
  "date_of_birth": "date",          // E.g. "1985-04-12"
  "gender": "string",               // M | F | X
  "contact": {
    "email": "string",
    "phone": "string",
    "address": "string"
  },

  "enrollment": {
    "plan_id": "string",            // Foreign key → plans.plan_id
    "effective_date": "date",       // When coverage began
    "termination_date": "date"      // null if currently active
  },

  "accumulators": {
    "plan_year": "string",          // Year these balances apply to. E.g. "2025"

    "individual_deductible": {
      "limit": "number",            // Plan's annual deductible ceiling. E.g. 500.00
      "used": "number",             // Amount counted toward deductible to date. E.g. 125.00
      "met": "boolean"              // true when used >= limit
    },

    "family_deductible": {          // null for members on individual-only plans
      "limit": "number",
      "used": "number",
      "met": "boolean"
    },

    "individual_oop_max": {
      "limit": "number",            // Plan's annual OOP maximum. E.g. 4000.00
      "used": "number",             // Total member cost-sharing accumulated to date
      "met": "boolean"              // true when used >= limit; payer pays 100% beyond this
    },

    "family_oop_max": {             // null for members on individual-only plans
      "limit": "number",
      "used": "number",
      "met": "boolean"
    }
  },

  "authorizations": [               // Prior authorizations on file for this member
    {
      "auth_id": "string",          // E.g. "AUTH-00321"
      "procedure_code": "string",   // CPT code the auth covers
      "authorized_date": "date",
      "expiration_date": "date"
    }
  ]
}
```

### Sample Record

```json
{
  "member_id": "MBR-10042",
  "first_name": "Jane",
  "last_name": "Smith",
  "date_of_birth": "1985-04-12",
  "gender": "F",
  "contact": {
    "email": "jane.smith@email.com",
    "phone": "555-123-4567",
    "address": "123 Main St, Springfield, IL 62701"
  },

  "enrollment": {
    "plan_id": "PLN-GOLD-001",
    "effective_date": "2025-01-01",
    "termination_date": null
  },

  "accumulators": {
    "plan_year": "2025",

    "individual_deductible": {
      "limit": 500.00,
      "used": 125.00,
      "met": false
    },
    "family_deductible": null,

    "individual_oop_max": {
      "limit": 4000.00,
      "used": 155.00,
      "met": false
    },
    "family_oop_max": null
  },

  "authorizations": [
    {
      "auth_id": "AUTH-00321",
      "procedure_code": "42820",
      "authorized_date": "2025-08-01",
      "expiration_date": "2025-11-01"
    }
  ]
}
```

---

## 4. Service Pricing — `fee_schedules.json`

Defines allowed amounts and cost-sharing rules per procedure code, split by network status. Covers **General Practice (GP)** and **Ear, Nose & Throat (ENT)** service categories.

### Schema

```json
{
  "procedure_code": "string",         // CPT code. E.g. "99213"
  "description": "string",
  "service_category": "string",       // GP | ENT

  "in_network": {
    "allowed_amount": "number",        // Maximum payable by the plan in-network
    "copay": "number",                 // Fixed member copay; 0.00 if none
    "copay_applies_before_deductible": "boolean", // true for most office visits
    "coinsurance_pct": "number"        // Member share after deductible. E.g. 0.10 = 10%
  },

  "out_of_network": {
    "allowed_amount": "number",        // Maximum payable by the plan out-of-network (UCR basis)
    "copay": "number",
    "copay_applies_before_deductible": "boolean",
    "coinsurance_pct": "number"
  }
}
```

### Sample Records

```json
[
  {
    "procedure_code": "99203",
    "description": "Office visit, new patient (low complexity) — GP",
    "service_category": "GP",
    "in_network":      { "allowed_amount": 145.00, "copay": 30.00, "copay_applies_before_deductible": true,  "coinsurance_pct": 0.00 },
    "out_of_network":  { "allowed_amount": 110.00, "copay":  0.00, "copay_applies_before_deductible": false, "coinsurance_pct": 0.40 }
  },
  {
    "procedure_code": "99213",
    "description": "Office visit, established patient (moderate complexity) — GP",
    "service_category": "GP",
    "in_network":      { "allowed_amount": 115.00, "copay": 30.00, "copay_applies_before_deductible": true,  "coinsurance_pct": 0.00 },
    "out_of_network":  { "allowed_amount":  85.00, "copay":  0.00, "copay_applies_before_deductible": false, "coinsurance_pct": 0.40 }
  },
  {
    "procedure_code": "99214",
    "description": "Office visit, established patient (high complexity) — GP",
    "service_category": "GP",
    "in_network":      { "allowed_amount": 175.00, "copay": 30.00, "copay_applies_before_deductible": true,  "coinsurance_pct": 0.00 },
    "out_of_network":  { "allowed_amount": 130.00, "copay":  0.00, "copay_applies_before_deductible": false, "coinsurance_pct": 0.40 }
  },
  {
    "procedure_code": "92504",
    "description": "Binocular microscopy — ENT",
    "service_category": "ENT",
    "in_network":      { "allowed_amount":  95.00, "copay": 50.00, "copay_applies_before_deductible": true,  "coinsurance_pct": 0.00 },
    "out_of_network":  { "allowed_amount":  70.00, "copay":  0.00, "copay_applies_before_deductible": false, "coinsurance_pct": 0.40 }
  },
  {
    "procedure_code": "42820",
    "description": "Tonsillectomy, patient age 12 or under — ENT",
    "service_category": "ENT",
    "in_network":      { "allowed_amount": 2800.00, "copay": 0.00, "copay_applies_before_deductible": false, "coinsurance_pct": 0.10 },
    "out_of_network":  { "allowed_amount": 2100.00, "copay": 0.00, "copay_applies_before_deductible": false, "coinsurance_pct": 0.40 }
  },
  {
    "procedure_code": "30140",
    "description": "Submucous resection, turbinate — ENT",
    "service_category": "ENT",
    "in_network":      { "allowed_amount": 3200.00, "copay": 0.00, "copay_applies_before_deductible": false, "coinsurance_pct": 0.10 },
    "out_of_network":  { "allowed_amount": 2400.00, "copay": 0.00, "copay_applies_before_deductible": false, "coinsurance_pct": 0.40 }
  }
]
```

---

## 5. Claim Ledger — `claims.json`

The claim ledger is the durable record of every claim submitted to the Claims Manager. It is written after each adjudication and serves as the backing store for `GET /claims/{claim_id}`. Because accumulators are not written back to `members.json`, the ledger is also the authoritative audit trail for what was paid and why.

### Schema

```json
{
  "claim_id": "string",              // Unique claim identifier. E.g. "CLM-20250901-001"
  "member_id": "string",             // Foreign key → members.member_id
  "provider_id": "string",           // Rendering provider (trusted as submitted)
  "date_of_service": "date",         // E.g. "2025-09-01"
  "received_at": "datetime",         // ISO 8601 timestamp when claim entered the system
  "adjudicated_at": "datetime",      // ISO 8601 timestamp when adjudication completed; null if pending

  "status": "string",                // RECEIVED | ADJUDICATED | PAID | DENIED | PARTIALLY_PAID

  "totals": {
    "billed_amount": "number",       // Sum of all line billed amounts
    "allowed_amount": "number",      // Sum of all line allowed amounts
    "member_liability": "number",    // Total owed by the member across all lines
    "payer_liability": "number"      // Total owed by the plan across all lines
  },

  "denial_reasons": [                // Empty array if claim is fully paid
    {
      "code": "string",              // E.g. "NOT_COVERED", "AUTH_REQUIRED_NOT_ON_FILE"
      "description": "string",
      "procedure_code": "string"     // The specific line this denial applies to; null if claim-level
    }
  ],

  "line_detail": [                   // One entry per claim line submitted
    {
      "line_number": "integer",
      "procedure_code": "string",
      "billed_amount": "number",
      "allowed_amount": "number",
      "deductible_applied": "number",   // Amount counted toward deductible on this line
      "copay_applied": "number",
      "coinsurance_applied": "number",
      "member_liability": "number",     // Sum of deductible + copay + coinsurance for this line
      "payer_liability": "number",      // allowed_amount minus member_liability
      "adjustment_reason_code": "string", // Standard CARC code. E.g. "CO-45" (contractual adjustment)
      "line_status": "string"           // PAID | DENIED
    }
  ]
}
```

### Claim Status Lifecycle

```
RECEIVED ──► ADJUDICATED ──► PAID
                         └──► DENIED
                         └──► PARTIALLY_PAID
```

A claim enters as `RECEIVED` the moment it is accepted by the Claims Manager. It moves to `ADJUDICATED` once the Benefits Determiner and Pricer have both responded. The final status is then resolved:

| Condition | Final Status |
|---|---|
| All lines covered and priced | `PAID` |
| All lines denied | `DENIED` |
| Mix of paid and denied lines | `PARTIALLY_PAID` |

### Sample Record

```json
{
  "claim_id": "CLM-20250901-001",
  "member_id": "MBR-10042",
  "provider_id": "PRV-90210",
  "date_of_service": "2025-09-01",
  "received_at": "2025-09-01T14:30:00Z",
  "adjudicated_at": "2025-09-01T14:30:01Z",

  "status": "PAID",

  "totals": {
    "billed_amount": 250.00,
    "allowed_amount": 115.00,
    "member_liability": 30.00,
    "payer_liability": 85.00
  },

  "denial_reasons": [],

  "line_detail": [
    {
      "line_number": 1,
      "procedure_code": "99213",
      "billed_amount": 250.00,
      "allowed_amount": 115.00,
      "deductible_applied": 0.00,
      "copay_applied": 30.00,
      "coinsurance_applied": 0.00,
      "member_liability": 30.00,
      "payer_liability": 85.00,
      "adjustment_reason_code": "CO-45",
      "line_status": "PAID"
    }
  ]
}
```

---

## 6. Open Considerations

These items are deferred from the current scope but should be revisited before moving beyond the mock implementation.

**Accumulator write-back.** Accumulators are seeded in `members.json` and treated as read-only at runtime. This means subsequent claims in the same session will see the same starting balances regardless of what was paid earlier. The claim ledger (`claims.json`) preserves the full adjudication history and can be used to reconstruct true YTD balances when this is eventually addressed.

**HMO referral tracking.** The current plan type is PPO, which does not require a GP referral before an ENT visit. If HMO plans are added, a referral record — structured similarly to the existing `authorizations` array on a member — would be needed to gate specialist visits.

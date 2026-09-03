#!/usr/bin/env python3
"""Generate seed data for the claim-runner practicum system."""

import json
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))

# ── Code vocabulary ────────────────────────────────────────────────────────────

GP_CORE = ["99202", "99203", "99204", "99205", "99211", "99212", "99213", "99214", "99215"]
GP_PREV = ["99395", "99396"]
GP_LAB  = ["93000", "85025", "80053"]
GP_ALL  = GP_CORE + GP_PREV + GP_LAB

ENT_DIAG     = ["92504", "92551", "92552", "92557", "69210"]
ENT_LARYNGO  = ["31575"]
ENT_SURGICAL = ["42820", "42821", "30140", "30520", "31240"]
ENT_ALL      = ENT_DIAG + ENT_LARYNGO + ENT_SURGICAL

ALL_CODES = GP_ALL + ENT_ALL

CODE_META = {
    "99202": ("Office visit, new patient, straightforward complexity", "GP"),
    "99203": ("Office visit, new patient, low complexity", "GP"),
    "99204": ("Office visit, new patient, moderate complexity", "GP"),
    "99205": ("Office visit, new patient, high complexity", "GP"),
    "99211": ("Office visit, established patient, minimal", "GP"),
    "99212": ("Office visit, established patient, straightforward", "GP"),
    "99213": ("Office visit, established patient, low complexity", "GP"),
    "99214": ("Office visit, established patient, moderate complexity", "GP"),
    "99215": ("Office visit, established patient, high complexity", "GP"),
    "99395": ("Preventive visit, established patient, 18-39 years", "GP"),
    "99396": ("Preventive visit, established patient, 40-64 years", "GP"),
    "93000": ("ECG with interpretation", "GP"),
    "85025": ("CBC with differential", "GP"),
    "80053": ("Comprehensive metabolic panel", "GP"),
    "92504": ("Binocular microscopy of the ear", "ENT"),
    "92551": ("Screening test, pure tone, air only", "ENT"),
    "92552": ("Pure tone audiometry, air only", "ENT"),
    "92557": ("Comprehensive audiometry", "ENT"),
    "69210": ("Removal of impacted cerumen", "ENT"),
    "31575": ("Laryngoscopy, flexible, diagnostic", "ENT"),
    "42820": ("Tonsillectomy/adenoidectomy, patient age 12 or under", "ENT"),
    "42821": ("Tonsillectomy/adenoidectomy, patient age over 12", "ENT"),
    "30140": ("Submucous resection of turbinate", "ENT"),
    "30520": ("Septoplasty", "ENT"),
    "31240": ("Nasal/sinus endoscopy, surgical", "ENT"),
}

# ── Fee schedule rates ─────────────────────────────────────────────────────────
# (in_net_allowed, oon_allowed, copay, copay_applies_before_ded, in_net_coins_pct)

FEE_RATES = {
    "99202": (95.00,    70.00,   25.00, True,  0.00),
    "99203": (130.00,   95.00,   25.00, True,  0.00),
    "99204": (185.00,  135.00,   40.00, True,  0.00),
    "99205": (250.00,  185.00,   40.00, True,  0.00),
    "99211": (45.00,    33.00,   15.00, True,  0.00),
    "99212": (80.00,    58.00,   25.00, True,  0.00),
    "99213": (115.00,   84.00,   30.00, True,  0.00),
    "99214": (170.00,  124.00,   40.00, True,  0.00),
    "99215": (230.00,  168.00,   40.00, True,  0.00),
    "99395": (185.00,  135.00,    0.00, True,  0.00),
    "99396": (220.00,  161.00,    0.00, True,  0.00),
    "93000": (75.00,    55.00,    0.00, False, 0.10),
    "85025": (22.00,    16.00,    0.00, False, 0.10),
    "80053": (28.00,    20.00,    0.00, False, 0.10),
    "92504": (95.00,    69.00,   50.00, True,  0.00),
    "92551": (35.00,    26.00,   50.00, True,  0.00),
    "92552": (55.00,    40.00,   50.00, True,  0.00),
    "92557": (95.00,    69.00,   50.00, True,  0.00),
    "69210": (65.00,    47.00,   50.00, True,  0.00),
    "31575": (285.00,  208.00,   75.00, False, 0.10),
    "42820": (2800.00, 2044.00,   0.00, False, 0.10),
    "42821": (3200.00, 2336.00,   0.00, False, 0.10),
    "30140": (3400.00, 2482.00,   0.00, False, 0.10),
    "30520": (4100.00, 2993.00,   0.00, False, 0.10),
    "31240": (3800.00, 2774.00,   0.00, False, 0.10),
}

# ── Plan metadata ──────────────────────────────────────────────────────────────

PLAN_META = [
    {"plan_id": "PLN-GOLD-001",   "plan_name": "Gold PPO",   "plan_type": "PPO",
     "deductible": 250.00,  "oop_max": 2000.00, "member_count": 40,
     "net_prefix": "PRV", "net_range": (10001, 10015)},
    {"plan_id": "PLN-SILVER-002", "plan_name": "Silver PPO", "plan_type": "PPO",
     "deductible": 750.00,  "oop_max": 4500.00, "member_count": 55,
     "net_prefix": "PRV", "net_range": (10005, 10020)},
    {"plan_id": "PLN-BRONZE-003", "plan_name": "Bronze HDHP","plan_type": "HDHP",
     "deductible": 1500.00, "oop_max": 7000.00, "member_count": 50,
     "net_prefix": "PRV", "net_range": (10010, 10025)},
    {"plan_id": "PLN-PREMIER-004","plan_name": "Premier HMO","plan_type": "HMO",
     "deductible": 0.00,    "oop_max": 1500.00, "member_count": 30,
     "net_prefix": "PRV", "net_range": (20001, 20010)},
    {"plan_id": "PLN-BASIC-005",  "plan_name": "Basic EPO",  "plan_type": "EPO",
     "deductible": 1000.00, "oop_max": 5000.00, "member_count": 25,
     "net_prefix": "PRV", "net_range": (30001, 30012)},
]

PLAN_BY_ID = {p["plan_id"]: p for p in PLAN_META}

BASIC_EXCLUDED = set(GP_PREV) | set(GP_LAB) | set(ENT_LARYNGO) | set(ENT_SURGICAL)
SILVER_BRONZE_EXCLUDED = set(ENT_SURGICAL)


# ── Fee schedules ──────────────────────────────────────────────────────────────

def generate_fee_schedules():
    result = []
    for code in ALL_CODES:
        in_net_allowed, oon_allowed, copay, pre_ded, in_coins = FEE_RATES[code]
        desc, category = CODE_META[code]
        result.append({
            "procedure_code": code,
            "description": desc,
            "service_category": category,
            "in_network": {
                "allowed_amount": in_net_allowed,
                "copay": copay,
                "copay_applies_before_deductible": pre_ded,
                "coinsurance_pct": in_coins,
            },
            "out_of_network": {
                "allowed_amount": oon_allowed,
                "copay": 0.00,
                "copay_applies_before_deductible": False,
                "coinsurance_pct": 0.40,
            },
        })
    return result


# ── Plans ──────────────────────────────────────────────────────────────────────

def _plan_coverage(plan_id, code):
    """Return ('covered', requires_auth) or ('excluded', reason)."""
    if plan_id == "PLN-BASIC-005" and code in BASIC_EXCLUDED:
        return ("excluded", "Not covered under Basic EPO benefit")
    if code in ENT_SURGICAL:
        if plan_id in ("PLN-GOLD-001", "PLN-PREMIER-004"):
            return ("covered", True)
        if plan_id in ("PLN-SILVER-002", "PLN-BRONZE-003"):
            return ("excluded", "Requires specialist rider")
    if code in ENT_LARYNGO:
        return ("covered", plan_id == "PLN-PREMIER-004")
    if code in ENT_DIAG:
        return ("covered", plan_id == "PLN-PREMIER-004")
    return ("covered", False)


def generate_plans():
    result = []
    for pm in PLAN_META:
        pid = pm["plan_id"]
        net_start, net_end = pm["net_range"]
        network = [f"PRV-{i:05d}" for i in range(net_start, net_end + 1)]
        covered = []
        excluded = []
        for code in ALL_CODES:
            status, extra = _plan_coverage(pid, code)
            desc = CODE_META[code][0]
            if status == "covered":
                covered.append({"code": code, "description": desc, "requires_auth": extra})
            else:
                excluded.append({"code": code, "description": desc, "exclusion_reason": extra})
        result.append({
            "plan_id": pid,
            "plan_name": pm["plan_name"],
            "plan_year": "2025",
            "plan_type": pm["plan_type"],
            "effective_date": "2025-01-01",
            "termination_date": "2025-12-31",
            "network_provider_ids": network,
            "covered_procedure_codes": covered,
            "excluded_procedure_codes": excluded,
        })
    return result


# ── Members ────────────────────────────────────────────────────────────────────

_FIRST_NAMES_M = ["James", "Robert", "Michael", "David", "Richard", "Charles", "Thomas",
                   "Daniel", "Matthew", "Anthony", "Mark", "Donald", "Steven", "Paul", "Andrew",
                   "Joshua", "Kenneth", "Kevin", "Brian", "George"]
_FIRST_NAMES_F = ["Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Susan", "Jessica",
                   "Sarah", "Karen", "Lisa", "Nancy", "Margaret", "Betty", "Sandra", "Ashley",
                   "Dorothy", "Kimberly", "Emily", "Donna", "Michelle"]
_FIRST_NAMES_X = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Avery",
                   "Quinn", "Reese", "Skyler"]
_LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
               "Davis", "Wilson", "Martinez", "Anderson", "Taylor", "Thomas", "Jackson",
               "White", "Harris", "Martin", "Thompson", "Moore", "Young"]


def _random_dob(min_age, max_age):
    age = random.randint(min_age, max_age)
    year = 2025 - age
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year:04d}-{month:02d}-{day:02d}"


def _make_auth(auth_num, code, active):
    if active:
        start = date(2025, random.randint(4, 6), random.randint(1, 28))
        end = date(2025, 12, 31)
    else:
        start = date(2025, 1, random.randint(1, 28))
        end = date(2025, random.randint(2, 5), random.randint(1, 28))
    return {
        "auth_id": f"AUTH-{auth_num:05d}",
        "procedure_code": code,
        "authorized_date": start.isoformat(),
        "expiration_date": end.isoformat(),
    }


def generate_members(plans):
    plan_lookup = {p["plan_id"]: p for p in plans}

    plan_assignments = []
    for pm in PLAN_META:
        plan_assignments.extend([pm["plan_id"]] * pm["member_count"])
    random.shuffle(plan_assignments)

    age_slots = [(18, 29)] * 30 + [(30, 44)] * 60 + [(45, 59)] * 70 + [(60, 75)] * 40
    random.shuffle(age_slots)

    genders = ["M"] * 100 + ["F"] * 90 + ["X"] * 10
    random.shuffle(genders)

    members = []
    auth_counter = 1

    for i in range(200):
        idx = i + 1
        plan_id = plan_assignments[i]
        pm = PLAN_BY_ID[plan_id]
        gender = genders[i]
        min_age, max_age = age_slots[i]

        if gender == "M":
            first = random.choice(_FIRST_NAMES_M)
        elif gender == "F":
            first = random.choice(_FIRST_NAMES_F)
        else:
            first = random.choice(_FIRST_NAMES_X)
        last = random.choice(_LAST_NAMES)

        member = {
            "member_id": f"MBR-{10000 + idx}",
            "first_name": first,
            "last_name": last,
            "date_of_birth": _random_dob(min_age, max_age),
            "gender": gender,
            "contact": {
                "email": f"member{idx:04d}@example.com",
                "phone": f"555-{idx:04d}",
                "address": f"{idx} Practice Lane, Springfield, IL 62701",
            },
            "enrollment": {
                "plan_id": plan_id,
                "effective_date": "2025-01-01",
                "termination_date": None,
            },
            "accumulators": {
                "plan_year": "2025",
                "individual_deductible": {
                    "limit": pm["deductible"],
                    "used": 0.00,
                    "met": False,
                },
                "family_deductible": None,
                "individual_oop_max": {
                    "limit": pm["oop_max"],
                    "used": 0.00,
                    "met": False,
                },
                "family_oop_max": None,
            },
            "authorizations": [],
        }
        members.append(member)

    # Gold: 12 of 40 get surgical ENT auths
    gold_members = [m for m in members if m["enrollment"]["plan_id"] == "PLN-GOLD-001"]
    for m in random.sample(gold_members, 12):
        codes = random.sample(ENT_SURGICAL, random.randint(1, 3))
        for j, code in enumerate(codes):
            active = (j % 2 == 0)
            m["authorizations"].append(_make_auth(auth_counter, code, active))
            auth_counter += 1

    # Premier: 15 of 30 get ENT auths
    premier_members = [m for m in members if m["enrollment"]["plan_id"] == "PLN-PREMIER-004"]
    for m in random.sample(premier_members, 15):
        codes = random.sample(ENT_ALL, random.randint(2, 4))
        for j, code in enumerate(codes):
            active = (j % 2 == 0)
            m["authorizations"].append(_make_auth(auth_counter, code, active))
            auth_counter += 1

    return members


# ── Claims ─────────────────────────────────────────────────────────────────────

def _random_dos():
    start = date(2025, 1, 1)
    return (start + timedelta(days=random.randint(0, 242))).isoformat()


def _compute_line_in_network(code, oop_remaining=None):
    in_net_allowed, _, copay, pre_ded, coins_pct = FEE_RATES[code]
    billed = round(in_net_allowed * 1.5, 2)
    if pre_ded and copay > 0:
        ml = copay
        cop_app = copay
        coins_app = 0.00
        ded_app = 0.00
    elif pre_ded and copay == 0:
        ml = 0.00
        cop_app = 0.00
        coins_app = 0.00
        ded_app = 0.00
    else:
        coins_app = round(in_net_allowed * coins_pct, 2)
        ml = coins_app
        cop_app = 0.00
        ded_app = 0.00
    if oop_remaining is not None:
        ml = min(ml, oop_remaining)
    pl = round(in_net_allowed - ml, 2)
    return {
        "billed": billed, "allowed": in_net_allowed,
        "ded_app": ded_app, "cop_app": cop_app, "coins_app": coins_app,
        "ml": ml, "pl": pl,
    }


def _compute_line_oon(code):
    _, oon_allowed, _, _, _ = FEE_RATES[code]
    billed = round(oon_allowed * 1.5, 2)
    coins_app = round(oon_allowed * 0.40, 2)
    ml = coins_app
    pl = round(oon_allowed - ml, 2)
    return {
        "billed": billed, "allowed": oon_allowed,
        "ded_app": 0.00, "cop_app": 0.00, "coins_app": coins_app,
        "ml": ml, "pl": pl,
    }


def _paid_line(line_num, code, pricing):
    return {
        "line_number": line_num,
        "procedure_code": code,
        "billed_amount": pricing["billed"],
        "allowed_amount": pricing["allowed"],
        "deductible_applied": pricing["ded_app"],
        "copay_applied": pricing["cop_app"],
        "coinsurance_applied": pricing["coins_app"],
        "member_liability": pricing["ml"],
        "payer_liability": pricing["pl"],
        "adjustment_reason_code": "CO-45",
        "line_status": "PAID",
    }


def _denied_line(line_num, code):
    return {
        "line_number": line_num,
        "procedure_code": code,
        "billed_amount": 0.00,
        "allowed_amount": 0.00,
        "deductible_applied": 0.00,
        "copay_applied": 0.00,
        "coinsurance_applied": 0.00,
        "member_liability": 0.00,
        "payer_liability": 0.00,
        "adjustment_reason_code": "CO-96",
        "line_status": "DENIED",
    }


def _totals(lines):
    return {
        "billed_amount": round(sum(l["billed_amount"] for l in lines), 2),
        "allowed_amount": round(sum(l["allowed_amount"] for l in lines), 2),
        "member_liability": round(sum(l["member_liability"] for l in lines), 2),
        "payer_liability": round(sum(l["payer_liability"] for l in lines), 2),
    }


def _make_claim(cid, member_id, provider_id, dos, status, lines, denial_reasons=None):
    return {
        "claim_id": cid,
        "member_id": member_id,
        "provider_id": provider_id,
        "date_of_service": dos,
        "received_at": f"{dos}T09:00:00Z",
        "adjudicated_at": f"{dos}T09:01:00Z",
        "status": status,
        "totals": _totals(lines),
        "denial_reasons": denial_reasons or [],
        "line_detail": lines,
    }


def _first_active_surgical_code(member):
    """Return the first active ENT_SURGICAL auth code for a member, or None."""
    for a in member["authorizations"]:
        if a["procedure_code"] in ENT_SURGICAL and a["expiration_date"] >= "2025-06-01":
            return a["procedure_code"]
    return None


def generate_claims(members, fee_schedules, counter):
    fs_map = {f["procedure_code"]: f for f in fee_schedules}

    def next_cid(dos):
        cid = f"CLM-{dos.replace('-', '')}-{counter[0]:03d}"
        counter[0] += 1
        return cid

    def in_net_provider(plan_id):
        pm = PLAN_BY_ID[plan_id]
        s, e = pm["net_range"]
        return f"PRV-{random.randint(s, e):05d}"

    def oon_provider(plan_id):
        return f"PRV-{random.randint(50001, 59999):05d}"

    # Partition members by plan
    by_plan = {}
    for m in members:
        pid = m["enrollment"]["plan_id"]
        by_plan.setdefault(pid, []).append(m)

    def has_active_auth(member, code):
        return any(
            a["procedure_code"] == code and a["expiration_date"] >= "2025-06-01"
            for a in member["authorizations"]
        )

    gold_with_surgical_auth = [
        m for m in by_plan.get("PLN-GOLD-001", [])
        if any(has_active_auth(m, c) for c in ENT_SURGICAL)
    ]
    gold_without_surgical_auth = [
        m for m in by_plan.get("PLN-GOLD-001", [])
        if m not in gold_with_surgical_auth
    ]
    premier_with_ent_auth = [
        m for m in by_plan.get("PLN-PREMIER-004", [])
        if any(has_active_auth(m, c) for c in ENT_ALL)
    ]
    premier_without_ent_auth = [
        m for m in by_plan.get("PLN-PREMIER-004", [])
        if m not in premier_with_ent_auth
    ]
    sv_pool = by_plan.get("PLN-SILVER-002", [])
    bz_pool = by_plan.get("PLN-BRONZE-003", [])
    silver_bronze = sv_pool + bz_pool
    basic_members = by_plan.get("PLN-BASIC-005", [])
    all_members_pool = members * 3
    random.shuffle(all_members_pool)

    claims = []

    # Category 1: 70 paid in-net GP visits (includes preventive-eligible codes via GP_CORE + GP_LAB)
    gp_paid_codes = GP_CORE + GP_LAB
    for i in range(70):
        m = all_members_pool[i]
        plan_id = m["enrollment"]["plan_id"]
        code = random.choice(gp_paid_codes)
        dos = _random_dos()
        pr = _compute_line_in_network(code)
        line = _paid_line(1, code, pr)
        claims.append(_make_claim(
            next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "PAID", [line]
        ))

    # Category 2: 30 paid in-net ENT diagnostic
    non_premier = [m for m in members if m["enrollment"]["plan_id"] != "PLN-PREMIER-004"]
    random.shuffle(non_premier)
    pool2 = (non_premier * 3)[:30]
    for i, m in enumerate(pool2):
        plan_id = m["enrollment"]["plan_id"]
        code = random.choice(ENT_DIAG)
        dos = _random_dos()
        pr = _compute_line_in_network(code)
        line = _paid_line(1, code, pr)
        claims.append(_make_claim(
            next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "PAID", [line]
        ))

    # Category 3: 10 paid in-net ENT surgical with valid auth (Gold members)
    surgical_members = gold_with_surgical_auth * 5
    random.shuffle(surgical_members)
    for i in range(10):
        m = surgical_members[i % len(surgical_members)]
        plan_id = m["enrollment"]["plan_id"]
        valid_codes = [a["procedure_code"] for a in m["authorizations"]
                       if a["procedure_code"] in ENT_SURGICAL and a["expiration_date"] >= "2025-06-01"]
        if not valid_codes:
            valid_codes = ENT_SURGICAL
        code = random.choice(valid_codes)
        dos = _random_dos()
        pr = _compute_line_in_network(code)
        line = _paid_line(1, code, pr)
        claims.append(_make_claim(
            next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "PAID", [line]
        ))

    # Category 4: 10 partially paid mixed-line claims — 5 Silver + 5 Bronze
    # Explicit per-plan slices guarantee both plans appear.
    mixed_members = (sv_pool * 3)[:5] + (bz_pool * 3)[:5]
    for m in mixed_members:
        plan_id = m["enrollment"]["plan_id"]
        gp_code = random.choice(GP_CORE)
        surgical_code = random.choice(ENT_SURGICAL)
        dos = _random_dos()
        pr = _compute_line_in_network(gp_code)
        paid_ln = _paid_line(1, gp_code, pr)
        denied_ln = _denied_line(2, surgical_code)
        lines = [paid_ln, denied_ln]
        dr = [{"code": "NOT_COVERED",
               "description": "Procedure not covered under member plan",
               "procedure_code": surgical_code}]
        claims.append(_make_claim(
            next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "PARTIALLY_PAID", lines, dr
        ))

    # Category 4b: 2 Gold PARTIALLY_PAID (GP paid + ENT surgical denied — no auth)
    gold_no_auth_pool = (gold_without_surgical_auth * 3)[:2]
    for m in gold_no_auth_pool:
        plan_id = m["enrollment"]["plan_id"]
        gp_code = random.choice(GP_CORE)
        surgical_code = random.choice(ENT_SURGICAL)
        dos = _random_dos()
        pr = _compute_line_in_network(gp_code)
        paid_ln = _paid_line(1, gp_code, pr)
        denied_ln = _denied_line(2, surgical_code)
        dr = [{"code": "AUTH_REQUIRED_NOT_ON_FILE",
               "description": "Prior authorization required and not on file",
               "procedure_code": surgical_code}]
        claims.append(_make_claim(
            next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "PARTIALLY_PAID",
            [paid_ln, denied_ln], dr
        ))

    # Category 4c: 2 Premier PARTIALLY_PAID (GP paid + ENT diag denied — no auth)
    premier_no_auth_pool = (premier_without_ent_auth * 3)[:2]
    for m in premier_no_auth_pool:
        plan_id = m["enrollment"]["plan_id"]
        gp_code = random.choice(GP_CORE)
        ent_code = random.choice(ENT_DIAG)
        dos = _random_dos()
        pr = _compute_line_in_network(gp_code)
        paid_ln = _paid_line(1, gp_code, pr)
        denied_ln = _denied_line(2, ent_code)
        dr = [{"code": "AUTH_REQUIRED_NOT_ON_FILE",
               "description": "Prior authorization required and not on file",
               "procedure_code": ent_code}]
        claims.append(_make_claim(
            next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "PARTIALLY_PAID",
            [paid_ln, denied_ln], dr
        ))

    # Category 4d: 2 Basic PARTIALLY_PAID (GP core paid + excluded code denied)
    basic_pool = (basic_members * 3)[:2]
    excluded_codes_sorted = sorted(BASIC_EXCLUDED)
    for m in basic_pool:
        plan_id = m["enrollment"]["plan_id"]
        gp_code = random.choice(GP_CORE)
        excl_code = random.choice(excluded_codes_sorted)
        dos = _random_dos()
        pr = _compute_line_in_network(gp_code)
        paid_ln = _paid_line(1, gp_code, pr)
        denied_ln = _denied_line(2, excl_code)
        dr = [{"code": "NOT_COVERED",
               "description": "Not covered under Basic EPO benefit",
               "procedure_code": excl_code}]
        claims.append(_make_claim(
            next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "PARTIALLY_PAID",
            [paid_ln, denied_ln], dr
        ))

    # Category 5: 10 denied not covered — Silver (3), Bronze (3), Basic (4)
    # Explicit per-plan slices guarantee Bronze appears regardless of combined list order.
    denied_nc_members = (sv_pool * 3)[:3] + (bz_pool * 3)[:3] + (basic_members * 3)[:4]
    for m in denied_nc_members:
        plan_id = m["enrollment"]["plan_id"]
        if plan_id in ("PLN-SILVER-002", "PLN-BRONZE-003"):
            code = random.choice(ENT_SURGICAL)
            reason = "Requires specialist rider"
        else:
            code = random.choice(sorted(BASIC_EXCLUDED))
            reason = "Not covered under Basic EPO benefit"
        dos = _random_dos()
        denied_ln = _denied_line(1, code)
        dr = [{"code": "NOT_COVERED",
               "description": "Procedure not covered under member plan",
               "procedure_code": code}]
        claims.append(_make_claim(
            next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "DENIED", [denied_ln], dr
        ))

    # Category 6: 10 denied auth required not on file — 8 Gold + 2 Premier
    # Reserve 2 slots for Premier so that plan always has DENIED claims.
    no_auth_members = (gold_without_surgical_auth * 5)[:8] + (premier_without_ent_auth * 3)[:2]
    for m in no_auth_members:
        plan_id = m["enrollment"]["plan_id"]
        if plan_id == "PLN-GOLD-001":
            code = random.choice(ENT_SURGICAL)
        else:
            code = random.choice(ENT_ALL)
        dos = _random_dos()
        denied_ln = _denied_line(1, code)
        dr = [{"code": "AUTH_REQUIRED_NOT_ON_FILE",
               "description": "Prior authorization required and not on file",
               "procedure_code": code}]
        claims.append(_make_claim(
            next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "DENIED", [denied_ln], dr
        ))

    # Category 7: 10 paid OON
    oon_pool = all_members_pool[:10]
    for m in oon_pool:
        plan_id = m["enrollment"]["plan_id"]
        code = random.choice(GP_CORE)
        dos = _random_dos()
        pr = _compute_line_oon(code)
        line = _paid_line(1, code, pr)
        claims.append(_make_claim(
            next_cid(dos), m["member_id"], oon_provider(plan_id), dos, "PAID", [line]
        ))

    # Category 8: 6 preventive in-network claims (99395/99396, copay=0, ml=0)
    non_basic = [m for m in members if m["enrollment"]["plan_id"] != "PLN-BASIC-005"]
    random.shuffle(non_basic)
    prev_pool = (non_basic * 3)[:6]
    for m in prev_pool:
        plan_id = m["enrollment"]["plan_id"]
        code = random.choice(GP_PREV)
        dos = _random_dos()
        pr = _compute_line_in_network(code)
        line = _paid_line(1, code, pr)
        claims.append(_make_claim(
            next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "PAID", [line]
        ))

    # Category 9: OOP bridge — 3 Gold members with surgical auth each receive 10 surgical claims.
    # Gold OOP=$2000; 42820 ml=$280/claim; 10 claims=$2800 > $2000 so OOP will be met after
    # reconcile_accumulators. add_oop_met_claims then generates the capped follow-on claims.
    bridge_candidates = []
    for m in gold_with_surgical_auth:
        code = _first_active_surgical_code(m)
        if code is not None and len(bridge_candidates) < 3:
            bridge_candidates.append((m, code))

    for (m, code) in bridge_candidates:
        plan_id = m["enrollment"]["plan_id"]
        for _ in range(10):
            dos = _random_dos()
            pr = _compute_line_in_network(code)
            line = _paid_line(1, code, pr)
            claims.append(_make_claim(
                next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "PAID", [line]
            ))

    # Category 10: 6 all-paid multi-line claims (GP + ENT diag, both lines PAID)
    # Silver/Bronze: both code types covered without auth
    sb_pool = list(silver_bronze)
    random.shuffle(sb_pool)
    multiline_pool = (sb_pool * 3)[:6]
    for m in multiline_pool:
        plan_id = m["enrollment"]["plan_id"]
        gp_code = random.choice(GP_CORE)
        ent_code = random.choice(ENT_DIAG)
        dos = _random_dos()
        pr1 = _compute_line_in_network(gp_code)
        pr2 = _compute_line_in_network(ent_code)
        line1 = _paid_line(1, gp_code, pr1)
        line2 = _paid_line(2, ent_code, pr2)
        claims.append(_make_claim(
            next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "PAID", [line1, line2]
        ))

    return claims


def add_oop_met_claims(members, fee_schedules, counter):
    """Generate 1 OOP-capped PAID claim for each member whose OOP max is met (up to 3).

    Called after reconcile_accumulators so met flags are accurate. The generated
    claims have member_liability=0 because oop_remaining=0 is passed to
    _compute_line_in_network.
    """
    def next_cid(dos):
        cid = f"CLM-{dos.replace('-', '')}-{counter[0]:03d}"
        counter[0] += 1
        return cid

    def in_net_provider(plan_id):
        pm = PLAN_BY_ID[plan_id]
        s, e = pm["net_range"]
        return f"PRV-{random.randint(s, e):05d}"

    oop_met_members = [
        m for m in members
        if m["accumulators"]["individual_oop_max"]["met"]
    ][:3]

    oop_claims = []
    gp_code = "99213"
    for m in oop_met_members:
        plan_id = m["enrollment"]["plan_id"]
        dos = _random_dos()
        pr = _compute_line_in_network(gp_code, oop_remaining=0)
        line = _paid_line(1, gp_code, pr)
        oop_claims.append(_make_claim(
            next_cid(dos), m["member_id"], in_net_provider(plan_id), dos, "PAID", [line]
        ))
    return oop_claims


# ── Accumulator reconciliation ─────────────────────────────────────────────────

def reconcile_accumulators(members, claims):
    oop_by_member = {}
    coins_by_member = {}

    for claim in claims:
        if claim["status"] in ("PAID", "PARTIALLY_PAID"):
            mid = claim["member_id"]
            oop_by_member[mid] = oop_by_member.get(mid, 0.0) + claim["totals"]["member_liability"]
            for line in claim["line_detail"]:
                if line["line_status"] == "PAID":
                    coins_by_member[mid] = coins_by_member.get(mid, 0.0) + line["coinsurance_applied"]

    for member in members:
        mid = member["member_id"]
        plan_id = member["enrollment"]["plan_id"]
        pm = PLAN_BY_ID[plan_id]

        total_oop = round(oop_by_member.get(mid, 0.0), 2)
        total_coins = round(coins_by_member.get(mid, 0.0), 2)

        ded_limit = pm["deductible"]
        oop_limit = pm["oop_max"]

        ded_used = round(min(total_coins, ded_limit), 2)
        oop_used = round(min(total_oop, oop_limit), 2)

        member["accumulators"]["individual_deductible"]["used"] = ded_used
        # Zero-deductible plans (Premier) are considered met at all times (0 >= 0).
        member["accumulators"]["individual_deductible"]["met"] = (
            ded_limit == 0 or total_coins >= ded_limit
        )
        member["accumulators"]["individual_oop_max"]["used"] = oop_used
        member["accumulators"]["individual_oop_max"]["met"] = (total_oop >= oop_limit)


# ── File I/O ───────────────────────────────────────────────────────────────────

def write_files(data_dir, plans, fee_schedules, members, claims):
    data_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "plans.json": plans,
        "fee_schedules.json": fee_schedules,
        "members.json": members,
        "claims.json": claims,
    }
    for name, data in files.items():
        path = data_dir / name
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    fee_schedules = generate_fee_schedules()
    plans = generate_plans()
    members = generate_members(plans)
    counter = [1]
    claims = generate_claims(members, fee_schedules, counter)
    reconcile_accumulators(members, claims)
    oop_claims = add_oop_met_claims(members, fee_schedules, counter)
    claims.extend(oop_claims)
    # Re-run so OOP-met claims (ml=0) are included in the final accumulator state.
    reconcile_accumulators(members, claims)
    write_files(DATA_DIR, plans, fee_schedules, members, claims)

    print("Seed data generation complete.")
    print(f"  plans.json:         {len(plans)} records")
    print(f"  fee_schedules.json: {len(fee_schedules)} records")
    print(f"  members.json:       {len(members)} records")
    print(f"  claims.json:        {len(claims)} records")
    print(f"Written to: {DATA_DIR}")


if __name__ == "__main__":
    main()

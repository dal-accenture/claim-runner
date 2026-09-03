"""Integration tests for scripts/generate_seed_data.py."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "generate_seed_data.py"


@pytest.fixture(scope="module")
def seed_data(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("data")
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO_ROOT),
        env={**os.environ, "DATA_DIR": str(tmp)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Script failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    plans = json.loads((tmp / "plans.json").read_text())
    fee_schedules = json.loads((tmp / "fee_schedules.json").read_text())
    members = json.loads((tmp / "members.json").read_text())
    claims = json.loads((tmp / "claims.json").read_text())
    return {"plans": plans, "fee_schedules": fee_schedules, "members": members, "claims": claims}


# ── T007: Member enrollment validation ────────────────────────────────────────

def test_member_count(seed_data):
    assert len(seed_data["members"]) == 200


def test_member_ids_unique(seed_data):
    ids = [m["member_id"] for m in seed_data["members"]]
    assert len(ids) == len(set(ids))


def test_member_plan_refs_valid(seed_data):
    plan_ids = {p["plan_id"] for p in seed_data["plans"]}
    for m in seed_data["members"]:
        assert m["enrollment"]["plan_id"] in plan_ids


def test_member_met_flags_consistent(seed_data):
    for m in seed_data["members"]:
        acc = m["accumulators"]
        ded = acc["individual_deductible"]
        oop = acc["individual_oop_max"]
        # Zero-deductible plans (Premier, limit=0) are met at all times: 0 >= 0.
        expected_ded_met = (ded["limit"] == 0 or ded["used"] >= ded["limit"])
        assert ded["met"] == expected_ded_met, \
            f"{m['member_id']} deductible met flag wrong: used={ded['used']} limit={ded['limit']}"
        assert oop["met"] == (oop["used"] >= oop["limit"]), \
            f"{m['member_id']} oop_max met flag wrong: used={oop['used']} limit={oop['limit']}"


def test_member_required_fields(seed_data):
    required = {"member_id", "first_name", "last_name", "date_of_birth", "gender",
                 "contact", "enrollment", "accumulators", "authorizations"}
    for m in seed_data["members"]:
        missing = required - m.keys()
        assert not missing, f"{m['member_id']} missing fields: {missing}"


# ── T011: Claims financial integrity ──────────────────────────────────────────

def test_claim_count(seed_data):
    assert len(seed_data["claims"]) >= 150


def test_claim_financial_balance(seed_data):
    errors = []
    for c in seed_data["claims"]:
        t = c["totals"]
        expected = round(t["member_liability"] + t["payer_liability"], 2)
        if abs(expected - round(t["allowed_amount"], 2)) > 0.01:
            errors.append(c["claim_id"])
    assert not errors, f"Claims with unbalanced totals: {errors}"


def test_claim_ids_unique(seed_data):
    ids = [c["claim_id"] for c in seed_data["claims"]]
    assert len(ids) == len(set(ids))


def test_claim_member_refs_valid(seed_data):
    member_ids = {m["member_id"] for m in seed_data["members"]}
    for c in seed_data["claims"]:
        assert c["member_id"] in member_ids, f"{c['claim_id']} references unknown member"


def test_claim_procedure_code_refs_valid(seed_data):
    codes = {f["procedure_code"] for f in seed_data["fee_schedules"]}
    for c in seed_data["claims"]:
        for line in c["line_detail"]:
            assert line["procedure_code"] in codes, \
                f"{c['claim_id']} line uses unknown code {line['procedure_code']}"


def test_line_financial_balance(seed_data):
    errors = []
    for c in seed_data["claims"]:
        for line in c["line_detail"]:
            expected_pl = round(line["allowed_amount"] - line["member_liability"], 2)
            if abs(expected_pl - line["payer_liability"]) > 0.01:
                errors.append((c["claim_id"], line["line_number"]))
    assert not errors, f"Lines with unbalanced amounts: {errors}"


# ── T012: Accumulator reconciliation ──────────────────────────────────────────

def test_oop_max_reconciles_with_claims(seed_data):
    paid_oop = {}
    for c in seed_data["claims"]:
        if c["status"] in ("PAID", "PARTIALLY_PAID"):
            mid = c["member_id"]
            paid_oop[mid] = round(paid_oop.get(mid, 0.0) + c["totals"]["member_liability"], 2)

    members_by_id = {m["member_id"]: m for m in seed_data["members"]}
    errors = []
    for mid, total in paid_oop.items():
        m = members_by_id[mid]
        oop_limit = m["accumulators"]["individual_oop_max"]["limit"]
        expected_used = round(min(total, oop_limit), 2)
        recorded = m["accumulators"]["individual_oop_max"]["used"]
        if abs(recorded - expected_used) > 0.01:
            errors.append((mid, total, expected_used, recorded))
    assert not errors, f"OOP max mismatch: {errors[:5]}"


def test_oop_max_met_flag(seed_data):
    for m in seed_data["members"]:
        oop = m["accumulators"]["individual_oop_max"]
        assert oop["met"] == (oop["used"] >= oop["limit"]), \
            f"{m['member_id']} oop_max met flag inconsistent"


# ── T013: Reproducibility ─────────────────────────────────────────────────────

def test_reproducibility(tmp_path):
    dirs = [tmp_path / "run1", tmp_path / "run2"]
    for d in dirs:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=str(REPO_ROOT),
            env={**os.environ, "DATA_DIR": str(d)},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    for fname in ["plans.json", "fee_schedules.json", "members.json", "claims.json"]:
        content1 = (dirs[0] / fname).read_text()
        content2 = (dirs[1] / fname).read_text()
        assert content1 == content2, f"{fname} differs between runs"


# ── T014: Scenario coverage ───────────────────────────────────────────────────

def test_scenario_paid_gp_copay(seed_data):
    """≥20 PAID in-network GP claims with copay > 0."""
    gp_copay_codes = {"99202","99203","99204","99205","99211","99212","99213","99214","99215",
                      "92504","92551","92552","92557","69210"}
    count = sum(
        1 for c in seed_data["claims"]
        if c["status"] == "PAID" and
           len(c["line_detail"]) == 1 and
           c["line_detail"][0]["procedure_code"] in gp_copay_codes and
           c["line_detail"][0]["copay_applied"] > 0
    )
    assert count >= 20, f"Only {count} PAID in-net copay claims (need ≥20)"


def test_scenario_ent_surgical_paid(seed_data):
    """≥5 PAID in-network ENT surgical claims."""
    ent_surgical = {"42820","42821","30140","30520","31240"}
    count = sum(
        1 for c in seed_data["claims"]
        if c["status"] == "PAID" and
           any(l["procedure_code"] in ent_surgical and l["line_status"] == "PAID"
               for l in c["line_detail"])
    )
    assert count >= 5, f"Only {count} paid ENT surgical claims (need ≥5)"


def test_scenario_auth_required_denials(seed_data):
    """≥5 claims denied with AUTH_REQUIRED_NOT_ON_FILE."""
    count = sum(
        1 for c in seed_data["claims"]
        if any(dr["code"] == "AUTH_REQUIRED_NOT_ON_FILE" for dr in c["denial_reasons"])
    )
    assert count >= 5, f"Only {count} auth-required denials (need ≥5)"


def test_scenario_not_covered_denials(seed_data):
    """≥5 claims denied with NOT_COVERED."""
    count = sum(
        1 for c in seed_data["claims"]
        if any(dr["code"] == "NOT_COVERED" for dr in c["denial_reasons"])
    )
    assert count >= 5, f"Only {count} not-covered denials (need ≥5)"


def test_scenario_oon_claims(seed_data):
    """≥5 paid OON claims (identified by non-zero coinsurance on all paid lines, no copay)."""
    plan_networks = {}
    for p in seed_data["plans"]:
        for pid in p["network_provider_ids"]:
            plan_networks.setdefault(p["plan_id"], set()).add(pid)

    member_plan = {m["member_id"]: m["enrollment"]["plan_id"] for m in seed_data["members"]}

    count = 0
    for c in seed_data["claims"]:
        if c["status"] != "PAID":
            continue
        plan_id = member_plan.get(c["member_id"])
        if plan_id and c["provider_id"] not in plan_networks.get(plan_id, set()):
            count += 1
    assert count >= 5, f"Only {count} OON paid claims (need ≥5)"


def test_scenario_members_with_no_claims(seed_data):
    """≥60 members with zero claims."""
    members_with_claims = {c["member_id"] for c in seed_data["claims"]}
    no_claims = [m for m in seed_data["members"] if m["member_id"] not in members_with_claims]
    assert len(no_claims) >= 60, f"Only {len(no_claims)} members without claims (need ≥60)"


def test_seed_data_outcomes_per_plan(seed_data):
    """Every plan must have at least one PAID, DENIED, and PARTIALLY_PAID claim."""
    member_plan = {m["member_id"]: m["enrollment"]["plan_id"] for m in seed_data["members"]}
    plan_outcomes: dict[str, set] = {}
    for c in seed_data["claims"]:
        plan_id = member_plan.get(c["member_id"])
        if plan_id:
            plan_outcomes.setdefault(plan_id, set()).add(c["status"])
    for plan in seed_data["plans"]:
        pid = plan["plan_id"]
        outcomes = plan_outcomes.get(pid, set())
        assert "PAID" in outcomes, f"{pid} has no PAID claims"
        assert "DENIED" in outcomes, f"{pid} has no DENIED claims"
        assert "PARTIALLY_PAID" in outcomes, f"{pid} has no PARTIALLY_PAID claims"


def test_preventive_claims(seed_data):
    """≥5 PAID preventive claims (99395/99396) with member_liability=0."""
    preventive_codes = {"99395", "99396"}
    count = sum(
        1 for c in seed_data["claims"]
        if c["status"] == "PAID" and
           len(c["line_detail"]) == 1 and
           c["line_detail"][0]["procedure_code"] in preventive_codes and
           c["line_detail"][0]["member_liability"] == 0.0
    )
    assert count >= 5, f"Only {count} preventive claims with $0 member liability (need ≥5)"


def test_oop_met_claims(seed_data):
    """≥3 PAID claims where the member's OOP max is met and claim member_liability=0."""
    members_by_id = {m["member_id"]: m for m in seed_data["members"]}
    count = sum(
        1 for c in seed_data["claims"]
        if c["status"] == "PAID" and
           c["totals"]["member_liability"] == 0.0 and
           members_by_id[c["member_id"]]["accumulators"]["individual_oop_max"]["met"]
    )
    assert count >= 3, f"Only {count} OOP-capped PAID claims for OOP-met members (need ≥3)"


def test_all_paid_multiline_claims(seed_data):
    """≥5 claims with ≥2 lines where every line has line_status PAID."""
    count = sum(
        1 for c in seed_data["claims"]
        if len(c["line_detail"]) >= 2 and
           all(line["line_status"] == "PAID" for line in c["line_detail"])
    )
    assert count >= 5, f"Only {count} all-paid multi-line claims (need ≥5)"


# ── Plan and fee schedule basic checks ────────────────────────────────────────

def test_plan_count(seed_data):
    assert len(seed_data["plans"]) == 5


def test_fee_schedule_count(seed_data):
    assert len(seed_data["fee_schedules"]) == 25


def test_fee_schedule_all_codes_present(seed_data):
    expected = {
        "99202","99203","99204","99205","99211","99212","99213","99214","99215",
        "99395","99396","93000","85025","80053",
        "92504","92551","92552","92557","69210","31575",
        "42820","42821","30140","30520","31240",
    }
    present = {f["procedure_code"] for f in seed_data["fee_schedules"]}
    assert present == expected


def test_plans_have_covered_codes(seed_data):
    for p in seed_data["plans"]:
        assert len(p["covered_procedure_codes"]) > 0


def test_plans_have_network_providers(seed_data):
    for p in seed_data["plans"]:
        assert len(p["network_provider_ids"]) > 0

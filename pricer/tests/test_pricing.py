from decimal import Decimal
import pytest
from pricer.models import ClaimLine
from pricer.pricing import compute_allowed, apply_cost_sharing, compute_totals, compute_snapshot

# ---------------------------------------------------------------------------
# Fee schedule fixtures
# ---------------------------------------------------------------------------

FS_99213_IN = {
    "allowed_amount": 115.00,
    "copay": 30.00,
    "copay_applies_before_deductible": True,
    "coinsurance_pct": 0.00,
}

FS_99213_OON = {
    "allowed_amount": 84.00,
    "copay": 0.00,
    "copay_applies_before_deductible": False,
    "coinsurance_pct": 0.40,
}

FS_42820_IN = {
    "allowed_amount": 2800.00,
    "copay": 0.00,
    "copay_applies_before_deductible": False,
    "coinsurance_pct": 0.10,
}

# Accumulator fixtures
ACC_PARTIAL_DED = {
    "individual_deductible": {"limit": 500.00, "used": 125.00, "met": False},
    "individual_oop_max": {"limit": 2000.00, "used": 155.00, "met": False},
}

ACC_DED_MET = {
    "individual_deductible": {"limit": 500.00, "used": 500.00, "met": True},
    "individual_oop_max": {"limit": 2000.00, "used": 500.00, "met": False},
}

ACC_OOP_MET = {
    "individual_deductible": {"limit": 250.00, "used": 250.00, "met": True},
    "individual_oop_max": {"limit": 2000.00, "used": 2000.00, "met": True},
}

ACC_OOP_NEAR = {
    "individual_deductible": {"limit": 500.00, "used": 500.00, "met": True},
    "individual_oop_max": {"limit": 2000.00, "used": 1950.00, "met": False},
}


# ===========================================================================
# T009: compute_allowed unit tests
# ===========================================================================

def _line(procedure_code="99213", units=1, billed=250.00):
    return ClaimLine(line_number=1, procedure_code=procedure_code, units=units, billed_amount=Decimal(str(billed)))


def test_allowed_in_network_uses_in_network_rate():
    allowed, adj = compute_allowed(_line(billed=250.00), FS_99213_IN)
    assert allowed == Decimal("115.00")
    assert adj == Decimal("135.00")


def test_allowed_oon_uses_out_of_network_rate():
    allowed, adj = compute_allowed(_line(billed=250.00), FS_99213_OON)
    assert allowed == Decimal("84.00")
    assert adj == Decimal("166.00")


def test_allowed_billed_below_fee_schedule():
    line = _line(billed=100.00)
    allowed, adj = compute_allowed(line, FS_99213_IN)
    assert allowed == Decimal("100.00")
    assert adj == Decimal("0.00")


def test_allowed_units_scaling():
    line = _line(billed=250.00, units=2)
    allowed, adj = compute_allowed(line, FS_99213_IN)
    # line_billed=500, fee_rate=230 → allowed=230, adj=270
    assert allowed == Decimal("230.00")
    assert adj == Decimal("270.00")


def test_allowed_co45_when_billed_exceeds():
    allowed, adj = compute_allowed(_line(billed=250.00), FS_99213_IN)
    assert adj > Decimal("0")


def test_allowed_no_adjustment_when_billed_at_or_below_rate():
    line = _line(billed=100.00)
    _, adj = compute_allowed(line, FS_99213_IN)
    assert adj == Decimal("0.00")


# ===========================================================================
# T012: apply_cost_sharing unit tests
# ===========================================================================

ZERO = Decimal("0")


def test_cost_sharing_copay_only_zero_coinsurance():
    """GP visit: copay=30 before deductible, coinsurance=0% — deductible not applied."""
    allowed = Decimal("115.00")
    ded_a, cop_a, coi_a, mem_l, pay_l, new_ded, new_oop = apply_cost_sharing(
        allowed, FS_99213_IN, ACC_PARTIAL_DED, ZERO, ZERO
    )
    assert cop_a == Decimal("30.00")
    assert ded_a == ZERO
    assert coi_a == ZERO
    assert mem_l == Decimal("30.00")
    assert pay_l == Decimal("85.00")
    assert new_ded == ZERO
    assert new_oop == Decimal("30.00")


def test_cost_sharing_deductible_partially_met():
    """Surgical: deductible partially met (125/500), 10% coinsurance."""
    allowed = Decimal("2800.00")
    ded_a, cop_a, coi_a, mem_l, pay_l, new_ded, new_oop = apply_cost_sharing(
        allowed, FS_42820_IN, ACC_PARTIAL_DED, ZERO, ZERO
    )
    assert ded_a == Decimal("375.00")   # 500-125=375 remaining
    assert cop_a == ZERO
    assert coi_a == Decimal("242.50")   # (2800-375)*0.10
    assert mem_l == Decimal("617.50")
    assert pay_l == Decimal("2182.50")
    assert new_ded == Decimal("375.00")
    assert new_oop == Decimal("617.50")


def test_cost_sharing_deductible_already_met():
    """Deductible met — coinsurance applies to full allowed amount."""
    allowed = Decimal("2800.00")
    ded_a, cop_a, coi_a, mem_l, pay_l, new_ded, new_oop = apply_cost_sharing(
        allowed, FS_42820_IN, ACC_DED_MET, ZERO, ZERO
    )
    assert ded_a == ZERO
    assert cop_a == ZERO
    assert coi_a == Decimal("280.00")   # 2800 × 0.10
    assert mem_l == Decimal("280.00")
    assert pay_l == Decimal("2520.00")


def test_cost_sharing_oop_already_met():
    """OOP max already met (met=true) — member_liability=0."""
    allowed = Decimal("115.00")
    ded_a, cop_a, coi_a, mem_l, pay_l, new_ded, new_oop = apply_cost_sharing(
        allowed, FS_99213_IN, ACC_OOP_MET, ZERO, ZERO
    )
    assert mem_l == ZERO
    assert pay_l == allowed


def test_cost_sharing_oop_hit_mid_claim():
    """OOP almost met (1950/2000); this line tries to add 617.50 but only 50 of OOP headroom."""
    allowed = Decimal("2800.00")
    ded_a, cop_a, coi_a, mem_l, pay_l, new_ded, new_oop = apply_cost_sharing(
        allowed, FS_42820_IN, ACC_OOP_NEAR, ZERO, ZERO
    )
    assert mem_l == Decimal("50.00")
    assert pay_l == Decimal("2750.00")
    assert new_oop == Decimal("50.00")


def test_cost_sharing_oon_coinsurance_40_pct():
    """OON 40% coinsurance, no copay, no deductible left."""
    allowed = Decimal("84.00")
    ded_a, cop_a, coi_a, mem_l, pay_l, new_ded, new_oop = apply_cost_sharing(
        allowed, FS_99213_OON, ACC_DED_MET, ZERO, ZERO
    )
    # coinsurance_pct=0.40, no deductible remaining
    assert coi_a == Decimal("33.60")    # 84 × 0.40
    assert mem_l == Decimal("33.60")
    assert pay_l == Decimal("50.40")


def test_cost_sharing_multi_line_running_counter():
    """Two surgical lines: running deductible counter from line 1 feeds line 2."""
    allowed = Decimal("2800.00")
    # Line 1 — partial deductible
    _, _, _, _, _, new_ded, new_oop = apply_cost_sharing(
        allowed, FS_42820_IN, ACC_PARTIAL_DED, ZERO, ZERO
    )
    # ded used after line 1 = 375; oop used after line 1 = 617.50
    assert new_ded == Decimal("375.00")

    # Line 2 — deductible now fully consumed (used=125+375=500=limit)
    ded_a2, _, coi_a2, _, _, _, _ = apply_cost_sharing(
        allowed, FS_42820_IN, ACC_PARTIAL_DED, new_ded, new_oop
    )
    assert ded_a2 == ZERO
    assert coi_a2 == Decimal("280.00")  # full 2800 × 0.10


def test_invariant_member_plus_payer_equals_allowed():
    for fs, acc in [(FS_99213_IN, ACC_PARTIAL_DED), (FS_42820_IN, ACC_PARTIAL_DED),
                    (FS_42820_IN, ACC_DED_MET), (FS_99213_IN, ACC_OOP_MET)]:
        allowed = Decimal("115.00") if "copay" in fs and fs["copay"] == 30.0 else Decimal("2800.00")
        _, _, _, mem_l, pay_l, _, _ = apply_cost_sharing(allowed, fs, acc, ZERO, ZERO)
        assert mem_l + pay_l == allowed


# ===========================================================================
# T015: compute_totals and compute_snapshot unit tests
# ===========================================================================

SAMPLE_LINES = [
    {
        "line_number": 1, "procedure_code": "99213",
        "billed_amount": Decimal("250.00"), "allowed_amount": Decimal("115.00"),
        "contractual_adjustment": Decimal("135.00"),
        "deductible_applied": ZERO, "copay_applied": Decimal("30.00"),
        "coinsurance_applied": ZERO, "member_liability": Decimal("30.00"),
        "payer_liability": Decimal("85.00"), "adjustment_reason_code": "CO-45",
        "line_status": "PAID",
    },
    {
        "line_number": 2, "procedure_code": "42820",
        "billed_amount": Decimal("4200.00"), "allowed_amount": Decimal("2800.00"),
        "contractual_adjustment": Decimal("1400.00"),
        "deductible_applied": Decimal("375.00"), "copay_applied": ZERO,
        "coinsurance_applied": Decimal("242.50"), "member_liability": Decimal("617.50"),
        "payer_liability": Decimal("2182.50"), "adjustment_reason_code": "CO-45",
        "line_status": "PAID",
    },
]


def test_totals_sum_correctly():
    t = compute_totals(SAMPLE_LINES)
    assert t["billed_amount"] == Decimal("4450.00")
    assert t["allowed_amount"] == Decimal("2915.00")
    assert t["member_liability"] == Decimal("647.50")
    assert t["payer_liability"] == Decimal("2267.50")


def test_totals_invariant():
    t = compute_totals(SAMPLE_LINES)
    assert t["member_liability"] + t["payer_liability"] == t["allowed_amount"]


def test_snapshot_before_matches_seeded():
    snap = compute_snapshot(ACC_PARTIAL_DED, Decimal("375.00"), Decimal("617.50"))
    assert snap["individual_deductible_used_before"] == Decimal("125.00")
    assert snap["individual_oop_used_before"] == Decimal("155.00")


def test_snapshot_after_equals_before_plus_claim():
    snap = compute_snapshot(ACC_PARTIAL_DED, Decimal("375.00"), Decimal("617.50"))
    assert snap["individual_deductible_used_after"] == Decimal("500.00")   # 125+375
    assert snap["individual_oop_used_after"] == Decimal("772.50")          # 155+617.50


def test_snapshot_no_change_when_copay_only():
    """GP copay-only visit: deductible not touched, OOP gains 30."""
    snap = compute_snapshot(ACC_PARTIAL_DED, ZERO, Decimal("30.00"))
    assert snap["individual_deductible_used_after"] == Decimal("125.00")
    assert snap["individual_oop_used_after"] == Decimal("185.00")

from decimal import Decimal
from .models import ClaimLine


def compute_allowed(line: ClaimLine, fs_block: dict) -> tuple[Decimal, Decimal]:
    line_billed = Decimal(str(line.billed_amount)) * line.units
    fee_rate = Decimal(str(fs_block["allowed_amount"])) * line.units
    allowed = min(line_billed, fee_rate)
    contractual_adjustment = line_billed - allowed
    return allowed, contractual_adjustment


def apply_cost_sharing(
    allowed_amount: Decimal,
    fs_block: dict,
    accumulators: dict,
    deductible_used_so_far: Decimal,
    oop_used_so_far: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    ded_acc = accumulators.get("individual_deductible", {})
    oop_acc = accumulators.get("individual_oop_max", {})

    ded_limit = Decimal(str(ded_acc.get("limit", "0")))
    ded_used_seeded = Decimal(str(ded_acc.get("used", "0")))
    oop_limit = Decimal(str(oop_acc.get("limit", "0")))
    oop_used_seeded = Decimal(str(oop_acc.get("used", "0")))
    oop_met = oop_acc.get("met", False)

    copay = Decimal(str(fs_block.get("copay", "0")))
    copay_before_ded = fs_block.get("copay_applies_before_deductible", False)
    coinsurance_pct = Decimal(str(fs_block.get("coinsurance_pct", "0")))

    # Step 1: OOP pre-check — if already met, member pays nothing
    oop_used_total = oop_used_seeded + oop_used_so_far
    if oop_met or oop_used_total >= oop_limit:
        return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), allowed_amount, deductible_used_so_far, oop_used_so_far

    remaining = allowed_amount
    deductible_applied = Decimal("0")
    copay_applied = Decimal("0")
    coinsurance_applied = Decimal("0")

    # Step 2: Copay before deductible
    if copay_before_ded and copay > Decimal("0"):
        copay_applied = min(copay, remaining)
        remaining -= copay_applied

    # Step 3: Deductible — only applies when there is coinsurance; copay-only plans skip it
    ded_used_total = ded_used_seeded + deductible_used_so_far
    ded_remaining = max(Decimal("0"), ded_limit - ded_used_total)
    if coinsurance_pct > Decimal("0") and ded_remaining > Decimal("0") and remaining > Decimal("0"):
        deductible_applied = min(ded_remaining, remaining)
        remaining -= deductible_applied

    # Step 4: Copay after deductible (if copay_before_ded is False)
    if not copay_before_ded and copay > Decimal("0") and remaining > Decimal("0"):
        copay_applied = min(copay, remaining)
        remaining -= copay_applied

    # Step 5: Coinsurance
    if coinsurance_pct > Decimal("0") and remaining > Decimal("0"):
        coinsurance_applied = (remaining * coinsurance_pct).quantize(Decimal("0.01"))
        remaining -= coinsurance_applied

    # Step 6: OOP cap
    member_liability_raw = deductible_applied + copay_applied + coinsurance_applied
    oop_space_left = max(Decimal("0"), oop_limit - oop_used_total)
    member_liability = min(member_liability_raw, oop_space_left)

    # Adjust components proportionally if OOP cap reduced member_liability
    if member_liability < member_liability_raw:
        excess = member_liability_raw - member_liability
        # Reduce coinsurance first, then copay, then deductible
        reduction = min(coinsurance_applied, excess)
        coinsurance_applied -= reduction
        excess -= reduction
        if excess > Decimal("0"):
            reduction = min(copay_applied, excess)
            copay_applied -= reduction
            excess -= reduction
        if excess > Decimal("0"):
            deductible_applied -= excess

    # Step 7: Payer liability
    payer_liability = allowed_amount - member_liability

    new_deductible_used = deductible_used_so_far + deductible_applied
    new_oop_used = oop_used_so_far + member_liability

    return (
        deductible_applied,
        copay_applied,
        coinsurance_applied,
        member_liability,
        payer_liability,
        new_deductible_used,
        new_oop_used,
    )


def compute_totals(line_details: list[dict]) -> dict:
    zero = Decimal("0")
    return {
        "billed_amount": sum((ld["billed_amount"] for ld in line_details), zero),
        "allowed_amount": sum((ld["allowed_amount"] for ld in line_details), zero),
        "member_liability": sum((ld["member_liability"] for ld in line_details), zero),
        "payer_liability": sum((ld["payer_liability"] for ld in line_details), zero),
    }


def compute_snapshot(
    accumulators: dict,
    deductible_used_this_claim: Decimal,
    oop_used_this_claim: Decimal,
) -> dict:
    ded_acc = accumulators.get("individual_deductible", {})
    oop_acc = accumulators.get("individual_oop_max", {})
    ded_before = Decimal(str(ded_acc.get("used", "0")))
    oop_before = Decimal(str(oop_acc.get("used", "0")))
    return {
        "individual_deductible_used_before": ded_before,
        "individual_deductible_used_after": ded_before + deductible_used_this_claim,
        "individual_oop_used_before": oop_before,
        "individual_oop_used_after": oop_before + oop_used_this_claim,
    }

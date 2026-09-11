"""
Financial Validation Service

Provides deterministic checks on the structured data produced by extraction_service
for:
- Invoice (validate_invoice)
- Balance Sheet (validate_balance_sheet)
- Profit & Loss Statement (validate_pl)
- Cash Flow Statement (validate_cash_flow)

All arithmetic is pure Python – no external APIs or LLM calls.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional


def _as_number(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _tolerance(reported: float) -> float:
    return max(0.01, 0.01 * abs(reported))


def _make_check(
    name: str,
    formula: str,
    operands: Dict[str, Any],
    calculated: Optional[float],
    reported: Optional[float],
    status: str,
) -> Dict[str, Any]:
    variance = (
        None
        if calculated is None or reported is None
        else abs(calculated - reported)
    )
    return {
        "name": name,
        "formula": formula,
        "operands": operands,
        "calculated_value": calculated,
        "reported_value": reported,
        "variance": variance,
        "status": status,
    }


# ── Invoice Validation ────────────────────────────────────────────────────────

def validate_invoice(extracted_data: dict) -> dict:
    checks: List[Dict[str, Any]] = []
    issues: List[str] = []

    # 1. line_item_check
    line_items = extracted_data.get("line_items") or []
    if not line_items:
        checks.append(
            _make_check(
                name="line_item_check",
                formula="quantity * unit_price ≈ amount",
                operands={"quantity": None, "unit_price": None, "amount": None},
                calculated=None,
                reported=None,
                status="NOT_APPLICABLE",
            )
        )
    else:
        for idx, item in enumerate(line_items, start=1):
            qty = _as_number(item.get("quantity"))
            price = _as_number(item.get("unit_price"))
            amount_reported = _as_number(item.get("amount") if item.get("amount") is not None else item.get("line_total"))

            if qty is None or price is None or amount_reported is None:
                checks.append(
                    _make_check(
                        name=f"line_item_check_{idx}",
                        formula="quantity * unit_price ≈ amount",
                        operands={
                            "quantity": item.get("quantity"),
                            "unit_price": item.get("unit_price"),
                            "amount": amount_reported,
                        },
                        calculated=None,
                        reported=amount_reported,
                        status="NOT_APPLICABLE",
                    )
                )
                continue

            calculated = qty * price
            tol = _tolerance(amount_reported)
            status = "PASS" if abs(calculated - amount_reported) <= tol else "FAIL"

            checks.append(
                _make_check(
                    name=f"line_item_check_{idx}",
                    formula="quantity * unit_price ≈ amount",
                    operands={"quantity": qty, "unit_price": price, "amount": amount_reported},
                    calculated=calculated,
                    reported=amount_reported,
                    status=status,
                )
            )
            if status == "FAIL":
                issues.append(
                    f"line_item_check_{idx}: reported {amount_reported:.2f} vs calculated {calculated:.2f}, variance {abs(calculated-amount_reported):.2f} exceeds tolerance {tol:.2f}"
                )

    # 2. subtotal_reconciliation
    subtotal_reported = _as_number(extracted_data.get("subtotal"))
    tax = _as_number(extracted_data.get("tax_amount"))
    total_reported = _as_number(extracted_data.get("total_amount"))

    if not line_items:
        checks.append(
            _make_check(
                name="subtotal_reconciliation",
                formula="sum(line_item.amount) ≈ subtotal",
                operands={"line_item_sum": None, "subtotal": subtotal_reported},
                calculated=None,
                reported=subtotal_reported,
                status="NOT_APPLICABLE",
            )
        )
    else:
        line_sum = sum(_as_number(item.get("amount") if item.get("amount") is not None else item.get("line_total")) or 0.0 for item in line_items)
        if subtotal_reported is None:
            checks.append(
                _make_check(
                    name="subtotal_reconciliation",
                    formula="sum(line_item.amount) ≈ subtotal",
                    operands={"line_item_sum": line_sum, "subtotal": None},
                    calculated=line_sum,
                    reported=None,
                    status="NOT_APPLICABLE",
                )
            )
        else:
            if (
                subtotal_reported is not None
                and total_reported is not None
                and tax is not None
                and abs(subtotal_reported - total_reported) <= _tolerance(total_reported)
            ):
                checks.append(
                    _make_check(
                        name="subtotal_reconciliation",
                        formula="sum(line_item.amount) ≈ subtotal",
                        operands={"line_item_sum": line_sum, "subtotal": subtotal_reported},
                        calculated=line_sum,
                        reported=subtotal_reported,
                        status="NOT_APPLICABLE",
                    )
                )
            else:
                tol = _tolerance(subtotal_reported)
                status = "PASS" if abs(line_sum - subtotal_reported) <= tol else "FAIL"
                checks.append(
                    _make_check(
                        name="subtotal_reconciliation",
                        formula="sum(line_item.amount) ≈ subtotal",
                        operands={"line_item_sum": line_sum, "subtotal": subtotal_reported},
                        calculated=line_sum,
                        reported=subtotal_reported,
                        status=status,
                    )
                )
                if status == "FAIL":
                    issues.append(
                        f"subtotal_reconciliation: reported {subtotal_reported:.2f} vs calculated {line_sum:.2f}, variance {abs(line_sum-subtotal_reported):.2f} exceeds tolerance {tol:.2f}"
                    )

    # 3. tax_inclusive_check
    tax_inclusive = False
    if subtotal_reported is not None and total_reported is not None and tax is not None:
        if abs(subtotal_reported - total_reported) <= _tolerance(total_reported):
            tax_inclusive = True
            checks.append(
                _make_check(
                    name="tax_inclusive_check",
                    formula="subtotal already includes tax (subtotal ≈ total)",
                    operands={"subtotal": subtotal_reported, "total_amount": total_reported, "tax_amount": tax},
                    calculated=total_reported,
                    reported=total_reported,
                    status="PASS",
                )
            )
        else:
            checks.append(
                _make_check(
                    name="tax_inclusive_check",
                    formula="tax already included in total",
                    operands={"subtotal": subtotal_reported, "total_amount": total_reported, "tax_amount": tax},
                    calculated=None,
                    reported=None,
                    status="NOT_APPLICABLE",
                )
            )
    else:
        checks.append(
            _make_check(
                name="tax_inclusive_check",
                formula="tax already included in total",
                operands={"subtotal": subtotal_reported, "total_amount": total_reported, "tax_amount": tax},
                calculated=None,
                reported=None,
                status="NOT_APPLICABLE",
            )
        )

    # 4. total_check
    discount_raw = extracted_data.get("discount")
    discount_val = _as_number(discount_raw)
    discount_present = discount_raw is not None
    required_for_regular = (
        subtotal_reported is not None and tax is not None and total_reported is not None
    )

    if tax_inclusive:
        if discount_present and discount_val is not None:
            calc_total = subtotal_reported - discount_val
        else:
            calc_total = subtotal_reported

        if total_reported is None:
            checks.append(
                _make_check(
                    name="total_check",
                    formula="subtotal (tax-inclusive) - discount ≈ total_amount",
                    operands={
                        "subtotal": subtotal_reported,
                        "discount": discount_val if discount_present else None,
                        "total_amount": total_reported,
                    },
                    calculated=None,
                    reported=total_reported,
                    status="NOT_APPLICABLE",
                )
            )
        else:
            tol = _tolerance(total_reported)
            status = "PASS" if abs(calc_total - total_reported) <= tol else "FAIL"
            checks.append(
                _make_check(
                    name="total_check",
                    formula="subtotal (tax-inclusive) - discount ≈ total_amount",
                    operands={
                        "subtotal": subtotal_reported,
                        "discount": discount_val if discount_present else None,
                        "total_amount": total_reported,
                    },
                    calculated=calc_total,
                    reported=total_reported,
                    status=status,
                )
            )
            if status == "FAIL":
                issues.append(
                    f"total_check (tax-inclusive): reported {total_reported:.2f} vs calculated {calc_total:.2f}, variance {abs(calc_total-total_reported):.2f} exceeds tolerance {tol:.2f}"
                )
    else:
        if not required_for_regular:
            checks.append(
                _make_check(
                    name="total_check",
                    formula="subtotal + tax_amount - discount ≈ total_amount",
                    operands={
                        "subtotal": subtotal_reported,
                        "tax_amount": tax,
                        "discount": discount_val if discount_present else None,
                        "total_amount": total_reported,
                    },
                    calculated=None,
                    reported=total_reported,
                    status="NOT_APPLICABLE",
                )
            )
        else:
            if discount_present and discount_val is not None:
                calc_total = subtotal_reported + tax - discount_val
            else:
                calc_total = subtotal_reported + tax

            tol = _tolerance(total_reported)
            status = "PASS" if abs(calc_total - total_reported) <= tol else "FAIL"
            checks.append(
                _make_check(
                    name="total_check",
                    formula="subtotal + tax_amount - discount ≈ total_amount",
                    operands={
                        "subtotal": subtotal_reported,
                        "tax_amount": tax,
                        "discount": discount_val if discount_present else None,
                        "total_amount": total_reported,
                    },
                    calculated=calc_total,
                    reported=total_reported,
                    status=status,
                )
            )
            if status == "FAIL":
                issues.append(
                    f"total_check: reported {total_reported:.2f} vs calculated {calc_total:.2f}, variance {abs(calc_total-total_reported):.2f} exceeds tolerance {tol:.2f}"
                )

    # 5. cash_change_check
    cash_paid = _as_number(extracted_data.get("cash_paid"))
    change_reported = _as_number(extracted_data.get("change"))
    if cash_paid is None or change_reported is None:
        checks.append(
            _make_check(
                name="cash_change_check",
                formula="cash_paid - total_amount ≈ change",
                operands={"cash_paid": cash_paid, "total_amount": total_reported, "change": change_reported},
                calculated=None,
                reported=change_reported,
                status="NOT_APPLICABLE",
            )
        )
    else:
        calc_change = cash_paid - (total_reported if total_reported is not None else 0.0)
        tol = _tolerance(change_reported)
        status = "PASS" if abs(calc_change - change_reported) <= tol else "FAIL"
        checks.append(
            _make_check(
                name="cash_change_check",
                formula="cash_paid - total_amount ≈ change",
                operands={"cash_paid": cash_paid, "total_amount": total_reported, "change": change_reported},
                calculated=calc_change,
                reported=change_reported,
                status=status,
            )
        )
        if status == "FAIL":
            issues.append(
                f"cash_change_check: reported {change_reported:.2f} vs calculated {calc_change:.2f}, variance {abs(calc_change-change_reported):.2f} exceeds tolerance {tol:.2f}"
            )

    overall_status = "PASS" if all(c["status"] != "FAIL" for c in checks) else "FAIL"
    return {"checks": checks, "overall_status": overall_status, "issues": issues}


# ── Balance Sheet Validation ──────────────────────────────────────────────────

def validate_balance_sheet(extracted_data: dict) -> dict:
    """Validate Balance Sheet equation and line item sums (Section 4.4)."""
    checks: List[Dict[str, Any]] = []
    issues: List[str] = []

    # Unwrap extracted_data if nested inside extracted_data key
    data = extracted_data.get("extracted_data", extracted_data)

    total_assets = _as_number(data.get("total_assets"))
    total_liabilities = _as_number(data.get("total_liabilities"))
    total_equity = _as_number(data.get("total_equity"))
    total_cap_liab = _as_number(data.get("total_capital_and_liabilities"))

    # If total_capital_and_liabilities is missing but liabilities + equity exist, calculate it
    if total_cap_liab is None and total_liabilities is not None and total_equity is not None:
        calc_cap_liab = total_liabilities + total_equity
    else:
        calc_cap_liab = total_cap_liab

    # 1. balance_sheet_equation: Total Capital & Liabilities ≈ Total Assets
    if calc_cap_liab is None or total_assets is None:
        checks.append(
            _make_check(
                name="balance_sheet_equation",
                formula="total_capital_and_liabilities ≈ total_assets",
                operands={
                    "total_capital_and_liabilities": calc_cap_liab,
                    "total_assets": total_assets,
                },
                calculated=calc_cap_liab,
                reported=total_assets,
                status="NOT_APPLICABLE",
            )
        )
    else:
        tol = _tolerance(total_assets)
        status = "PASS" if abs(calc_cap_liab - total_assets) <= tol else "FAIL"
        checks.append(
            _make_check(
                name="balance_sheet_equation",
                formula="total_capital_and_liabilities ≈ total_assets",
                operands={
                    "total_capital_and_liabilities": calc_cap_liab,
                    "total_assets": total_assets,
                },
                calculated=calc_cap_liab,
                reported=total_assets,
                status=status,
            )
        )
        if status == "FAIL":
            issues.append(
                f"balance_sheet_equation: reported assets {total_assets:.2f} vs calculated cap&liab {calc_cap_liab:.2f} exceeds tolerance {tol:.2f}"
            )

    # 2. assets_reconciliation: sum(asset_items) ≈ total_assets
    asset_items = extracted_data.get("asset_items") or []
    if asset_items and total_assets is not None:
        asset_sum = sum(_as_number(i.get("amount")) or 0.0 for i in asset_items if _as_number(i.get("amount")) is not None)
        tol = _tolerance(total_assets)
        status = "PASS" if abs(asset_sum - total_assets) <= tol else "FAIL"
        checks.append(
            _make_check(
                name="assets_reconciliation",
                formula="sum(asset_items) ≈ total_assets",
                operands={"asset_items_sum": asset_sum, "total_assets": total_assets},
                calculated=asset_sum,
                reported=total_assets,
                status=status,
            )
        )
        if status == "FAIL":
            issues.append(f"assets_reconciliation: sum of items {asset_sum:.2f} vs reported total {total_assets:.2f}")
    else:
        checks.append(
            _make_check(
                name="assets_reconciliation",
                formula="sum(asset_items) ≈ total_assets",
                operands={"asset_items_sum": None, "total_assets": total_assets},
                calculated=None,
                reported=total_assets,
                status="NOT_APPLICABLE",
            )
        )

    # 3. liabilities_reconciliation: sum(liability_items) ≈ total_capital_and_liabilities
    liability_items = extracted_data.get("liability_items") or []
    target_liab = calc_cap_liab if calc_cap_liab is not None else total_liabilities
    if liability_items and target_liab is not None:
        liab_sum = sum(_as_number(i.get("amount")) or 0.0 for i in liability_items if _as_number(i.get("amount")) is not None)
        tol = _tolerance(target_liab)
        status = "PASS" if abs(liab_sum - target_liab) <= tol else "FAIL"
        checks.append(
            _make_check(
                name="liabilities_reconciliation",
                formula="sum(liability_items) ≈ total_capital_and_liabilities",
                operands={"liability_items_sum": liab_sum, "target_total": target_liab},
                calculated=liab_sum,
                reported=target_liab,
                status=status,
            )
        )
        if status == "FAIL":
            issues.append(f"liabilities_reconciliation: sum of items {liab_sum:.2f} vs reported total {target_liab:.2f}")
    else:
        checks.append(
            _make_check(
                name="liabilities_reconciliation",
                formula="sum(liability_items) ≈ total_capital_and_liabilities",
                operands={"liability_items_sum": None, "target_total": target_liab},
                calculated=None,
                reported=target_liab,
                status="NOT_APPLICABLE",
            )
        )

    overall_status = "PASS" if all(c["status"] != "FAIL" for c in checks) else "FAIL"
    return {"checks": checks, "overall_status": overall_status, "issues": issues}


# ── Profit & Loss Validation ──────────────────────────────────────────────────

def validate_pl(extracted_data: dict) -> dict:
    """Validate Profit & Loss formulas (Section 4.4)."""
    checks: List[Dict[str, Any]] = []
    issues: List[str] = []

    data = extracted_data.get("extracted_data", extracted_data)

    interest_earned = _as_number(data.get("interest_earned"))
    other_income = _as_number(data.get("other_income"))
    total_income = _as_number(data.get("total_income"))

    interest_expended = _as_number(data.get("interest_expended"))
    operating_expenses = _as_number(data.get("operating_expenses"))
    provisions = _as_number(data.get("provisions_and_contingencies"))
    total_expenditure = _as_number(data.get("total_expenditure"))

    net_profit_before_mi = _as_number(data.get("net_profit_before_minority_interest"))
    minority_interest = _as_number(data.get("minority_interest"))
    net_profit_attributable = _as_number(data.get("net_profit_attributable_to_group"))

    current_profit = _as_number(data.get("current_profit"))
    brought_forward = _as_number(data.get("brought_forward_profit"))
    total_appropriation = _as_number(data.get("total_available_for_appropriation"))

    # 1. total_income_check: Interest Earned + Other Income ≈ Total Income
    if interest_earned is None or other_income is None or total_income is None:
        checks.append(
            _make_check(
                name="total_income_check",
                formula="interest_earned + other_income ≈ total_income",
                operands={"interest_earned": interest_earned, "other_income": other_income, "total_income": total_income},
                calculated=None,
                reported=total_income,
                status="NOT_APPLICABLE",
            )
        )
    else:
        calc_inc = interest_earned + other_income
        tol = _tolerance(total_income)
        status = "PASS" if abs(calc_inc - total_income) <= tol else "FAIL"
        checks.append(
            _make_check(
                name="total_income_check",
                formula="interest_earned + other_income ≈ total_income",
                operands={"interest_earned": interest_earned, "other_income": other_income, "total_income": total_income},
                calculated=calc_inc,
                reported=total_income,
                status=status,
            )
        )
        if status == "FAIL":
            issues.append(f"total_income_check: calculated {calc_inc:.2f} vs reported {total_income:.2f}")

    # 2. total_expenditure_check: Interest Expended + Operating Expenses + Provisions ≈ Total Expenditure
    if interest_expended is None or operating_expenses is None or provisions is None or total_expenditure is None:
        checks.append(
            _make_check(
                name="total_expenditure_check",
                formula="interest_expended + operating_expenses + provisions_and_contingencies ≈ total_expenditure",
                operands={
                    "interest_expended": interest_expended,
                    "operating_expenses": operating_expenses,
                    "provisions_and_contingencies": provisions,
                    "total_expenditure": total_expenditure,
                },
                calculated=None,
                reported=total_expenditure,
                status="NOT_APPLICABLE",
            )
        )
    else:
        calc_exp = interest_expended + operating_expenses + provisions
        tol = _tolerance(total_expenditure)
        status = "PASS" if abs(calc_exp - total_expenditure) <= tol else "FAIL"
        checks.append(
            _make_check(
                name="total_expenditure_check",
                formula="interest_expended + operating_expenses + provisions_and_contingencies ≈ total_expenditure",
                operands={
                    "interest_expended": interest_expended,
                    "operating_expenses": operating_expenses,
                    "provisions_and_contingencies": provisions,
                    "total_expenditure": total_expenditure,
                },
                calculated=calc_exp,
                reported=total_expenditure,
                status=status,
            )
        )
        if status == "FAIL":
            issues.append(f"total_expenditure_check: calculated {calc_exp:.2f} vs reported {total_expenditure:.2f}")

    # 3. net_profit_before_minority_interest_check: Total Income - Total Expenditure ≈ Net Profit before Minority Interest
    if total_income is None or total_expenditure is None or net_profit_before_mi is None:
        checks.append(
            _make_check(
                name="net_profit_before_minority_interest_check",
                formula="total_income - total_expenditure ≈ net_profit_before_minority_interest",
                operands={
                    "total_income": total_income,
                    "total_expenditure": total_expenditure,
                    "net_profit_before_minority_interest": net_profit_before_mi,
                },
                calculated=None,
                reported=net_profit_before_mi,
                status="NOT_APPLICABLE",
            )
        )
    else:
        calc_np_bmi = total_income - total_expenditure
        tol = _tolerance(net_profit_before_mi)
        status = "PASS" if abs(calc_np_bmi - net_profit_before_mi) <= tol else "FAIL"
        checks.append(
            _make_check(
                name="net_profit_before_minority_interest_check",
                formula="total_income - total_expenditure ≈ net_profit_before_minority_interest",
                operands={
                    "total_income": total_income,
                    "total_expenditure": total_expenditure,
                    "net_profit_before_minority_interest": net_profit_before_mi,
                },
                calculated=calc_np_bmi,
                reported=net_profit_before_mi,
                status=status,
            )
        )
        if status == "FAIL":
            issues.append(f"net_profit_before_minority_interest_check: calculated {calc_np_bmi:.2f} vs reported {net_profit_before_mi:.2f}")

    # 4. net_profit_attributable_check: Net Profit before Minority Interest - Minority Interest ≈ Group Net Profit
    if net_profit_before_mi is None or minority_interest is None or net_profit_attributable is None:
        checks.append(
            _make_check(
                name="net_profit_attributable_check",
                formula="net_profit_before_minority_interest - minority_interest ≈ net_profit_attributable_to_group",
                operands={
                    "net_profit_before_minority_interest": net_profit_before_mi,
                    "minority_interest": minority_interest,
                    "net_profit_attributable_to_group": net_profit_attributable,
                },
                calculated=None,
                reported=net_profit_attributable,
                status="NOT_APPLICABLE",
            )
        )
    else:
        calc_np_attr = net_profit_before_mi - minority_interest
        tol = _tolerance(net_profit_attributable)
        status = "PASS" if abs(calc_np_attr - net_profit_attributable) <= tol else "FAIL"
        checks.append(
            _make_check(
                name="net_profit_attributable_check",
                formula="net_profit_before_minority_interest - minority_interest ≈ net_profit_attributable_to_group",
                operands={
                    "net_profit_before_minority_interest": net_profit_before_mi,
                    "minority_interest": minority_interest,
                    "net_profit_attributable_to_group": net_profit_attributable,
                },
                calculated=calc_np_attr,
                reported=net_profit_attributable,
                status=status,
            )
        )
        if status == "FAIL":
            issues.append(f"net_profit_attributable_check: calculated {calc_np_attr:.2f} vs reported {net_profit_attributable:.2f}")

    # 5. appropriation_check: Current Profit + Brought Forward Profit ≈ Total Available for Appropriation
    if current_profit is None or brought_forward is None or total_appropriation is None:
        checks.append(
            _make_check(
                name="appropriation_check",
                formula="current_profit + brought_forward_profit ≈ total_available_for_appropriation",
                operands={
                    "current_profit": current_profit,
                    "brought_forward_profit": brought_forward,
                    "total_available_for_appropriation": total_appropriation,
                },
                calculated=None,
                reported=total_appropriation,
                status="NOT_APPLICABLE",
            )
        )
    else:
        calc_app = current_profit + brought_forward
        tol = _tolerance(total_appropriation)
        status = "PASS" if abs(calc_app - total_appropriation) <= tol else "FAIL"
        checks.append(
            _make_check(
                name="appropriation_check",
                formula="current_profit + brought_forward_profit ≈ total_available_for_appropriation",
                operands={
                    "current_profit": current_profit,
                    "brought_forward_profit": brought_forward,
                    "total_available_for_appropriation": total_appropriation,
                },
                calculated=calc_app,
                reported=total_appropriation,
                status=status,
            )
        )
        if status == "FAIL":
            issues.append(f"appropriation_check: calculated {calc_app:.2f} vs reported {total_appropriation:.2f}")

    overall_status = "PASS" if all(c["status"] != "FAIL" for c in checks) else "FAIL"
    return {"checks": checks, "overall_status": overall_status, "issues": issues}


# ── Cash Flow Validation ──────────────────────────────────────────────────────

def validate_cash_flow(extracted_data: dict) -> dict:
    """Validate Cash Flow Statement formulas (Section 4.4)."""
    checks: List[Dict[str, Any]] = []
    issues: List[str] = []

    data = extracted_data.get("extracted_data", extracted_data)

    op_cf = _as_number(data.get("operating_cash_flow"))
    inv_cf = _as_number(data.get("investing_cash_flow"))
    fin_cf = _as_number(data.get("financing_cash_flow"))
    fx_adj = _as_number(data.get("fx_translation_adjustment")) or 0.0
    net_change = _as_number(data.get("net_change_in_cash"))

    opening_cash = _as_number(data.get("opening_cash"))
    amalg_cash = _as_number(data.get("cash_acquired_on_amalgamation")) or 0.0
    closing_cash = _as_number(data.get("closing_cash"))

    # 1. net_cash_flow_reconciliation
    if op_cf is None or inv_cf is None or fin_cf is None or net_change is None:
        checks.append(
            _make_check(
                name="net_cash_flow_reconciliation",
                formula="operating_cash_flow + investing_cash_flow + financing_cash_flow + fx_translation_adjustment ≈ net_change_in_cash",
                operands={
                    "operating_cash_flow": op_cf,
                    "investing_cash_flow": inv_cf,
                    "financing_cash_flow": fin_cf,
                    "fx_translation_adjustment": fx_adj,
                    "net_change_in_cash": net_change,
                },
                calculated=None,
                reported=net_change,
                status="NOT_APPLICABLE",
            )
        )
    else:
        calc_net = op_cf + inv_cf + fin_cf + fx_adj
        tol = _tolerance(net_change)
        status = "PASS" if abs(calc_net - net_change) <= tol else "FAIL"
        checks.append(
            _make_check(
                name="net_cash_flow_reconciliation",
                formula="operating_cash_flow + investing_cash_flow + financing_cash_flow + fx_translation_adjustment ≈ net_change_in_cash",
                operands={
                    "operating_cash_flow": op_cf,
                    "investing_cash_flow": inv_cf,
                    "financing_cash_flow": fin_cf,
                    "fx_translation_adjustment": fx_adj,
                    "net_change_in_cash": net_change,
                },
                calculated=calc_net,
                reported=net_change,
                status=status,
            )
        )
        if status == "FAIL":
            issues.append(f"net_cash_flow_reconciliation: calculated {calc_net:.2f} vs reported {net_change:.2f}")

    # 2. closing_cash_reconciliation
    if opening_cash is None or net_change is None or closing_cash is None:
        checks.append(
            _make_check(
                name="closing_cash_reconciliation",
                formula="opening_cash + net_change_in_cash + cash_acquired_on_amalgamation ≈ closing_cash",
                operands={
                    "opening_cash": opening_cash,
                    "net_change_in_cash": net_change,
                    "cash_acquired_on_amalgamation": amalg_cash,
                    "closing_cash": closing_cash,
                },
                calculated=None,
                reported=closing_cash,
                status="NOT_APPLICABLE",
            )
        )
    else:
        calc_closing = opening_cash + net_change + amalg_cash
        tol = _tolerance(closing_cash)
        status = "PASS" if abs(calc_closing - closing_cash) <= tol else "FAIL"
        checks.append(
            _make_check(
                name="closing_cash_reconciliation",
                formula="opening_cash + net_change_in_cash + cash_acquired_on_amalgamation ≈ closing_cash",
                operands={
                    "opening_cash": opening_cash,
                    "net_change_in_cash": net_change,
                    "cash_acquired_on_amalgamation": amalg_cash,
                    "closing_cash": closing_cash,
                },
                calculated=calc_closing,
                reported=closing_cash,
                status=status,
            )
        )
        if status == "FAIL":
            issues.append(f"closing_cash_reconciliation: calculated {calc_closing:.2f} vs reported {closing_cash:.2f}")

    overall_status = "PASS" if all(c["status"] != "FAIL" for c in checks) else "FAIL"
    return {"checks": checks, "overall_status": overall_status, "issues": issues}

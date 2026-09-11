import pytest

from app.services.financial_validation_service import (
    validate_invoice,
    validate_balance_sheet,
    validate_pl,
    validate_cash_flow,
)


def base_invoice():
    return {
        "subtotal": 100.0,
        "tax_amount": 10.0,
        "discount": 5.0,
        "total_amount": 105.0,
        "line_items": [
            {"quantity": 2, "unit_price": 30.0, "amount": 60.0},
            {"quantity": 1, "unit_price": 40.0, "amount": 40.0},
        ],
        "cash_paid": None,
        "change": None,
    }


def test_normal_invoice_passes():
    data = base_invoice()
    result = validate_invoice(data)
    assert result["overall_status"] == "PASS"
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["line_item_check_1"] == "PASS"
    assert statuses["line_item_check_2"] == "PASS"
    assert statuses["subtotal_reconciliation"] == "PASS"
    assert statuses["total_check"] == "PASS"
    assert statuses["tax_inclusive_check"] == "NOT_APPLICABLE"
    assert statuses["cash_change_check"] == "NOT_APPLICABLE"
    assert not result["issues"]


def test_tax_inclusive_invoice():
    data = base_invoice()
    data["subtotal"] = 115.0
    data["tax_amount"] = 15.0
    data["discount"] = 0.0
    data["total_amount"] = 115.0
    result = validate_invoice(data)
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["tax_inclusive_check"] == "PASS"
    assert statuses["total_check"] == "PASS"
    assert result["overall_status"] == "PASS"


def test_missing_cash_paid_and_change():
    data = base_invoice()
    data.pop("cash_paid", None)
    data.pop("change", None)
    result = validate_invoice(data)
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["cash_change_check"] == "NOT_APPLICABLE"
    assert result["overall_status"] == "PASS"


def test_total_mismatch_failure():
    data = base_invoice()
    data["total_amount"] = 999.99
    result = validate_invoice(data)
    assert result["overall_status"] == "FAIL"
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["total_check"] == "FAIL"
    assert any("total_check" in issue for issue in result["issues"])


def test_no_line_items():
    data = base_invoice()
    data["line_items"] = []
    data["subtotal"] = None
    result = validate_invoice(data)
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["line_item_check"] == "NOT_APPLICABLE"
    assert statuses["subtotal_reconciliation"] == "NOT_APPLICABLE"
    assert statuses["total_check"] == "NOT_APPLICABLE"
    assert result["overall_status"] == "PASS"


# ── Balance Sheet Validation Tests ──────────────────────────────────────────

def test_balance_sheet_passes():
    data = {
        "total_assets": 1000000.0,
        "total_liabilities": 400000.0,
        "total_equity": 600000.0,
        "total_capital_and_liabilities": 1000000.0,
        "asset_items": [{"name": "Cash", "amount": 1000000.0}],
        "liability_items": [{"name": "Equity & Liab", "amount": 1000000.0}],
    }
    result = validate_balance_sheet(data)
    assert result["overall_status"] == "PASS"
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["balance_sheet_equation"] == "PASS"
    assert statuses["assets_reconciliation"] == "PASS"
    assert statuses["liabilities_reconciliation"] == "PASS"


def test_balance_sheet_fails_mismatch():
    data = {
        "total_assets": 1000000.0,
        "total_capital_and_liabilities": 800000.0,
    }
    result = validate_balance_sheet(data)
    assert result["overall_status"] == "FAIL"
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["balance_sheet_equation"] == "FAIL"


def test_balance_sheet_not_applicable():
    data = {"total_assets": None, "total_capital_and_liabilities": None}
    result = validate_balance_sheet(data)
    assert result["overall_status"] == "PASS"
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["balance_sheet_equation"] == "NOT_APPLICABLE"


# ── Profit & Loss Validation Tests ────────────────────────────────────────────

def test_pl_validation_passes():
    data = {
        "interest_earned": 500.0,
        "other_income": 1500.0,
        "total_income": 2000.0,
        "interest_expended": 200.0,
        "operating_expenses": 800.0,
        "provisions_and_contingencies": 100.0,
        "total_expenditure": 1100.0,
        "net_profit_before_minority_interest": 900.0,
        "minority_interest": 100.0,
        "net_profit_attributable_to_group": 800.0,
    }
    result = validate_pl(data)
    assert result["overall_status"] == "PASS"
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["total_income_check"] == "PASS"
    assert statuses["total_expenditure_check"] == "PASS"
    assert statuses["net_profit_before_minority_interest_check"] == "PASS"
    assert statuses["net_profit_attributable_check"] == "PASS"


def test_pl_validation_fails_expenditure():
    data = {
        "interest_expended": 200.0,
        "operating_expenses": 800.0,
        "provisions_and_contingencies": 100.0,
        "total_expenditure": 5000.0,  # Mismatch!
    }
    result = validate_pl(data)
    assert result["overall_status"] == "FAIL"
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["total_expenditure_check"] == "FAIL"


def test_pl_validation_not_applicable():
    data = {}
    result = validate_pl(data)
    assert result["overall_status"] == "PASS"
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["total_income_check"] == "NOT_APPLICABLE"


# ── Cash Flow Validation Tests ────────────────────────────────────────────────

def test_cash_flow_validation_passes():
    data = {
        "operating_cash_flow": 150000.0,
        "investing_cash_flow": -50000.0,
        "financing_cash_flow": -20000.0,
        "fx_translation_adjustment": 0.0,
        "net_change_in_cash": 80000.0,
        "opening_cash": 50000.0,
        "cash_acquired_on_amalgamation": 0.0,
        "closing_cash": 130000.0,
    }
    result = validate_cash_flow(data)
    assert result["overall_status"] == "PASS"
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["net_cash_flow_reconciliation"] == "PASS"
    assert statuses["closing_cash_reconciliation"] == "PASS"


def test_cash_flow_validation_fails_closing():
    data = {
        "opening_cash": 50000.0,
        "net_change_in_cash": 80000.0,
        "closing_cash": 999999.0,  # Mismatch!
    }
    result = validate_cash_flow(data)
    assert result["overall_status"] == "FAIL"
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["closing_cash_reconciliation"] == "FAIL"


def test_cash_flow_validation_not_applicable():
    data = {}
    result = validate_cash_flow(data)
    assert result["overall_status"] == "PASS"
    statuses = {c["name"]: c["status"] for c in result["checks"]}
    assert statuses["net_cash_flow_reconciliation"] == "NOT_APPLICABLE"

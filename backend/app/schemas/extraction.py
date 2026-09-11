"""
Pydantic schemas for extracted data payloads across all supported document types:
- Invoice
- Balance Sheet
- Profit & Loss Statement
- Cash Flow Statement
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """Source text excerpt and page number evidence for an extracted field."""

    source_text: str | None = None
    page_number: int | None = None


# ── Invoice Schemas ─────────────────────────────────────────────────────────

class InvoiceLineItem(BaseModel):
    """Line item detail on an invoice."""

    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    line_total: float | None = None


class InvoiceHeaderData(BaseModel):
    """Header-level fields extracted from an invoice."""

    invoice_number: str | None = None
    invoice_date: str | None = None
    vendor_name: str | None = None
    customer_name: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax_amount: float | None = None
    discount: float | None = None
    total_amount: float | None = None
    cash_paid: float | None = None
    change: float | None = None
    additional_fields: dict[str, Any] = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    """Structured extraction payload returned for Invoice documents."""

    document_type: str = "invoice"
    extracted_data: InvoiceHeaderData = Field(default_factory=InvoiceHeaderData)
    line_items: list[InvoiceLineItem] = Field(default_factory=list)
    evidence: dict[str, Evidence] = Field(default_factory=dict)


# ── Balance Sheet Schemas ───────────────────────────────────────────────────

class BalanceSheetLineItem(BaseModel):
    """Line item detail on a Balance Sheet."""

    category: str | None = None
    name: str | None = None
    amount: float | None = None


class BalanceSheetData(BaseModel):
    """Fields extracted from a Balance Sheet."""

    company_name: str | None = None
    as_at_date: str | None = None
    period: str | None = None
    currency: str | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None
    total_capital_and_liabilities: float | None = None
    additional_fields: dict[str, Any] = Field(default_factory=dict)


class BalanceSheetExtractionResult(BaseModel):
    """Structured extraction payload returned for Balance Sheet documents."""

    document_type: str = "balance_sheet"
    extracted_data: BalanceSheetData = Field(default_factory=BalanceSheetData)
    asset_items: list[BalanceSheetLineItem] = Field(default_factory=list)
    liability_items: list[BalanceSheetLineItem] = Field(default_factory=list)
    evidence: dict[str, Evidence] = Field(default_factory=dict)


# ── Profit & Loss Schemas ───────────────────────────────────────────────────

class PLLineItem(BaseModel):
    """Line item detail on a Profit & Loss statement."""

    category: str | None = None
    description: str | None = None
    amount: float | None = None


class PLData(BaseModel):
    """Fields extracted from a Profit & Loss statement."""

    company_name: str | None = None
    period: str | None = None
    currency: str | None = None
    revenue: float | None = None
    cost_of_sales: float | None = None
    gross_profit: float | None = None
    operating_expenses: float | None = None
    operating_profit: float | None = None
    tax: float | None = None
    net_profit: float | None = None
    interest_earned: float | None = None
    other_income: float | None = None
    total_income: float | None = None
    interest_expended: float | None = None
    provisions_and_contingencies: float | None = None
    total_expenditure: float | None = None
    net_profit_before_minority_interest: float | None = None
    minority_interest: float | None = None
    net_profit_attributable_to_group: float | None = None
    current_profit: float | None = None
    brought_forward_profit: float | None = None
    total_available_for_appropriation: float | None = None
    additional_fields: dict[str, Any] = Field(default_factory=dict)


class PLExtractionResult(BaseModel):
    """Structured extraction payload returned for Profit & Loss documents."""

    document_type: str = "profit_and_loss"
    extracted_data: PLData = Field(default_factory=PLData)
    line_items: list[PLLineItem] = Field(default_factory=list)
    evidence: dict[str, Evidence] = Field(default_factory=dict)


# ── Cash Flow Statement Schemas ─────────────────────────────────────────────

class CashFlowLineItem(BaseModel):
    """Line item detail on a Cash Flow statement."""

    category: str | None = None
    description: str | None = None
    amount: float | None = None


class CashFlowData(BaseModel):
    """Fields extracted from a Cash Flow statement."""

    company_name: str | None = None
    period: str | None = None
    currency: str | None = None
    operating_cash_flow: float | None = None
    investing_cash_flow: float | None = None
    financing_cash_flow: float | None = None
    fx_translation_adjustment: float | None = None
    net_change_in_cash: float | None = None
    opening_cash: float | None = None
    cash_acquired_on_amalgamation: float | None = None
    closing_cash: float | None = None
    additional_fields: dict[str, Any] = Field(default_factory=dict)


class CashFlowExtractionResult(BaseModel):
    """Structured extraction payload returned for Cash Flow Statement documents."""

    document_type: str = "cash_flow_statement"
    extracted_data: CashFlowData = Field(default_factory=CashFlowData)
    line_items: list[CashFlowLineItem] = Field(default_factory=list)
    evidence: dict[str, Evidence] = Field(default_factory=dict)

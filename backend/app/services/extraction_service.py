"""
Structured AI Extraction Service using Groq API.

Extracts structured header fields, line items, and source evidence from documents:
- Invoice (extract_invoice_fields)
- Balance Sheet (extract_balance_sheet_fields)
- Profit & Loss Statement (extract_pl_fields)
- Cash Flow Statement (extract_cash_flow_fields)
"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

from groq import Groq, GroqError, APIConnectionError, APIStatusError, RateLimitError

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.extraction import (
    Evidence,
    ExtractionResult,
    InvoiceHeaderData,
    InvoiceLineItem,
    BalanceSheetExtractionResult,
    BalanceSheetData,
    BalanceSheetLineItem,
    PLExtractionResult,
    PLData,
    PLLineItem,
    CashFlowExtractionResult,
    CashFlowData,
    CashFlowLineItem,
)

logger = get_logger(__name__)

# Preferred Groq inference model
_GROQ_MODEL: str = "groq/compound"


class ExtractionError(Exception):
    """Exception raised when document extraction fails or Groq API fails."""
    pass


# ── Lazy-initialized Groq Client Singleton ───────────────────────────────────

_GROQ_CLIENT: Groq | None = None


def _get_groq_client() -> Groq:
    """Lazy-initialize and return the shared Groq client instance."""
    global _GROQ_CLIENT
    if _GROQ_CLIENT is None:
        api_key = settings.GROQ_API_KEY
        if not api_key:
            raise ExtractionError("GROQ_API_KEY environment variable is missing or empty.")
        _GROQ_CLIENT = Groq(api_key=api_key)
    return _GROQ_CLIENT


# ── Invoice Extraction ────────────────────────────────────────────────────────

def extract_invoice_fields(
    ocr_text: str | None = None,
    page_texts: Sequence[dict[str, Any] | str] | None = None,
) -> ExtractionResult:
    """Extract structured fields from invoice text using Groq LLM."""
    formatted_prompt_input, total_char_length = _format_document_input(ocr_text, page_texts)

    if not formatted_prompt_input or total_char_length < 3:
        logger.warning("Extraction skipped: document text is empty or near-empty.")
        return ExtractionResult(
            document_type="invoice",
            extracted_data=InvoiceHeaderData(),
            line_items=[],
            evidence={},
        )

    logger.info("Starting Groq invoice extraction call (model=%s, input_len=%d)", _GROQ_MODEL, total_char_length)

    system_prompt = _build_system_prompt()
    user_prompt = f"Extract all visible fields from the following invoice text:\n\n{formatted_prompt_input}"

    raw_json_str = _call_groq(system_prompt, user_prompt)
    return _parse_extraction_response(raw_json_str)


# ── Balance Sheet Extraction ─────────────────────────────────────────────────

def extract_balance_sheet_fields(
    ocr_text: str | None = None,
    page_texts: Sequence[dict[str, Any] | str] | None = None,
) -> BalanceSheetExtractionResult:
    """Extract structured fields from Balance Sheet text using Groq LLM."""
    formatted_prompt_input, total_char_length = _format_document_input(ocr_text, page_texts)

    if not formatted_prompt_input or total_char_length < 3:
        logger.warning("Extraction skipped: Balance Sheet text is empty or near-empty.")
        return BalanceSheetExtractionResult(
            document_type="balance_sheet",
            extracted_data=BalanceSheetData(),
            asset_items=[],
            liability_items=[],
            evidence={},
        )

    logger.info("Starting Groq Balance Sheet extraction call (model=%s, input_len=%d)", _GROQ_MODEL, total_char_length)

    system_prompt = _build_balance_sheet_system_prompt()
    user_prompt = f"Extract all visible fields from the following Balance Sheet text:\n\n{formatted_prompt_input}"

    raw_json_str = _call_groq(system_prompt, user_prompt)
    return _parse_generic_response(raw_json_str, BalanceSheetExtractionResult)


# ── Profit & Loss Extraction ──────────────────────────────────────────────────

def extract_pl_fields(
    ocr_text: str | None = None,
    page_texts: Sequence[dict[str, Any] | str] | None = None,
) -> PLExtractionResult:
    """Extract structured fields from Profit & Loss text using Groq LLM."""
    formatted_prompt_input, total_char_length = _format_document_input(ocr_text, page_texts)

    if not formatted_prompt_input or total_char_length < 3:
        logger.warning("Extraction skipped: P&L text is empty or near-empty.")
        return PLExtractionResult(
            document_type="profit_and_loss",
            extracted_data=PLData(),
            line_items=[],
            evidence={},
        )

    logger.info("Starting Groq P&L extraction call (model=%s, input_len=%d)", _GROQ_MODEL, total_char_length)

    system_prompt = _build_pl_system_prompt()
    user_prompt = f"Extract all visible fields from the following Profit & Loss statement text:\n\n{formatted_prompt_input}"

    raw_json_str = _call_groq(system_prompt, user_prompt)
    return _parse_generic_response(raw_json_str, PLExtractionResult)


# ── Cash Flow Statement Extraction ─────────────────────────────────────────────

def extract_cash_flow_fields(
    ocr_text: str | None = None,
    page_texts: Sequence[dict[str, Any] | str] | None = None,
) -> CashFlowExtractionResult:
    """Extract structured fields from Cash Flow Statement text using Groq LLM."""
    formatted_prompt_input, total_char_length = _format_document_input(ocr_text, page_texts)

    if not formatted_prompt_input or total_char_length < 3:
        logger.warning("Extraction skipped: Cash Flow text is empty or near-empty.")
        return CashFlowExtractionResult(
            document_type="cash_flow_statement",
            extracted_data=CashFlowData(),
            line_items=[],
            evidence={},
        )

    logger.info("Starting Groq Cash Flow extraction call (model=%s, input_len=%d)", _GROQ_MODEL, total_char_length)

    system_prompt = _build_cash_flow_system_prompt()
    user_prompt = f"Extract all visible fields from the following Cash Flow Statement text:\n\n{formatted_prompt_input}"

    raw_json_str = _call_groq(system_prompt, user_prompt)
    return _parse_generic_response(raw_json_str, CashFlowExtractionResult)


# ── Internal Helpers ─────────────────────────────────────────────────────────

_MAX_INPUT_CHARS: int = 12_000  # ~12 000 chars leaves headroom for system prompt


def _format_document_input(
    ocr_text: str | None,
    page_texts: Sequence[dict[str, Any] | str] | None,
) -> tuple[str, int]:
    """Format OCR page texts into structured page-demarcated prompt input."""
    formatted_text = ""
    total_len = 0
    if page_texts:
        parts = []
        for idx, item in enumerate(page_texts, start=1):
            if isinstance(item, dict):
                p_num = item.get("page_number", idx)
                text = (item.get("text") or "").strip()
            else:
                p_num = idx
                text = (str(item) or "").strip()

            if text:
                parts.append(f"--- PAGE {p_num} ---\n{text}")
                total_len += len(text)

        formatted_text = "\n\n".join(parts)
    elif ocr_text:
        formatted_text = ocr_text.strip()
        total_len = len(formatted_text)

    if len(formatted_text) > _MAX_INPUT_CHARS:
        logger.warning(
            "Document text length (%d chars) exceeds limit of %d chars. Truncating for model context safety.",
            len(formatted_text),
            _MAX_INPUT_CHARS,
        )
        formatted_text = formatted_text[:_MAX_INPUT_CHARS]

    return formatted_text, len(formatted_text)



def _build_system_prompt() -> str:
    """Build system instructions for strict JSON invoice extraction."""
    return (
        "You are an expert document AI parser specializing in invoice processing.\n"
        "Your task is to extract all visible fields from the provided invoice text and return "
        "ONLY a valid JSON object matching the exact schema below.\n\n"
        "RULES:\n"
        "1. Extract ALL visible header fields and line items present in the text.\n"
        "2. Top-level header fields to extract: invoice_number, invoice_date, vendor_name, "
        "customer_name, currency, subtotal, tax_amount, discount, total_amount.\n"
        "3. Any extra header fields present (such as PO number, payment terms, billing/shipping address) "
        "MUST be placed inside 'additional_fields' dict.\n"
        "4. Extract line_items as a list of objects: [{description, quantity, unit_price, line_total}].\n"
        "5. For each top-level header field, include an entry in 'evidence' dict mapping field_name to:\n"
        "   {\"source_text\": \"exact text snippet from document\", \"page_number\": page_number_int_or_null}.\n"
        "6. NEVER invent, infer, or extrapolate values not explicitly in the source text. Use null for missing values.\n"
        "7. Return ONLY the JSON object. Do not include markdown codeblocks or conversational text.\n\n"
        "JSON SCHEMA:\n"
        "{\n"
        '  "document_type": "invoice",\n'
        '  "extracted_data": {\n'
        '    "invoice_number": string | null,\n'
        '    "invoice_date": string | null,\n'
        '    "vendor_name": string | null,\n'
        '    "customer_name": string | null,\n'
        '    "currency": string | null,\n'
        '    "subtotal": float | null,\n'
        '    "tax_amount": float | null,\n'
        '    "discount": float | null,\n'
        '    "total_amount": float | null,\n'
        '    "additional_fields": {}\n'
        "  },\n"
        '  "line_items": [\n'
        '    {"description": string|null, "quantity": float|null, "unit_price": float|null, "line_total": float|null}\n'
        "  ],\n"
        '  "evidence": {\n'
        '    "field_name": {"source_text": string|null, "page_number": int|null}\n'
        "  }\n"
        "}"
    )


def _build_balance_sheet_system_prompt() -> str:
    """Build system instructions for strict JSON Balance Sheet extraction."""
    return (
        "You are an expert document AI parser specializing in Balance Sheet processing.\n"
        "Your task is to extract all visible fields from the provided Balance Sheet text and return "
        "ONLY a valid JSON object matching the exact schema below.\n\n"
        "RULES:\n"
        "1. Extract header information (company_name, as_at_date, period, currency) and main totals:\n"
        "   total_assets, total_liabilities, total_equity, total_capital_and_liabilities.\n"
        "2. Extract asset_items and liability_items lists: [{category, name, amount}].\n"
        "3. Any extra line items or header fields MUST be placed in 'additional_fields'.\n"
        "4. Include evidence dict mapping field_name to {\"source_text\": snippet, \"page_number\": page_num}.\n"
        "5. NEVER invent or infer missing values. Return null for missing fields.\n\n"
        "JSON SCHEMA:\n"
        "{\n"
        '  "document_type": "balance_sheet",\n'
        '  "extracted_data": {\n'
        '    "company_name": string | null,\n'
        '    "as_at_date": string | null,\n'
        '    "period": string | null,\n'
        '    "currency": string | null,\n'
        '    "total_assets": float | null,\n'
        '    "total_liabilities": float | null,\n'
        '    "total_equity": float | null,\n'
        '    "total_capital_and_liabilities": float | null,\n'
        '    "additional_fields": {}\n'
        "  },\n"
        '  "asset_items": [{"category": string|null, "name": string|null, "amount": float|null}],\n'
        '  "liability_items": [{"category": string|null, "name": string|null, "amount": float|null}],\n'
        '  "evidence": {\n'
        '    "field_name": {"source_text": string|null, "page_number": int|null}\n'
        "  }\n"
        "}"
    )


def _build_pl_system_prompt() -> str:
    """Build system instructions for strict JSON Profit & Loss extraction."""
    return (
        "You are an expert document AI parser specializing in Profit & Loss statement processing.\n"
        "Your task is to extract all visible fields from the provided P&L text and return "
        "ONLY a valid JSON object matching the exact schema below.\n\n"
        "RULES:\n"
        "1. Extract header information and key P&L fields:\n"
        "   company_name, period, currency, revenue, cost_of_sales, gross_profit, operating_expenses, "
        "   operating_profit, tax, net_profit, interest_earned, other_income, total_income, "
        "   interest_expended, provisions_and_contingencies, total_expenditure, "
        "   net_profit_before_minority_interest, minority_interest, net_profit_attributable_to_group, "
        "   current_profit, brought_forward_profit, total_available_for_appropriation.\n"
        "2. Extract line_items list: [{category, description, amount}].\n"
        "3. Any extra line items or header fields MUST be placed in 'additional_fields'.\n"
        "4. Include evidence dict mapping field_name to {\"source_text\": snippet, \"page_number\": page_num}.\n"
        "5. NEVER invent or infer missing values. Return null for missing fields.\n\n"
        "JSON SCHEMA:\n"
        "{\n"
        '  "document_type": "profit_and_loss",\n'
        '  "extracted_data": {\n'
        '    "company_name": string | null,\n'
        '    "period": string | null,\n'
        '    "currency": string | null,\n'
        '    "revenue": float | null,\n'
        '    "cost_of_sales": float | null,\n'
        '    "gross_profit": float | null,\n'
        '    "operating_expenses": float | null,\n'
        '    "operating_profit": float | null,\n'
        '    "tax": float | null,\n'
        '    "net_profit": float | null,\n'
        '    "interest_earned": float | null,\n'
        '    "other_income": float | null,\n'
        '    "total_income": float | null,\n'
        '    "interest_expended": float | null,\n'
        '    "provisions_and_contingencies": float | null,\n'
        '    "total_expenditure": float | null,\n'
        '    "net_profit_before_minority_interest": float | null,\n'
        '    "minority_interest": float | null,\n'
        '    "net_profit_attributable_to_group": float | null,\n'
        '    "current_profit": float | null,\n'
        '    "brought_forward_profit": float | null,\n'
        '    "total_available_for_appropriation": float | null,\n'
        '    "additional_fields": {}\n'
        "  },\n"
        '  "line_items": [{"category": string|null, "description": string|null, "amount": float|null}],\n'
        '  "evidence": {\n'
        '    "field_name": {"source_text": string|null, "page_number": int|null}\n'
        "  }\n"
        "}"
    )


def _build_cash_flow_system_prompt() -> str:
    """Build system instructions for strict JSON Cash Flow Statement extraction."""
    return (
        "You are an expert document AI parser specializing in Cash Flow Statement processing.\n"
        "Your task is to extract all visible fields from the provided Cash Flow text and return "
        "ONLY a valid JSON object matching the exact schema below.\n\n"
        "RULES:\n"
        "1. Extract header information and key Cash Flow fields:\n"
        "   company_name, period, currency, operating_cash_flow, investing_cash_flow, financing_cash_flow, "
        "   fx_translation_adjustment, net_change_in_cash, opening_cash, cash_acquired_on_amalgamation, closing_cash.\n"
        "2. Bracketed/parentheses values like (500.0) MUST be extracted as negative numbers (e.g. -500.0).\n"
        "3. Extract line_items list: [{category, description, amount}].\n"
        "4. Any extra line items or header fields MUST be placed in 'additional_fields'.\n"
        "5. Include evidence dict mapping field_name to {\"source_text\": snippet, \"page_number\": page_num}.\n"
        "6. NEVER invent or infer missing values. Return null for missing fields.\n\n"
        "JSON SCHEMA:\n"
        "{\n"
        '  "document_type": "cash_flow_statement",\n'
        '  "extracted_data": {\n'
        '    "company_name": string | null,\n'
        '    "period": string | null,\n'
        '    "currency": string | null,\n'
        '    "operating_cash_flow": float | null,\n'
        '    "investing_cash_flow": float | null,\n'
        '    "financing_cash_flow": float | null,\n'
        '    "fx_translation_adjustment": float | null,\n'
        '    "net_change_in_cash": float | null,\n'
        '    "opening_cash": float | null,\n'
        '    "cash_acquired_on_amalgamation": float | null,\n'
        '    "closing_cash": float | null,\n'
        '    "additional_fields": {}\n'
        "  },\n"
        '  "line_items": [{"category": string|null, "description": string|null, "amount": float|null}],\n'
        '  "evidence": {\n'
        '    "field_name": {"source_text": string|null, "page_number": int|null}\n'
        "  }\n"
        "}"
    )


def _call_groq(system_prompt: str, user_prompt: str) -> str:
    """Execute Groq API completion request with error handling."""
    client = _get_groq_client()
    try:
        completion = client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        content = completion.choices[0].message.content or ""
        logger.info("Groq extraction API call successful.")
        return content
    except (RateLimitError, APIConnectionError, APIStatusError, GroqError) as exc:
        logger.error("Groq API error during extraction: %s", exc)
        raise ExtractionError(f"Groq API call failed: {exc}") from exc
    except Exception as exc:
        logger.error("Unexpected error during Groq API call: %s", exc)
        raise ExtractionError(f"Unexpected error during extraction: {exc}") from exc


def _parse_extraction_response(raw_json_str: str) -> ExtractionResult:
    """Parse raw LLM response text into Pydantic ExtractionResult defensively."""
    return _parse_generic_response(raw_json_str, ExtractionResult)


def _parse_generic_response(raw_json_str: str, model_cls: type[Any]) -> Any:
    """Parse raw LLM response text into specified Pydantic model defensively."""
    cleaned = raw_json_str.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Groq response as JSON. Raw output preview: %.100s", raw_json_str)
        raise ExtractionError("LLM response was not valid JSON.") from exc

    try:
        return model_cls.model_validate(data)
    except Exception as exc:
        logger.error("Failed to validate JSON payload into %s schema: %s", model_cls.__name__, exc)
        raise ExtractionError(f"Extracted data did not match the expected {model_cls.__name__} schema.") from exc

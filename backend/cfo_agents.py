"""Autonomous CFO specialist sub-agents and unified multi-agent orchestrator.

Every financial figure is computed deterministically in integer minor units
(no floats). In live mode, the orchestrator may refine only the executive
summary headline via the configured OpenShift AI model, guarded by
`cited_amounts()` with automatic deterministic fallback so the specialist
cards never fail.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, StrictInt

from . import advice
from .advice import ATTEMPTS, ModelConfig, ModelError, cited_amounts, day_name, pln, use_currency
from .forecast import classify_transaction
from .insights import stress_test
from .models import SUPPORTED_CURRENCIES, CurrencyCode, InsightRequest, Transaction
from .telemetry import log_llm_call


log = logging.getLogger("autonomous_cfo.cfo_agents")

AutonomyLevel = Literal["analyzed", "recommended", "requires_approval", "simulation_only"]

# ─── Constants ───────────────────────────────────────────────────────────────

FX_SHOCK_BPS = 500          # 5.00% adverse FX shock
FX_FORWARD_COST_BPS = 35    # 0.35% simulated Commerzbank FX Forward spread
FX_OPTION_COST_BPS = 120    # 1.20% simulated Commerzbank FX Option premium

VAT_ADVANCE_BPS = 1900      # 19.00% quarterly VAT / advance tax reserve proxy on net operating cash

FESTGELD_ANNUAL_BPS = 310   # 3.10% p.a. simulated Commerzbank Fixed-Term Deposit (Festgeld)
MMF_ANNUAL_BPS = 340        # 3.40% p.a. simulated Commerzbank Money Market Fund

_CURRENCY_CODE_RE = re.compile(
    r"\b(" + "|".join(sorted(SUPPORTED_CURRENCIES)) + r")\b",
)
_FX_PAIR_RE = re.compile(
    r"@\s*\d+(?:[.,]\d+)?\s*([A-Z]{3})/([A-Z]{3})\b",
    re.IGNORECASE,
)
_CROSS_BORDER_RE = re.compile(
    r"\b(international\s+wire|swift|foreign\s+exchange|cross[- ]border|export|import(?:ed)?|fx\s+conversion)\b",
    re.IGNORECASE,
)
_INTL_SUPPLIER_RE = re.compile(
    r"\b(asimex|fattoria|sapori)\b",
    re.IGNORECASE,
)
_TAX_KEYWORD_RE = re.compile(
    r"\b(tax\s+office|finanzamt|vat|krankenkasse|social\s+security|health\s+fund|zus|pit|income\s+tax|wage\s+tax|tax\s+payment|tax)\b",
    re.IGNORECASE,
)

_DEDUCTIBLE_LABELS: dict[str, str] = {
    "rent": "Commercial Rent",
    "b2b_supplier": "B2B Suppliers & Inventory",
    "utility": "Utilities & Energy",
    "staff_payroll": "Staff Payroll",
}

HEADLINE_SCHEMA = {
    "type": "object",
    "properties": {"summary_headline": {"type": "string"}},
    "required": ["summary_headline"],
}

HEADLINE_SYSTEM_PROMPT = """You are the Chief Financial Officer orchestrator of a small business finance assistant.
The specialist agents (Liquidity, FX Hedging, Tax, and Investment) have already calculated every figure.
Rules:
- Write 1-2 crisp plain-English sentences summarizing the combined CFO outlook.
- Use ONLY the exact amounts and facts provided. Never calculate, round, or invent any number, rate, or date.
- No markdown, no bullet points.
- Reply with JSON: {"summary_headline": "..."}."""


# ─── Pydantic Response Models ────────────────────────────────────────────────


class FxExposureItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_id: str
    date: date
    counterparty: str
    amount_minor: NonNegativeInt
    direction: Literal["inflow", "outflow"]
    detected_currency: str
    exposure_kind: Literal["direct_fx", "cross_border", "international_supplier"]
    reason: str


class FxHedgeRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument_kind: Literal["fx_forward", "fx_option"]
    product_name: str
    protected_amount_minor: NonNegativeInt
    estimated_cost_minor: NonNegativeInt
    cost_bps: NonNegativeInt
    coverage_pct: int = Field(ge=0, le=100)
    autonomy_level: AutonomyLevel
    simulated: Literal[True] = True
    detail: str


class FxHedgingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: Literal["fx_hedging"] = "fx_hedging"
    home_currency: CurrencyCode
    risk_level: Literal["none", "low", "medium", "high"]
    total_exposure_minor: NonNegativeInt
    adverse_shock_bps: NonNegativeInt = FX_SHOCK_BPS
    adverse_shock_impact_minor: NonNegativeInt
    exposures: list[FxExposureItem]
    hedges: list[FxHedgeRecommendation]
    autonomy_level: AutonomyLevel
    simulated: Literal[True] = True
    summary: str = Field(min_length=1)


class TaxObligationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_id: str
    date: date
    counterparty: str
    amount_minor: NonNegativeInt
    reference: str


class DeductibleCategorySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["rent", "b2b_supplier", "utility", "staff_payroll"]
    display_name: str
    transaction_count: PositiveInt
    total_minor: NonNegativeInt


class TaxAgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: Literal["tax_agent"] = "tax_agent"
    currency: CurrencyCode
    scheduled_tax_total_minor: NonNegativeInt
    operating_inflows_minor: NonNegativeInt
    operating_outflows_minor: NonNegativeInt
    net_operating_cash_minor: StrictInt
    vat_advance_reserve_minor: NonNegativeInt
    recommended_quarterly_reserve_minor: NonNegativeInt
    tax_obligations: list[TaxObligationItem]
    deductible_categories: list[DeductibleCategorySummary]
    total_deductible_minor: NonNegativeInt
    reserve_at_risk: bool
    reserve_shortfall_minor: NonNegativeInt
    cash_dip_warning: str | None
    autonomy_level: AutonomyLevel
    simulated: Literal[True] = True
    summary: str = Field(min_length=1)


class InvestmentOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_kind: Literal["fixed_term_deposit", "money_market_fund", "capex_equipment_financing", "capex_leasing"]
    product_name: str
    annual_rate_bps: NonNegativeInt
    allocated_minor: NonNegativeInt
    projected_yield_30d_minor: NonNegativeInt
    projected_yield_90d_minor: NonNegativeInt
    autonomy_level: AutonomyLevel
    simulated: Literal[True] = True
    detail: str


class InvestmentAgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: Literal["investment_agent"] = "investment_agent"
    currency: CurrencyCode
    min_balance_minor: StrictInt
    safety_cushion_minor: NonNegativeInt
    investable_surplus_minor: NonNegativeInt
    surplus_threshold_needed_minor: NonNegativeInt
    liquidity_first_mode: bool
    options: list[InvestmentOption]
    autonomy_level: AutonomyLevel
    simulated: Literal[True] = True
    summary: str = Field(min_length=1)


class MultiAgentSuiteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fx_hedging: FxHedgingResponse
    tax_agent: TaxAgentResponse
    investment_agent: InvestmentAgentResponse
    summary_headline: str = Field(min_length=1)
    agents_active: Literal[4] = 4
    model: str
    latency_ms: NonNegativeInt


# ─── Deterministic Math Helpers ──────────────────────────────────────────────


def _pct_minor(amount_minor: int, bps: int) -> int:
    """Exact basis-point percentage of a minor-unit amount, rounded half up."""
    if amount_minor <= 0 or bps <= 0:
        return 0
    return int(
        (Decimal(amount_minor) * Decimal(bps) / Decimal(10_000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _annualized_yield_minor(principal_minor: int, annual_bps: int, days: int) -> int:
    """Exact projected yield in minor units over `days` on a 365-day year, rounded half up."""
    if principal_minor <= 0 or annual_bps <= 0 or days <= 0:
        return 0
    return int(
        (Decimal(principal_minor) * Decimal(annual_bps) * Decimal(days) / Decimal(10_000 * 365)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _tx_category(tx: Transaction) -> str:
    if tx.category is not None:
        return tx.category
    category, _ = classify_transaction(
        tx.transaction_type or "",
        tx.counterparty or tx.label,
        tx.payment_reference or "",
        tx.amount_minor,
    )
    return category


def _detect_fx_exposure(tx: Transaction, home_currency: str) -> FxExposureItem | None:
    """Identify foreign currency, FX conversion, cross-border, or international supplier exposure."""
    fields = " ".join(
        part
        for part in (tx.label, tx.counterparty, tx.transaction_type, tx.payment_reference)
        if part
    )
    if not fields:
        return None

    counterparty = tx.counterparty or tx.label
    direction: Literal["inflow", "outflow"] = "inflow" if tx.amount_minor > 0 else "outflow"
    amount = abs(tx.amount_minor)

    # 1. Explicit FX conversion note like "@ 1.050 EUR/CHF" or "@ 1.0800 USD/EUR"
    pair_match = _FX_PAIR_RE.search(fields)
    if pair_match:
        c1, c2 = pair_match.group(1).upper(), pair_match.group(2).upper()
        foreign = c2 if c1 == home_currency else (c1 if c2 == home_currency else c2)
        return FxExposureItem(
            transaction_id=tx.id,
            date=tx.date,
            counterparty=counterparty,
            amount_minor=amount,
            direction=direction,
            detected_currency=foreign,
            exposure_kind="direct_fx",
            reason=f"FX conversion noted ({pair_match.group(0).strip()}) involving {foreign}.",
        )

    # 2. Non-home currency code explicitly mentioned in label/reference/type
    mentioned = [
        code
        for code in _CURRENCY_CODE_RE.findall(fields)
        if code != home_currency
    ]
    if mentioned:
        foreign = mentioned[0]
        return FxExposureItem(
            transaction_id=tx.id,
            date=tx.date,
            counterparty=counterparty,
            amount_minor=amount,
            direction=direction,
            detected_currency=foreign,
            exposure_kind="direct_fx",
            reason=f"Non-home currency {foreign} referenced on a {home_currency} account.",
        )

    # 3. Cross-border wire / import-export marker
    cross_match = _CROSS_BORDER_RE.search(fields)
    if cross_match:
        return FxExposureItem(
            transaction_id=tx.id,
            date=tx.date,
            counterparty=counterparty,
            amount_minor=amount,
            direction=direction,
            detected_currency="CROSS-BORDER",
            exposure_kind="cross_border",
            reason=f"Cross-border payment indicator ('{cross_match.group(0)}').",
        )

    # 4. Known international supply-chain counterparties (indirect FX pass-through)
    intl_match = _INTL_SUPPLIER_RE.search(fields)
    if intl_match:
        return FxExposureItem(
            transaction_id=tx.id,
            date=tx.date,
            counterparty=counterparty,
            amount_minor=amount,
            direction=direction,
            detected_currency="CROSS-BORDER",
            exposure_kind="international_supplier",
            reason=f"International supplier ({counterparty}) with cross-border sourcing exposure.",
        )

    return None


# ─── 1. FX Hedging Agent ─────────────────────────────────────────────────────


def analyze_fx_hedging(mode: str, request: InsightRequest) -> FxHedgingResponse:
    """Scan transactions for FX / cross-border exposure and structure simulated Commerzbank hedges."""
    del mode  # Deterministic calculation; orchestrator handles optional live headline refinement.
    home_currency = request.currency
    with use_currency(home_currency):
        exposures: list[FxExposureItem] = []
        for tx in sorted(request.transactions, key=lambda item: (item.date, item.id)):
            if tx.amount_minor == 0:
                continue
            item = _detect_fx_exposure(tx, home_currency)
            if item is not None:
                exposures.append(item)

        total_exposure = sum(item.amount_minor for item in exposures)
        adverse_shock = _pct_minor(total_exposure, FX_SHOCK_BPS)

        if total_exposure == 0:
            return FxHedgingResponse(
                home_currency=home_currency,
                risk_level="none",
                total_exposure_minor=0,
                adverse_shock_bps=FX_SHOCK_BPS,
                adverse_shock_impact_minor=0,
                exposures=[],
                hedges=[],
                autonomy_level="analyzed",
                simulated=True,
                summary=(
                    f"No foreign currency or cross-border supplier exposure detected across "
                    f"{len(request.transactions)} {home_currency} transactions."
                ),
            )

        has_direct_fx = any(item.exposure_kind == "direct_fx" for item in exposures)
        if has_direct_fx or adverse_shock >= 50_000:
            risk_level: Literal["none", "low", "medium", "high"] = "high"
        elif total_exposure >= 100_000:
            risk_level = "medium"
        else:
            risk_level = "low"

        forward_cost = _pct_minor(total_exposure, FX_FORWARD_COST_BPS)
        option_cost = _pct_minor(total_exposure, FX_OPTION_COST_BPS)

        hedges = [
            FxHedgeRecommendation(
                instrument_kind="fx_forward",
                product_name="Commerzbank FX Forward (Devisentermingeschäft)",
                protected_amount_minor=total_exposure,
                estimated_cost_minor=forward_cost,
                cost_bps=FX_FORWARD_COST_BPS,
                coverage_pct=100,
                autonomy_level="requires_approval",
                simulated=True,
                detail=(
                    f"Lock in the exchange rate on {pln(total_exposure)} to neutralize a 5% adverse move "
                    f"({pln(adverse_shock)}) for an estimated spread cost of {pln(forward_cost)}."
                ),
            ),
            FxHedgeRecommendation(
                instrument_kind="fx_option",
                product_name="Commerzbank FX Option",
                protected_amount_minor=total_exposure,
                estimated_cost_minor=option_cost,
                cost_bps=FX_OPTION_COST_BPS,
                coverage_pct=100,
                autonomy_level="requires_approval",
                simulated=True,
                detail=(
                    f"Cap downside FX risk on {pln(total_exposure)} against a {pln(adverse_shock)} adverse shock "
                    f"while retaining upside participation for an estimated premium of {pln(option_cost)}."
                ),
            ),
        ]

        currencies_seen = sorted({item.detected_currency for item in exposures})
        summary = (
            f"Detected {len(exposures)} FX/cross-border transaction(s) ({', '.join(currencies_seen)}) "
            f"totaling {pln(total_exposure)}. A 5% adverse FX shock would impact cash by {pln(adverse_shock)}; "
            f"a simulated Commerzbank FX Forward protects 100% for an estimated {pln(forward_cost)}."
        )

        return FxHedgingResponse(
            home_currency=home_currency,
            risk_level=risk_level,
            total_exposure_minor=total_exposure,
            adverse_shock_bps=FX_SHOCK_BPS,
            adverse_shock_impact_minor=adverse_shock,
            exposures=exposures,
            hedges=hedges,
            autonomy_level="requires_approval",
            simulated=True,
            summary=summary,
        )


# ─── 2. Tax Agent ────────────────────────────────────────────────────────────


def analyze_tax_reserve(mode: str, request: InsightRequest) -> TaxAgentResponse:
    """Compute quarterly advance tax reserve, deductible expense breakdown, and cash-dip risk."""
    del mode
    with use_currency(request.currency):
        tax_obligations: list[TaxObligationItem] = []
        deductible_counts: dict[str, int] = {}
        deductible_totals: dict[str, int] = {}
        operating_inflows = 0
        operating_outflows = 0

        for tx in sorted(request.transactions, key=lambda item: (item.date, item.id)):
            if tx.amount_minor > 0:
                operating_inflows += tx.amount_minor
                continue
            if tx.amount_minor == 0:
                continue

            outflow = -tx.amount_minor
            operating_outflows += outflow
            category = _tx_category(tx)
            combined = " ".join(
                part
                for part in (tx.label, tx.counterparty, tx.transaction_type, tx.payment_reference)
                if part
            )

            is_tax = bool(_TAX_KEYWORD_RE.search(combined)) or (
                category == "tax_social" and "capital" not in combined.lower()
            )
            if is_tax:
                tax_obligations.append(
                    TaxObligationItem(
                        transaction_id=tx.id,
                        date=tx.date,
                        counterparty=tx.counterparty or tx.label,
                        amount_minor=outflow,
                        reference=tx.payment_reference or tx.label,
                    )
                )
            elif category in _DEDUCTIBLE_LABELS:
                deductible_counts[category] = deductible_counts.get(category, 0) + 1
                deductible_totals[category] = deductible_totals.get(category, 0) + outflow

        scheduled_tax_total = sum(item.amount_minor for item in tax_obligations)
        net_operating_cash = operating_inflows - operating_outflows
        vat_advance_reserve = _pct_minor(net_operating_cash, VAT_ADVANCE_BPS) if net_operating_cash > 0 else 0
        recommended_reserve = scheduled_tax_total + vat_advance_reserve

        deductible_categories = [
            DeductibleCategorySummary(
                category=cat,  # type: ignore[arg-type]
                display_name=_DEDUCTIBLE_LABELS[cat],
                transaction_count=deductible_counts[cat],
                total_minor=deductible_totals[cat],
            )
            for cat in ("rent", "b2b_supplier", "utility", "staff_payroll")
            if cat in deductible_totals
        ]
        total_deductible = sum(item.total_minor for item in deductible_categories)

        days = request.baseline.days
        in_window_tax_dates = [
            item.date for item in tax_obligations if days[0].date <= item.date <= days[-1].date
        ]
        due_cutoff = min(in_window_tax_dates) if in_window_tax_dates else days[-1].date
        days_up_to_due = [day for day in days if day.date <= due_cutoff]
        lowest_day = min(days_up_to_due, key=lambda day: day.balance_minor)

        reserve_at_risk = recommended_reserve > 0 and lowest_day.balance_minor < recommended_reserve
        if reserve_at_risk:
            reserve_shortfall = recommended_reserve - lowest_day.balance_minor
            cash_dip_warning: str | None = (
                f"Projected cash dips to {pln(lowest_day.balance_minor)} on {day_name(lowest_day.date)}, "
                f"which is {pln(reserve_shortfall)} below the {pln(recommended_reserve)} tax reserve "
                f"before {day_name(due_cutoff)}."
            )
            autonomy_level: AutonomyLevel = "requires_approval"
        else:
            reserve_shortfall = 0
            cash_dip_warning = None
            autonomy_level = "recommended" if recommended_reserve > 0 else "analyzed"

        summary = (
            f"Recommended quarterly tax reserve is {pln(recommended_reserve)} "
            f"({pln(scheduled_tax_total)} scheduled tax/social outflows plus {pln(vat_advance_reserve)} "
            f"estimated VAT/advance reserve). Identified {pln(total_deductible)} in deductible operating expenses."
        )
        if cash_dip_warning:
            summary = f"{summary} Warning: {cash_dip_warning}"

        return TaxAgentResponse(
            currency=request.currency,
            scheduled_tax_total_minor=scheduled_tax_total,
            operating_inflows_minor=operating_inflows,
            operating_outflows_minor=operating_outflows,
            net_operating_cash_minor=net_operating_cash,
            vat_advance_reserve_minor=vat_advance_reserve,
            recommended_quarterly_reserve_minor=recommended_reserve,
            tax_obligations=tax_obligations,
            deductible_categories=deductible_categories,
            total_deductible_minor=total_deductible,
            reserve_at_risk=reserve_at_risk,
            reserve_shortfall_minor=reserve_shortfall,
            cash_dip_warning=cash_dip_warning,
            autonomy_level=autonomy_level,
            simulated=True,
            summary=summary,
        )


# ─── 3. Investment Agent ─────────────────────────────────────────────────────


def analyze_investments(mode: str, request: InsightRequest) -> InvestmentAgentResponse:
    """Evaluate investable surplus above the stress-test safety cushion and propose Commerzbank options."""
    del mode
    with use_currency(request.currency):
        stress = stress_test(request)
        safety_cushion = stress.recommended_limit_minor
        min_balance = min(day.balance_minor for day in request.baseline.days)
        investable_surplus = max(0, min_balance - safety_cushion)

        if investable_surplus > 0:
            festgeld_30d = _annualized_yield_minor(investable_surplus, FESTGELD_ANNUAL_BPS, 30)
            festgeld_90d = _annualized_yield_minor(investable_surplus, FESTGELD_ANNUAL_BPS, 90)
            mmf_30d = _annualized_yield_minor(investable_surplus, MMF_ANNUAL_BPS, 30)
            mmf_90d = _annualized_yield_minor(investable_surplus, MMF_ANNUAL_BPS, 90)

            options = [
                InvestmentOption(
                    option_kind="fixed_term_deposit",
                    product_name="Commerzbank Fixed-Term Deposit (Festgeld, 3.1% p.a.)",
                    annual_rate_bps=FESTGELD_ANNUAL_BPS,
                    allocated_minor=investable_surplus,
                    projected_yield_30d_minor=festgeld_30d,
                    projected_yield_90d_minor=festgeld_90d,
                    autonomy_level="requires_approval",
                    simulated=True,
                    detail=(
                        f"Place {pln(investable_surplus)} in a fixed-term deposit at 3.1% p.a. for an "
                        f"estimated {pln(festgeld_30d)} (30d) or {pln(festgeld_90d)} (90d) yield."
                    ),
                ),
                InvestmentOption(
                    option_kind="money_market_fund",
                    product_name="Commerzbank Money Market Fund (3.4% p.a.)",
                    annual_rate_bps=MMF_ANNUAL_BPS,
                    allocated_minor=investable_surplus,
                    projected_yield_30d_minor=mmf_30d,
                    projected_yield_90d_minor=mmf_90d,
                    autonomy_level="requires_approval",
                    simulated=True,
                    detail=(
                        f"Allocate {pln(investable_surplus)} to a daily-liquid money market fund at 3.4% p.a. "
                        f"for an estimated {pln(mmf_30d)} (30d) or {pln(mmf_90d)} (90d) yield."
                    ),
                ),
                InvestmentOption(
                    option_kind="capex_equipment_financing",
                    product_name="Commerzbank Capex Equipment Financing",
                    annual_rate_bps=0,
                    allocated_minor=investable_surplus,
                    projected_yield_30d_minor=0,
                    projected_yield_90d_minor=0,
                    autonomy_level="recommended",
                    simulated=True,
                    detail=(
                        f"Keep {pln(investable_surplus)} earning treasury yield while financing planned "
                        f"equipment upgrades via dedicated Commerzbank Capex Equipment Financing."
                    ),
                ),
            ]
            summary = (
                f"Investable surplus of {pln(investable_surplus)} sits above the {pln(safety_cushion)} "
                f"stress-test safety cushion (14-day minimum balance {pln(min_balance)}). "
                f"Simulated 90-day yield is {pln(festgeld_90d)} in Festgeld (3.1% p.a.) or "
                f"{pln(mmf_90d)} in the Money Market Fund (3.4% p.a.)."
            )
            return InvestmentAgentResponse(
                currency=request.currency,
                min_balance_minor=min_balance,
                safety_cushion_minor=safety_cushion,
                investable_surplus_minor=investable_surplus,
                surplus_threshold_needed_minor=0,
                liquidity_first_mode=False,
                options=options,
                autonomy_level="requires_approval",
                simulated=True,
                summary=summary,
            )

        threshold_needed = max(0, safety_cushion - min_balance)
        options = [
            InvestmentOption(
                option_kind="capex_leasing",
                product_name="Commerzbank Capex Leasing",
                annual_rate_bps=0,
                allocated_minor=0,
                projected_yield_30d_minor=0,
                projected_yield_90d_minor=0,
                autonomy_level="recommended",
                simulated=True,
                detail=(
                    f"Preserve working capital during liquidity-first mode: use simulated Commerzbank Capex "
                    f"Leasing for equipment needs until cash rises by {pln(threshold_needed)} above the "
                    f"{pln(safety_cushion)} safety cushion."
                ),
            )
        ]
        summary = (
            f"Liquidity-first priority: 14-day minimum balance ({pln(min_balance)}) does not exceed the "
            f"{pln(safety_cushion)} stress-test safety cushion, leaving {pln(0)} investable surplus. "
            f"Build {pln(threshold_needed)} more cash buffer before deploying into deposits; use simulated "
            f"Commerzbank Capex Leasing to preserve working capital."
        )
        return InvestmentAgentResponse(
            currency=request.currency,
            min_balance_minor=min_balance,
            safety_cushion_minor=safety_cushion,
            investable_surplus_minor=0,
            surplus_threshold_needed_minor=threshold_needed,
            liquidity_first_mode=True,
            options=options,
            autonomy_level="recommended",
            simulated=True,
            summary=summary,
        )


# ─── 4. Unified Multi-Agent Orchestrator ─────────────────────────────────────


def _build_deterministic_headline(
    fx: FxHedgingResponse,
    tax: TaxAgentResponse,
    inv: InvestmentAgentResponse,
) -> str:
    parts: list[str] = []
    if fx.total_exposure_minor > 0:
        parts.append(
            f"FX exposure of {pln(fx.total_exposure_minor)} carries a {pln(fx.adverse_shock_impact_minor)} "
            f"5% shock risk"
        )
    else:
        parts.append("No FX exposure detected")

    if tax.reserve_at_risk:
        parts.append(
            f"tax reserve of {pln(tax.recommended_quarterly_reserve_minor)} is at risk by "
            f"{pln(tax.reserve_shortfall_minor)}"
        )
    else:
        parts.append(f"quarterly tax reserve stands at {pln(tax.recommended_quarterly_reserve_minor)}")

    if inv.investable_surplus_minor > 0:
        parts.append(f"investable surplus of {pln(inv.investable_surplus_minor)} is ready for yield deployment")
    else:
        parts.append(
            f"liquidity-first mode active ({pln(inv.surplus_threshold_needed_minor)} needed above safety cushion)"
        )

    return f"CFO 4-Agent Suite: {'; '.join(parts)}."


def _parse_headline_json(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelError("The model didn't return JSON.") from exc
    headline = data.get("summary_headline") if isinstance(data, dict) else None
    if not isinstance(headline, str) or not headline.strip():
        raise ModelError("The model's answer is missing summary_headline.")
    return headline.strip()


def _refine_headline_live(
    fx: FxHedgingResponse,
    tax: TaxAgentResponse,
    inv: InvestmentAgentResponse,
    fallback_headline: str,
) -> tuple[str, str, int]:
    """Optionally refine the executive headline via OpenShift AI with cited_amounts() guard."""
    facts_lines = [
        f"Currency: {fx.home_currency}.",
        f"FX Hedging Agent: {fx.summary}",
        f"Tax Agent: {tax.summary}",
        f"Investment Agent: {inv.summary}",
    ]
    facts_text = "\n".join(facts_lines)
    allowed_minor: set[int] = {
        fx.total_exposure_minor,
        fx.adverse_shock_impact_minor,
        *(h.protected_amount_minor for h in fx.hedges),
        *(h.estimated_cost_minor for h in fx.hedges),
        tax.scheduled_tax_total_minor,
        tax.operating_inflows_minor,
        tax.operating_outflows_minor,
        abs(tax.net_operating_cash_minor),
        tax.vat_advance_reserve_minor,
        tax.recommended_quarterly_reserve_minor,
        tax.total_deductible_minor,
        tax.reserve_shortfall_minor,
        abs(inv.min_balance_minor),
        inv.safety_cushion_minor,
        inv.investable_surplus_minor,
        inv.surplus_threshold_needed_minor,
        *(o.projected_yield_30d_minor for o in inv.options),
        *(o.projected_yield_90d_minor for o in inv.options),
        *cited_amounts(facts_text),
    }

    messages = [
        {"role": "system", "content": HEADLINE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Facts:\n{facts_text}\n\n"
                "Task: write a concise 1-2 sentence executive CFO headline covering FX, tax reserve, "
                "and investment/liquidity status using only the exact figures above."
            ),
        },
    ]

    started = time.monotonic()
    try:
        primary = ModelConfig.from_env()
    except ModelError as exc:
        log.warning("cfo_agents live headline skipped (model unconfigured): %s", exc)
        return fallback_headline, "deterministic-fallback", 0

    fallback_cfg = ModelConfig.fallback_from_env(
        timeout=primary.timeout,
        ssl_context=primary.ssl_context,
    )
    configs = [primary, fallback_cfg] if fallback_cfg else [primary]
    attempts_total = 0
    last_model = primary.name

    for idx, config in enumerate(configs):
        fallback_used = idx > 0
        last_model = config.name
        try:
            for attempt in range(1, ATTEMPTS + 1):
                attempts_total += 1
                candidate = _parse_headline_json(
                    advice.call_model(config, messages, schema=HEADLINE_SCHEMA)
                )
                unknown = [amt for amt in cited_amounts(candidate) if amt not in allowed_minor]
                if not unknown:
                    latency = round((time.monotonic() - started) * 1000)
                    log_llm_call(
                        endpoint="cfo-agents",
                        model=config.name,
                        latency_ms=latency,
                        status="ok",
                        attempts=attempts_total,
                        grounded=True,
                        fallback_used=fallback_used,
                    )
                    return candidate, config.name, latency
                log.warning(
                    "cfo_agents model=%s attempt=%d rejected: unknown amount %s",
                    config.name,
                    attempt,
                    pln(unknown[0]),
                )
        except ModelError as exc:
            log.warning("cfo_agents model=%s failed: %s", config.name, exc)

    latency = round((time.monotonic() - started) * 1000)
    log_llm_call(
        endpoint="cfo-agents",
        model=os.environ.get("CFO_MODEL_NAME", last_model),
        latency_ms=latency,
        status="error",
        attempts=max(1, attempts_total),
        grounded=False,
        fallback_used=len(configs) > 1,
    )
    return fallback_headline, "deterministic-fallback", latency


def run_multi_agent_suite(mode: str, request: InsightRequest) -> MultiAgentSuiteResponse:
    """Run FX Hedging, Tax, and Investment specialist agents alongside the Liquidity baseline."""
    with use_currency(request.currency):
        fx = analyze_fx_hedging(mode, request)
        tax = analyze_tax_reserve(mode, request)
        inv = analyze_investments(mode, request)
        deterministic_headline = _build_deterministic_headline(fx, tax, inv)

        if mode == "live":
            headline, model_name, latency_ms = _refine_headline_live(
                fx, tax, inv, deterministic_headline
            )
        else:
            headline = deterministic_headline
            model_name = "demo-deterministic"
            latency_ms = 0

        return MultiAgentSuiteResponse(
            fx_hedging=fx,
            tax_agent=tax,
            investment_agent=inv,
            summary_headline=headline,
            agents_active=4,
            model=model_name,
            latency_ms=latency_ms,
        )

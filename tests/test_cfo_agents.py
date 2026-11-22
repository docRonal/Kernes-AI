"""Deterministic and live-fallback tests for KERNES CFO specialist sub-agents."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.advice import ModelError
from backend.cfo_agents import (
    FxHedgingResponse,
    InvestmentAgentResponse,
    MultiAgentSuiteResponse,
    TaxAgentResponse,
    analyze_fx_hedging,
    analyze_investments,
    analyze_tax_reserve,
    run_multi_agent_suite,
)
from backend.forecast import build_forecast
from backend.models import InsightRequest, Transaction


DEMO = Path(__file__).resolve().parents[1] / "demo"
AMALFI_CSV = DEMO / "pizzeria_amalfi_sample.csv"
NO_SHORTFALL_CSV = DEMO / "no_shortfall_case.csv"
USD_MIXED_FX_CSV = DEMO / "stress_cases" / "amalfi_usd_mixed_fx.csv"
POLAND_PLN_CSV = DEMO / "stress_cases" / "amalfi_poland_branch_pln.csv"


def _make_request(csv_path: Path, opening_minor: int, start: date) -> InsightRequest:
    forecast = build_forecast(csv_path.read_bytes(), opening_minor, start)
    return InsightRequest(
        baseline=forecast.baseline,
        transactions=forecast.transactions,
        currency=forecast.currency,
    )


class ScriptedModel:
    def __init__(self, answers: list[object]):
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, config, messages, *, schema):
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, str) else json.dumps(answer)


@pytest.fixture
def live_model(monkeypatch):
    def configure(*answers: object, model_name: str = "kernes-qwen-7b") -> ScriptedModel:
        fake = ScriptedModel(list(answers))
        monkeypatch.setattr("backend.advice.call_model", fake)
        monkeypatch.setenv("CFO_MODEL_URL", "http://model.invalid/v1/chat/completions")
        monkeypatch.setenv("CFO_MODEL_NAME", model_name)
        monkeypatch.delenv("CFO_FALLBACK_MODEL_URL", raising=False)
        monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
        return fake

    return configure


# ─── 1. FX Hedging Agent ─────────────────────────────────────────────────────


def test_fx_hedging_amalfi_detects_chf_and_international_suppliers():
    req = _make_request(AMALFI_CSV, opening_minor=500_000, start=date(2025, 6, 23))
    res = analyze_fx_hedging("demo", req)

    assert isinstance(res, FxHedgingResponse)
    assert res.home_currency == "EUR"
    assert res.risk_level == "high"
    assert res.autonomy_level == "requires_approval"
    assert res.simulated is True

    # Luigi Amalfi CHF wire (437,500) + Asimex x3 (67,050 + 57,531 + 60,560) + Fattoria (77,493) = 700,134
    assert res.total_exposure_minor == 700_134
    assert res.adverse_shock_bps == 500
    assert res.adverse_shock_impact_minor == 35_007  # 5% of 700,134 rounded half up

    kinds = {item.exposure_kind for item in res.exposures}
    assert "direct_fx" in kinds
    assert "international_supplier" in kinds
    assert any(item.detected_currency == "CHF" and item.amount_minor == 437_500 for item in res.exposures)

    assert len(res.hedges) == 2
    forward = next(h for h in res.hedges if h.instrument_kind == "fx_forward")
    option = next(h for h in res.hedges if h.instrument_kind == "fx_option")
    assert "Devisentermingeschäft" in forward.product_name
    assert forward.protected_amount_minor == 700_134
    assert forward.estimated_cost_minor == 2_450  # 35 bps of 700,134
    assert option.protected_amount_minor == 700_134
    assert option.estimated_cost_minor == 8_402   # 120 bps of 700,134
    assert forward.simulated is True and option.simulated is True


def test_fx_hedging_usd_mixed_fx_detects_eur_import():
    req = _make_request(USD_MIXED_FX_CSV, opening_minor=500_000, start=date(2025, 6, 23))
    res = analyze_fx_hedging("demo", req)

    assert res.home_currency == "USD"
    assert res.risk_level == "high"
    assert len(res.exposures) == 1
    exposure = res.exposures[0]
    assert exposure.detected_currency == "EUR"
    assert exposure.exposure_kind == "direct_fx"
    # -1,000.00 EUR @ 1.0800 USD/EUR = 108,000 USD minor units
    assert exposure.amount_minor == 108_000
    assert res.total_exposure_minor == 108_000
    assert res.adverse_shock_impact_minor == 5_400
    assert len(res.hedges) == 2
    assert res.hedges[0].estimated_cost_minor == 378   # 35 bps
    assert res.hedges[1].estimated_cost_minor == 1_296  # 120 bps


@pytest.mark.parametrize(
    ("csv_path", "expected_currency", "start"),
    [
        (POLAND_PLN_CSV, "PLN", date(2025, 6, 23)),
        (NO_SHORTFALL_CSV, "EUR", date(2026, 11, 23)),
    ],
)
def test_fx_hedging_domestic_statements_have_zero_exposure(csv_path, expected_currency, start):
    req = _make_request(csv_path, opening_minor=2_000_000, start=start)
    res = analyze_fx_hedging("demo", req)

    assert res.home_currency == expected_currency
    assert res.risk_level == "none"
    assert res.total_exposure_minor == 0
    assert res.adverse_shock_impact_minor == 0
    assert res.exposures == []
    assert res.hedges == []
    assert res.autonomy_level == "analyzed"
    assert res.simulated is True


# ─── 2. Tax Agent ────────────────────────────────────────────────────────────


def test_tax_agent_amalfi_identifies_obligations_deductibles_and_cash_dip():
    req = _make_request(AMALFI_CSV, opening_minor=300_000, start=date(2025, 6, 23))
    res = analyze_tax_reserve("demo", req)

    assert isinstance(res, TaxAgentResponse)
    assert res.currency == "EUR"
    # Tax Office (88,000 + 115,000) + Techniker Krankenkasse (265,000) = 468,000
    assert res.scheduled_tax_total_minor == 468_000
    assert len(res.tax_obligations) == 3
    assert res.net_operating_cash_minor < 0
    assert res.vat_advance_reserve_minor == 0
    assert res.recommended_quarterly_reserve_minor == 468_000

    by_cat = {item.category: item for item in res.deductible_categories}
    assert set(by_cat) == {"rent", "b2b_supplier", "utility", "staff_payroll"}
    assert by_cat["rent"].total_minor == 760_000
    assert by_cat["utility"].total_minor == 65_000
    assert by_cat["staff_payroll"].total_minor == 540_000
    assert by_cat["b2b_supplier"].total_minor == 262_634
    assert res.total_deductible_minor == 1_627_634

    assert res.reserve_at_risk is True
    assert res.reserve_shortfall_minor > 0
    assert res.cash_dip_warning is not None
    assert res.autonomy_level == "requires_approval"


def test_tax_agent_poland_pln_detects_zus_and_deductibles():
    req = _make_request(POLAND_PLN_CSV, opening_minor=1_500_000, start=date(2025, 6, 23))
    res = analyze_tax_reserve("demo", req)

    assert res.currency == "PLN"
    assert res.scheduled_tax_total_minor == 320_000  # ZUS Warszawa -3,200.00 PLN
    assert len(res.tax_obligations) == 1
    assert "ZUS" in res.tax_obligations[0].counterparty
    by_cat = {item.category: item.total_minor for item in res.deductible_categories}
    assert by_cat["rent"] == 1_100_000
    assert by_cat["b2b_supplier"] == 420_000
    assert by_cat["staff_payroll"] == 950_000
    assert "PLN" in res.summary


def test_tax_agent_positive_net_operating_cash_adds_vat_advance_reserve():
    req = _make_request(NO_SHORTFALL_CSV, opening_minor=5_000_000, start=date(2026, 11, 23))
    # Add a large B2B client inflow so net operating cash is positive (+10,000 EUR = +1,000,000 minor)
    extra_inflow = Transaction(
        id="TX-9999",
        date=date(2026, 11, 25),
        amount_minor=1_600_000,
        label="Corporate Catering Contract",
        category="b2b_client",
    )
    req_pos = InsightRequest(
        baseline=req.baseline,
        transactions=[*req.transactions, extra_inflow],
        currency="EUR",
    )
    res = analyze_tax_reserve("demo", req_pos)

    # Inflows: 600,000 + 1,600,000 = 2,200,000; Outflows: 400,000 + 800,000 = 1,200,000 -> net = 1,000,000
    assert res.net_operating_cash_minor == 1_000_000
    assert res.vat_advance_reserve_minor == 190_000  # 19% of 1,000,000
    assert res.recommended_quarterly_reserve_minor == 190_000
    assert res.reserve_at_risk is False
    assert res.cash_dip_warning is None
    assert res.autonomy_level == "recommended"


# ─── 3. Investment Agent ─────────────────────────────────────────────────────


def test_investment_agent_surplus_mode_recommends_festgeld_mmf_and_capex():
    # no_shortfall_case: opening 20,000 EUR -> min balance 14,000 EUR, stress limit 0 -> surplus 14,000 EUR
    req = _make_request(NO_SHORTFALL_CSV, opening_minor=2_000_000, start=date(2026, 11, 23))
    res = analyze_investments("demo", req)

    assert isinstance(res, InvestmentAgentResponse)
    assert res.currency == "EUR"
    assert res.min_balance_minor == 1_400_000
    assert res.safety_cushion_minor == 0
    assert res.investable_surplus_minor == 1_400_000
    assert res.surplus_threshold_needed_minor == 0
    assert res.liquidity_first_mode is False
    assert res.autonomy_level == "requires_approval"
    assert res.simulated is True

    by_kind = {opt.option_kind: opt for opt in res.options}
    assert set(by_kind) == {"fixed_term_deposit", "money_market_fund", "capex_equipment_financing"}

    festgeld = by_kind["fixed_term_deposit"]
    assert "Festgeld" in festgeld.product_name
    assert festgeld.annual_rate_bps == 310
    # 1,400,000 * 310 * 30 / (10,000 * 365) = 3,567.12 -> 3,567
    assert festgeld.projected_yield_30d_minor == 3_567
    # 1,400,000 * 310 * 90 / (10,000 * 365) = 10,701.37 -> 10,701
    assert festgeld.projected_yield_90d_minor == 10_701

    mmf = by_kind["money_market_fund"]
    assert mmf.annual_rate_bps == 340
    # 1,400,000 * 340 * 30 / (10,000 * 365) = 3,912.33 -> 3,912
    assert mmf.projected_yield_30d_minor == 3_912
    # 1,400,000 * 340 * 90 / (10,000 * 365) = 11,736.99 -> 11,737
    assert mmf.projected_yield_90d_minor == 11_737


def test_investment_agent_liquidity_first_mode_recommends_capex_leasing():
    req = _make_request(AMALFI_CSV, opening_minor=300_000, start=date(2025, 6, 23))
    res = analyze_investments("demo", req)

    assert res.liquidity_first_mode is True
    assert res.investable_surplus_minor == 0
    assert res.min_balance_minor < 0
    assert res.safety_cushion_minor > 0
    assert res.surplus_threshold_needed_minor == res.safety_cushion_minor - res.min_balance_minor
    assert len(res.options) == 1
    assert res.options[0].option_kind == "capex_leasing"
    assert "Capex Leasing" in res.options[0].product_name
    assert res.autonomy_level == "recommended"
    assert res.simulated is True


# ─── 4. Unified Orchestrator ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("csv_path", "opening_minor", "start"),
    [
        (AMALFI_CSV, 500_000, date(2025, 6, 23)),
        (NO_SHORTFALL_CSV, 2_000_000, date(2026, 11, 23)),
        (USD_MIXED_FX_CSV, 500_000, date(2025, 6, 23)),
        (POLAND_PLN_CSV, 1_500_000, date(2025, 6, 23)),
    ],
)
def test_orchestrator_demo_mode_across_all_four_csvs(csv_path, opening_minor, start):
    req = _make_request(csv_path, opening_minor=opening_minor, start=start)
    suite = run_multi_agent_suite("demo", req)

    assert isinstance(suite, MultiAgentSuiteResponse)
    assert suite.agents_active == 4
    assert suite.model == "demo-deterministic"
    assert suite.latency_ms == 0
    assert suite.fx_hedging.home_currency == req.currency
    assert suite.tax_agent.currency == req.currency
    assert suite.investment_agent.currency == req.currency
    assert len(suite.summary_headline) > 10


def test_orchestrator_live_mode_refines_grounded_headline(live_model):
    req = _make_request(USD_MIXED_FX_CSV, opening_minor=500_000, start=date(2025, 6, 23))
    fake = live_model(
        {
            "summary_headline": (
                "FX exposure stands at USD 1,080.00 with a USD 54.00 5% shock impact while "
                "liquidity-first mode remains active."
            )
        }
    )

    suite = run_multi_agent_suite("live", req)

    assert fake.calls == 1
    assert suite.model == "kernes-qwen-7b"
    assert "USD 1,080.00" in suite.summary_headline
    assert suite.agents_active == 4
    assert suite.fx_hedging.total_exposure_minor == 108_000


def test_orchestrator_live_mode_rejects_hallucinated_amount_and_falls_back(live_model):
    req = _make_request(USD_MIXED_FX_CSV, opening_minor=500_000, start=date(2025, 6, 23))
    fake = live_model(
        {"summary_headline": "FX exposure is USD 99,999.99 so hedge immediately."},
        {"summary_headline": "FX exposure is USD 88,888.88 so hedge immediately."},
    )

    suite = run_multi_agent_suite("live", req)

    assert fake.calls == 2
    assert suite.model == "deterministic-fallback"
    assert "USD 99,999.99" not in suite.summary_headline
    assert "USD 1,080.00" in suite.summary_headline
    assert suite.fx_hedging.total_exposure_minor == 108_000


def test_orchestrator_live_mode_never_fails_when_model_errors(live_model):
    req = _make_request(AMALFI_CSV, opening_minor=500_000, start=date(2025, 6, 23))
    live_model(ModelError("endpoint timed out"))

    suite = run_multi_agent_suite("live", req)

    assert suite.model == "deterministic-fallback"
    assert suite.agents_active == 4
    assert suite.fx_hedging.total_exposure_minor == 700_134
    assert suite.tax_agent.scheduled_tax_total_minor == 468_000


def test_response_models_forbid_extra_fields():
    req = _make_request(NO_SHORTFALL_CSV, opening_minor=2_000_000, start=date(2026, 11, 23))
    suite = run_multi_agent_suite("demo", req)

    with pytest.raises(ValidationError):
        MultiAgentSuiteResponse.model_validate({**suite.model_dump(), "unexpected": 1})
    with pytest.raises(ValidationError):
        FxHedgingResponse.model_validate({**suite.fx_hedging.model_dump(), "unexpected": 1})
    with pytest.raises(ValidationError):
        TaxAgentResponse.model_validate({**suite.tax_agent.model_dump(), "unexpected": 1})
    with pytest.raises(ValidationError):
        InvestmentAgentResponse.model_validate({**suite.investment_agent.model_dump(), "unexpected": 1})

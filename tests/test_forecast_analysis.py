import json
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from backend.forecast import build_forecast, parse_transactions
from backend.history_forecast import analyze_statement_patterns, estimate_transactions
from backend.main import create_app


ROOT = Path(__file__).resolve().parents[1]
AMALFI_FULL = ROOT / "red-hat-examples" / "pizzeria-amalfi-bank-statement-2025-v6.csv"
CREDIT_PEAK = ROOT / "demo" / "credit_peak_case.csv"


def _csv_from_rows(rows: list[tuple[str, str, int, str]]) -> bytes:
    header = (
        '"Account Number";"Booking Date";"Value Date";"Transaction Type";'
        '"Payment Reference";"Beneficiary/Payer";"Amount";"Currency"\n'
    )
    lines = [header]
    for iso_date, party, amount_minor, cur in rows:
        y, m, d = iso_date.split("-")
        bank_date = f"{d}.{m}.{y[2:]}"
        sign = "-" if amount_minor < 0 else ""
        abs_m = abs(amount_minor)
        amt = f"{sign}{abs_m // 100},{abs_m % 100:02d}"
        ttype = "INCOMING PAYMENT" if amount_minor > 0 else "SUPPLIER PAYMENT"
        lines.append(f'"DE00";" {bank_date}";"{bank_date}";"{ttype}";"Ref";"{party}";"{amt}";"{cur}"\n')
    return "".join(lines).encode("utf-8")


def test_full_year_amalfi_forecast_eliminates_daily_smear_across_28_days():
    raw = AMALFI_FULL.read_bytes()
    fc_w12 = build_forecast(raw, 1_500_000, date(2026, 1, 1))
    assert not any("Estimated daily" in tx.label for tx in fc_w12.transactions)
    tax_jan10 = [tx for tx in fc_w12.transactions if tx.date == date(2026, 1, 10) and "Tax Office" in tx.label]
    assert len(tax_jan10) == 1
    assert tax_jan10[0].amount_minor == -88_000
    assert tax_jan10[0].category == "tax_social"

    # +14d forward window (Jan 15-28) keeps every monthly & weekday schedule intact without daily smear
    end_bal = fc_w12.baseline.days[-1].balance_minor
    fc_w34 = build_forecast(raw, end_bal, date(2026, 1, 15))
    assert not any("Estimated daily" in tx.label for tx in fc_w34.transactions)
    jan15_labels = [tx.label for tx in fc_w34.transactions if tx.date == date(2026, 1, 15)]
    jan27_labels = [tx.label for tx in fc_w34.transactions if tx.date == date(2026, 1, 27)]
    jan28_labels = [tx.label for tx in fc_w34.transactions if tx.date == date(2026, 1, 28)]
    assert any("Luigi Amalfi" in lbl for lbl in jan15_labels)
    assert any("Techniker Krankenkasse" in lbl for lbl in jan27_labels)
    assert any("Vincenzo Amalfi" in lbl for lbl in jan28_labels)


def test_jittered_monthly_schedule_detects_delay_and_projects_typical_day():
    raw = _csv_from_rows(
        [
            ("2025-01-05", "Slow Client GmbH", 250_000, "EUR"),
            ("2025-02-07", "Slow Client GmbH", 250_000, "EUR"),
            ("2025-03-06", "Slow Client GmbH", 250_000, "EUR"),
            ("2025-04-08", "Slow Client GmbH", 250_000, "EUR"),
        ]
    )
    txs, _ = parse_transactions(raw)
    analysis = analyze_statement_patterns(txs, date(2025, 5, 1))
    assert len(analysis["patterns"]) == 1
    p = analysis["patterns"][0]
    assert p["counterparty"] == "Slow Client GmbH"
    assert p["max_delay_days"] == 3
    assert p["avg_delay_days"] >= 1
    assert "drift" in p["regularity"].lower()

    window = [date(2025, 5, d) for d in range(1, 15)]
    est = estimate_transactions(txs, window)
    slow_est = [t for t in est if "Slow Client GmbH" in t.label]
    assert len(slow_est) == 1
    assert slow_est[0].amount_minor == 250_000
    assert slow_est[0].date in {date(2025, 5, 6), date(2025, 5, 7)}


def test_forecast_analysis_endpoint_full_year_demo_mode():
    client = TestClient(create_app("demo"))
    resp = client.post(
        "/api/forecast-analysis",
        data={"starting_balance_minor": "1500000", "start_date": "2026-01-01"},
        files={"file": ("amalfi-2025.csv", AMALFI_FULL.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["currency"] == "EUR"
    assert body["history_span_days"] == 365
    assert body["transactions_analyzed"] == 1125
    assert body["months_analyzed"] == 12
    assert body["closure_months"] == ["2025-06"]
    assert body["daily_volatility_minor"] > 0
    assert "+20%" in (body["trend_note"] or "")
    assert "2025-01" in (body["seasonality_note"] or "")
    assert "Fri" in (body["weekend_lift_note"] or "")
    assert body["model"] == "demo-deterministic"
    assert body["ai_error"] is None
    assert len(body["chart_drivers"]) >= 2
    assert len(body["ai_callouts"]) >= 3

    names = {p["counterparty"] for p in body["patterns"]}
    assert "Commerzbank Global Pay" in names
    assert "Main Street Real Estate GmbH" in names
    assert "Tax Office Frankfurt am Main" in names
    cwm = next(p for p in body["patterns"] if p["counterparty"] == "Central Wholesale Market")
    assert cwm["max_delay_days"] == 2


def test_forecast_analysis_endpoint_short_csv():
    client = TestClient(create_app("demo"))
    resp = client.post(
        "/api/forecast-analysis",
        data={"starting_balance_minor": "100000", "start_date": "2026-11-16"},
        files={"file": ("credit_peak_case.csv", CREDIT_PEAK.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["transactions_analyzed"] == 3
    assert "3 recorded transactions" in body["trend_summary"]
    assert any(d["kind"] == "low" and d["date"] == "2026-11-26" for d in body["chart_drivers"])


def test_forecast_analysis_live_mode_grounding_and_fallback(monkeypatch):
    monkeypatch.setenv("CFO_MODEL_URL", "https://primary.test/v1")
    monkeypatch.setenv("CFO_MODEL_NAME", "kernes-qwen-7b")
    monkeypatch.setenv("CFO_FALLBACK_MODEL_URL", "https://fallback.test/v1")
    monkeypatch.setenv("CFO_FALLBACK_MODEL_NAME", "kernes-qwen")

    calls: list[str] = []

    def fake_call_model(config, messages, *, schema):
        calls.append(config.name)
        if config.name == "kernes-qwen-7b":
            # Hallucinated figure triggers grounding rejection across primary attempts
            return json.dumps(
                {
                    "trend_summary": "Cash drops by EUR 999,999.00 on January 1.",
                    "ai_callouts": ["Fake EUR 999,999.00 warning", "Another note"],
                }
            )
        return json.dumps(
            {
                "trend_summary": (
                    "Full-year history shows +20% stronger recent inflows after the June closure, "
                    "with Main Street Real Estate GmbH (-EUR 3,800.00) driving the January 1 dip."
                ),
                "ai_callouts": [
                    "Recent 6-month inflows rose +20% after the 2025-06 closure.",
                    "Main Street Real Estate GmbH pulls EUR 3,800.00 on January 1.",
                    "Commerzbank Global Pay settles on time (±0d) every Mon, Tue, Fri.",
                ],
            }
        )

    monkeypatch.setattr("backend.forecast_analysis.call_model", fake_call_model)
    client = TestClient(create_app("live"))
    resp = client.post(
        "/api/forecast-analysis",
        data={"starting_balance_minor": "1500000", "start_date": "2026-01-01"},
        files={"file": ("amalfi-2025.csv", AMALFI_FULL.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["model"] == "kernes-qwen"
    assert body["ai_error"] is None
    assert "EUR 3,800.00" in body["trend_summary"]
    assert len(body["ai_callouts"]) == 3
    assert "kernes-qwen-7b" in calls and "kernes-qwen" in calls


def test_forecast_analysis_live_mode_degrades_gracefully_when_model_unconfigured(monkeypatch):
    monkeypatch.delenv("CFO_MODEL_URL", raising=False)
    monkeypatch.delenv("CFO_MODEL_NAME", raising=False)
    client = TestClient(create_app("live"))
    resp = client.post(
        "/api/forecast-analysis",
        data={"starting_balance_minor": "1500000", "start_date": "2026-01-01"},
        files={"file": ("amalfi-2025.csv", AMALFI_FULL.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["model"] == "deterministic-fallback"
    assert body["ai_error"] is not None
    assert body["history_span_days"] == 365
    assert len(body["patterns"]) >= 10

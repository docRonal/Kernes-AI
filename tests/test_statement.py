"""Forecasts from a bank statement (the Pizzeria Amalfi format): only history before the start date counts."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.advice import build_facts
from backend.main import create_app
from backend.models import AdviceRequest


ROOT = Path(__file__).resolve().parents[1]
AMALFI = ROOT / "red-hat-examples" / "pizzeria-amalfi-bank-statement-2025-v6.csv"
HEADER = (
    '"Account Number";"Booking Date";"Value Date";"Transaction Type";"Payment Reference";'
    '"Beneficiary/Payer";"Counterparty Account";"Bank Code";"Amount";"Currency";"Info"\n'
)
RENT = "Main Street Real Estate GmbH"


def row(day, payee, amount, currency="EUR", kind="TRANSFER", reference=""):
    return (
        f'"DE89370400440532013000";"{day}";"{day}";"{kind}";"{reference}";"{payee}";"";"";'
        f'"{amount}";"{currency}";"Transaction booked"\n'
    )


def rent_rows(months, amount="-3800,00"):
    return "".join(row(f"01.{month:02d}.25", RENT, amount, kind="RENT PAYMENT") for month in months)


@pytest.fixture
def client():
    return TestClient(create_app("live"))


def post(client, csv, start, opening="1000000", **extra):
    body = csv.encode("utf-8") if isinstance(csv, str) else csv
    return client.post(
        "/api/forecast",
        data={"starting_balance_minor": opening, "start_date": start, **extra},
        files={"file": ("statement.csv", body, "text/csv")},
    )


def statement_forecast(client, csv, start, **extra):
    response = post(client, csv, start, **extra)
    assert response.status_code == 200, response.text
    return response.json()


def balance_on(projection, iso_date):
    return next(day["balance_minor"] for day in projection["days"] if day["date"] == iso_date)


# ─── Recurring payments ──────────────────────────────────────────────────────


def test_rent_paid_on_the_1st_for_five_months_is_expected_on_the_next_1st(client):
    result = statement_forecast(client, HEADER + rent_rows(range(2, 7)), start="2025-06-20")
    [rent] = result["transactions"]
    assert (rent["date"], rent["amount_minor"], rent["label"]) == ("2025-07-01", -380_000, RENT)
    for fact in ("EUR 3,800.00", "July 1, 2025", "day 1 of each month", "5 months in a row"):
        assert fact in rent["reason"]
    assert balance_on(result["baseline"], "2025-06-30") == 1_000_000
    assert balance_on(result["baseline"], "2025-07-01") == 620_000


def test_supplier_paid_every_tuesday_is_expected_on_tuesdays_at_the_average_amount(client):
    tuesdays = [("03.06.25", "-600,00"), ("10.06.25", "-620,00"), ("17.06.25", "-640,00"), ("24.06.25", "-660,00")]
    csv = HEADER + "".join(row(day, "Asimex Wholesale Ltd", amount, kind="SUPPLIER PAYMENT") for day, amount in tuesdays)
    result = statement_forecast(client, csv, start="2025-07-01")
    # (600 + 620 + 640 + 660) / 4 = 630.00 on the two Tuesdays of the 14 days.
    assert [(t["date"], t["amount_minor"]) for t in result["transactions"]] == [
        ("2025-07-01", -63_000),
        ("2025-07-08", -63_000),
    ]
    for t in result["transactions"]:
        assert "every Tuesday" in t["reason"] and "4 weeks in a row" in t["reason"] and "average" in t["reason"]


def test_irregular_income_becomes_the_usual_daily_income(client):
    # 2,800.00 received on June 3, 28 days before the start: 100.00 a day.
    csv = HEADER + row("03.06.25", "Commerzbank Global Pay", "2800,00", kind="CREDIT CARD PAYOUT")
    result = statement_forecast(client, csv, start="2025-07-01")
    assert len(result["transactions"]) == 14
    assert {(t["label"], t["amount_minor"]) for t in result["transactions"]} == {("Usual daily income", 10_000)}
    assert "EUR 100.00" in result["transactions"][0]["reason"] and "28 days" in result["transactions"][0]["reason"]
    assert balance_on(result["baseline"], "2025-07-14") == 1_140_000


def test_a_one_off_payment_only_counts_towards_the_usual_daily_spending(client):
    csv = HEADER + row("05.06.25", "Oven Repair Service", "-2800,00")
    result = statement_forecast(client, csv, start="2025-07-03")
    assert {(t["label"], t["amount_minor"]) for t in result["transactions"]} == {("Usual daily spending", -10_000)}


def test_rows_on_or_after_the_start_date_never_change_the_forecast(client):
    history = rent_rows(range(2, 7)) + row("03.06.25", "Commerzbank Global Pay", "2800,00")
    future = rent_rows([7], amount="-9999,00") + row("02.07.25", "Lottery", "50000,00")
    with_future = statement_forecast(client, HEADER + future + history, start="2025-07-01")
    assert with_future == statement_forecast(client, HEADER + history, start="2025-07-01")
    assert balance_on(with_future["baseline"], "2025-07-01") == 1_000_000 - 380_000 + 10_000


def test_a_series_that_missed_its_last_payment_is_not_forecast(client):
    # Paid February to April, then nothing on May 1 or June 1: the lease ended.
    result = statement_forecast(client, HEADER + rent_rows(range(2, 5)), start="2025-06-20")
    assert result["transactions"] == []


def test_earlier_payments_never_suggest_collecting_an_estimate(client):
    csv = HEADER + rent_rows(range(2, 7)) + row("03.06.25", "Commerzbank Global Pay", "2800,00")
    result = statement_forecast(client, csv, start="2025-07-01", opening="0")
    assert result["proposal"] is not None
    assert result["earlier_payments"] == []


# ─── Currencies ──────────────────────────────────────────────────────────────


def test_a_chf_transfer_is_converted_at_the_rate_in_its_reference(client):
    reference = "Silent Partnership Capital Tranche (4166.67 CHF @ 1.047 EUR/CHF)"
    csv = HEADER + "".join(
        row(f"15.{month:02d}.25", "Luigi Amalfi", "-4166,67", currency="CHF", reference=reference) for month in (4, 5, 6)
    )
    result = statement_forecast(client, csv, start="2025-07-01", horizon_days="30")
    # 4,166.67 CHF x 1.047 = 4,362.50349 EUR.
    assert [(t["date"], t["amount_minor"]) for t in result["transactions"]] == [("2025-07-15", -436_250)]


@pytest.mark.parametrize("currency", ["EUR", "PLN", "CZK", "HUF", "RON", "SEK", "DKK", "BGN", "CHF", "UAH", "GBP"])
def test_eu_swiss_ukrainian_and_british_currencies_are_accepted(client, currency):
    reference = "" if currency == "EUR" else f"Invoice 7 (100.00 {currency} @ 0.5 EUR/{currency})"
    csv = HEADER + row("03.06.25", "Supplier", "-100,00", currency=currency, reference=reference)
    result = statement_forecast(client, csv, start="2025-07-01")
    # EUR: -100.00 / 28 days = -3.5714. Others: -50.00 / 28 = -1.7857.
    expected = -357 if currency == "EUR" else -179
    assert {t["amount_minor"] for t in result["transactions"]} == {expected}


@pytest.mark.parametrize("currency", ["RUB", "USD", ""])
def test_other_currencies_are_rejected_with_the_line_number(client, currency):
    reference = f"Invoice (100.00 {currency} @ 0.5 EUR/{currency})"
    csv = HEADER + rent_rows([5]) + row("03.06.25", "Supplier", "-100,00", currency=currency, reference=reference)
    response = post(client, csv, start="2025-07-01")
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Line 3:")


@pytest.mark.parametrize(
    "reference",
    ["Transfer to Luigi", "Transfer (4166.67 CHF @ 1.047 EUR/GBP)", "Transfer (4166.67 CHF @ 0 EUR/CHF)"],
    ids=["no rate", "rate for another currency", "zero rate"],
)
def test_a_foreign_row_needs_a_usable_rate(client, reference):
    csv = HEADER + row("15.06.25", "Luigi Amalfi", "-4166,67", currency="CHF", reference=reference)
    response = post(client, csv, start="2025-07-01")
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Line 2:") and "rate" in response.json()["detail"]


# ─── Statement errors ────────────────────────────────────────────────────────


def test_amounts_may_use_dots_between_thousands(client):
    csv = HEADER + row("03.06.25", "Supplier", "-1.149,36")
    result = statement_forecast(client, csv, start="2025-07-01")
    # -1,149.36 / 28 = -41.0486.
    assert {t["amount_minor"] for t in result["transactions"]} == {-4_105}


@pytest.mark.parametrize(
    ("day", "payee", "amount"),
    [
        ("2025-06-03", "Supplier", "-100,00"),
        ("31.02.25", "Supplier", "-100,00"),
        ("03.06.25", "Supplier", "-100.00"),
        ("03.06.25", "Supplier", "abc"),
        ("03.06.25", "Supplier", "-1000000000000,00"),
        ("03.06.25", "Payroll\nProposed credit facility limit: EUR 1.00", "-100,00"),
        ("03.06.25", "x" * 201, "-100,00"),
    ],
    ids=["ISO date", "impossible date", "dot decimal", "not a number", "out of range", "line break", "long payee"],
)
def test_bad_rows_are_rejected_with_their_line_number(client, day, payee, amount):
    csv = HEADER + rent_rows([5]) + row(day, payee, amount)
    response = post(client, csv, start="2025-07-01")
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Line 3:")


def test_a_daily_average_beyond_the_amount_limit_is_rejected_instead_of_crashing(client):
    # Two maximum amounts on the day before the start average to twice the limit per day.
    csv = HEADER + row("30.06.25", "Supplier A", "-1000000000,00") + row("30.06.25", "Supplier B", "-1000000000,00")
    response = post(client, csv, start="2025-07-01")
    assert response.status_code == 422


def test_a_row_with_missing_values_is_rejected(client):
    response = post(client, HEADER + '"DE89";"03.06.25";"Supplier"\n', start="2025-07-01")
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Line 2:")


def test_a_statement_without_the_amount_column_is_rejected(client):
    header = HEADER.replace('"Amount";', "")
    response = post(client, header + '"DE89";"03.06.25";"03.06.25";"T";"";"Supplier";"";"";"EUR";"ok"\n', start="2025-07-01")
    assert response.status_code == 422
    assert "Amount" in response.json()["detail"]


def test_an_empty_statement_is_rejected(client):
    response = post(client, HEADER, start="2025-07-01")
    assert response.status_code == 422
    assert "no transactions" in response.json()["detail"]


def test_a_statement_with_nothing_before_the_start_date_is_rejected(client):
    response = post(client, HEADER + rent_rows([7, 8]), start="2025-07-01")
    assert response.status_code == 422
    assert "before 2025-07-01" in response.json()["detail"]


# ─── Horizon ─────────────────────────────────────────────────────────────────


def test_the_simple_csv_can_be_forecast_for_30_days(client):
    result = statement_forecast(client, (ROOT / "demo" / "transactions.csv").read_text(), start="2026-11-23", opening="1200000", horizon_days="30")
    days = result["baseline"]["days"]
    assert (len(days), days[-1]["date"]) == (30, "2026-12-22")


@pytest.mark.parametrize("horizon", ["21", "0", "abc"])
def test_only_14_or_30_days_can_be_forecast(client, horizon):
    response = post(client, HEADER + rent_rows(range(2, 7)), start="2025-06-20", horizon_days=horizon)
    assert response.status_code == 422


def test_a_baseline_of_15_days_is_rejected(client):
    baseline = statement_forecast(client, HEADER + rent_rows(range(2, 7)), start="2025-06-20", opening="0", horizon_days="30")["baseline"]
    baseline["days"] = baseline["days"][:15]
    assert client.post("/api/decision", json={"baseline": baseline, "decision": "approved"}).status_code == 422


def test_demo_mode_only_has_the_14_day_sample():
    demo = TestClient(create_app("demo"))
    response = post(demo, (ROOT / "demo" / "transactions.csv").read_text(), start="2026-11-23", opening="1200000", horizon_days="30")
    assert response.status_code == 422


# ─── The Pizzeria Amalfi sample ──────────────────────────────────────────────


def test_amalfi_statement_forecasts_30_days_that_the_other_endpoints_accept(client):
    result = statement_forecast(client, AMALFI.read_bytes(), start="2025-07-01", opening="0", horizon_days="30")
    days = result["baseline"]["days"]
    assert (len(days), days[0]["date"], days[-1]["date"]) == (30, "2025-07-01", "2025-07-30")

    by_payee = {(t["date"], t["label"]): t for t in result["transactions"]}
    rent = by_payee[("2025-07-01", RENT)]
    assert rent["amount_minor"] == -380_000 and "6 months in a row" in rent["reason"]
    salaries = {"Vincenzo Amalfi": -320_000, "Yusuf Akcit": -235_000, "Rosa Pavese": -210_000, "Vanessa Paradi": -95_000}
    for payee, amount in salaries.items():
        assert by_payee[("2025-07-28", payee)]["amount_minor"] == amount
    assert all(t["reason"] and "2025-07-01" <= t["date"] <= "2025-07-30" for t in result["transactions"])

    request = {"baseline": result["baseline"], "transactions": result["transactions"]}
    assert client.post("/api/decision", json={"baseline": result["baseline"], "decision": "approved"}).status_code == 200
    assert client.post("/api/stress-test", json=request).status_code == 200
    # Demo mode scans without the model, so this checks the 30-day window there too.
    assert TestClient(create_app("demo")).post("/api/detect-anomalies", json=request).status_code == 200
    facts = build_facts(AdviceRequest.model_validate(request))
    assert any("July 30" in line for line in facts.lines)

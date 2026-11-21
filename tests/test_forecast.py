import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.forecast import project, propose, suggest_earlier_payments
from backend.main import create_app
from backend.models import Deficit, Projection, Transaction
from tests._csv_helpers import STARTER_AMALFI_CSV, amalfi_csv


DEMO = Path(__file__).resolve().parents[1] / "demo"
START = "2026-11-23"


@pytest.fixture
def client():
    return TestClient(create_app("live"))


def forecast(client, csv: bytes | str, opening="1200000", start=START, **extra):
    body = csv.encode("utf-8") if isinstance(csv, str) else csv
    return client.post(
        "/api/forecast",
        data={"starting_balance_minor": opening, "start_date": start, **extra},
        files={"file": ("statement.csv", body, "text/csv")},
    )


def balances(projection):
    return [day["balance_minor"] for day in projection["days"]]


def balance_on(projection, iso_date):
    return next(day["balance_minor"] for day in projection["days"] if day["date"] == iso_date)


def starter(client, **extra):
    response = forecast(client, STARTER_AMALFI_CSV, **extra)
    assert response.status_code == 200, response.text
    return response.json()


# ─── Baseline and proposal ───────────────────────────────────────────────────


def test_starter_sample_forecasts_14_days_and_proposes_the_gap(client):
    result = starter(client)
    days = result["baseline"]["days"]
    assert [day["date"] for day in days][:2] == ["2026-11-23", "2026-11-24"]
    assert days[-1]["date"] == "2026-12-06" and len(days) == 14
    # Opening balance applies before the first day's movements; Friday has payroll and rent together.
    assert balances(result["baseline"]) == [1_200_000] * 4 + [-500_000] * 3 + [400_000] * 7
    assert result["baseline"]["first_deficit"] == {"date": "2026-11-27", "shortfall_minor": 500_000}
    assert result["proposal"] == {
        "limit_minor": 500_000,
        "first_shortfall": {"date": "2026-11-27", "shortfall_minor": 500_000},
        "deepest_shortfall": {"date": "2026-11-27", "shortfall_minor": 500_000},
        "relevant_transaction_ids": ["TX-0001", "TX-0002", "TX-0003"],
    }
    assert result["scenario"] is None


def test_peak_shortfall_is_deeper_than_the_first(client):
    response = forecast(client, (DEMO / "credit_peak_case.csv").read_bytes(), opening="100000")
    assert response.status_code == 200, response.text
    proposal = response.json()["proposal"]
    assert proposal["first_shortfall"] == {"date": "2026-11-24", "shortfall_minor": 20_000}
    assert proposal["deepest_shortfall"] == {"date": "2026-11-26", "shortfall_minor": 70_000}
    assert proposal["limit_minor"] == 70_000


def test_no_shortfall_means_no_proposal(client):
    csv_bytes = amalfi_csv(("2026-11-25", "Client invoice", 50_000), ("2026-11-28", "Rent", -30_000))
    result = forecast(client, csv_bytes).json()
    assert result["baseline"]["first_deficit"] is None
    assert result["proposal"] is None
    assert result["earlier_payments"] == []


def test_tied_deepest_shortfall_uses_the_earliest_day(client):
    csv_bytes = amalfi_csv(
        ("2026-11-24", "Supplier", -150_000),
        ("2026-11-25", "Refund", 150_000),
        ("2026-11-28", "Tax", -150_000),
    )
    result = forecast(client, csv_bytes, opening="100000").json()
    assert result["proposal"]["deepest_shortfall"] == {"date": "2026-11-24", "shortfall_minor": 50_000}
    # Relevant rows run until the balance recovers from that deepest day.
    assert result["proposal"]["relevant_transaction_ids"] == ["TX-0001", "TX-0002"]


def test_same_day_movements_are_netted_before_checking_for_a_shortfall(client):
    csv_bytes = amalfi_csv(("2026-11-24", "Supplier", -150_000), ("2026-11-24", "Customer", 100_000))
    result = forecast(client, csv_bytes, opening="100000").json()
    assert balance_on(result["baseline"], "2026-11-24") == 50_000
    assert result["baseline"]["first_deficit"] is None


def test_negative_opening_balance_is_short_on_day_one(client):
    result = forecast(client, amalfi_csv(("2026-11-30", "Invoice", 90_000)), opening="-10000").json()
    assert result["baseline"]["first_deficit"] == {"date": "2026-11-23", "shortfall_minor": 10_000}
    assert result["proposal"]["limit_minor"] == 10_000


def test_rows_outside_the_window_are_returned_but_not_counted(client):
    csv_bytes = amalfi_csv(
        ("2026-11-20", "Paid last week", -999_999),
        ("2026-12-07", "After day 14", -999_999),
        ("2026-11-24", "Cash", 1_000),
    )
    result = forecast(client, csv_bytes, opening="0").json()
    assert [t["id"] for t in result["transactions"]] == ["TX-0001", "TX-0003", "TX-0002"]
    assert balances(result["baseline"]) == [0] + [1000] * 13
    assert result["proposal"] is None


def test_bom_quotes_header_order_and_blank_lines_are_accepted(client):
    csv_text = (
        "\ufeff"
        '"Beneficiary/Payer";"Amount";"Booking Date";"Currency";"Value Date";"Transaction Type";"Payment Reference";"Account Number"\n'
        '"Rent; office, GmbH";"-10,00";"24.11.26";"EUR";"24.11.26";"RENT";"Nov rent";"DE89370400440532013000"\n\n'
    )
    result = forecast(client, csv_text.encode("utf-8"), opening="0").json()
    assert result["transactions"] == [
        {"id": "TX-0001", "date": "2026-11-24", "amount_minor": -1000, "label": "Rent; office, GmbH"}
    ]


# ─── Instead of borrowing: ask for an invoice earlier ────────────────────────


def test_the_invoice_that_closes_the_gap_is_suggested_for_the_day_before(client):
    result = starter(client)
    assert result["earlier_payments"] == [{"transaction_id": "TX-0003", "pay_by": "2026-11-26", "limit_after_minor": 0}]
    # The suggestion is the what-if the user can run, and it removes the gap.
    option = result["earlier_payments"][0]
    moved = starter(client, move_transaction_id=option["transaction_id"], move_to_date=option["pay_by"])
    assert moved["scenario"]["first_deficit"] is None


def test_pay_by_never_falls_before_the_forecast_starts(client):
    peak = forecast(client, (DEMO / "credit_peak_case.csv").read_bytes(), opening="100000").json()
    assert peak["earlier_payments"] == [{"transaction_id": "TX-0003", "pay_by": "2026-11-23", "limit_after_minor": 0}]
    short_today = forecast(client, amalfi_csv(("2026-11-30", "Invoice", 90_000)), opening="-10000").json()
    assert short_today["earlier_payments"] == [{"transaction_id": "TX-0001", "pay_by": "2026-11-23", "limit_after_minor": 0}]


def test_a_gap_on_the_first_day_of_the_calendar_does_not_crash():
    # The day before 0001-01-01 doesn't exist, so the client is asked to pay on day one.
    start = date(1, 1, 1)
    txs = [Transaction(id="TX-0001", date=date(1, 1, 5), amount_minor=500, label="Invoice")]
    baseline = project(txs, -100, start)
    proposal = propose(baseline, txs)
    options = suggest_earlier_payments(baseline, txs, proposal)
    assert [(e.transaction_id, e.pay_by, e.limit_after_minor) for e in options] == [
        ("TX-0001", date(1, 1, 1), 0)
    ]


def test_options_are_ranked_by_the_credit_still_needed(client):
    csv_bytes = amalfi_csv(
        ("2026-11-25", "Rent", -500_000),
        ("2026-11-24", "Paid before the gap", 50_000),
        ("2026-11-27", "Small invoice", 100_000),
        ("2026-11-30", "Big invoice", 600_000),
    )
    result = forecast(client, csv_bytes, opening="0").json()
    assert result["proposal"]["limit_minor"] == 450_000
    assert result["earlier_payments"] == [
        {"transaction_id": "TX-0004", "pay_by": "2026-11-24", "limit_after_minor": 0},
        {"transaction_id": "TX-0003", "pay_by": "2026-11-24", "limit_after_minor": 350_000},
    ]


def test_a_payment_that_leaves_the_deepest_gap_untouched_is_not_suggested(client):
    csv_bytes = amalfi_csv(
        ("2026-11-24", "Supplier", -100_000),
        ("2026-11-26", "Client invoice", 100_000),
        ("2026-12-01", "Tax", -300_000),
    )
    result = forecast(client, csv_bytes, opening="0").json()
    assert result["proposal"]["deepest_shortfall"] == {"date": "2026-12-01", "shortfall_minor": 300_000}
    assert result["earlier_payments"] == []


# ─── What-if: move an incoming payment ───────────────────────────────────────


def test_moving_an_invoice_earlier_changes_only_the_scenario(client):
    plain = starter(client)
    moved = starter(client, move_transaction_id="TX-0003", move_to_date="2026-11-26")
    assert moved["baseline"] == plain["baseline"]
    assert moved["proposal"] == plain["proposal"]
    assert moved["earlier_payments"] == plain["earlier_payments"]  # suggestions come from the baseline
    assert moved["transactions"] == plain["transactions"]  # the original date stays
    assert balance_on(moved["baseline"], "2026-11-27") == -500_000
    assert balance_on(moved["scenario"], "2026-11-27") == 400_000
    assert moved["scenario"]["first_deficit"] is None


@pytest.mark.parametrize(
    "move, message",
    [
        ({"move_transaction_id": "TX-0003"}, "both"),
        ({"move_to_date": "2026-11-26"}, "both"),
        ({"move_transaction_id": "NOPE", "move_to_date": "2026-11-26"}, "no transaction"),
        ({"move_transaction_id": "TX-0001", "move_to_date": "2026-11-26"}, "not an incoming payment"),
        ({"move_transaction_id": "TX-0003", "move_to_date": "2026-11-22"}, "new date between"),
        ({"move_transaction_id": "TX-0003", "move_to_date": "2026-12-07"}, "new date between"),
    ],
)
def test_invalid_moves_are_rejected(client, move, message):
    response = forecast(client, STARTER_AMALFI_CSV, **move)
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_a_payment_outside_the_window_cannot_be_moved(client):
    csv_bytes = amalfi_csv(("2026-12-20", "Big invoice", 500_000))
    response = forecast(client, csv_bytes, move_transaction_id="TX-0001", move_to_date="2026-11-25")
    assert response.status_code == 422
    assert "outside the 14-day forecast" in response.json()["detail"]


# ─── Invalid CSV ─────────────────────────────────────────────────────────────

AMALFI_HEADER = (
    '"Account Number";"Booking Date";"Value Date";"Transaction Type";'
    '"Payment Reference";"Beneficiary/Payer";"Amount";"Currency"\n'
)


@pytest.mark.parametrize(
    "csv, message",
    [
        (b"\xff\xfe", "UTF-8"),
        (b"", "Unsupported CSV format"),
        (b"id,date,amount_minor,label\nA,2026-11-24,-100,Rent\n", "Unsupported CSV format"),
        (b"Account Number;Booking Date\nDE00;01.07.25\n", "missing required columns"),
        (AMALFI_HEADER, "no transactions"),
        (AMALFI_HEADER + '"DE00";"24.11.26";"24.11.26";"TEST";"Ref";"Vendor";"-10,00"\n', "values"),
        (AMALFI_HEADER + '"DE00";"31.02.25";"31.02.25";"TEST";"Ref";"Vendor";"-10,00";"EUR"\n', "not a real date"),
        (AMALFI_HEADER + '"DE00";"99.99.25";"99.99.25";"TEST";"Ref";"Vendor";"-10,00";"EUR"\n', "not a real date"),
        (AMALFI_HEADER + '"DE00";"2025/06/24";"2025/06/24";"TEST";"Ref";"Vendor";"-10,00";"EUR"\n', "bank date format"),
        (AMALFI_HEADER + '"DE00";"24.11.26";"24.11.26";"TEST";"Ref";"Vendor";"abc";"EUR"\n', "invalid amount format"),
        (AMALFI_HEADER + '"DE00";"24.11.26";"24.11.26";"TEST";"Ref";"Vendor";"999999999999999";"EUR"\n', "out of range"),
        (AMALFI_HEADER + '"DE00";"24.11.26";"24.11.26";"TEST";"Ref";"Vendor";"-10,00";""\n', "missing currency"),
        (AMALFI_HEADER + '"DE00";"24.11.26";"24.11.26";"TEST";"Ref";"Vendor";"-10,00";"XYZ"\n', "unsupported or unknown currency"),
        (
            AMALFI_HEADER
            + '"DE00";"24.11.26";"24.11.26";"TEST";"Ref";"Vendor";"100,00";"EUR"\n'
            + '"DE00";"25.11.26";"25.11.26";"TEST";"Ref";"Vendor";"-50,00";"PLN"\n',
            "mixed currency",
        ),
    ],
)
def test_invalid_csv_is_rejected_with_a_readable_message(client, csv, message):
    response = forecast(client, csv)
    assert response.status_code == 422
    assert message.lower() in response.json()["detail"].lower()


def test_oversized_upload_is_rejected(client):
    response = forecast(client, AMALFI_HEADER + "x" * 1_000_001)
    assert response.status_code == 422
    assert "larger than 1 MB" in response.json()["detail"]


def test_out_of_range_opening_balance_is_rejected(client):
    response = forecast(client, STARTER_AMALFI_CSV, opening=str(10**12))
    assert response.status_code == 422


# ─── Human decision (simulation) ─────────────────────────────────────────────


def decide(client, decision, baseline):
    return client.post("/api/decision", json={"decision": decision, "baseline": baseline})


def test_approving_covers_every_day_of_the_gap(client):
    baseline = starter(client)["baseline"]
    response = decide(client, "approved", baseline)
    assert response.status_code == 200, response.text
    outcome = response.json()
    assert outcome["simulated"] is True
    assert outcome["limit_minor"] == 500_000
    assert outcome["largest_uncovered"] is None
    assert [day["uncovered_minor"] for day in outcome["days"]] == [0] * 14
    assert [day["facility_used_minor"] for day in outcome["days"]] == [0] * 4 + [500_000] * 3 + [0] * 7
    assert [day["balance_minor"] for day in outcome["days"]] == balances(baseline)  # forecast stays intact


def test_rejecting_keeps_the_original_gap(client):
    baseline = starter(client)["baseline"]
    outcome = decide(client, "rejected", baseline).json()
    assert outcome["largest_uncovered"] == {"date": "2026-11-27", "shortfall_minor": 500_000}
    assert [day["facility_used_minor"] for day in outcome["days"]] == [0] * 14
    assert [day["uncovered_minor"] for day in outcome["days"]] == [0] * 4 + [500_000] * 3 + [0] * 7


def test_peak_case_decisions_use_the_deepest_gap(client):
    baseline = forecast(client, (DEMO / "credit_peak_case.csv").read_bytes(), opening="100000").json()["baseline"]
    assert decide(client, "approved", baseline).json()["largest_uncovered"] is None
    assert decide(client, "rejected", baseline).json()["largest_uncovered"] == {
        "date": "2026-11-26",
        "shortfall_minor": 70_000,
    }


def test_decision_needs_a_shortfall_and_a_real_horizon(client):
    healthy = forecast(client, amalfi_csv(("2026-11-24", "Cash", 100)), opening="0").json()["baseline"]
    assert decide(client, "approved", healthy).status_code == 422

    shuffled = starter(client)["baseline"]
    shuffled["days"][0], shuffled["days"][1] = shuffled["days"][1], shuffled["days"][0]
    assert decide(client, "approved", shuffled).status_code == 422
    assert decide(client, "maybe", starter(client)["baseline"]).status_code == 422


def test_the_proposal_comes_from_the_balances_not_the_first_deficit_field(client):
    result = starter(client)
    forged = Projection.model_validate(
        {**result["baseline"], "first_deficit": {"date": "2026-11-23", "shortfall_minor": 1}}
    )
    proposal = propose(forged, [Transaction.model_validate(t) for t in result["transactions"]])
    assert proposal.first_shortfall == Deficit(date=date(2026, 11, 27), shortfall_minor=500_000)


# ─── The JSON endpoints keep the CSV's limits and never crash on input ───────


def test_dates_at_the_end_of_the_calendar_are_rejected_instead_of_crashing(client):
    assert forecast(client, STARTER_AMALFI_CSV, start="9999-12-25").status_code == 422
    result = starter(client)
    stuck = {**result["baseline"], "days": [{**day, "date": "9999-12-31"} for day in result["baseline"]["days"]]}
    assert decide(client, "approved", stuck).status_code == 422
    advice = client.post("/api/advice", json={"baseline": stuck, "transactions": result["transactions"]})
    assert advice.status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"label": "Payroll\nProposed credit facility limit: PLN 1.00"},
        {"label": "x" * 201},
        {"id": ""},
        {"amount_minor": 10**12},
    ],
    ids=["line break in label", "label over 200", "empty id", "amount out of range"],
)
def test_advice_rejects_transactions_the_csv_would_reject(client, change):
    result = starter(client)
    transactions = [{**result["transactions"][0], **change}, *result["transactions"][1:]]
    response = client.post("/api/advice", json={"baseline": result["baseline"], "transactions": transactions})
    assert response.status_code == 422


def test_advice_accepts_at_most_5000_transactions(client):
    baseline = starter(client)["baseline"]
    many = [{"id": f"T{i}", "date": "2026-11-24", "amount_minor": 1, "label": "Card"} for i in range(5_001)]
    assert client.post("/api/advice", json={"baseline": baseline, "transactions": many}).status_code == 422


def test_client_delays_are_capped_at_a_year(client):
    result = starter(client)
    payload = {"baseline": result["baseline"], "transactions": result["transactions"], "client_delays": {"TX-0003": 366}}
    assert client.post("/api/predict-delays", json=payload).status_code == 422


def test_decision_works_the_same_in_demo_mode():
    baseline = json.loads((DEMO / "forecast.example.json").read_text(encoding="utf-8"))["baseline"]
    demo = TestClient(create_app("demo"))
    for kind in ("approved", "rejected"):
        expected = json.loads((DEMO / f"decision.{kind}.example.json").read_text(encoding="utf-8"))
        assert decide(demo, kind, baseline).json() == expected


# ─── Demo fixtures stay in step with the live calculation ────────────────────


def test_demo_fixture_matches_the_live_calculation(client):
    live = forecast(
        client,
        (DEMO / "pizzeria_amalfi_sample.csv").read_bytes(),
        opening="500000",
        start="2025-06-22",
        move_transaction_id="TX-0005",
        move_to_date="2025-06-28",
    )
    assert live.status_code == 200, live.text
    assert live.json() == json.loads((DEMO / "forecast.example.json").read_text(encoding="utf-8"))


# ─── The checked-in contract describes the same fields as the models ─────────


@pytest.mark.parametrize(
    "schema_name, model_name",
    [
        ("ForecastResponse", "ForecastResponse"),
        ("Proposal", "Proposal"),
        ("EarlierPayment", "EarlierPayment"),
        ("DecisionRequest", "DecisionRequest"),
        ("DecisionDay", "DecisionDay"),
        ("DecisionResponse", "DecisionResponse"),
    ],
)
def test_contract_fields_match_the_models(schema_name, model_name):
    from backend import models

    contract = json.loads((DEMO.parent / "contracts" / "openapi.json").read_text(encoding="utf-8"))
    schema = contract["components"]["schemas"][schema_name]
    model_schema = getattr(models, model_name).model_json_schema()
    assert set(schema["properties"]) == set(model_schema["properties"])
    assert set(schema["required"]) == set(model_schema["required"])


# ─── Server-side Pizzeria Amalfi / German MT940 bank CSV support ─────────────


@pytest.mark.parametrize("mode", ["demo", "live"])
def test_amalfi_semicolon_csv_forecasts_and_decisions_run_on_server(mode):
    app_client = TestClient(create_app(mode))
    csv_bytes = (DEMO / "pizzeria_amalfi_sample.csv").read_bytes()

    resp = forecast(app_client, csv_bytes, opening="500000", start="2025-06-22")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["baseline"]["first_deficit"] == {"date": "2025-06-28", "shortfall_minor": 625_000}
    assert body["proposal"]["deepest_shortfall"] == {"date": "2025-07-03", "shortfall_minor": 824_891}
    assert body["proposal"]["limit_minor"] == 824_891

    # CHF tranche (-4166.67 CHF @ 1.050 EUR/CHF) converts accurately with Decimal rounding.
    chf_tx = next(t for t in body["transactions"] if t["date"] == "2025-06-15")
    assert chf_tx["amount_minor"] == -437_500

    # Earlier payment move and /api/decision work server-side on Amalfi baseline too.
    moved = forecast(
        app_client,
        csv_bytes,
        opening="500000",
        start="2025-06-22",
        move_transaction_id="TX-0005",
        move_to_date="2025-06-28",
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["scenario"]["days"] != body["baseline"]["days"]

    approved = app_client.post("/api/decision", json={"decision": "approved", "baseline": body["baseline"]})
    rejected = app_client.post("/api/decision", json={"decision": "rejected", "baseline": body["baseline"]})
    assert approved.status_code == rejected.status_code == 200
    assert approved.json()["limit_minor"] == 824_891
    assert approved.json()["largest_uncovered"] is None
    assert rejected.json()["largest_uncovered"] == {"date": "2025-07-03", "shortfall_minor": 824_891}


def test_full_red_hat_amalfi_dataset_parses_cleanly(client):
    full_csv = DEMO.parent / "red-hat-examples" / "pizzeria-amalfi-bank-statement-2025-v6.csv"
    resp = forecast(client, full_csv.read_bytes(), opening="500000", start="2025-06-22")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["transactions"]) == 1125


@pytest.mark.parametrize(
    "bad_csv",
    [
        "Account Number;Booking Date\nDE00;01.07.25\n",
        (
            '"Account Number";"Booking Date";"Value Date";"Transaction Type";'
            '"Payment Reference";"Beneficiary/Payer";"Amount";"Currency"\n'
            '"DE00";"99.99.25";"99.99.25";"TEST";"Ref";"Vendor";"-10,00";"EUR"\n'
        ),
        (
            '"Account Number";"Booking Date";"Value Date";"Transaction Type";'
            '"Payment Reference";"Beneficiary/Payer";"Amount";"Currency"\n'
            '"DE00";"01.07.25";"01.07.25";"TEST";"Ref";"Vendor";"-10,00";"XYZ"\n'
        ),
    ],
    ids=["missing bank columns", "invalid bank date", "unsupported currency"],
)
def test_invalid_bank_csv_returns_422(client, bad_csv):
    resp = forecast(client, bad_csv, opening="500000", start="2025-06-22")
    assert resp.status_code == 422

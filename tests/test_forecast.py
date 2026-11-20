import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


DEMO = Path(__file__).resolve().parents[1] / "demo"
START = "2026-11-23"
HEADER = "id,date,amount_minor,label\n"


@pytest.fixture
def client():
    return TestClient(create_app("live"))


def forecast(client, csv: bytes | str, opening="1200000", start=START, **extra):
    body = csv.encode("utf-8") if isinstance(csv, str) else csv
    return client.post(
        "/api/forecast",
        data={"starting_balance_minor": opening, "start_date": start, **extra},
        files={"file": ("transactions.csv", body, "text/csv")},
    )


def balances(projection):
    return [day["balance_minor"] for day in projection["days"]]


def balance_on(projection, iso_date):
    return next(day["balance_minor"] for day in projection["days"] if day["date"] == iso_date)


def starter(client, **extra):
    response = forecast(client, (DEMO / "transactions.csv").read_bytes(), **extra)
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
        "relevant_transaction_ids": ["PAY-001", "PAY-002", "INV-001"],
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
    result = forecast(client, HEADER + "INV-9,2026-11-25,50000,Client invoice\nPAY-9,2026-11-28,-30000,Rent\n").json()
    assert result["baseline"]["first_deficit"] is None
    assert result["proposal"] is None


def test_tied_deepest_shortfall_uses_the_earliest_day(client):
    csv = HEADER + "A,2026-11-24,-150000,Supplier\nB,2026-11-25,150000,Refund\nC,2026-11-28,-150000,Tax\n"
    result = forecast(client, csv, opening="100000").json()
    assert result["proposal"]["deepest_shortfall"] == {"date": "2026-11-24", "shortfall_minor": 50_000}
    # Relevant rows run until the balance recovers from that deepest day.
    assert result["proposal"]["relevant_transaction_ids"] == ["A", "B"]


def test_same_day_movements_are_netted_before_checking_for_a_shortfall(client):
    csv = HEADER + "OUT,2026-11-24,-150000,Supplier\nIN,2026-11-24,100000,Customer\n"
    result = forecast(client, csv, opening="100000").json()
    assert balance_on(result["baseline"], "2026-11-24") == 50_000
    assert result["baseline"]["first_deficit"] is None


def test_negative_opening_balance_is_short_on_day_one(client):
    result = forecast(client, HEADER + "IN,2026-11-30,90000,Invoice\n", opening="-10000").json()
    assert result["baseline"]["first_deficit"] == {"date": "2026-11-23", "shortfall_minor": 10_000}
    assert result["proposal"]["limit_minor"] == 10_000


def test_rows_outside_the_window_are_returned_but_not_counted(client):
    csv = HEADER + "OLD,2026-11-20,-999999,Paid last week\nLATE,2026-12-07,-999999,After day 14\nIN,2026-11-24,1000,Cash\n"
    result = forecast(client, csv, opening="0").json()
    assert [t["id"] for t in result["transactions"]] == ["OLD", "LATE", "IN"]
    assert balances(result["baseline"]) == [0] + [1000] * 13
    assert result["proposal"] is None


def test_bom_quotes_header_order_and_blank_lines_are_accepted(client):
    csv = '﻿label,amount_minor,date,id\n"Rent, office",-1000,2026-11-24,R1\n\n'
    result = forecast(client, csv.encode("utf-8"), opening="0").json()
    assert result["transactions"] == [{"id": "R1", "date": "2026-11-24", "amount_minor": -1000, "label": "Rent, office"}]


# ─── What-if: move an incoming payment ───────────────────────────────────────


def test_moving_an_invoice_earlier_changes_only_the_scenario(client):
    plain = starter(client)
    moved = starter(client, move_transaction_id="INV-001", move_to_date="2026-11-26")
    assert moved["baseline"] == plain["baseline"]
    assert moved["proposal"] == plain["proposal"]
    assert moved["transactions"] == plain["transactions"]  # the original date stays
    assert balance_on(moved["baseline"], "2026-11-27") == -500_000
    assert balance_on(moved["scenario"], "2026-11-27") == 400_000
    assert moved["scenario"]["first_deficit"] is None


@pytest.mark.parametrize(
    "move, message",
    [
        ({"move_transaction_id": "INV-001"}, "both"),
        ({"move_to_date": "2026-11-26"}, "both"),
        ({"move_transaction_id": "NOPE", "move_to_date": "2026-11-26"}, "no transaction"),
        ({"move_transaction_id": "PAY-001", "move_to_date": "2026-11-26"}, "not an incoming payment"),
        ({"move_transaction_id": "INV-001", "move_to_date": "2026-11-22"}, "new date between"),
        ({"move_transaction_id": "INV-001", "move_to_date": "2026-12-07"}, "new date between"),
    ],
)
def test_invalid_moves_are_rejected(client, move, message):
    response = forecast(client, (DEMO / "transactions.csv").read_bytes(), **move)
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_a_payment_outside_the_window_cannot_be_moved(client):
    csv = HEADER + "INV-LATE,2026-12-20,500000,Big invoice\n"
    response = forecast(client, csv, move_transaction_id="INV-LATE", move_to_date="2026-11-25")
    assert response.status_code == 422
    assert "outside the 14-day forecast" in response.json()["detail"]


# ─── Invalid CSV ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "csv, message",
    [
        (b"\xff\xfe", "UTF-8"),
        (b"", "header"),
        (b"id,date,amount,label\n", "header"),
        (b"id,date,amount_minor,label,extra\n", "header"),
        (HEADER, "no transactions"),
        (HEADER + "A,2026-11-24,-100\n", "Line 2: expected 4 values"),
        (HEADER + ",2026-11-24,-100,Rent\n", "Line 2: the id is empty"),
        (HEADER + "A,24.11.2026,-100,Rent\n", "Line 2: the date must look like"),
        (HEADER + "A,2026-02-30,-100,Rent\n", "Line 2: 2026-02-30 is not a real date"),
        (HEADER + "A,2026-11-24,-1.50,Rent\n", "Line 2: amount_minor must be a whole number"),
        (HEADER + "A,2026-11-24,abc,Rent\n", "Line 2: amount_minor must be a whole number"),
        (HEADER + "A,2026-11-24,-100,\n", "Line 2: the label is empty"),
        (HEADER + "A,2026-11-24,-100,Rent\nA,2026-11-25,-100,Rent\n", "Line 3: the id A appears more than once"),
        (HEADER + "A,2026-11-24,999999999999999,Rent\n", "Line 2: the amount is out of range"),
    ],
)
def test_invalid_csv_is_rejected_with_a_readable_message(client, csv, message):
    response = forecast(client, csv)
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_oversized_upload_is_rejected(client):
    response = forecast(client, HEADER + "x" * 1_000_001)
    assert response.status_code == 422
    assert "larger than 1 MB" in response.json()["detail"]


def test_out_of_range_opening_balance_is_rejected(client):
    response = forecast(client, (DEMO / "transactions.csv").read_bytes(), opening=str(10**12))
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
    healthy = forecast(client, HEADER + "IN,2026-11-24,100,Cash\n", opening="0").json()["baseline"]
    assert decide(client, "approved", healthy).status_code == 422

    shuffled = starter(client)["baseline"]
    shuffled["days"][0], shuffled["days"][1] = shuffled["days"][1], shuffled["days"][0]
    assert decide(client, "approved", shuffled).status_code == 422
    assert decide(client, "maybe", starter(client)["baseline"]).status_code == 422


def test_decision_works_the_same_in_demo_mode():
    baseline = json.loads((DEMO / "forecast.example.json").read_text(encoding="utf-8"))["baseline"]
    demo = TestClient(create_app("demo"))
    for kind in ("approved", "rejected"):
        expected = json.loads((DEMO / f"decision.{kind}.example.json").read_text(encoding="utf-8"))
        assert decide(demo, kind, baseline).json() == expected


# ─── Demo fixtures stay in step with the live calculation ────────────────────


def test_demo_fixture_matches_the_live_calculation(client):
    live = starter(client, move_transaction_id="INV-001", move_to_date="2026-11-26")
    assert live == json.loads((DEMO / "forecast.example.json").read_text(encoding="utf-8"))


# ─── The checked-in contract describes the same fields as the models ─────────


@pytest.mark.parametrize(
    "schema_name, model_name",
    [
        ("ForecastResponse", "ForecastResponse"),
        ("Proposal", "Proposal"),
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

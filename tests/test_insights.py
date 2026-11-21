"""Stress test, payment optimization, credit check and the ask-CFO chat.

Every expected figure is worked out by hand from the CSV in the test; the comments
show the arithmetic in EUR.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


DEMO = Path(__file__).resolve().parents[1] / "demo"
HEADER = "id,date,amount_minor,label\n"
START = "2026-11-23"


@pytest.fixture
def client():
    return TestClient(create_app("live"))


class ScriptedModel:
    """Stands in for advice.call_model, the one function that talks to the model server."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, config, messages, *, schema):
        self.prompts.append(messages[-1]["content"])
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, str) else json.dumps(answer)


@pytest.fixture
def model(monkeypatch):
    def start(*answers):
        fake = ScriptedModel(answers)
        monkeypatch.setattr("backend.advice.call_model", fake)
        monkeypatch.setenv("CFO_MODEL_URL", "http://model.invalid/v1/chat/completions")
        monkeypatch.setenv("CFO_MODEL_NAME", "llama-test")
        monkeypatch.delenv("CFO_FALLBACK_MODEL_URL", raising=False)
        return fake

    return start


def facts(client, csv: str | bytes, opening: str) -> dict:
    """The forecast fields the browser sends back: baseline and transactions."""
    body = csv.encode() if isinstance(csv, str) else csv
    response = client.post(
        "/api/forecast",
        data={"starting_balance_minor": opening, "start_date": START},
        files={"file": ("transactions.csv", body, "text/csv")},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    return {"baseline": result["baseline"], "transactions": result["transactions"]}


def starter(client):
    # Opening 12,000; payroll 11,000 and rent 6,000 on Fri Nov 27; invoice 9,000 on Mon Nov 30.
    # Balances: 12,000 until Nov 26, -5,000 on Nov 27-29, 4,000 from Nov 30.
    return facts(client, (DEMO / "transactions.csv").read_bytes(), "1200000")


def peak(client):
    # Opening 1,000; equipment 1,200 on Nov 24; utility 500 on Nov 26; invoice 1,000 on Nov 29.
    # Balances: 1,000; -200 on Nov 24-25; -700 on Nov 26-28; 300 from Nov 29.
    return facts(client, (DEMO / "credit_peak_case.csv").read_bytes(), "100000")


# ─── Stress test ─────────────────────────────────────────────────────────────


def test_stress_test_finds_the_buffer_the_proposed_limit_lacks(client):
    # Late invoices keep the gap at 5,000; costs 10% higher give 12,000 - 12,100 - 6,600 = -6,700.
    response = client.post("/api/stress-test", json=starter(client))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["proposed_limit_minor"] == 500_000
    assert [(s["name"], s["deepest_shortfall"], s["extra_needed_minor"]) for s in body["scenarios"]] == [
        ("inflows_3_days_late", {"date": "2026-11-27", "shortfall_minor": 500_000}, 0),
        ("inflows_5_days_late", {"date": "2026-11-27", "shortfall_minor": 500_000}, 0),
        ("outflows_10_percent_higher", {"date": "2026-11-27", "shortfall_minor": 670_000}, 170_000),
        ("combined", {"date": "2026-11-27", "shortfall_minor": 670_000}, 170_000),
    ]
    assert body["buffer_minor"] == 170_000
    assert body["recommended_limit_minor"] == 670_000


def test_a_healthy_forecast_can_still_need_a_buffer_when_clients_pay_late(client):
    # Opening 1,000; +2,500 on Nov 24; -3,000 on Nov 25: the balance never goes below 500.
    # 3 days late, the 2,500 lands on Nov 27, so Nov 25-26 sit at -2,000.
    # Combined: 1,000 - 3,300 = -2,300 on Nov 25, the worst case.
    csv = HEADER + "IN,2026-11-24,250000,Client invoice\nOUT,2026-11-25,-300000,Supplier\n"
    body = client.post("/api/stress-test", json=facts(client, csv, "100000")).json()
    assert body["proposed_limit_minor"] == 0
    by_name = {s["name"]: s for s in body["scenarios"]}
    assert by_name["inflows_3_days_late"]["deepest_shortfall"] == {"date": "2026-11-25", "shortfall_minor": 200_000}
    assert by_name["outflows_10_percent_higher"]["deepest_shortfall"] is None
    assert body["buffer_minor"] == 230_000
    assert body["recommended_limit_minor"] == 230_000


def test_three_and_five_days_late_are_different_scenarios(client):
    # Opening 0; +1,000 on Nov 24; -1,000 on Nov 28. 3 days late the money is in on Nov 27,
    # just in time; 5 days late it lands on Nov 29, after the payment leaves: -1,000 on Nov 28.
    csv = HEADER + "IN,2026-11-24,100000,Client invoice\nOUT,2026-11-28,-100000,Supplier\n"
    body = client.post("/api/stress-test", json=facts(client, csv, "0")).json()
    by_name = {s["name"]: s["deepest_shortfall"] for s in body["scenarios"]}
    assert by_name["inflows_3_days_late"] is None
    assert by_name["inflows_5_days_late"] == {"date": "2026-11-28", "shortfall_minor": 100_000}


def test_ten_percent_more_is_rounded_half_up_to_the_grosz(client):
    # 10% of 1.05 EUR is 10.5 grosz, rounded up to 11: -105 becomes -116, so 100 - 116 = -16.
    body = client.post("/api/stress-test", json=facts(client, HEADER + "OUT,2026-11-24,-105,Card fee\n", "100")).json()
    costlier = next(s for s in body["scenarios"] if s["name"] == "outflows_10_percent_higher")
    assert costlier["deepest_shortfall"] == {"date": "2026-11-24", "shortfall_minor": 16}


# ─── Payment optimization ────────────────────────────────────────────────────


def test_rent_paid_later_and_the_invoice_collected_earlier_both_remove_the_gap(client):
    # Rent paid Mon Nov 30 instead of Fri Nov 27: 12,000 - 11,000 = 1,000 on Nov 27-29,
    # then 1,000 + 9,000 - 6,000 = 4,000. No gap, 3 days later.
    # Invoice by Thu Nov 26 instead of Mon Nov 30: no gap, 4 days earlier, so it ranks second.
    # Payroll is never suggested for a later date.
    response = client.post("/api/optimize-payments", json=starter(client))
    assert response.status_code == 200, response.text
    assert response.json() == {
        "proposed_limit_minor": 500_000,
        "actions": [
            {"kind": "pay_later", "transaction_id": "PAY-002", "due_date": "2026-11-27",
             "new_date": "2026-11-30", "limit_after_minor": 0, "saves_minor": 500_000},
            {"kind": "collect_earlier", "transaction_id": "INV-001", "due_date": "2026-11-30",
             "new_date": "2026-11-26", "limit_after_minor": 0, "saves_minor": 500_000},
        ],
    }


def test_each_payment_moves_only_as_far_as_it_needs_to(client):
    # Equipment 1,200 paid on Nov 29, when the invoice arrives: 5 days later, no gap
    # (paid any earlier it still meets the -700 dip).
    # Invoice by Nov 23 (the day before the first gap): 6 days earlier, no gap.
    # Utility 500 paid on Nov 29 instead of Nov 26: the -200 on Nov 24-25 stays, so 200 is still needed.
    body = client.post("/api/optimize-payments", json=peak(client)).json()
    assert [
        (a["kind"], a["transaction_id"], a["new_date"], a["limit_after_minor"], a["saves_minor"]) for a in body["actions"]
    ] == [
        ("pay_later", "PEAK-001", "2026-11-29", 0, 70_000),
        ("collect_earlier", "PEAK-003", "2026-11-23", 0, 70_000),
        ("pay_later", "PEAK-002", "2026-11-29", 20_000, 50_000),
    ]


def test_nothing_to_optimize_without_a_shortfall(client):
    healthy = facts(client, (DEMO / "no_shortfall_case.csv").read_bytes(), "1500000")
    assert client.post("/api/optimize-payments", json=healthy).json() == {"proposed_limit_minor": 0, "actions": []}


# ─── Credit check ────────────────────────────────────────────────────────────

# Opening 1,000; -2,000 on Nov 24; +3,000 on Nov 25; -1,500 on Nov 26.
# Balances: 1,000; -1,000 on Nov 24; 2,000 on Nov 25; 500 from Nov 26. Limit 1,000.
DELAY_CSV = HEADER + (
    "OUT,2026-11-24,-200000,Supplier\nIN,2026-11-25,300000,Client invoice\nOUT2,2026-11-26,-150000,Rent\n"
)


def points(body) -> dict:
    return {factor["name"]: factor["points"] for factor in body["factors"]}


def test_starter_scores_low_risk_but_depends_on_one_client(client):
    # Repaid on Nov 30 (0). Coverage 9,000 / 5,000 = 180%, under 200% (10). 3 days short (0).
    # Facility 5,000 / 17,000 going out = 29%, 25-50% (5). One invoice is 100% of the money in (15).
    response = client.post("/api/credit-check", json=starter(client))
    assert response.status_code == 200, response.text
    body = response.json()
    assert points(body) == {"repayment": 0, "coverage": 10, "duration": 0, "depth": 5, "concentration": 15, "delays": 0}
    assert (body["score"], body["risk"], body["limit_minor"]) == (70, "low", 500_000)


def test_peak_case_scores_medium(client):
    # Coverage 1,000 / 700 = 142% (10). 5 days short (10). 700 / 1,700 = 41% (5). One invoice (15).
    body = client.post("/api/credit-check", json=peak(client)).json()
    assert points(body) == {"repayment": 0, "coverage": 10, "duration": 10, "depth": 5, "concentration": 15, "delays": 0}
    assert (body["score"], body["risk"]) == (60, "medium")


def test_a_gap_that_never_closes_is_high_risk(client):
    # Opening 0 and 5,000 out on Nov 24: still -5,000 on Dec 6 (30), nothing comes in (25),
    # 13 days short (20), the facility is 100% of the money going out (15). 100 - 90 = 10.
    body = client.post("/api/credit-check", json=facts(client, HEADER + "OUT,2026-11-24,-500000,Supplier\n", "0")).json()
    assert points(body) == {"repayment": 30, "coverage": 25, "duration": 20, "depth": 15, "concentration": 0, "delays": 0}
    assert (body["score"], body["risk"]) == (10, "high")


@pytest.mark.parametrize("key", ["IN", "Client invoice"])
def test_clients_who_paid_late_before_lower_the_score(client, key):
    # Without delays: coverage 300% (0), 1 day short (0), 1,000 / 3,500 = 28% (5), one invoice (15): 80, low.
    # Paid 2 days late, the 3,000 lands on Nov 27: 1,000 - 2,000 - 1,500 = -2,500 on Nov 26 (15): 65, medium.
    payload = facts(client, DELAY_CSV, "100000")
    assert client.post("/api/credit-check", json=payload).json()["score"] == 80
    body = client.post("/api/credit-check", json={**payload, "client_delays": {key: 2}}).json()
    assert points(body)["delays"] == 15
    assert "EUR 2,500.00" in next(f["reason"] for f in body["factors"] if f["name"] == "delays")
    assert (body["score"], body["risk"]) == (65, "medium")


def test_no_credit_check_without_a_shortfall(client):
    healthy = facts(client, (DEMO / "no_shortfall_case.csv").read_bytes(), "1500000")
    assert client.post("/api/credit-check", json=healthy).status_code == 422


GOOD_VERDICT = {
    "explanation": (
        "The EUR 5,000.00 facility scores 70 out of 100, which is low risk. It is repaid when the "
        "Client invoice (INV-001) for EUR 9,000.00 arrives, but that single client brings all the money in."
    )
}


def test_the_model_explains_the_calculated_verdict(client, model):
    fake = model(GOOD_VERDICT)
    body = client.post("/api/credit-check", json=starter(client)).json()
    assert body["explanation"] == GOOD_VERDICT["explanation"]
    assert (body["model"], body["explanation_error"]) == ("llama-test", None)
    assert body["latency_ms"] >= 0
    for fact in ("70 out of 100", "Risk level: low", "EUR 5,000.00", "EUR 9,000.00", "180%"):
        assert fact in fake.prompts[0]


def test_an_answer_with_the_wrong_risk_level_is_retried(client, model):
    wrong = {"explanation": "The EUR 5,000.00 facility is high risk."}
    fake = model(wrong, GOOD_VERDICT)
    body = client.post("/api/credit-check", json=starter(client)).json()
    assert body["explanation"] == GOOD_VERDICT["explanation"]
    assert len(fake.prompts) == 2


def test_an_invented_amount_never_reaches_the_owner_but_the_score_does(client, model):
    invented = {"explanation": "Low risk: the facility of EUR 7,777.00 is safe."}
    model(invented, invented)
    response = client.post("/api/credit-check", json=starter(client))
    assert response.status_code == 200
    body = response.json()
    assert body["explanation"] is None
    assert "EUR 7,777.00" in body["explanation_error"]
    assert (body["score"], body["risk"]) == (70, "low")


def test_the_score_survives_a_missing_model(client, monkeypatch):
    monkeypatch.delenv("CFO_MODEL_URL", raising=False)
    body = client.post("/api/credit-check", json=starter(client)).json()
    assert (body["score"], body["explanation"]) == (70, None)
    assert "isn't configured" in body["explanation_error"]


def test_demo_mode_scores_without_calling_a_model():
    demo = TestClient(create_app("demo"))
    payload = json.loads((DEMO / "forecast.example.json").read_text(encoding="utf-8"))
    body = demo.post("/api/credit-check", json={"baseline": payload["baseline"], "transactions": payload["transactions"]}).json()
    assert (body["score"], body["explanation"]) == (70, None)
    assert "live mode" in body["explanation_error"]


# ─── Ask the CFO ─────────────────────────────────────────────────────────────

def ask(client, payload, question):
    return client.post("/api/ask-cfo", json={**payload, "question": question})


def test_a_question_is_answered_from_the_forecast_figures(client, model):
    # No number in the question, so there is no what-if to read: one model call.
    answer = {"answer": "Friday, November 27 is the riskiest day, with a balance of -EUR 5,000.00."}
    fake = model(answer)
    response = ask(client, starter(client), "What is the riskiest day?")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["answer"], body["what_if"], body["model"]) == (answer["answer"], None, "llama-test")
    assert len(fake.prompts) == 1
    for fact in ("Friday, November 27: -EUR 5,000.00", "Proposed credit facility: EUR 5,000.00", "What is the riskiest day?"):
        assert fact in fake.prompts[0]


def test_a_bigger_payment_is_recalculated_before_the_model_answers(client, model):
    # Payroll 11,000 + 2,000 = 13,000: Friday becomes 12,000 - 13,000 - 6,000 = -7,000,
    # which is 2,000 more than the proposed 5,000.
    answer = {"answer": "No: with payroll at EUR 13,000.00 you would need EUR 7,000.00, EUR 2,000.00 more than proposed."}
    fake = model({"transaction_id": "PAY-001", "amount_change_pln": 2000, "days_later": 0}, answer)
    body = ask(client, starter(client), "Will we have enough money if salaries grow by 2,000 EUR?").json()
    assert body["what_if"] == {
        "transaction_id": "PAY-001",
        "new_amount_minor": -1_300_000,
        "new_date": "2026-11-27",
        "deepest_shortfall": {"date": "2026-11-27", "shortfall_minor": 700_000},
    }
    assert body["answer"] == answer["answer"]
    assert "a facility of EUR 7,000.00 would be needed" in fake.prompts[1]
    assert "EUR 2,000.00 more than the proposed facility" in fake.prompts[1]


def test_a_late_invoice_is_moved_before_the_model_answers(client, model):
    # The invoice 3 days late: Mon Nov 30 becomes Thu Dec 3, so the -5,000 lasts until Dec 2.
    model({"transaction_id": "INV-001", "amount_change_pln": 0, "days_later": 3}, {"answer": "The gap stays at EUR 5,000.00."})
    body = ask(client, starter(client), "What if the client pays 3 days late?").json()
    assert body["what_if"] == {
        "transaction_id": "INV-001",
        "new_amount_minor": 900_000,
        "new_date": "2026-12-03",
        "deepest_shortfall": {"date": "2026-11-27", "shortfall_minor": 500_000},
    }


def test_money_moved_before_the_forecast_counts_from_the_first_day(client, model):
    # The invoice 10 days early lands on Fri Nov 20, before the forecast: it counts from Mon Nov 23,
    # so Friday is 12,000 + 9,000 - 17,000 = 4,000 and there is no gap.
    model({"transaction_id": "INV-001", "amount_change_pln": 0, "days_later": -10}, {"answer": "There would be no gap."})
    body = ask(client, starter(client), "What if the client pays 10 days early?").json()
    assert body["what_if"]["new_date"] == "2026-11-20"
    assert body["what_if"]["deepest_shortfall"] is None


def test_the_question_decides_which_way_a_date_moves(client, model):
    # The real 3B model read "3 days late" as -3 days and -300 EUR. "late" makes it +3 days and
    # 300 isn't in the question, so: PEAK-003 on Wed Dec 2, -700 from Nov 26 until then.
    model({"transaction_id": "PEAK-003", "amount_change_pln": -300, "days_later": -3}, {"answer": "You would need EUR 700.00."})
    body = ask(client, peak(client), "What if the client invoice is paid 3 days late?").json()
    assert body["what_if"] == {
        "transaction_id": "PEAK-003",
        "new_amount_minor": 100_000,
        "new_date": "2026-12-02",
        "deepest_shortfall": {"date": "2026-11-26", "shortfall_minor": 70_000},
    }


def test_a_number_the_owner_did_not_write_is_dropped(client, model):
    # The real model also moved payroll 2 days earlier; only the 2,000 comes from the question.
    model({"transaction_id": "PAY-001", "amount_change_pln": 2000, "days_later": -2}, {"answer": "You would need EUR 7,000.00."})
    body = ask(client, starter(client), "Will we have enough money if payroll grows by 2,000 EUR?").json()
    assert (body["what_if"]["new_amount_minor"], body["what_if"]["new_date"]) == (-1_300_000, "2026-11-27")


def test_a_percentage_is_not_read_as_an_amount(client, model):
    fake = model({"answer": "The stress test covers costs 10% higher."})
    body = ask(client, starter(client), "What if rent is 10% higher?").json()
    assert body["what_if"] is None
    assert len(fake.prompts) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"transaction_id": "NOPE", "amount_change_pln": 100, "days_later": 0},
        {"transaction_id": "PAY-001", "amount_change_pln": 0, "days_later": 0},
        {"transaction_id": "PAY-001", "amount_change_pln": 1e30, "days_later": 0},
        "not json",
    ],
    ids=["unknown id", "no change", "huge amount", "not json"],
)
def test_an_unusable_what_if_is_ignored(client, model, change):
    model(change, {"answer": "Friday, November 27 is the riskiest day."})
    body = ask(client, starter(client), "What if a payment changes by 100 EUR?").json()
    assert body["what_if"] is None
    assert body["answer"] == "Friday, November 27 is the riskiest day."


def test_an_answer_with_an_invented_amount_is_refused(client, model):
    invented = {"answer": "You need EUR 1,234.00."}
    model(invented, invented)
    response = ask(client, starter(client), "How much do I need?")
    assert response.status_code == 503
    assert "EUR 1,234.00" in response.json()["detail"]


def test_the_question_must_be_real_text(client):
    payload = starter(client)
    assert ask(client, payload, "   ").status_code == 422
    assert ask(client, payload, "x" * 501).status_code == 422


def test_demo_mode_has_no_consultant():
    demo = TestClient(create_app("demo"))
    payload = json.loads((DEMO / "forecast.example.json").read_text(encoding="utf-8"))
    question = {"baseline": payload["baseline"], "transactions": payload["transactions"], "question": "Hi?"}
    assert demo.post("/api/ask-cfo", json=question).status_code == 503

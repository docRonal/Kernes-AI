import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.forecast import classify_transaction
from backend.main import create_app


DEMO = Path(__file__).resolve().parents[1] / "demo"


class FakeModel:
    """Tiny local OpenAI-compatible server returning scripted JSON payloads."""

    def __init__(self, answers, status=200):
        self.answers = list(answers)
        self.status = status
        self.requests: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                fake.requests.append(json.loads(self.rfile.read(length)))
                answer = fake.answers.pop(0) if len(fake.answers) > 1 else fake.answers[0]
                content = answer if isinstance(answer, str) else json.dumps(answer)
                body = json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]}).encode()
                self.send_response(fake.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1/chat/completions"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def live(monkeypatch):
    models: list[FakeModel] = []

    def start(answers, status=200):
        model = FakeModel(answers, status)
        models.append(model)
        monkeypatch.setenv("CFO_MODEL_URL", model.url)
        monkeypatch.setenv("CFO_MODEL_NAME", "kernes-qwen-7b")
        monkeypatch.setenv("CFO_MODEL_TIMEOUT", "5")
        monkeypatch.delenv("CFO_FALLBACK_MODEL_URL", raising=False)
        monkeypatch.delenv("CFO_FALLBACK_MODEL_NAME", raising=False)
        return TestClient(create_app("live")), model

    yield start
    for model in models:
        model.close()


def _forecast_json(csv_path: Path, opening: str, start: str) -> dict:
    client = TestClient(create_app("demo"))
    resp = client.post(
        "/api/forecast",
        data={"starting_balance_minor": opening, "start_date": start},
        files={"file": (csv_path.name, csv_path.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_amalfi_and_credit_peak_transactions_are_classified_safely():
    amalfi = _forecast_json(DEMO / "pizzeria_amalfi_sample.csv", "500000", "2025-06-22")
    by_label: dict[str, list[dict]] = {}
    for tx in amalfi["transactions"]:
        by_label.setdefault(tx["label"], []).append(tx)

    assert by_label["Pizzeria Amalfi Customers (Debit)"][0]["category"] == "retail_card"
    assert by_label["Pizzeria Amalfi Customers (Debit)"][0]["actionability"] == "retail_non_contactable"

    assert by_label["Commerzbank Global Pay"][0]["category"] == "card_acquirer"
    assert by_label["Commerzbank Global Pay"][0]["actionability"] == "retail_non_contactable"

    assert by_label["Central Wholesale Market"][0]["category"] == "retail_card"
    assert by_label["Central Wholesale Market"][0]["actionability"] == "retail_non_contactable"

    for mandatory_party in (
        "Techniker Krankenkasse Social Health Fund",
        "Tax Office Frankfurt am Main",
    ):
        assert by_label[mandatory_party][0]["category"] == "tax_social"
        assert by_label[mandatory_party][0]["actionability"] == "fixed_mandatory"

    assert by_label["City Energy & Utilities AG"][0]["category"] == "utility"
    assert by_label["City Energy & Utilities AG"][0]["actionability"] == "fixed_mandatory"

    for staff in ("Yusuf Akcit", "Rosa Pavese", "Vanessa Paradi"):
        assert by_label[staff][0]["category"] == "staff_payroll"
        assert by_label[staff][0]["actionability"] == "fixed_mandatory"

    assert by_label["Vincenzo Amalfi"][0]["category"] == "owner_draw"
    assert by_label["Vincenzo Amalfi"][0]["actionability"] == "owner_draw_flexible"

    for supplier in ("Asimex Wholesale Ltd", "Fattoria La Vino GmbH"):
        assert by_label[supplier][0]["category"] == "b2b_supplier"
        assert by_label[supplier][0]["actionability"] == "email_defer_supplier"

    assert by_label["Main Street Real Estate GmbH"][0]["category"] == "rent"
    assert by_label["Main Street Real Estate GmbH"][0]["actionability"] == "email_defer_supplier"

    peak = _forecast_json(DEMO / "credit_peak_case.csv", "100000", "2026-11-23")
    peak_map = {t["label"]: t for t in peak["transactions"]}
    assert (peak_map["Equipment payment"]["category"], peak_map["Equipment payment"]["actionability"]) == (
        "b2b_supplier",
        "email_defer_supplier",
    )
    assert (peak_map["Utility bill"]["category"], peak_map["Utility bill"]["actionability"]) == (
        "utility",
        "fixed_mandatory",
    )
    assert (peak_map["Client invoice"]["category"], peak_map["Client invoice"]["actionability"]) == (
        "b2b_client",
        "email_collect_early",
    )
    assert classify_transaction("CARD SETTLEMENT (DEBIT)", "Walk-in Customers", "POS", 45000) == (
        "retail_card",
        "retail_non_contactable",
    )


def test_action_plan_survival_mode_on_amalfi_filters_out_non_actionable_items(live):
    fc = _forecast_json(DEMO / "pizzeria_amalfi_sample.csv", "500000", "2025-06-22")
    payload = {
        "baseline": fc["baseline"],
        "transactions": fc["transactions"],
        "currency": "EUR",
        "profile": {"business_type": "Pizzeria / Restaurant", "goal": "Avoid running out of cash"},
    }

    demo_client = TestClient(create_app("demo"))
    demo_resp = demo_client.post("/api/action-plan", json=payload)
    assert demo_resp.status_code == 200, demo_resp.text
    demo_data = demo_resp.json()
    assert demo_data["mode"] == "survival"
    assert demo_data["model"] == "demo-deterministic"
    assert 1 <= len(demo_data["steps"]) <= 4

    email_steps = [s for s in demo_data["steps"] if s["email_draft"]]
    assert len(email_steps) == 1
    assert email_steps[0]["email_kind"] == "defer_supplier"
    assert email_steps[0]["counterparty"] == "Main Street Real Estate GmbH"
    assert "Main Street Real Estate GmbH" in email_steps[0]["email_draft"]

    counterparties = {s["counterparty"] for s in demo_data["steps"] if s["counterparty"]}
    assert "Vincenzo Amalfi" in counterparties
    for forbidden in ("Pizzeria Amalfi Customers (Debit)", "Commerzbank Global Pay", "Techniker Krankenkasse Social Health Fund", "Yusuf Akcit", "Rosa Pavese", "Vanessa Paradi"):
        assert forbidden not in counterparties

    credit_step = next(s for s in demo_data["steps"] if s["action_kind"] == "credit_facility")
    assert credit_step["impact_minor"] == 824_891
    assert credit_step["autonomy_level"] == "requires_approval"

    live_answer = {
        "headline": "Close the EUR 8,248.91 dip without touching staff pay",
        "summary": (
            "Your pizzeria cash balance first dips by EUR 6,250.00 on Saturday, June 28 and hits -EUR 8,248.91 on "
            "Thursday, July 3. Delay Vincenzo Amalfi's draw and ask Main Street Real Estate GmbH for 3 days, or "
            "cover up to EUR 8,248.91 with a simulated credit line."
        ),
        "email_draft": (
            "Hello,\n\nRegarding Pizzeria Commercial Space Rent 07/2025 for EUR 3,800.00, could we move payment "
            "from Tuesday, July 1 to Friday, July 4?\n\nKind regards,\nThe finance team"
        ),
    }
    live_client, fake = live([live_answer])
    live_resp = live_client.post("/api/action-plan", json=payload)
    assert live_resp.status_code == 200, live_resp.text
    live_data = live_resp.json()
    assert live_data["headline"] == live_answer["headline"]
    assert live_data["model"] == "kernes-qwen-7b"
    assert "Pizzeria / Restaurant" in fake.requests[0]["messages"][1]["content"]


def test_action_plan_collect_early_retries_fallback_and_strips_off_limits(live, monkeypatch):
    fc = _forecast_json(DEMO / "credit_peak_case.csv", "100000", "2026-11-23")
    payload = {
        "baseline": fc["baseline"],
        "transactions": fc["transactions"],
        "currency": "EUR",
        "profile": {"business_type": "Local coffee shop", "goal": "Get paid faster by clients"},
    }

    bad_hallucinated = {
        "headline": "Borrow EUR 9,999.00 immediately",
        "summary": "Your gap is EUR 9,999.00 on November 26.",
        "email_draft": "Hello, please pay early.",
    }
    good_fallback = {
        "headline": "Ask client to pay EUR 1,000.00 early to clear the EUR 700.00 dip",
        "summary": (
            "Cash dips by EUR 200.00 on Tuesday, November 24 and reaches -EUR 700.00 on Thursday, November 26. "
            "Collecting Client invoice (TX-0003) by Monday, November 23 closes the gap."
        ),
        "email_draft": (
            "Hello,\n\nCould you settle Client invoice (TX-0003) for EUR 1,000.00 by Monday, November 23 instead of "
            "Sunday, November 29? This avoids any shortfall or credit facility fees.\n\nKind regards,\nThe finance team"
        ),
    }

    live_client, primary = live([bad_hallucinated, bad_hallucinated])
    fallback = FakeModel([good_fallback])
    try:
        monkeypatch.setenv("CFO_FALLBACK_MODEL_URL", fallback.url)
        monkeypatch.setenv("CFO_FALLBACK_MODEL_NAME", "kernes-qwen")
        resp = live_client.post("/api/action-plan", json=payload)
    finally:
        fallback.close()

    assert resp.status_code == 200, resp.text
    assert len(primary.requests) == 2
    assert len(fallback.requests) == 1
    body = resp.json()
    assert body["model"] == "kernes-qwen"
    assert body["mode"] == "survival"
    email_step = next(s for s in body["steps"] if s["email_kind"] == "collect_early")
    assert email_step["counterparty"] == "Client invoice"
    assert "EUR 1,000.00" in email_step["email_draft"]
    assert "shortfall" not in email_step["email_draft"].lower()
    assert "credit facility" not in email_step["email_draft"].lower()
    assert "fees" not in email_step["email_draft"].lower()


def test_action_plan_growth_mode_and_pln_currency():
    healthy = _forecast_json(DEMO / "no_shortfall_case.csv", "1500000", "2026-11-23")
    demo_client = TestClient(create_app("demo"))
    growth_resp = demo_client.post(
        "/api/action-plan",
        json={
            "baseline": healthy["baseline"],
            "transactions": healthy["transactions"],
            "currency": "EUR",
            "profile": {"business_type": "Pizzeria", "goal": "Buy a new pizza oven"},
        },
    )
    assert growth_resp.status_code == 200, growth_resp.text
    growth = growth_resp.json()
    assert growth["mode"] == "growth"
    assert all(s["email_draft"] is None for s in growth["steps"])
    budget_step = next(s for s in growth["steps"] if "budget" in s["title"].lower() or "growth" in s["title"].lower())
    # With late inflows and higher expenses, the projected minimum is EUR 1,800.
    assert budget_step["impact_minor"] == 180_000

    pln_fc = _forecast_json(DEMO / "stress_cases" / "amalfi_poland_branch_pln.csv", "1000000", "2025-06-22")
    pln_resp = demo_client.post(
        "/api/action-plan",
        json={
            "baseline": pln_fc["baseline"],
            "transactions": pln_fc["transactions"],
            "currency": "PLN",
        },
    )
    assert pln_resp.status_code == 200, pln_resp.text
    pln_data = pln_resp.json()
    assert "PLN " in pln_data["headline"]
    assert "EUR" not in pln_data["headline"]
    assert "EUR" not in pln_data["summary"]
    email_step = next(s for s in pln_data["steps"] if s["email_draft"])
    assert "PLN " in email_step["email_draft"]
    assert "EUR" not in email_step["email_draft"]


def test_action_plan_backward_compat_and_live_503_when_model_missing(live, monkeypatch):
    peak = _forecast_json(DEMO / "credit_peak_case.csv", "100000", "2026-11-23")
    minimal_transactions = [
        {"id": t["id"], "date": t["date"], "amount_minor": t["amount_minor"], "label": t["label"]}
        for t in peak["transactions"]
    ]
    payload = {"baseline": peak["baseline"], "transactions": minimal_transactions, "currency": "EUR"}

    demo_client = TestClient(create_app("demo"))
    assert demo_client.post("/api/action-plan", json=payload).status_code == 200

    live_client, _primary = live([{"headline": "x", "summary": "x"}], status=500)
    fallback = FakeModel([{"headline": "x", "summary": "x"}], status=500)
    try:
        monkeypatch.setenv("CFO_FALLBACK_MODEL_URL", fallback.url)
        monkeypatch.setenv("CFO_FALLBACK_MODEL_NAME", "kernes-qwen")
        both_failed = live_client.post("/api/action-plan", json=payload)
        assert both_failed.status_code == 503
        assert "unavailable" in both_failed.json()["detail"].lower()
    finally:
        fallback.close()

    monkeypatch.delenv("CFO_MODEL_URL", raising=False)
    monkeypatch.delenv("CFO_MODEL_NAME", raising=False)
    unconfigured_client = TestClient(create_app("live"))
    err = unconfigured_client.post("/api/action-plan", json=payload)
    assert err.status_code == 503
    assert "unavailable" in err.json()["detail"].lower()


def test_action_plan_uses_grounded_ai_suggested_questions_and_filters_hallucinations(live):
    peak = _forecast_json(DEMO / "credit_peak_case.csv", "100000", "2026-11-23")
    payload = {
        "baseline": peak["baseline"],
        "transactions": peak["transactions"],
        "currency": "EUR",
        "profile": {"business_type": "Bakery", "goal": "Smooth out supplier bills"},
    }
    live_answer = {
        "headline": "Collect EUR 1,000.00 early to clear the EUR 700.00 dip",
        "summary": (
            "Cash dips by EUR 200.00 on Tuesday, November 24 and reaches -EUR 700.00 on Thursday, November 26. "
            "Ask Client invoice to settle early."
        ),
        "email_draft": "",
        "suggested_questions": [
            "What if Equipment payment is delayed by 4 days?",
            "What if Utility bill jumps by EUR 9,999.00?",  # hallucinated amount -> must be filtered out
            "How much cash buffer covers Thursday, November 26?",
        ],
    }
    live_client, _fake = live([live_answer])
    resp = live_client.post("/api/action-plan", json=payload)
    assert resp.status_code == 200, resp.text
    questions = resp.json()["suggested_questions"]
    assert questions == [
        "What if Equipment payment is delayed by 4 days?",
        "How much cash buffer covers Thursday, November 26?",
    ]

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.advice import cited_amounts
from backend.main import create_app


DEMO = Path(__file__).resolve().parents[1] / "demo"
BASE_INPUT = {"starting_balance_minor": "1200000", "start_date": "2026-11-23"}

GOOD = {
    "explanation": (
        "Your balance drops to -EUR 5,000.00 on Friday, November 27, when Payroll (PAY-001) and Office rent "
        "(PAY-002) go out before the Client invoice (INV-001) arrives. A credit facility of EUR 5,000.00 covers it."
    ),
    "email_draft": "Hello, could you pay INV-001 for EUR 9,000.00 by Thursday, November 26? The finance team",
}
WRONG_FIGURE = {**GOOD, "explanation": "You are EUR 5,500.00 short on Friday. A facility of EUR 5,000.00 covers it."}
NO_LIMIT = {**GOOD, "explanation": "Payroll and rent leave before the client pays, so the balance dips on Friday."}


class FakeModel:
    """A tiny OpenAI-compatible chat completions server with scripted answers."""

    def __init__(self, answers, status=200):
        self.answers = list(answers)
        self.status = status
        self.requests: list[dict] = []
        self.headers: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                fake.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                fake.headers.append(dict(self.headers))
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

    def start(answers, status=200, token=None):
        model = FakeModel(answers, status)
        models.append(model)
        monkeypatch.setenv("CFO_MODEL_URL", model.url)
        monkeypatch.setenv("CFO_MODEL_NAME", "kernes-qwen")
        monkeypatch.setenv("CFO_MODEL_TIMEOUT", "5")
        if token:
            monkeypatch.setenv("CFO_MODEL_TOKEN", token)
        else:
            monkeypatch.delenv("CFO_MODEL_TOKEN", raising=False)
        return TestClient(create_app("live")), model

    yield start
    for model in models:
        model.close()


def advice_payload(client, csv_name="transactions.csv", opening="1200000"):
    response = client.post(
        "/api/forecast",
        data={**BASE_INPUT, "starting_balance_minor": opening},
        files={"file": (csv_name, (DEMO / csv_name).read_bytes(), "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    return {"baseline": body["baseline"], "transactions": body["transactions"]}


def test_live_advice_grounds_the_model_in_calculated_facts(live):
    client, model = live([GOOD], token="secret-token")
    response = client.post("/api/advice", json=advice_payload(client))

    assert response.status_code == 200
    body = response.json()
    assert body["explanation"] == GOOD["explanation"]
    assert body["email_draft"] == GOOD["email_draft"]
    assert body["model"] == "kernes-qwen"
    assert body["latency_ms"] >= 0

    sent = model.requests[0]
    assert sent["model"] == "kernes-qwen"
    prompt = sent["messages"][1]["content"]
    for fact in ("-EUR 5,000.00", "Friday, November 27", "EUR 11,000.00", "PAY-002", "INV-001", "Thursday, November 26"):
        assert fact in prompt
    assert model.headers[0]["Authorization"] == "Bearer secret-token"
    assert "secret-token" not in prompt


PEAK_GOOD = {
    **GOOD,
    "explanation": (
        "The balance is projected to go below zero on Tuesday, November 24, with a gap of EUR 200.00, and to "
        "reach its deepest point of -EUR 700.00 on Thursday, November 26. A EUR 700.00 facility covers it."
    ),
}
# What Llama 3.2 3B wrote on the cluster: the equipment payment posing as the first gap.
PEAK_TRANSACTION_AS_GAP = {
    **GOOD,
    "explanation": (
        "The balance is projected to go below zero on Tuesday, November 24, by EUR 1,200.00. The deepest gap is "
        "EUR 700.00 on Thursday, November 26, and after it a EUR 200.00 overdraft... A EUR 700.00 facility covers it."
    ),
}


def test_peak_case_prompt_separates_first_and_deepest_shortfall(live):
    client, model = live([PEAK_GOOD])
    response = client.post("/api/advice", json=advice_payload(client, "credit_peak_case.csv", "100000"))

    assert response.status_code == 200
    prompt = model.requests[0]["messages"][1]["content"]
    assert "First day below zero: Tuesday, November 24. The balance that day is -EUR 200.00, a gap of EUR 200.00." in prompt
    assert "Deepest point: Thursday, November 26. The balance that day is -EUR 700.00, a gap of EUR 700.00." in prompt
    assert "Proposed credit facility limit: EUR 700.00." in prompt


@pytest.mark.parametrize(
    "explanation",
    [
        PEAK_TRANSACTION_AS_GAP["explanation"],
        # Only the peak: the owner can't tell the first gap from the deepest one.
        "The gap peaks at -PLN 700.00 on Thursday, November 26, so a PLN 700.00 facility covers it.",
    ],
)
def test_peak_case_rejects_a_wrong_or_missing_first_gap(live, explanation):
    client, model = live([{**GOOD, "explanation": explanation}])
    response = client.post("/api/advice", json=advice_payload(client, "credit_peak_case.csv", "100000"))
    assert response.status_code == 503
    assert len(model.requests) == 2  # one retry, then a clear error


def test_falls_back_to_the_second_model_when_the_first_misquotes(live, monkeypatch):
    client, primary = live([PEAK_TRANSACTION_AS_GAP])
    fallback = FakeModel([PEAK_GOOD])
    try:
        monkeypatch.setenv("CFO_FALLBACK_MODEL_URL", fallback.url)
        monkeypatch.setenv("CFO_FALLBACK_MODEL_NAME", "kernes-qwen-fallback")
        response = client.post("/api/advice", json=advice_payload(client, "credit_peak_case.csv", "100000"))
    finally:
        fallback.close()
    assert response.status_code == 200
    assert response.json()["model"] == "kernes-qwen-fallback"
    assert response.json()["explanation"] == PEAK_GOOD["explanation"]
    assert len(primary.requests) == 2


def test_retries_once_when_the_model_misquotes_a_figure(live):
    client, model = live([WRONG_FIGURE, GOOD])
    response = client.post("/api/advice", json=advice_payload(client))
    assert response.status_code == 200
    assert response.json()["explanation"] == GOOD["explanation"]
    assert len(model.requests) == 2


@pytest.mark.parametrize("answer", [WRONG_FIGURE, NO_LIMIT, "not json", {"email_draft": "x"}])
def test_unusable_answers_return_503(live, answer):
    client, model = live([answer])
    response = client.post("/api/advice", json=advice_payload(client))
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]


def test_upstream_error_returns_503(live):
    client, _ = live([GOOD], status=500)
    response = client.post("/api/advice", json=advice_payload(client))
    assert response.status_code == 503
    assert "HTTP 500" in response.json()["detail"]


def test_unreachable_model_returns_503(live, monkeypatch):
    client, _ = live([GOOD])
    monkeypatch.setenv("CFO_MODEL_URL", "http://127.0.0.1:9/v1/chat/completions")
    response = client.post("/api/advice", json=advice_payload(client))
    assert response.status_code == 503


def test_no_shortfall_has_nothing_to_explain(live):
    client, model = live([GOOD])
    response = client.post("/api/advice", json=advice_payload(client, opening="2000000"))
    assert response.status_code == 422
    assert model.requests == []


def test_no_reminder_without_a_later_incoming_payment(live):
    client, model = live([GOOD])
    payload = advice_payload(client)
    payload["transactions"] = [t for t in payload["transactions"] if t["id"] != "INV-001"]
    payload["baseline"]["days"] = [
        {**day, "balance_minor": day["balance_minor"] - (900_000 if day["date"] >= "2026-11-30" else 0)}
        for day in payload["baseline"]["days"]
    ]
    response = client.post("/api/advice", json=payload)
    assert response.status_code == 200
    assert response.json()["email_draft"] is None
    assert 'set email_draft to ""' in model.requests[0]["messages"][1]["content"]


def test_reminder_drops_invented_fees_and_facility_mentions(live):
    draft = (
        "Hello,\n\nPlease pay INV-001 for EUR 9,000.00 by Thursday, November 26. This avoids late fees. "
        "It aligns with the credit facility limit of EUR 5,000.00. It covers our shortfall and overdraft. "
        "Thank you.\n\nKind regards,\nThe finance team"
    )
    client, _ = live([{**GOOD, "email_draft": draft}])
    response = client.post("/api/advice", json=advice_payload(client))
    assert response.status_code == 200
    assert response.json()["email_draft"] == (
        "Hello,\n\nPlease pay INV-001 for EUR 9,000.00 by Thursday, November 26. Thank you.\n\n"
        "Kind regards,\nThe finance team"
    )


def test_invalid_ca_bundle_returns_503(live, monkeypatch):
    client, _ = live([GOOD])
    monkeypatch.setenv("CFO_CA_BUNDLE", "/nonexistent/ca.crt")
    response = client.post("/api/advice", json=advice_payload(client))
    assert response.status_code == 503
    assert "CFO_CA_BUNDLE" in response.json()["detail"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("-EUR 5,000.00 on Friday", [500_000]),
        ("about 5 000 zł", [0]),  # a plain space ends the number on purpose
        ("November 27, 5,000 EUR", [500_000]),
        ("EUR 700. Then 1,200.50 EUR", [70_000, 120_050]),
        ("no money here, 2026", []),
    ],
)
def test_cited_amounts(text, expected):
    assert cited_amounts(text) == expected



def test_fallback_model_succeeds_when_primary_unreachable(live, monkeypatch):
    client, model = live([GOOD])
    fallback_url = model.requests  # reuse the live fixture's local HTTP server URL via env
    assert fallback_url == []
    monkeypatch.setenv("CFO_FALLBACK_MODEL_URL", os.environ["CFO_MODEL_URL"])
    monkeypatch.setenv("CFO_FALLBACK_MODEL_NAME", "kernes-qwen")
    monkeypatch.setenv("CFO_MODEL_URL", "http://127.0.0.1:9/v1/chat/completions")
    monkeypatch.setenv("CFO_MODEL_NAME", "llama-32-3b-instruct")

    response = client.post("/api/advice", json=advice_payload(client))
    assert response.status_code == 200
    assert response.json()["model"] == "kernes-qwen"
    assert model.requests[0]["model"] == "kernes-qwen"


def test_returns_503_when_both_primary_and_fallback_fail(live, monkeypatch):
    client, _ = live([GOOD], status=500)
    monkeypatch.setenv("CFO_FALLBACK_MODEL_URL", "http://127.0.0.1:9/v1/chat/completions")
    monkeypatch.setenv("CFO_FALLBACK_MODEL_NAME", "kernes-qwen")

    response = client.post("/api/advice", json=advice_payload(client))
    assert response.status_code == 503



def test_client_delay_prediction_warns_owner_with_calculated_shift(live):
    client, model = live(
        [
            {
                **GOOD,
                "delay_warning": (
                    "Client invoice INV-001 for EUR 9,000.00 was previously delayed by 2 days, "
                    "shifting expected receipt to Wednesday, December 2; the deepest gap remains EUR 5,000.00."
                ),
            }
        ]
    )
    payload = advice_payload(client)
    payload["client_delays"] = {"INV-001": 2}

    response = client.post("/api/predict-delays", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "delayed by 2 days" in data["delay_warning"]
    prompt = model.requests[0]["messages"][1]["content"]
    assert "delayed by 2 day(s)" in prompt
    assert "Wednesday, December 2" in prompt


def test_send_reminder_is_always_simulated(live, monkeypatch):
    # Old SMTP settings must not turn the simulation into a real email.
    monkeypatch.setenv("CFO_SMTP_HOST", "smtp.example.invalid")
    client, _ = live([GOOD])

    response = client.post(
        "/api/send-reminder",
        json={
            "to_email": "billing@acme.example",
            "subject": "Payment reminder: INV-001",
            "body": "Hello, please pay INV-001 by Thursday, November 26.",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "simulated"
    assert response.json()["recipient"] == "billing@acme.example"


def test_same_day_payments_come_with_their_total(live):
    # Qwen 7B summed payroll and rent on its own; the total is now a fact it can quote.
    total = {**GOOD, "explanation": GOOD["explanation"] + " Payments of EUR 17,000.00 leave on Friday."}
    client, model = live([total])
    response = client.post("/api/advice", json=advice_payload(client))
    assert response.status_code == 200
    assert "Outgoing payments on Friday, November 27 total EUR 17,000.00." in model.requests[0]["messages"][1]["content"]



def test_amalfi_recurring_obligations_noted_when_inflows_pause(live):
    client, model = live([GOOD])
    payload = advice_payload(client)
    response = client.post("/api/advice", json=payload)
    assert response.status_code == 200
    prompt = model.requests[0]["messages"][1]["content"]
    assert "Ongoing regular obligations (Payroll, Office rent)" in prompt
    assert "closure or vacation" in prompt


def test_fallback_model_uses_separate_timeout_from_env(monkeypatch):
    from backend.advice import ModelConfig

    monkeypatch.setenv("CFO_MODEL_URL", "http://primary.local:8080/v1/chat/completions")
    monkeypatch.setenv("CFO_MODEL_NAME", "kernes-qwen-7b")
    monkeypatch.setenv("CFO_MODEL_TIMEOUT", "30")
    monkeypatch.setenv("CFO_FALLBACK_MODEL_URL", "http://fallback.local:8080/v1/chat/completions")
    monkeypatch.setenv("CFO_FALLBACK_MODEL_NAME", "kernes-qwen")
    monkeypatch.setenv("CFO_FALLBACK_MODEL_TIMEOUT", "60")

    primary = ModelConfig.from_env()
    fallback = ModelConfig.fallback_from_env(timeout=primary.timeout, ssl_context=primary.ssl_context)
    assert primary.timeout == 30.0
    assert fallback is not None
    assert fallback.timeout == 60.0


def test_health_ai_reports_unconfigured_and_degraded(monkeypatch):
    monkeypatch.delenv("CFO_MODEL_URL", raising=False)
    monkeypatch.delenv("CFO_MODEL_NAME", raising=False)
    unconfigured = TestClient(create_app("demo")).get("/health/ai")
    assert unconfigured.status_code == 200
    assert unconfigured.json()["status"] == "unconfigured"

    monkeypatch.setenv("CFO_MODEL_URL", "http://primary.local:8080/v1/chat/completions")
    monkeypatch.setenv("CFO_MODEL_NAME", "kernes-qwen-7b")
    monkeypatch.setenv("CFO_FALLBACK_MODEL_URL", "http://fallback.local:8080/v1/chat/completions")
    monkeypatch.setenv("CFO_FALLBACK_MODEL_NAME", "kernes-qwen")

    class _OkResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=None, context=None):
        if "primary.local" in req.full_url:
            raise TimeoutError("primary timed out")
        return _OkResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    degraded = TestClient(create_app("live")).get("/health/ai")
    assert degraded.status_code == 200
    body = degraded.json()
    assert body["status"] == "degraded"
    assert body["primary"]["reachable"] is False
    assert body["fallback"]["reachable"] is True

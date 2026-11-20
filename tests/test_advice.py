import json
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
        "Your balance drops to -PLN 5,000.00 on Friday, November 27, when Payroll (PAY-001) and Office rent "
        "(PAY-002) go out before the Client invoice (INV-001) arrives. A credit facility of PLN 5,000.00 covers it."
    ),
    "email_draft": "Hello, could you pay INV-001 for PLN 9,000.00 by Thursday, November 26? The finance team",
}
WRONG_FIGURE = {**GOOD, "explanation": "You are PLN 5,500.00 short on Friday. A facility of PLN 5,000.00 covers it."}
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
    for fact in ("-PLN 5,000.00", "Friday, November 27", "PLN 11,000.00", "PAY-002", "INV-001", "Thursday, November 26"):
        assert fact in prompt
    assert model.headers[0]["Authorization"] == "Bearer secret-token"
    assert "secret-token" not in prompt


def test_peak_case_prompt_separates_first_and_deepest_shortfall(live):
    client, model = live([{**GOOD, "explanation": "The gap peaks at -PLN 700.00, so a PLN 700.00 facility covers it."}])
    response = client.post("/api/advice", json=advice_payload(client, "credit_peak_case.csv", "100000"))

    assert response.status_code == 200
    prompt = model.requests[0]["messages"][1]["content"]
    assert "First day below zero: Tuesday, November 24, balance -PLN 200.00." in prompt
    assert "Deepest point: Thursday, November 26, balance -PLN 700.00." in prompt
    assert "Proposed credit facility limit: PLN 700.00." in prompt


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
        "Hello,\n\nPlease pay INV-001 for PLN 9,000.00 by Thursday, November 26. This avoids late fees. "
        "It aligns with the credit facility limit of PLN 5,000.00. It covers our shortfall and overdraft. "
        "Thank you.\n\nKind regards,\nThe finance team"
    )
    client, _ = live([{**GOOD, "email_draft": draft}])
    response = client.post("/api/advice", json=advice_payload(client))
    assert response.status_code == 200
    assert response.json()["email_draft"] == (
        "Hello,\n\nPlease pay INV-001 for PLN 9,000.00 by Thursday, November 26. Thank you.\n\n"
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
        ("-PLN 5,000.00 on Friday", [500_000]),
        ("about 5 000 zł", [0]),  # a plain space ends the number on purpose
        ("November 27, 5,000 PLN", [500_000]),
        ("PLN 700. Then 1,200.50 PLN", [70_000, 120_050]),
        ("no money here, 2026", []),
    ],
)
def test_cited_amounts(text, expected):
    assert cited_amounts(text) == expected

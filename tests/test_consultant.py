import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


DEMO = Path(__file__).resolve().parents[1] / "demo"


def _payload() -> dict:
    forecast = json.loads((DEMO / "forecast.example.json").read_text(encoding="utf-8"))
    return {
        "baseline": forecast["baseline"],
        "transactions": forecast["transactions"],
    }


@pytest.fixture
def live_consultant(monkeypatch):
    def start(answers: list[dict], *, status: int = 200):
        queue = list(answers)

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                _ = self.rfile.read(length)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if status != 200:
                    self.wfile.write(b'{"error":"down"}')
                    return
                answer = queue.pop(0) if queue else {"text": "PLN 5,000.00"}
                body = {"choices": [{"message": {"content": json.dumps(answer)}}]}
                self.wfile.write(json.dumps(body).encode("utf-8"))

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setenv("CFO_MODEL_URL", f"http://127.0.0.1:{server.server_port}/v1/chat/completions")
        monkeypatch.setenv("CFO_MODEL_NAME", "llama-32-3b-instruct")
        monkeypatch.delenv("CFO_FALLBACK_MODEL_URL", raising=False)
        monkeypatch.delenv("CFO_FALLBACK_MODEL_NAME", raising=False)
        return TestClient(create_app("live")), server

    yield start


def test_credit_check_deterministic_and_live(live_consultant):
    demo_client = TestClient(create_app("demo"))
    base = _payload()

    r_clean = demo_client.post("/api/credit-check", json=base)
    assert r_clean.status_code == 200
    clean = r_clean.json()
    assert clean["proposed_limit_minor"] == 500_000
    assert clean["deficit_days"] == 3
    assert clean["inflow_coverage_pct"] == 180
    assert clean["model"] == "demo-deterministic"

    r_delayed = demo_client.post("/api/credit-check", json={**base, "client_delays": {"INV-001": 4}})
    assert r_delayed.status_code == 200
    assert r_delayed.json()["score"] < clean["score"]

    live_client, srv = live_consultant([{"text": "The borrower needs PLN 5,000.00 and recovers on Monday."}])
    try:
        r_live = live_client.post("/api/credit-check", json=base)
        assert r_live.status_code == 200
        assert r_live.json()["model"] == "llama-32-3b-instruct"
        assert "PLN 5,000.00" in r_live.json()["reasoning"]
    finally:
        srv.shutdown()


def test_stress_test_calculates_extra_buffer():
    client = TestClient(create_app("demo"))
    base = _payload()

    resp = client.post("/api/stress-test", json={**base, "delay_days": 3, "expense_shock_pct": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert data["baseline_limit_minor"] == 500_000
    # Expenses: (-1,100,000 - 600,000) * 1.1 = -1,870,000; 1,200,000 - 1,870,000 = -670,000
    assert data["stressed_limit_minor"] == 670_000
    assert data["extra_buffer_minor"] == 170_000


def test_optimize_payments_finds_best_reduction():
    client = TestClient(create_app("demo"))
    resp = client.post("/api/optimize-payments", json=_payload())
    assert resp.status_code == 200
    data = resp.json()
    assert data["baseline_limit_minor"] == 500_000
    assert len(data["actions"]) >= 1
    top = data["actions"][0]
    assert top["limit_reduction_minor"] == 500_000
    assert top["new_limit_minor"] == 0


def test_ask_cfo_live_and_rejects_invented_amounts(live_consultant):
    base = _payload()
    live_client, srv = live_consultant([{"text": "The lowest balance is -PLN 5,000.00 on Friday, November 27."}])
    try:
        resp = live_client.post("/api/ask-cfo", json={**base, "question": "What is my worst day?"})
        assert resp.status_code == 200
        assert "PLN 5,000.00" in resp.json()["answer"]
    finally:
        srv.shutdown()

    bad_client, srv2 = live_consultant([{"text": "You should borrow PLN 99,999.00 immediately."}])
    try:
        resp2 = bad_client.post("/api/ask-cfo", json={**base, "question": "What should I do?"})
        assert resp2.status_code == 503
    finally:
        srv2.shutdown()

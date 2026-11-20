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
def live_extras(monkeypatch):
    def start(answers: list[dict]):
        queue = list(answers)

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                _ = self.rfile.read(length)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
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


def test_detect_anomalies_finds_same_day_spike_and_duplicates(live_extras):
    demo_client = TestClient(create_app("demo"))
    base = _payload()

    # Starter case has PAY-001 (-1,100,000) and PAY-002 (-600,000) on 2026-11-27 -> same_day_spike
    r1 = demo_client.post("/api/detect-anomalies", json=base)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["risk_flag"] == "review_recommended"
    assert any(f["kind"] == "same_day_spike" for f in d1["findings"])

    # Add a duplicate outflow within 2 days and an outlier expense
    dup_payload = {
        "baseline": base["baseline"],
        "transactions": [
            *base["transactions"],
            {"id": "DUP-001", "date": "2026-11-28", "amount_minor": -600_000, "label": "Office rent duplicate"},
        ],
    }
    r2 = demo_client.post("/api/detect-anomalies", json=dup_payload)
    assert r2.status_code == 200
    kinds = {f["kind"] for f in r2.json()["findings"]}
    assert "duplicate_payment" in kinds

    live_client, srv = live_extras([{"text": "Review the PLN 17,000.00 payment concentration on Friday, November 27."}])
    try:
        r_live = live_client.post("/api/detect-anomalies", json=base)
        assert r_live.status_code == 200
        assert r_live.json()["model"] == "llama-32-3b-instruct"
    finally:
        srv.shutdown()

    bad_client, srv2 = live_extras([{"text": "Suspicious PLN 88,888.00 transfer detected."}])
    try:
        r_bad = bad_client.post("/api/detect-anomalies", json=base)
        assert r_bad.status_code == 503
    finally:
        srv2.shutdown()


def test_compare_financing_options_ranks_cheapest_and_live(live_extras):
    demo_client = TestClient(create_app("demo"))
    base = _payload()

    resp = demo_client.post("/api/compare-options", json=base)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["options"]) >= 2
    assert data["options"][0]["estimated_cost_minor"] <= data["options"][1]["estimated_cost_minor"]
    assert data["recommended_option"] == data["options"][0]["option_kind"]

    live_client, srv = live_extras([{"text": "The credit facility for PLN 5,000.00 is the lowest-cost option here."}])
    try:
        r_live = live_client.post("/api/compare-options", json=base)
        assert r_live.status_code == 200
        assert r_live.json()["model"] == "llama-32-3b-instruct"
    finally:
        srv.shutdown()

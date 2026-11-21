import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


DEMO = Path(__file__).resolve().parents[1] / "demo"


def _payload() -> dict:
    days = [
        {"date": f"2026-11-{day:02d}", "balance_minor": bal}
        for day, bal in [
            (23, 1_200_000),
            (24, 1_200_000),
            (25, 1_200_000),
            (26, 1_200_000),
            (27, -500_000),
            (28, -500_000),
            (29, -500_000),
            (30, 400_000),
        ]
    ] + [{"date": f"2026-12-0{day}", "balance_minor": 400_000} for day in range(1, 7)]
    return {
        "baseline": {
            "days": days,
            "first_deficit": {"date": "2026-11-27", "shortfall_minor": 500_000},
        },
        "transactions": [
            {"id": "PAY-001", "date": "2026-11-27", "amount_minor": -1_100_000, "label": "Payroll"},
            {"id": "PAY-002", "date": "2026-11-27", "amount_minor": -600_000, "label": "Office rent"},
            {"id": "INV-001", "date": "2026-11-30", "amount_minor": 900_000, "label": "Client invoice"},
        ],
        "currency": "EUR",
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
                answer = queue.pop(0) if queue else {"text": "EUR 5,000.00"}
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

    live_client, srv = live_extras([{"text": "Review the EUR 17,000.00 payment concentration on Friday, November 27."}])
    try:
        r_live = live_client.post("/api/detect-anomalies", json=base)
        assert r_live.status_code == 200
        assert r_live.json()["model"] == "llama-32-3b-instruct"
    finally:
        srv.shutdown()

    bad_client, srv2 = live_extras([{"text": "Suspicious EUR 88,888.00 transfer detected."}])
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
    assert len(data["options"]) >= 3
    kinds = {opt["option_kind"] for opt in data["options"]}
    assert {"credit_facility", "invoice_factoring", "defer_outflow"} <= kinds
    assert data["options"][0]["estimated_cost_minor"] <= data["options"][1]["estimated_cost_minor"]
    assert data["recommended_option"] == data["options"][0]["option_kind"]

    live_client, srv = live_extras([{"text": "The credit facility for EUR 5,000.00 is the lowest-cost option here."}])
    try:
        r_live = live_client.post("/api/compare-options", json=base)
        assert r_live.status_code == 200
        assert r_live.json()["model"] == "llama-32-3b-instruct"
    finally:
        srv.shutdown()


def _forecast_payload_from_csv(csv_rel_path: str, opening_minor: int, start_date: str) -> dict:
    client = TestClient(create_app("live"))
    csv_path = DEMO / csv_rel_path
    resp = client.post(
        "/api/forecast",
        data={"starting_balance_minor": str(opening_minor), "start_date": start_date},
        files={"file": (csv_path.name, csv_path.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_stress_duplicate_anomaly_fixture_triggers_detectors():
    fc = _forecast_payload_from_csv("stress_cases/amalfi_duplicate_anomaly_eur.csv", 500_000, "2025-06-22")
    demo_client = TestClient(create_app("demo"))
    resp = demo_client.post(
        "/api/detect-anomalies",
        json={"baseline": fc["baseline"], "transactions": fc["transactions"], "currency": fc["currency"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["risk_flag"] == "review_recommended"
    kinds = {f["kind"] for f in body["findings"]}
    assert {"duplicate_payment", "outlier_expense"} <= kinds


def test_detect_anomalies_clean_on_no_shortfall_fixture():
    fc = _forecast_payload_from_csv("no_shortfall_case.csv", 1_500_000, "2026-11-23")
    demo_client = TestClient(create_app("demo"))
    resp = demo_client.post(
        "/api/detect-anomalies",
        json={"baseline": fc["baseline"], "transactions": fc["transactions"], "currency": fc["currency"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["risk_flag"] == "clean"
    assert body["findings"] == []
    assert "No duplicate payments" in body["summary"]


def test_compare_options_returns_none_needed_without_shortfall(monkeypatch):
    monkeypatch.delenv("CFO_MODEL_URL", raising=False)
    fc = _forecast_payload_from_csv("no_shortfall_case.csv", 1_500_000, "2026-11-23")
    payload = {"baseline": fc["baseline"], "transactions": fc["transactions"], "currency": fc["currency"]}

    for mode, expected_model in [("demo", "demo-deterministic"), ("live", "deterministic")]:
        client = TestClient(create_app(mode))
        resp = client.post("/api/compare-options", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["options"] == []
        assert data["recommended_option"] == "none_needed"
        assert data["model"] == expected_model


def test_advisory_extras_factoring_fee_and_invalid_window_validation():
    demo_client = TestClient(create_app("demo"))
    base = _payload()

    cmp_low = demo_client.post("/api/compare-options", json={**base, "factoring_fee_bps": 100}).json()
    cmp_high = demo_client.post("/api/compare-options", json={**base, "factoring_fee_bps": 300}).json()
    fact_low = next(o for o in cmp_low["options"] if o["option_kind"] == "invoice_factoring")
    fact_high = next(o for o in cmp_high["options"] if o["option_kind"] == "invoice_factoring")
    assert fact_high["estimated_cost_minor"] == 3 * fact_low["estimated_cost_minor"]

    broken_days = list(base["baseline"]["days"])
    broken_days[-1] = {**broken_days[-1], "date": "2026-12-20"}
    broken_payload = {
        "baseline": {**base["baseline"], "days": broken_days},
        "transactions": base["transactions"],
    }
    assert demo_client.post("/api/detect-anomalies", json=broken_payload).status_code == 422
    assert demo_client.post("/api/compare-options", json=broken_payload).status_code == 422

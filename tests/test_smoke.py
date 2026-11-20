import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


DEMO = Path(__file__).resolve().parents[1] / "demo"
BASE_INPUT = {
    "starting_balance_minor": "1200000",
    "start_date": "2026-11-23",
}
MOVE = {"move_transaction_id": "INV-001", "move_to_date": "2026-11-26"}


def forecast(client, data, csv=None):
    incoming = (DEMO / "transactions.csv").read_bytes() if csv is None else csv
    return client.post(
        "/api/forecast",
        data=data,
        files={"file": ("transactions.csv", incoming, "text/csv")},
    )


def test_preview_serves_html_assets_and_demo_csv():
    client = TestClient(create_app("demo"))
    assert client.get("/health").json() == {"status": "ok"}
    assert "Autonomous CFO" in client.get("/").text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/styles.css").status_code == 200
    assert client.get("/demo/transactions.csv").content == (DEMO / "transactions.csv").read_bytes()
    operations = client.get("/openapi.json").json()["paths"]
    assert "multipart/form-data" in operations["/api/forecast"]["post"]["requestBody"]["content"]


def test_demo_baseline_scenario_and_draft():
    client = TestClient(create_app("demo"))
    baseline = forecast(client, BASE_INPUT)
    compared = forecast(client, {**BASE_INPUT, **MOVE})
    assert baseline.status_code == compared.status_code == 200
    original = baseline.json()
    changed = compared.json()
    assert original["scenario"] is None
    assert changed["baseline"] == original["baseline"]
    assert changed["baseline"]["first_deficit"] == {"date": "2026-11-27", "shortfall_minor": 500_000}
    assert changed["scenario"]["first_deficit"] is None
    friday = next(day for day in changed["scenario"]["days"] if day["date"] == "2026-11-27")
    assert friday["balance_minor"] == 400_000

    payload = {
        "first_deficit": original["baseline"]["first_deficit"],
        "transactions": original["transactions"],
    }
    advice = client.post("/api/advice", json=payload)
    assert advice.status_code == 200
    assert advice.json() == json.loads((DEMO / "advice.example.json").read_text(encoding="utf-8"))

    payload["first_deficit"] = {"date": "2026-11-27", "shortfall_minor": 123}
    assert client.post("/api/advice", json=payload).status_code == 422


@pytest.mark.parametrize(
    "data, csv",
    [
        ({**BASE_INPUT, "starting_balance_minor": "123"}, None),
        ({**BASE_INPUT, "move_transaction_id": "INV-001"}, None),
        ({**BASE_INPUT, **MOVE, "move_to_date": "2026-11-25"}, None),
        ({**BASE_INPUT, "currency": "EUR"}, None),
        (BASE_INPUT, b"id,date,amount_minor,label\n"),
        (BASE_INPUT, b"\xff"),
    ],
)
def test_demo_rejects_unsupported_inputs(data, csv):
    assert forecast(TestClient(create_app("demo")), data, csv).status_code == 422


def test_live_mode_exposes_health_without_demo_fallbacks():
    client = TestClient(create_app("live"))
    assert client.get("/health").status_code == 200
    assert forecast(client, BASE_INPUT).status_code == 503
    response = client.post(
        "/api/advice",
        json={"first_deficit": {"date": "2026-11-27", "shortfall_minor": 1}, "transactions": []},
    )
    assert response.status_code == 503

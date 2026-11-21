import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


STRESS_DIR = Path(__file__).resolve().parents[1] / "demo" / "stress_cases"
START = "2025-06-22"


@pytest.fixture
def live_client():
    return TestClient(create_app("live"))


@pytest.fixture
def demo_client():
    return TestClient(create_app("demo"))


def _upload(client: TestClient, filename: str, opening: str = "500000", start: str = START):
    return client.post(
        "/api/forecast",
        data={"starting_balance_minor": opening, "start_date": start},
        files={"file": (filename, (STRESS_DIR / filename).read_bytes(), "text/csv")},
    )


def test_severe_shortfall_eur_flows_through_downstream_endpoints(demo_client, live_client):
    resp = _upload(live_client, "amalfi_severe_shortfall_eur.csv", opening="500000")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["currency"] == "EUR"
    assert data["baseline"]["first_deficit"] is not None
    assert data["proposal"]["limit_minor"] > 0
    assert len(data["earlier_payments"]) >= 1

    payload = {
        "baseline": data["baseline"],
        "transactions": data["transactions"],
        "currency": data["currency"],
    }
    assert live_client.post("/api/stress-test", json=payload).status_code == 200
    assert live_client.post("/api/optimize-payments", json=payload).status_code == 200
    assert demo_client.post("/api/compare-options", json=payload).status_code == 200
    assert demo_client.post("/api/credit-check", json=payload).status_code == 200
    ap = demo_client.post("/api/action-plan", json=payload)
    assert ap.status_code == 200, ap.text
    ap_body = ap.json()
    assert ap_body["mode"] == "survival"
    assert any(s["action_kind"] == "credit_facility" for s in ap_body["steps"])


def test_healthy_surplus_eur_has_no_shortfall_or_credit_need(live_client):
    resp = _upload(live_client, "amalfi_healthy_surplus_eur.csv", opening="500000")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["currency"] == "EUR"
    assert data["baseline"]["first_deficit"] is None
    assert data["proposal"] is None

    payload = {
        "baseline": data["baseline"],
        "transactions": data["transactions"],
        "currency": data["currency"],
    }
    assert live_client.post("/api/credit-check", json=payload).status_code == 422
    opt = live_client.post("/api/optimize-payments", json=payload)
    assert opt.status_code == 200
    assert opt.json()["proposed_limit_minor"] == 0

    ap = TestClient(create_app("demo")).post("/api/action-plan", json=payload)
    assert ap.status_code == 200, ap.text
    ap_body = ap.json()
    assert ap_body["mode"] == "growth"
    assert all(s["email_draft"] is None for s in ap_body["steps"])


def test_poland_branch_pln_is_autodetected_and_propagated(demo_client, live_client):
    resp = _upload(live_client, "amalfi_poland_branch_pln.csv", opening="1000000")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["currency"] == "PLN"
    assert data["baseline"]["first_deficit"] is not None

    payload = {
        "baseline": data["baseline"],
        "transactions": data["transactions"],
        "currency": data["currency"],
    }
    advice = demo_client.post("/api/advice", json=payload)
    assert advice.status_code == 200, advice.text
    assert "PLN " in advice.json()["explanation"]
    assert "EUR" not in advice.json()["explanation"]

    credit = demo_client.post("/api/credit-check", json=payload)
    assert credit.status_code == 200, credit.text
    assert any("PLN " in f["reason"] for f in credit.json()["factors"])

    compare = demo_client.post("/api/compare-options", json=payload)
    assert compare.status_code == 200, compare.text
    assert all("PLN " in o["detail"] and "EUR" not in o["detail"] for o in compare.json()["options"])


def test_usd_mixed_fx_converts_eur_row_and_detects_usd(demo_client, live_client):
    resp = _upload(live_client, "amalfi_usd_mixed_fx.csv", opening="500000")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["currency"] == "USD"
    # -1000.00 EUR @ 1.0800 USD/EUR -> -1080.00 USD -> -108000 minor
    fx_tx = next(t for t in data["transactions"] if "Sapori" in t["label"])
    assert fx_tx["amount_minor"] == -108_000

    advice = demo_client.post(
        "/api/advice",
        json={"baseline": data["baseline"], "transactions": data["transactions"], "currency": "USD"},
    )
    assert advice.status_code == 200, advice.text
    assert "USD " in advice.json()["explanation"]
    assert "EUR" not in advice.json()["explanation"]

    ap = demo_client.post(
        "/api/action-plan",
        json={"baseline": data["baseline"], "transactions": data["transactions"], "currency": "USD"},
    )
    assert ap.status_code == 200, ap.text
    ap_body = ap.json()
    assert "USD " in ap_body["headline"] or "USD " in ap_body["summary"]
    assert "EUR" not in ap_body["headline"] and "EUR" not in ap_body["summary"]


def test_duplicate_anomaly_eur_flags_duplicate_and_outlier(demo_client, live_client):
    resp = _upload(live_client, "amalfi_duplicate_anomaly_eur.csv", opening="500000")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["currency"] == "EUR"

    anomalies = demo_client.post(
        "/api/detect-anomalies",
        json={"baseline": data["baseline"], "transactions": data["transactions"], "currency": "EUR"},
    )
    assert anomalies.status_code == 200, anomalies.text
    body = anomalies.json()
    assert body["risk_flag"] == "review_recommended"
    kinds = {f["kind"] for f in body["findings"]}
    assert "duplicate_payment" in kinds
    assert "outlier_expense" in kinds

    ap = demo_client.post(
        "/api/action-plan",
        json={"baseline": data["baseline"], "transactions": data["transactions"], "currency": "EUR"},
    )
    assert ap.status_code == 200, ap.text
    ap_body = ap.json()
    assert ap_body["mode"] == "survival"
    assert ap_body["steps"][0]["action_kind"] == "review_anomaly"


@pytest.mark.parametrize(
    "filename, expected_fragment",
    [
        ("error_unknown_currency.csv", "unsupported or unknown currency 'XYZ'"),
        ("error_missing_currency.csv", "missing currency"),
        ("error_bad_date.csv", "not a real date"),
        ("error_bad_amount.csv", "invalid amount format"),
        ("error_missing_columns.csv", "missing required columns"),
        ("error_legacy_comma_format.csv", "Unsupported CSV format"),
    ],
)
def test_error_stress_csvs_return_422_with_clear_reason(live_client, filename, expected_fragment):
    resp = _upload(live_client, filename, opening="500000")
    assert resp.status_code == 422, f"{filename} unexpectedly returned {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", "")
    assert expected_fragment.lower() in detail.lower(), f"{filename}: {detail!r}"


def test_legacy_transactions_csv_route_is_removed_and_amalfi_remains(demo_client):
    assert demo_client.get("/demo/transactions.csv").status_code == 404
    amalfi = demo_client.get("/demo/amalfi.csv")
    assert amalfi.status_code == 200
    assert "Pizzeria Amalfi" in amalfi.text

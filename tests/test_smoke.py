import csv
import json
import os
import re
import ssl
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


DEMO = Path(__file__).resolve().parents[1] / "demo"
QA_CASES = json.loads((DEMO / "qa_cases.json").read_text(encoding="utf-8"))["cases"]
BASE_INPUT = {
    "starting_balance_minor": "1200000",
    "start_date": "2026-11-23",
}
MOVE = {"move_transaction_id": "INV-001", "move_to_date": "2026-11-26"}


def forecast(client, data, csv_bytes=None):
    incoming = (DEMO / "transactions.csv").read_bytes() if csv_bytes is None else csv_bytes
    return client.post(
        "/api/forecast",
        data=data,
        files={"file": ("transactions.csv", incoming, "text/csv")},
    )


def test_preview_serves_html_assets_and_demo_csv():
    client = TestClient(create_app("demo"))
    assert client.get("/health").json() == {"status": "ok"}
    page = client.get("/")
    assert page.status_code == 200
    assert 'class="app-shell"' in page.text
    styles = client.get("/assets/styles.css")
    assert styles.status_code == 200
    assert "css/tokens.css" in styles.text
    for asset in (
        "app.js", "chart.js", "parser.js", "sample-amalfi.js",
        "js/api.js", "js/format.js", "js/proposal.js", "js/render.js",
        "css/tokens.css", "css/dashboard.css", "css/forms.css", "css/panels.css", "css/responsive.css",
    ):
        assert client.get(f"/assets/{asset}").status_code == 200, asset
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

    payload = {"baseline": original["baseline"], "transactions": original["transactions"]}
    advice = client.post("/api/advice", json=payload)
    assert advice.status_code == 200
    assert advice.json() == json.loads((DEMO / "advice.example.json").read_text(encoding="utf-8"))

    payload["transactions"] = payload["transactions"][:2]
    assert client.post("/api/advice", json=payload).status_code == 422


@pytest.mark.parametrize(
    "data, csv_bytes",
    [
        ({**BASE_INPUT, "starting_balance_minor": "123"}, None),
        ({**BASE_INPUT, "move_transaction_id": "INV-001"}, None),
        ({**BASE_INPUT, **MOVE, "move_to_date": "2026-11-25"}, None),
        ({**BASE_INPUT, "currency": "USD"}, None),  # not an EU currency
        (BASE_INPUT, b"id,date,amount_minor,label\n"),
        (BASE_INPUT, b"\xff"),
    ],
)
def test_demo_rejects_unsupported_inputs(data, csv_bytes):
    assert forecast(TestClient(create_app("demo")), data, csv_bytes).status_code == 422


def test_live_mode_exposes_health_without_demo_fallbacks(monkeypatch):
    monkeypatch.delenv("CFO_MODEL_URL", raising=False)
    monkeypatch.delenv("CFO_MODEL_NAME", raising=False)
    client = TestClient(create_app("live"))
    assert client.get("/health").status_code == 200
    result = forecast(client, BASE_INPUT)
    assert result.status_code == 200  # live forecast is implemented
    body = result.json()
    response = client.post("/api/advice", json={"baseline": body["baseline"], "transactions": body["transactions"]})
    assert response.status_code == 503  # no model configured, no saved sample in live mode


# ─── QA Synthetic Fixtures & End-to-End Workflow ─────────────────────────────


def test_qa_cases_manifest_and_csv_fixtures():
    assert len(QA_CASES) >= 3
    for case in QA_CASES:
        csv_path = DEMO / case["csv"]
        assert csv_path.is_file(), f"Missing fixture CSV: {csv_path}"
        text = csv_path.read_text(encoding="utf-8")
        rows = list(csv.reader(text.splitlines()))
        assert rows[0] == ["id", "date", "amount_minor", "label"]
        seen_ids = set()
        for row in rows[1:]:
            assert len(row) == 4
            tx_id, tx_date, amount_minor, label = row
            assert tx_id and tx_id not in seen_ids
            seen_ids.add(tx_id)
            date.fromisoformat(tx_date)
            int(amount_minor)
            assert label.strip()
        assert len(case["expected_baseline_balances"]) == 14
        if case["explanation_expectations"] is not None:
            exp = case["explanation_expectations"]
            assert exp["required_amount_groups"]
            assert exp["required_date_groups"]
            draft_exp = case["email_draft_expectations"]
            assert isinstance(draft_exp, dict)
            assert draft_exp["any_tokens"]
            assert draft_exp["forbidden_tokens"]


def test_demo_proposal_and_decision_simulation():
    client = TestClient(create_app("demo"))
    baseline_resp = forecast(client, BASE_INPUT)
    assert baseline_resp.status_code == 200
    body = baseline_resp.json()
    assert body["proposal"]["limit_minor"] == 500_000

    for decision_kind in ("approved", "rejected"):
        decision_resp = client.post(
            "/api/decision",
            json={"decision": decision_kind, "baseline": body["baseline"]},
        )
        assert decision_resp.status_code == 200
        expected = json.loads((DEMO / f"decision.{decision_kind}.example.json").read_text(encoding="utf-8"))
        assert decision_resp.json() == expected


@pytest.mark.parametrize("case", QA_CASES, ids=[c["id"] for c in QA_CASES])
def test_live_workflow_all_synthetic_cases(case):
    client = TestClient(create_app("live"))
    csv_bytes = (DEMO / case["csv"]).read_bytes()
    payload = {
        "starting_balance_minor": str(case["starting_balance_minor"]),
        "start_date": case["start_date"],
    }

    resp = forecast(client, payload, csv_bytes)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    start = date.fromisoformat(case["start_date"])
    expected_dates = [(start + timedelta(days=offset)).isoformat() for offset in range(14)]
    days = body["baseline"]["days"]
    assert [day["date"] for day in days] == expected_dates
    assert [day["balance_minor"] for day in days] == case["expected_baseline_balances"]
    assert body["baseline"]["first_deficit"] == case["expected_first_deficit"]
    assert body["proposal"] == case["expected_proposal"]
    assert body["scenario"] is None

    if case["expected_decisions"] is None:
        for decision_kind in ("approved", "rejected"):
            decision_resp = client.post(
                "/api/decision",
                json={"decision": decision_kind, "baseline": body["baseline"]},
            )
            assert decision_resp.status_code == case["expected_decision_status"]
    else:
        for decision_kind, expected_decision in case["expected_decisions"].items():
            decision_resp = client.post(
                "/api/decision",
                json={"decision": decision_kind, "baseline": body["baseline"]},
            )
            assert decision_resp.status_code == 200, decision_resp.text
            outcome = decision_resp.json()
            assert outcome["decision"] == decision_kind
            assert outcome["simulated"] is True
            assert outcome["limit_minor"] == expected_decision["limit_minor"]
            assert outcome["largest_uncovered"] == expected_decision["largest_uncovered"]
            assert [d["balance_minor"] for d in outcome["days"]] == case["expected_baseline_balances"]
            assert [d["facility_used_minor"] for d in outcome["days"]] == expected_decision["facility_used_minor"]
            assert [d["uncovered_minor"] for d in outcome["days"]] == expected_decision["uncovered_minor"]

    move = case["scenario_move"]
    if move is not None:
        move_resp = forecast(
            client,
            {
                **payload,
                "move_transaction_id": move["move_transaction_id"],
                "move_to_date": move["move_to_date"],
            },
            csv_bytes,
        )
        assert move_resp.status_code == 200, move_resp.text
        moved = move_resp.json()
        assert moved["baseline"] == body["baseline"]
        assert moved["proposal"] == body["proposal"]
        assert moved["transactions"] == body["transactions"]
        assert [d["balance_minor"] for d in moved["scenario"]["days"]] == move["expected_scenario_balances"]
        assert moved["scenario"]["first_deficit"] == move["expected_first_deficit"]
        key_base = next(d["balance_minor"] for d in moved["baseline"]["days"] if d["date"] == move["expected_key_date"])
        key_scn = next(d["balance_minor"] for d in moved["scenario"]["days"] if d["date"] == move["expected_key_date"])
        assert key_base == move["expected_baseline_minor"]
        assert key_scn == move["expected_scenario_minor"]


def test_live_rejects_amalfi_semicolon_bank_statement():
    amalfi_snippet = (
        '"Account Number";"Booking Date";"Value Date";"Transaction Type";"Payment Reference";'
        '"Beneficiary/Payer";"Counterparty Account";"Bank Code";"Amount";"Currency";"Info"\n'
        '"DE89370400440532013000";"31.12.25";"31.12.25";"CARD SETTLEMENT (DEBIT)";'
        '"Daily Debit Card Revenue Settlement";"Pizzeria Amalfi Customers";"DE92500500000959561143";'
        '"HELADEFFXXX";"275,35";"EUR";"Transaction booked"\n'
    ).encode("utf-8")
    resp = forecast(TestClient(create_app("live")), BASE_INPUT, amalfi_snippet)
    assert resp.status_code == 422
    assert "header" in resp.json()["detail"].lower()


# ─── Reusable Remote / OpenShift Deployment Verification ─────────────────────


def _http_call(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    ssl_ctx: ssl.SSLContext | None = None,
    timeout: int = 120,
) -> tuple[int, dict | str]:
    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}", data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            content_type = resp.headers.get("content-type", "")
            return resp.status, json.loads(raw) if "application/json" in content_type else raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def _multipart_forecast(
    base_url: str,
    fields: dict[str, str],
    filename: str,
    csv_bytes: bytes,
    ssl_ctx: ssl.SSLContext | None,
) -> tuple[int, dict | str]:
    boundary = f"----qa-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for key, val in fields.items():
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                f"{val}\r\n"
            ).encode("utf-8")
        )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: text/csv\r\n\r\n"
        ).encode("utf-8")
        + csv_bytes
        + f"\r\n--{boundary}--\r\n".encode("utf-8")
    )
    payload = b"".join(parts)
    return _http_call(
        base_url,
        "/api/forecast",
        method="POST",
        body=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        ssl_ctx=ssl_ctx,
    )


def _assert_explanation_grounded(explanation: str, expectations: dict) -> None:
    lower = explanation.lower()
    for group in expectations["required_amount_groups"]:
        assert any(token.lower() in lower for token in group), (
            f"Explanation missing expected amount from {group}: {explanation!r}"
        )
    for group in expectations["required_date_groups"]:
        assert any(token.lower() in lower for token in group), (
            f"Explanation missing expected date from {group}: {explanation!r}"
        )
    assert any(
        re.search(rf"\b{re.escape(token.lower())}\b", lower) or token.lower() in lower
        for token in expectations["any_transaction_tokens"]
    ), f"Explanation missing expected transaction token: {explanation!r}"


def _assert_email_draft_valid(email_draft: str | None, expectations: dict | None) -> None:
    if expectations is None:
        return
    assert isinstance(email_draft, str) and email_draft.strip(), f"Expected non-empty email_draft, got {email_draft!r}"
    lower = email_draft.lower()
    assert any(token.lower() in lower for token in expectations["any_tokens"]), (
        f"Email draft missing expected invoice/date token from {expectations['any_tokens']}: {email_draft!r}"
    )
    leaked = [token for token in expectations["forbidden_tokens"] if token.lower() in lower]
    assert not leaked, f"Email draft leaked internal terms {leaked}: {email_draft!r}"


@pytest.mark.skipif(
    not os.environ.get("CFO_BASE_URL"),
    reason="Set CFO_BASE_URL to verify a running local or OpenShift deployment.",
)
def test_remote_deployment_workflow():
    base_url = os.environ["CFO_BASE_URL"].rstrip("/")
    require_advice = os.environ.get("CFO_REQUIRE_LIVE_ADVICE", "0") == "1"
    ssl_ctx = ssl._create_unverified_context() if os.environ.get("CFO_INSECURE_TLS") == "1" else None

    status, health = _http_call(base_url, "/health", ssl_ctx=ssl_ctx)
    assert status == 200 and health == {"status": "ok"}

    status, html = _http_call(base_url, "/", ssl_ctx=ssl_ctx)
    assert status == 200 and "KERNES CFO" in html

    status, _ = _http_call(base_url, "/demo/transactions.csv", ssl_ctx=ssl_ctx)
    assert status == 200

    status, openapi = _http_call(base_url, "/openapi.json", ssl_ctx=ssl_ctx)
    assert status == 200
    advice_props = openapi["components"]["schemas"]["AdviceRequest"]["properties"]
    uses_baseline_advice = "baseline" in advice_props
    advice_resp_props = openapi["components"]["schemas"]["AdviceResponse"]["properties"]
    returns_model = "model" in advice_resp_props

    for case in QA_CASES:
        csv_bytes = (DEMO / case["csv"]).read_bytes()
        fields = {
            "starting_balance_minor": str(case["starting_balance_minor"]),
            "start_date": case["start_date"],
        }
        status, body = _multipart_forecast(base_url, fields, case["csv"], csv_bytes, ssl_ctx)
        assert status == 200, f"{case['id']} forecast failed: {body}"
        assert [d["balance_minor"] for d in body["baseline"]["days"]] == case["expected_baseline_balances"]
        assert body["baseline"]["first_deficit"] == case["expected_first_deficit"]
        assert body["proposal"] == case["expected_proposal"]

        if case["expected_decisions"] is None:
            for decision_kind in ("approved", "rejected"):
                dec_status, _ = _http_call(
                    base_url,
                    "/api/decision",
                    method="POST",
                    body=json.dumps({"decision": decision_kind, "baseline": body["baseline"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    ssl_ctx=ssl_ctx,
                )
                assert dec_status == case["expected_decision_status"]
            if uses_baseline_advice:
                adv_status, adv_body = _http_call(
                    base_url,
                    "/api/advice",
                    method="POST",
                    body=json.dumps({"baseline": body["baseline"], "transactions": body["transactions"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    ssl_ctx=ssl_ctx,
                )
                assert adv_status == 422, f"{case['id']} expected /api/advice 422, got {adv_status}: {adv_body}"
        else:
            for decision_kind, expected_decision in case["expected_decisions"].items():
                dec_status, dec_body = _http_call(
                    base_url,
                    "/api/decision",
                    method="POST",
                    body=json.dumps({"decision": decision_kind, "baseline": body["baseline"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    ssl_ctx=ssl_ctx,
                )
                assert dec_status == 200, dec_body
                assert dec_body["simulated"] is True
                assert dec_body["limit_minor"] == expected_decision["limit_minor"]
                assert dec_body["largest_uncovered"] == expected_decision["largest_uncovered"]
                assert [d["uncovered_minor"] for d in dec_body["days"]] == expected_decision["uncovered_minor"]

            advice_req = (
                {"baseline": body["baseline"], "transactions": body["transactions"]}
                if uses_baseline_advice
                else {"first_deficit": body["baseline"]["first_deficit"], "transactions": body["transactions"]}
            )
            adv_status, adv_body = _http_call(
                base_url,
                "/api/advice",
                method="POST",
                body=json.dumps(advice_req).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                ssl_ctx=ssl_ctx,
                timeout=150,
            )
            if adv_status == 200:
                _assert_explanation_grounded(adv_body["explanation"], case["explanation_expectations"])
                _assert_email_draft_valid(adv_body.get("email_draft"), case.get("email_draft_expectations"))
                if returns_model:
                    assert isinstance(adv_body.get("model"), str) and adv_body["model"].strip()
            elif require_advice:
                pytest.fail(f"{case['id']} expected live /api/advice 200, got HTTP {adv_status}: {adv_body}")
            else:
                assert adv_status == 503

        move = case["scenario_move"]
        if move is not None:
            mv_status, mv_body = _multipart_forecast(
                base_url,
                {
                    **fields,
                    "move_transaction_id": move["move_transaction_id"],
                    "move_to_date": move["move_to_date"],
                },
                case["csv"],
                csv_bytes,
                ssl_ctx,
            )
            assert mv_status == 200, mv_body
            assert mv_body["baseline"] == body["baseline"]
            assert mv_body["proposal"] == body["proposal"]
            assert [d["balance_minor"] for d in mv_body["scenario"]["days"]] == move["expected_scenario_balances"]
            assert mv_body["scenario"]["first_deficit"] == move["expected_first_deficit"]

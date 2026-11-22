import importlib
import json
import sys
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from backend.main import create_app
from backend.mcp_server import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    MCP_PROTOCOL_VERSION,
    MCP_SERVER_NAME,
    MCP_SERVER_VERSION,
    create_mcp_router,
)


DEMO = Path(__file__).resolve().parents[1] / "demo"
AMALFI_CSV = DEMO / "pizzeria_amalfi_sample.csv"

CORE_TOOLS = {
    "liquidity_stress_test",
    "liquidity_optimize_payments",
    "liquidity_detect_anomalies",
    "liquidity_compare_financing",
    "cfo_action_plan",
}

OPTIONAL_CFO_TOOLS = {
    "fx_hedging_agent",
    "tax_planning_agent",
    "investment_advisory_agent",
}


def _mcp_client(mode: str = "demo") -> TestClient:
    app = FastAPI()
    app.include_router(create_mcp_router(mode))
    return TestClient(app)


@pytest.fixture(scope="module")
def amalfi_forecast() -> dict:
    """Real Pizzeria Amalfi 14-day forecast payload produced by the demo backend."""
    app_client = TestClient(create_app("demo"))
    resp = app_client.post(
        "/api/forecast",
        data={"starting_balance_minor": "500000", "start_date": "2025-06-22"},
        files={"file": (AMALFI_CSV.name, AMALFI_CSV.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _insight_args(forecast: dict, *, currency: str | None = None) -> dict:
    return {
        "baseline": forecast["baseline"],
        "transactions": forecast["transactions"],
        "currency": currency or forecast.get("currency", "EUR"),
    }


def _rpc(client: TestClient, method: str, params: dict | None = None, req_id: int | str | None = 1) -> dict:
    body: dict = {"jsonrpc": "2.0", "method": method}
    if req_id is not None:
        body["id"] = req_id
    if params is not None:
        body["params"] = params
    resp = client.post("/mcp", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_create_mcp_router_rejects_invalid_mode():
    with pytest.raises(ValueError, match="CFO_MODE"):
        create_mcp_router("staging")


def test_get_mcp_tools_manifest_structure():
    client = _mcp_client("demo")
    resp = client.get("/api/mcp/tools")
    assert resp.status_code == 200
    data = resp.json()

    assert data["protocol"] == "mcp"
    assert data["protocol_version"] == MCP_PROTOCOL_VERSION
    assert data["server_name"] == MCP_SERVER_NAME
    assert data["server_version"] == MCP_SERVER_VERSION

    tools_by_name = {tool["name"]: tool for tool in data["tools"]}
    assert CORE_TOOLS.issubset(tools_by_name.keys())

    valid_levels = {"analyzed", "recommended", "requires_approval", "simulation_only"}
    for name in CORE_TOOLS:
        tool = tools_by_name[name]
        assert tool["description"]
        assert tool["autonomy_level"] in valid_levels
        assert tool["annotations"]["autonomy_level"] == tool["autonomy_level"]
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["annotations"]["destructiveHint"] is False
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        assert "baseline" in schema["properties"]
        assert "transactions" in schema["properties"]


def test_mcp_lifecycle_initialize_initialized_ping_and_tools_list():
    client = _mcp_client("demo")

    init = _rpc(client, "initialize", {"protocolVersion": MCP_PROTOCOL_VERSION, "clientInfo": {"name": "pytest"}}, req_id=1)
    assert init["jsonrpc"] == "2.0"
    assert init["id"] == 1
    assert init["result"] == {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
    }

    # Notification without id -> HTTP 200 {}
    notif = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert notif.status_code == 200
    assert notif.json() == {}

    # Ping
    ping = _rpc(client, "ping", req_id="ping-1")
    assert ping == {"jsonrpc": "2.0", "id": "ping-1", "result": {}}

    # tools/list matches GET /api/mcp/tools
    listed = _rpc(client, "tools/list", req_id=2)
    manifest = client.get("/api/mcp/tools").json()
    assert listed["id"] == 2
    assert [t["name"] for t in listed["result"]["tools"]] == [t["name"] for t in manifest["tools"]]


@pytest.mark.parametrize(
    ("tool_name", "expected_keys"),
    [
        ("liquidity_stress_test", {"proposed_limit_minor", "scenarios", "buffer_minor", "recommended_limit_minor"}),
        ("liquidity_optimize_payments", {"proposed_limit_minor", "actions"}),
        ("liquidity_detect_anomalies", {"findings", "risk_flag", "summary", "model"}),
        ("liquidity_compare_financing", {"options", "recommended_option", "explanation", "model"}),
        ("cfo_action_plan", {"mode", "headline", "summary", "steps", "suggested_questions", "model"}),
    ],
)
def test_mcp_tools_call_core_tools_on_amalfi_forecast(amalfi_forecast, tool_name, expected_keys):
    client = _mcp_client("demo")
    resp = _rpc(
        client,
        "tools/call",
        {"name": tool_name, "arguments": _insight_args(amalfi_forecast)},
        req_id=f"call-{tool_name}",
    )

    assert "error" not in resp, resp
    result = resp["result"]
    assert result["isError"] is False
    assert isinstance(result["content"], list) and len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"

    parsed_text = json.loads(result["content"][0]["text"])
    assert parsed_text == result["structuredContent"]
    assert expected_keys.issubset(result["structuredContent"].keys())


def test_mcp_tools_call_respects_currency_context(amalfi_forecast):
    client = _mcp_client("demo")
    resp = _rpc(
        client,
        "tools/call",
        {"name": "cfo_action_plan", "arguments": _insight_args(amalfi_forecast, currency="PLN")},
        req_id="pln-check",
    )
    assert resp["result"]["isError"] is False
    structured = resp["result"]["structuredContent"]
    combined_text = structured["headline"] + " " + structured["summary"] + " " + " ".join(
        step["detail"] for step in structured["steps"]
    )
    assert "PLN" in combined_text


def test_mcp_lazy_imports_optional_cfo_agents_when_present_and_absent(monkeypatch, amalfi_forecast):
    client = _mcp_client("demo")

    # 1) Simulate backend.cfo_agents absent
    real_import = importlib.import_module

    def _missing_cfo_agents(name: str, package: str | None = None):
        if name == "backend.cfo_agents":
            raise ModuleNotFoundError("No module named 'backend.cfo_agents'")
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", _missing_cfo_agents)
    absent_names = {t["name"] for t in client.get("/api/mcp/tools").json()["tools"]}
    assert CORE_TOOLS == absent_names
    assert OPTIONAL_CFO_TOOLS.isdisjoint(absent_names)

    # Calling an unavailable optional tool returns -32602
    missing_call = _rpc(
        client,
        "tools/call",
        {"name": "fx_hedging_agent", "arguments": _insight_args(amalfi_forecast)},
        req_id=99,
    )
    assert missing_call["error"]["code"] == JSONRPC_INVALID_PARAMS

    # 2) Simulate backend.cfo_agents present with all 3 callables
    monkeypatch.setattr(importlib, "import_module", real_import)

    class _StubResponse(BaseModel):
        model_config = ConfigDict(extra="forbid")
        agent: str
        mode: str
        currency: str
        simulated: bool = True

    fake_mod = types.ModuleType("backend.cfo_agents")
    fake_mod.analyze_fx_hedging = lambda *, mode, request: _StubResponse(
        agent="fx_hedging", mode=mode, currency=request.currency
    )
    fake_mod.analyze_tax_reserve = lambda *, mode, request: _StubResponse(
        agent="tax_reserve", mode=mode, currency=request.currency
    )
    fake_mod.analyze_investments = lambda *, mode, request: _StubResponse(
        agent="investments", mode=mode, currency=request.currency
    )
    monkeypatch.setitem(sys.modules, "backend.cfo_agents", fake_mod)

    present_names = {t["name"] for t in client.get("/api/mcp/tools").json()["tools"]}
    assert (CORE_TOOLS | OPTIONAL_CFO_TOOLS).issubset(present_names)

    for tool_name, expected_agent in [
        ("fx_hedging_agent", "fx_hedging"),
        ("tax_planning_agent", "tax_reserve"),
        ("investment_advisory_agent", "investments"),
    ]:
        res = _rpc(
            client,
            "tools/call",
            {"name": tool_name, "arguments": _insight_args(amalfi_forecast, currency="EUR")},
            req_id=f"opt-{tool_name}",
        )
        assert res["result"]["isError"] is False
        assert res["result"]["structuredContent"] == {
            "agent": expected_agent,
            "mode": "demo",
            "currency": "EUR",
            "simulated": True,
        }


def test_mcp_jsonrpc_error_codes_and_no_secret_or_traceback_leaks(monkeypatch, amalfi_forecast):
    client = _mcp_client("demo")

    # Parse error (-32700)
    bad_json = client.post("/mcp", content=b"{not-valid-json", headers={"Content-Type": "application/json"})
    assert bad_json.status_code == 200
    assert bad_json.json()["error"]["code"] == JSONRPC_PARSE_ERROR

    # Invalid request (-32600): wrong jsonrpc version
    bad_ver = client.post("/mcp", json={"jsonrpc": "1.0", "id": 1, "method": "ping"})
    assert bad_ver.json()["error"]["code"] == JSONRPC_INVALID_REQUEST

    # Invalid request (-32600): non-object JSON
    bad_root = client.post("/mcp", json=["not", "an", "object"])
    assert bad_root.json()["error"]["code"] == JSONRPC_INVALID_REQUEST

    # Invalid request (-32600): boolean id is invalid per JSON-RPC 2.0
    bad_id = client.post("/mcp", json={"jsonrpc": "2.0", "id": True, "method": "ping"})
    assert bad_id.json()["error"]["code"] == JSONRPC_INVALID_REQUEST

    # Method not found (-32601)
    unknown_method = _rpc(client, "resources/read", req_id=10)
    assert unknown_method["id"] == 10
    assert unknown_method["error"]["code"] == JSONRPC_METHOD_NOT_FOUND

    # Invalid params (-32602): non-object params
    bad_params = client.post("/mcp", json={"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": ["bad"]})
    assert bad_params.json()["error"]["code"] == JSONRPC_INVALID_PARAMS

    # Invalid params (-32602): unknown tool
    unknown_tool = _rpc(client, "tools/call", {"name": "nonexistent_tool", "arguments": {}}, req_id=12)
    assert unknown_tool["error"]["code"] == JSONRPC_INVALID_PARAMS

    # Invalid params (-32602): invalid tool arguments
    bad_args = _rpc(
        client,
        "tools/call",
        {"name": "liquidity_stress_test", "arguments": {"currency": "INVALID_CCY"}},
        req_id=13,
    )
    assert bad_args["error"]["code"] == JSONRPC_INVALID_PARAMS
    assert "validation_errors" in bad_args["error"]["data"]
    assert "Traceback" not in json.dumps(bad_args)

    # Internal error (-32603): never leaks traceback or secrets
    import backend.mcp_server as mcp_mod

    def _boom(_req):
        raise RuntimeError("SECRET_API_KEY=sk-live-12345")

    monkeypatch.setattr(mcp_mod, "stress_test", _boom)
    boom_resp = _rpc(
        client,
        "tools/call",
        {"name": "liquidity_stress_test", "arguments": _insight_args(amalfi_forecast)},
        req_id=14,
    )
    assert boom_resp["error"]["code"] == JSONRPC_INTERNAL_ERROR
    serialized = json.dumps(boom_resp)
    assert "SECRET_API_KEY" not in serialized
    assert "sk-live-12345" not in serialized
    assert "Traceback" not in serialized

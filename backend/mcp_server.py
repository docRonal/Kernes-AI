"""MCP (Model Context Protocol) JSON-RPC 2.0 server and discovery router for KERNES CFO.

Exposes the deterministic Autonomous CFO tools (Liquidity, FX Hedging, Tax, and
Investment agents) over standard MCP JSON-RPC 2.0 (`POST /mcp`) plus a REST
discovery manifest (`GET /api/mcp/tools`) with Challenge Card 4-level autonomy
metadata. Uses only stdlib + FastAPI + Pydantic v2 already in `uv.lock`.
"""

from __future__ import annotations

import importlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from .action_plan import build_action_plan
from .advice import use_currency
from .advisory_extras import compare_financing_options, detect_anomalies
from .forecast import ForecastInputError
from .insights import optimize_payments, stress_test
from .models import (
    ActionPlanRequest,
    AnomalyDetectRequest,
    CompareOptionsRequest,
    InsightRequest,
)


log = logging.getLogger("autonomous_cfo.mcp")

MCP_PROTOCOL = "mcp"
MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "kernes-cfo-mcp"
MCP_SERVER_VERSION = "0.1.0"

# Standard JSON-RPC 2.0 error codes
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

AutonomyLevel = Literal["analyzed", "recommended", "requires_approval", "simulation_only"]

AUTONOMY_BADGES: dict[AutonomyLevel, str] = {
    "analyzed": "1 · Analyzed by agent",
    "recommended": "2 · Agent recommends",
    "requires_approval": "3 · Your decision needed",
    "simulation_only": "4 · Simulation only — nothing sent",
}


class McpToolAnnotations(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    readOnlyHint: Literal[True] = True
    destructiveHint: Literal[False] = False
    idempotentHint: Literal[True] = True
    openWorldHint: Literal[False] = False
    autonomy_level: AutonomyLevel
    autonomy_badge: str
    agent: str


class McpToolDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    inputSchema: dict[str, Any]
    autonomy_level: AutonomyLevel
    annotations: McpToolAnnotations


class McpManifestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol: Literal["mcp"] = MCP_PROTOCOL
    protocol_version: str = MCP_PROTOCOL_VERSION
    server_name: str = MCP_SERVER_NAME
    server_version: str = MCP_SERVER_VERSION
    tools: list[McpToolDescriptor]


@dataclass(frozen=True)
class _ToolSpec:
    name: str
    title: str
    description: str
    input_model: type[BaseModel]
    autonomy_level: AutonomyLevel
    agent: str
    handler: Callable[[str, BaseModel], BaseModel]


def _lazy_cfo_agent(fn_name: str) -> Callable[..., BaseModel] | None:
    """Lazy-import an optional agent callable from `backend.cfo_agents` if available."""
    try:
        module = importlib.import_module("backend.cfo_agents")
    except ImportError:
        return None
    fn = getattr(module, fn_name, None)
    return fn if callable(fn) else None


def _build_tool_registry() -> dict[str, _ToolSpec]:
    specs: list[_ToolSpec] = [
        _ToolSpec(
            name="liquidity_stress_test",
            title="Liquidity Stress Test",
            description=(
                "Runs deterministic 14-day cash-flow stress scenarios (3-day and 5-day inflow delays, "
                "10% higher outflows, and combined stress) to compute the recommended credit buffer."
            ),
            input_model=InsightRequest,
            autonomy_level="analyzed",
            agent="liquidity_agent",
            handler=lambda _mode, req: stress_test(req),  # type: ignore[arg-type]
        ),
        _ToolSpec(
            name="liquidity_optimize_payments",
            title="Liquidity Payment Optimizer",
            description=(
                "Ranks deterministic payment timing moves (collecting eligible invoices earlier or "
                "deferring non-mandatory supplier bills) that shrink the required credit facility."
            ),
            input_model=InsightRequest,
            autonomy_level="recommended",
            agent="liquidity_agent",
            handler=lambda _mode, req: optimize_payments(req),  # type: ignore[arg-type]
        ),
        _ToolSpec(
            name="liquidity_detect_anomalies",
            title="Liquidity Anomaly Detector",
            description=(
                "Scans recorded 14-day transactions for duplicate payments, outlier outflows, and "
                "same-day payment concentration spikes before approving any credit facility."
            ),
            input_model=AnomalyDetectRequest,
            autonomy_level="analyzed",
            agent="liquidity_agent",
            handler=lambda mode, req: detect_anomalies(mode=mode, request=req),  # type: ignore[arg-type]
        ),
        _ToolSpec(
            name="liquidity_compare_financing",
            title="Liquidity Financing Comparison",
            description=(
                "Compares deterministic minor-unit costs across a short-term credit facility, "
                "invoice factoring, and supplier outflow deferral."
            ),
            input_model=CompareOptionsRequest,
            autonomy_level="requires_approval",
            agent="liquidity_agent",
            handler=lambda mode, req: compare_financing_options(mode=mode, request=req),  # type: ignore[arg-type]
        ),
        _ToolSpec(
            name="cfo_action_plan",
            title="CFO Guided Action Plan",
            description=(
                "Composes a deterministic survival or growth action plan combining anomaly checks, "
                "payment moves, stress buffers, and owner-ready outreach drafts."
            ),
            input_model=ActionPlanRequest,
            autonomy_level="recommended",
            agent="liquidity_agent",
            handler=lambda mode, req: build_action_plan(mode=mode, request=req),  # type: ignore[arg-type]
        ),
    ]

    optional_specs: list[tuple[str, str, str, str, AutonomyLevel, str]] = [
        (
            "fx_hedging_agent",
            "analyze_fx_hedging",
            "FX Hedging Agent",
            (
                "Detects foreign-currency and cross-border supplier exposure, quantifies a 5% adverse "
                "FX shock in integer minor units, and simulates Commerzbank FX Forward and FX Option hedges."
            ),
            "simulation_only",
            "fx_hedging_agent",
        ),
        (
            "tax_planning_agent",
            "analyze_tax_reserve",
            "Tax Planning Agent",
            (
                "Calculates deterministic quarterly advance tax reserve coverage, categorizes "
                "tax-deductible operating expenses, and checks cash coverage against upcoming tax dates."
            ),
            "analyzed",
            "tax_agent",
        ),
        (
            "investment_advisory_agent",
            "analyze_investments",
            "Investment & Capex Advisory Agent",
            (
                "Computes safe investable cash surplus above the stress buffer and simulates "
                "Commerzbank Fixed-Term Deposit, Money Market Fund, or liquidity-preserving Capex Leasing."
            ),
            "simulation_only",
            "investment_agent",
        ),
    ]

    for tool_name, fn_name, title, description, autonomy_level, agent in optional_specs:
        fn = _lazy_cfo_agent(fn_name)
        if fn is not None:
            specs.append(
                _ToolSpec(
                    name=tool_name,
                    title=title,
                    description=description,
                    input_model=InsightRequest,
                    autonomy_level=autonomy_level,
                    agent=agent,
                    handler=lambda mode, req, _fn=fn: _fn(mode=mode, request=req),
                )
            )

    return {spec.name: spec for spec in specs}


def _describe_tool(spec: _ToolSpec) -> McpToolDescriptor:
    return McpToolDescriptor(
        name=spec.name,
        description=spec.description,
        inputSchema=spec.input_model.model_json_schema(),
        autonomy_level=spec.autonomy_level,
        annotations=McpToolAnnotations(
            title=spec.title,
            autonomy_level=spec.autonomy_level,
            autonomy_badge=AUTONOMY_BADGES[spec.autonomy_level],
            agent=spec.agent,
        ),
    )


def _rpc_result(req_id: str | int | None, result: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"jsonrpc": "2.0", "id": req_id, "result": result},
    )


def _rpc_error(
    req_id: str | int | None,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return JSONResponse(
        status_code=200,
        content={"jsonrpc": "2.0", "id": req_id, "error": error},
    )


def _is_valid_rpc_id(value: Any) -> bool:
    return value is None or isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def _sanitize_validation_errors(exc: ValidationError) -> list[dict[str, str]]:
    sanitized: list[dict[str, str]] = []
    for err in exc.errors(include_url=False, include_input=False):
        loc = ".".join(str(part) for part in err.get("loc", ()))
        sanitized.append(
            {
                "field": loc or "arguments",
                "message": str(err.get("msg", "Invalid value")),
                "type": str(err.get("type", "value_error")),
            }
        )
    return sanitized[:10]


def create_mcp_router(mode: str) -> APIRouter:
    if mode not in {"demo", "live"}:
        raise ValueError("CFO_MODE must be demo or live.")

    router = APIRouter(tags=["mcp"])

    @router.get(
        "/api/mcp/tools",
        response_model=McpManifestResponse,
        summary="MCP tool discovery manifest for Autonomous CFO agents",
    )
    def list_mcp_tools() -> McpManifestResponse:
        registry = _build_tool_registry()
        return McpManifestResponse(
            protocol=MCP_PROTOCOL,
            protocol_version=MCP_PROTOCOL_VERSION,
            server_name=MCP_SERVER_NAME,
            server_version=MCP_SERVER_VERSION,
            tools=[_describe_tool(spec) for spec in registry.values()],
        )

    @router.post(
        "/mcp",
        summary="MCP JSON-RPC 2.0 agent orchestration endpoint",
    )
    async def mcp_jsonrpc(request: Request) -> JSONResponse:
        raw_body = await request.body()
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _rpc_error(None, JSONRPC_PARSE_ERROR, "Parse error: invalid JSON payload.")

        if not isinstance(payload, dict):
            return _rpc_error(None, JSONRPC_INVALID_REQUEST, "Invalid Request: expected a JSON object.")

        has_id = "id" in payload
        req_id = payload.get("id")
        if has_id and not _is_valid_rpc_id(req_id):
            return _rpc_error(None, JSONRPC_INVALID_REQUEST, "Invalid Request: id must be string, integer, or null.")

        if payload.get("jsonrpc") != "2.0":
            return _rpc_error(req_id, JSONRPC_INVALID_REQUEST, "Invalid Request: jsonrpc must be '2.0'.")

        method = payload.get("method")
        if not isinstance(method, str) or not method.strip():
            return _rpc_error(req_id, JSONRPC_INVALID_REQUEST, "Invalid Request: method must be a non-empty string.")

        params = payload.get("params")
        if params is not None and not isinstance(params, dict):
            return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, "Invalid params: expected an object.")
        params_dict: dict[str, Any] = params or {}

        if method == "initialize":
            return _rpc_result(
                req_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": MCP_SERVER_NAME,
                        "version": MCP_SERVER_VERSION,
                    },
                },
            )

        if method == "notifications/initialized":
            if has_id and req_id is not None:
                return _rpc_result(req_id, {})
            return JSONResponse(status_code=200, content={})

        if method == "ping":
            return _rpc_result(req_id, {})

        if method == "tools/list":
            registry = _build_tool_registry()
            return _rpc_result(
                req_id,
                {"tools": [_describe_tool(spec).model_dump(mode="json") for spec in registry.values()]},
            )

        if method == "tools/call":
            tool_name = params_dict.get("name")
            if not isinstance(tool_name, str) or not tool_name.strip():
                return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, "Invalid params: 'name' must be a non-empty string.")

            raw_arguments = params_dict.get("arguments", {})
            if not isinstance(raw_arguments, dict):
                return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, "Invalid params: 'arguments' must be an object.")

            registry = _build_tool_registry()
            spec = registry.get(tool_name)
            if spec is None:
                return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, f"Unknown tool: {tool_name}")

            try:
                parsed_args = spec.input_model.model_validate(raw_arguments)
            except ValidationError as exc:
                return _rpc_error(
                    req_id,
                    JSONRPC_INVALID_PARAMS,
                    f"Invalid arguments for tool '{tool_name}'.",
                    data={"validation_errors": _sanitize_validation_errors(exc)},
                )

            currency = getattr(parsed_args, "currency", "EUR")
            try:
                with use_currency(currency):
                    result_model = spec.handler(mode, parsed_args)
            except ForecastInputError as exc:
                return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, str(exc))
            except HTTPException as exc:
                if 400 <= exc.status_code < 500:
                    return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, str(exc.detail))
                log.warning("MCP tool '%s' upstream error status=%s", tool_name, exc.status_code)
                return _rpc_result(
                    req_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({"error": "Tool execution temporarily unavailable."}),
                            }
                        ],
                        "structuredContent": {"error": "Tool execution temporarily unavailable."},
                        "isError": True,
                    },
                )
            except ValueError as exc:
                return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, str(exc))
            except Exception:
                log.exception("Unexpected error executing MCP tool '%s'", tool_name)
                return _rpc_error(req_id, JSONRPC_INTERNAL_ERROR, "Internal tool execution error.")

            structured = (
                result_model.model_dump(mode="json")
                if isinstance(result_model, BaseModel)
                else result_model
            )
            return _rpc_result(
                req_id,
                {
                    "content": [{"type": "text", "text": json.dumps(structured)}],
                    "structuredContent": structured,
                    "isError": False,
                },
            )

        return _rpc_error(req_id, JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}")

    return router

"""Optional zero-dependency MLflow REST telemetry for LLM inference monitoring.

When ``MLFLOW_TRACKING_URI`` is configured, each live model call logs its
operational metadata (endpoint, model name, status, attempts, latency, grounding
outcome) asynchronously via the MLflow 2.0 REST API without adding third-party
dependencies or ever blocking user requests. Prompts, CSV data, and tokens are
never transmitted or logged.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


log = logging.getLogger("autonomous_cfo.telemetry")

DEFAULT_EXPERIMENT_NAME = "kernes-cfo"
MLFLOW_TIMEOUT_SECONDS = 5.0

_cache_lock = threading.Lock()
_experiment_ids: dict[tuple[str, str], str] = {}


def _ssl_context() -> ssl.SSLContext | None:
    ca_bundle = os.environ.get("CFO_CA_BUNDLE", "").strip()
    if not ca_bundle:
        return None
    return ssl.create_default_context(cafile=ca_bundle)


def _mlflow_call(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    token: str | None = None,
    ssl_context: ssl.SSLContext | None = None,
) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=MLFLOW_TIMEOUT_SECONDS, context=ssl_context) as resp:
            raw = resp.read(262_144).decode("utf-8", errors="replace")
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read(65_536).decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {}


def _ensure_experiment_id(
    base_url: str,
    experiment_name: str,
    *,
    token: str | None,
    ssl_context: ssl.SSLContext | None,
) -> str:
    cache_key = (base_url, experiment_name)
    with _cache_lock:
        cached = _experiment_ids.get(cache_key)
    if cached:
        return cached

    quoted = urllib.parse.quote(experiment_name, safe="")
    status, payload = _mlflow_call(
        "GET",
        f"{base_url}/api/2.0/mlflow/experiments/get-by-name?experiment_name={quoted}",
        token=token,
        ssl_context=ssl_context,
    )
    exp_id = (payload.get("experiment") or {}).get("experiment_id") if status == 200 else None

    if not exp_id:
        c_status, c_payload = _mlflow_call(
            "POST",
            f"{base_url}/api/2.0/mlflow/experiments/create",
            body={"name": experiment_name},
            token=token,
            ssl_context=ssl_context,
        )
        if c_status == 200:
            exp_id = c_payload.get("experiment_id")
        else:
            # Handle race condition if another worker created it in the meantime.
            r_status, r_payload = _mlflow_call(
                "GET",
                f"{base_url}/api/2.0/mlflow/experiments/get-by-name?experiment_name={quoted}",
                token=token,
                ssl_context=ssl_context,
            )
            if r_status == 200:
                exp_id = (r_payload.get("experiment") or {}).get("experiment_id")

    if not exp_id:
        raise RuntimeError(f"Could not resolve MLflow experiment '{experiment_name}'.")

    with _cache_lock:
        _experiment_ids[cache_key] = str(exp_id)
    return str(exp_id)


def _send_run(
    *,
    base_url: str,
    experiment_name: str,
    token: str | None,
    ssl_context: ssl.SSLContext | None,
    endpoint: str,
    model: str,
    latency_ms: int,
    status: str,
    attempts: int,
    grounded: bool,
    fallback_used: bool,
) -> None:
    try:
        now_ms = int(time.time() * 1000)
        exp_id = _ensure_experiment_id(base_url, experiment_name, token=token, ssl_context=ssl_context)
        c_status, created = _mlflow_call(
            "POST",
            f"{base_url}/api/2.0/mlflow/runs/create",
            body={
                "experiment_id": exp_id,
                "run_name": endpoint,
                "start_time": now_ms,
                "tags": [
                    {"key": "mlflow.runName", "value": endpoint},
                    {"key": "endpoint", "value": endpoint},
                    {"key": "status", "value": status},
                ],
            },
            token=token,
            ssl_context=ssl_context,
        )
        run_id = (created.get("run") or {}).get("info", {}).get("run_id") if c_status == 200 else None
        if not run_id:
            return

        _mlflow_call(
            "POST",
            f"{base_url}/api/2.0/mlflow/runs/log-batch",
            body={
                "run_id": run_id,
                "metrics": [
                    {"key": "latency_ms", "value": float(max(0, latency_ms)), "timestamp": now_ms, "step": 0},
                    {"key": "attempts", "value": float(max(1, attempts)), "timestamp": now_ms, "step": 0},
                    {"key": "grounded_ok", "value": 1.0 if grounded else 0.0, "timestamp": now_ms, "step": 0},
                    {"key": "fallback_used", "value": 1.0 if fallback_used else 0.0, "timestamp": now_ms, "step": 0},
                ],
                "params": [
                    {"key": "endpoint", "value": endpoint[:250]},
                    {"key": "model", "value": (model or "unknown")[:250]},
                    {"key": "status", "value": status[:64]},
                ],
            },
            token=token,
            ssl_context=ssl_context,
        )
        _mlflow_call(
            "POST",
            f"{base_url}/api/2.0/mlflow/runs/update",
            body={
                "run_id": run_id,
                "status": "FINISHED" if status == "ok" else "FAILED",
                "end_time": now_ms + max(0, int(latency_ms)),
            },
            token=token,
            ssl_context=ssl_context,
        )
    except Exception as exc:
        log.debug("mlflow telemetry skipped: %s", exc)


def log_llm_call(
    *,
    endpoint: str,
    model: str,
    latency_ms: int,
    status: str,
    attempts: int = 1,
    grounded: bool = True,
    fallback_used: bool = False,
    sync: bool = False,
) -> None:
    """Log operational metadata for an LLM call to MLflow when ``MLFLOW_TRACKING_URI`` is set."""
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip().rstrip("/")
    if not tracking_uri.startswith(("http://", "https://")):
        return

    experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", DEFAULT_EXPERIMENT_NAME).strip() or DEFAULT_EXPERIMENT_NAME
    token = os.environ.get("MLFLOW_TRACKING_TOKEN") or None
    ssl_context = _ssl_context()

    kwargs = {
        "base_url": tracking_uri,
        "experiment_name": experiment_name,
        "token": token,
        "ssl_context": ssl_context,
        "endpoint": endpoint,
        "model": model,
        "latency_ms": latency_ms,
        "status": status,
        "attempts": attempts,
        "grounded": grounded,
        "fallback_used": fallback_used,
    }
    if sync:
        _send_run(**kwargs)
        return

    thread = threading.Thread(target=_send_run, kwargs=kwargs, daemon=True)
    thread.start()

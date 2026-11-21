import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from backend import telemetry


def test_mlflow_telemetry_is_noop_when_unconfigured(monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    telemetry.log_llm_call(
        endpoint="advice",
        model="kernes-qwen-7b",
        latency_ms=1200,
        status="ok",
        sync=True,
    )


def test_mlflow_telemetry_logs_metadata_without_secrets(monkeypatch):
    calls: list[tuple[str, str, dict | None, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            auth = self.headers.get("Authorization")
            calls.append(("GET", self.path, None, auth))
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error_code": "RESOURCE_DOES_NOT_EXIST"}).encode())

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            auth = self.headers.get("Authorization")
            calls.append(("POST", self.path, payload, auth))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if self.path.endswith("/experiments/create"):
                resp = {"experiment_id": "exp-42"}
            elif self.path.endswith("/runs/create"):
                resp = {"run": {"info": {"run_id": "run-99"}}}
            else:
                resp = {}
            self.wfile.write(json.dumps(resp).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        telemetry._experiment_ids.clear()
        monkeypatch.setenv("MLFLOW_TRACKING_URI", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("MLFLOW_EXPERIMENT_NAME", "kernes-test")
        monkeypatch.setenv("MLFLOW_TRACKING_TOKEN", "secret-mlflow-token")

        telemetry.log_llm_call(
            endpoint="advice",
            model="kernes-qwen-7b",
            latency_ms=850,
            status="ok",
            attempts=1,
            grounded=True,
            fallback_used=False,
            sync=True,
        )
    finally:
        server.shutdown()

    paths = [path.split("?", 1)[0] for _, path, _, _ in calls]
    assert paths == [
        "/api/2.0/mlflow/experiments/get-by-name",
        "/api/2.0/mlflow/experiments/create",
        "/api/2.0/mlflow/runs/create",
        "/api/2.0/mlflow/runs/log-batch",
        "/api/2.0/mlflow/runs/update",
    ]
    assert all(auth == "Bearer secret-mlflow-token" for _, _, _, auth in calls)
    serialized = json.dumps([payload for _, _, payload, _ in calls if payload is not None])
    assert "secret-mlflow-token" not in serialized
    log_batch = calls[3][2]
    assert {m["key"]: m["value"] for m in log_batch["metrics"]} == {
        "latency_ms": 850.0,
        "attempts": 1.0,
        "grounded_ok": 1.0,
        "fallback_used": 0.0,
    }


def test_mlflow_telemetry_swallows_endpoint_errors(monkeypatch):
    telemetry._experiment_ids.clear()
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")
    telemetry.log_llm_call(
        endpoint="ask-cfo",
        model="kernes-qwen",
        latency_ms=400,
        status="error",
        grounded=False,
        sync=True,
    )

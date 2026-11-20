import io
import json
import socket
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


DEMO = Path(__file__).resolve().parents[1] / "demo"


def _sample_payload() -> dict:
    forecast = json.loads((DEMO / "forecast.example.json").read_text(encoding="utf-8"))
    return {
        "first_deficit": forecast["baseline"]["first_deficit"],
        "transactions": forecast["transactions"],
    }


class _FakeResponse:
    def __init__(self, body: dict):
        self._raw = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_live_advice_requires_endpoint_configuration(monkeypatch):
    monkeypatch.delenv("CFO_MODEL_URL", raising=False)
    monkeypatch.delenv("CFO_MODEL_NAME", raising=False)
    client = TestClient(create_app("live"))

    response = client.post("/api/advice", json=_sample_payload())
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_live_advice_calls_openshift_ai_and_verifies_figures(monkeypatch):
    monkeypatch.setenv("CFO_MODEL_URL", "http://kernes-qwen.local:8080/v1/chat/completions")
    monkeypatch.setenv("CFO_MODEL_NAME", "kernes-qwen")
    monkeypatch.setenv("CFO_MODEL_TOKEN", "secret-token")
    monkeypatch.setenv("CFO_MODEL_TIMEOUT_SECONDS", "12")

    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "explanation": (
                                        "On 2026-11-27, cash drops by 5,000.00 PLN because "
                                        "payroll and rent clear before INV-001."
                                    ),
                                    "email_draft": (
                                        "Hello, could you settle invoice INV-001 by 2026-11-26?"
                                    ),
                                }
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = TestClient(create_app("live"))

    response = client.post("/api/advice", json=_sample_payload())
    assert response.status_code == 200
    data = response.json()
    assert "5,000.00 PLN" in data["explanation"]
    assert "INV-001" in data["email_draft"]

    assert captured["url"] == "http://kernes-qwen.local:8080/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer secret-token"
    assert captured["timeout"] == 12.0
    assert captured["body"]["model"] == "kernes-qwen"
    user_prompt = captured["body"]["messages"][1]["content"]
    assert "2026-11-27" in user_prompt
    assert "5,000.00 PLN" in user_prompt
    assert "INV-001" in user_prompt


def test_live_advice_accepts_fenced_json_and_omits_auth_when_no_token(monkeypatch):
    monkeypatch.setenv("CFO_MODEL_URL", "http://kernes-qwen.local:8080/v1/chat/completions")
    monkeypatch.setenv("CFO_MODEL_NAME", "kernes-qwen")
    monkeypatch.delenv("CFO_MODEL_TOKEN", raising=False)

    captured_headers = {}

    def fake_urlopen(req, timeout):
        captured_headers.update({k.lower(): v for k, v in req.header_items()})
        fenced = (
            "```json\n"
            + json.dumps(
                {
                    "explanation": "Projected shortfall of 5000 PLN on November 27 due to Payroll.",
                    "email_draft": "Please pay INV-001 earlier if possible.",
                }
            )
            + "\n```"
        )
        return _FakeResponse({"choices": [{"message": {"content": fenced}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = TestClient(create_app("live"))

    response = client.post("/api/advice", json=_sample_payload())
    assert response.status_code == 200
    assert "authorization" not in captured_headers


@pytest.mark.parametrize(
    "exc",
    [
        TimeoutError("timed out"),
        socket.timeout("timed out"),
        urllib.error.URLError(TimeoutError("timed out")),
    ],
)
def test_live_advice_handles_timeouts_with_503(monkeypatch, exc):
    monkeypatch.setenv("CFO_MODEL_URL", "http://kernes-qwen.local:8080/v1/chat/completions")
    monkeypatch.setenv("CFO_MODEL_NAME", "kernes-qwen")

    def fake_urlopen(req, timeout):
        raise exc

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = TestClient(create_app("live"))

    response = client.post("/api/advice", json=_sample_payload())
    assert response.status_code == 503
    assert "timed out" in response.json()["detail"].lower()


def test_live_advice_handles_http_and_connection_errors_with_503(monkeypatch):
    monkeypatch.setenv("CFO_MODEL_URL", "http://kernes-qwen.local:8080/v1/chat/completions")
    monkeypatch.setenv("CFO_MODEL_NAME", "kernes-qwen")

    def raise_http_error(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url, 502, "Bad Gateway", hdrs=None, fp=io.BytesIO(b"bad gateway")
        )

    monkeypatch.setattr("urllib.request.urlopen", raise_http_error)
    client = TestClient(create_app("live"))
    response = client.post("/api/advice", json=_sample_payload())
    assert response.status_code == 503
    assert "502" in response.json()["detail"]

    def raise_url_error(req, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", raise_url_error)
    response = client.post("/api/advice", json=_sample_payload())
    assert response.status_code == 503


@pytest.mark.parametrize(
    "content",
    [
        "not json at all",
        json.dumps({"explanation": "Only explanation"}),
        json.dumps(
            {
                "explanation": "Shortfall of 9,999.00 PLN on 2026-11-27 for INV-001.",
                "email_draft": "Please pay INV-001.",
            }
        ),
        json.dumps(
            {
                "explanation": "Shortfall of 5,000.00 PLN next week for INV-001.",
                "email_draft": "Please pay INV-001.",
            }
        ),
        json.dumps(
            {
                "explanation": "Shortfall of 5,000.00 PLN on 2026-11-27.",
                "email_draft": "Please pay your invoice soon.",
            }
        ),
    ],
)
def test_live_advice_rejects_invalid_or_ungrounded_model_output(monkeypatch, content):
    monkeypatch.setenv("CFO_MODEL_URL", "http://kernes-qwen.local:8080/v1/chat/completions")
    monkeypatch.setenv("CFO_MODEL_NAME", "kernes-qwen")

    def fake_urlopen(req, timeout):
        return _FakeResponse({"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = TestClient(create_app("live"))

    response = client.post("/api/advice", json=_sample_payload())
    assert response.status_code == 503

"""OpenShift AI adapter and demo-mode handler for /api/advice."""

from __future__ import annotations

import json
import os
import re
import socket
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError

from .models import AdviceRequest, AdviceResponse, Transaction


DEMO_DIR = Path(__file__).resolve().parents[1] / "demo"
DEFAULT_TIMEOUT_SECONDS = 15.0

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def _format_pln(amount_minor: int) -> str:
    """Format integer grosz as a PLN string with two decimal places."""
    sign = "-" if amount_minor < 0 else ""
    abs_minor = abs(amount_minor)
    whole, frac = divmod(abs_minor, 100)
    return f"{sign}{whole:,}.{frac:02d} PLN"


def _read_timeout_seconds() -> float:
    raw = os.environ.get("CFO_MODEL_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise HTTPException(503, "Invalid CFO_MODEL_TIMEOUT_SECONDS configuration.") from exc
    if value <= 0:
        raise HTTPException(503, "CFO_MODEL_TIMEOUT_SECONDS must be positive.")
    return value


def _build_messages(request: AdviceRequest) -> list[dict[str, str]]:
    """Build grounded system and user messages for the OpenShift AI model."""
    shortfall_minor = request.first_deficit.shortfall_minor
    shortfall_date = request.first_deficit.date.isoformat()
    shortfall_pln = _format_pln(shortfall_minor)

    tx_lines = []
    for tx in sorted(request.transactions, key=lambda item: (item.date, item.id)):
        direction = "inflow" if tx.amount_minor >= 0 else "outflow"
        tx_lines.append(
            f"- {tx.id} | {tx.date.isoformat()} | {direction} | {_format_pln(tx.amount_minor)} | {tx.label}"
        )
    tx_block = "\n".join(tx_lines) if tx_lines else "- (none provided)"

    system_prompt = (
        "You are an Autonomous CFO Liquidity Agent. "
        "Explain the projected cash shortfall and draft a polite payment reminder email. "
        "Return ONLY valid JSON with two string keys: \"explanation\" and \"email_draft\". "
        "Use ONLY the exact figures, dates, and transaction IDs supplied by the user. "
        "Include the exact shortfall date and shortfall amount in PLN in \"explanation\", "
        "and reference the relevant incoming invoice ID (if any) in \"email_draft\". "
        "Do not invent numbers or perform new calculations."
    )

    user_prompt = (
        f"First projected shortfall:\n"
        f"- Date: {shortfall_date}\n"
        f"- Shortfall amount: {shortfall_pln} ({shortfall_minor} grosz)\n\n"
        f"Transactions:\n{tx_block}\n\n"
        f"Respond with JSON: {{\"explanation\": \"...\", \"email_draft\": \"...\"}}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _extract_json_object(content: str) -> dict:
    """Parse a JSON object from model output, tolerating markdown code fences."""
    cleaned = content.strip()
    fence_match = _CODE_FENCE_RE.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            raise HTTPException(503, "OpenShift AI returned non-JSON advice content.")
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise HTTPException(503, "OpenShift AI returned invalid JSON advice content.") from exc

    if not isinstance(parsed, dict):
        raise HTTPException(503, "OpenShift AI returned a non-object JSON payload.")
    return parsed


def _amount_patterns(amount_minor: int) -> list[str]:
    """Return formatted numeric representations (without currency) for grounding checks."""
    whole, frac = divmod(abs(amount_minor), 100)
    patterns = [
        f"{whole}.{frac:02d}",
        f"{whole:,}.{frac:02d}",
        f"{whole:,}.{frac:02d}".replace(",", " "),
    ]
    if frac == 0:
        patterns.extend([str(whole), f"{whole:,}", f"{whole:,}".replace(",", " ")])
    return patterns


def _date_patterns(target_date: date) -> list[str]:
    """Return common date representations for grounding checks."""
    return [
        target_date.isoformat(),
        f"{target_date.strftime('%B')} {target_date.day}",
        f"{target_date.day} {target_date.strftime('%B')}",
        f"{target_date.strftime('%b')} {target_date.day}",
        f"{target_date.day} {target_date.strftime('%b')}",
        target_date.strftime("%d.%m.%Y"),
        target_date.strftime("%d.%m"),
    ]


def _contains_any(haystack: str, needles: list[str]) -> bool:
    lowered = haystack.lower()
    return any(needle.lower() in lowered for needle in needles)


def _verify_grounded_response(
    advice: AdviceResponse,
    request: AdviceRequest,
) -> None:
    """Verify that the model's response uses the supplied shortfall figures and context."""
    explanation = advice.explanation.strip()
    email_draft = advice.email_draft.strip()
    if not explanation or not email_draft:
        raise HTTPException(503, "OpenShift AI returned empty explanation or email draft.")

    combined = f"{explanation}\n{email_draft}"

    amount_ok = _contains_any(explanation, _amount_patterns(request.first_deficit.shortfall_minor))
    date_ok = _contains_any(explanation, _date_patterns(request.first_deficit.date))
    if not amount_ok or not date_ok:
        raise HTTPException(
            503,
            "OpenShift AI response did not reference the supplied shortfall date and amount.",
        )

    if request.transactions:
        tx_tokens: list[str] = []
        for tx in request.transactions:
            tx_tokens.append(tx.id)
            if len(tx.label.strip()) >= 3:
                tx_tokens.append(tx.label.strip())
        if tx_tokens and not _contains_any(combined, tx_tokens):
            raise HTTPException(
                503,
                "OpenShift AI response did not reference any supplied transactions.",
            )


def _call_openshift_ai(request: AdviceRequest) -> AdviceResponse:
    """Call an OpenAI-compatible OpenShift AI chat completions endpoint."""
    url = os.environ.get("CFO_MODEL_URL", "").strip()
    model_name = os.environ.get("CFO_MODEL_NAME", "").strip()
    token = os.environ.get("CFO_MODEL_TOKEN", "").strip()

    if not url or not model_name:
        raise HTTPException(503, "OpenShift AI is not configured (CFO_MODEL_URL / CFO_MODEL_NAME missing).")

    timeout = _read_timeout_seconds()
    payload = {
        "model": model_name,
        "temperature": 0.1,
        "messages": _build_messages(request),
    }

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    http_request = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8")
    except (TimeoutError, socket.timeout) as exc:
        raise HTTPException(503, "OpenShift AI request timed out.") from exc
    except urllib.error.HTTPError as exc:
        raise HTTPException(503, f"OpenShift AI returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise HTTPException(503, "OpenShift AI request timed out.") from exc
        raise HTTPException(503, "OpenShift AI is unavailable.") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise HTTPException(503, "Failed to read OpenShift AI response.") from exc

    try:
        upstream = json.loads(raw_body)
        content = upstream["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(503, "OpenShift AI returned an unexpected response structure.") from exc

    if not isinstance(content, str):
        raise HTTPException(503, "OpenShift AI returned non-text completion content.")

    parsed = _extract_json_object(content)
    try:
        advice = AdviceResponse.model_validate(parsed)
    except ValidationError as exc:
        raise HTTPException(503, "OpenShift AI response did not match the advice contract.") from exc

    _verify_grounded_response(advice, request)
    return advice


def get_advice(*, mode: str, request: AdviceRequest) -> AdviceResponse:
    if mode == "live":
        return _call_openshift_ai(request)

    forecast = json.loads((DEMO_DIR / "forecast.example.json").read_text(encoding="utf-8"))
    expected = {
        "first_deficit": forecast["baseline"]["first_deficit"],
        "transactions": forecast["transactions"],
    }
    if request.model_dump(mode="json") != expected:
        raise HTTPException(422, "Submit the bundled baseline forecast in demo mode.")

    return AdviceResponse.model_validate_json(
        (DEMO_DIR / "advice.example.json").read_text(encoding="utf-8")
    )

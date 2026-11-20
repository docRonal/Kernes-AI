"""Explanations and reminder drafts from the model served on OpenShift AI.

The model never calculates. The server recalculates the proposal from the
forecast, formats every figure, and sends those facts to the model. It then
checks that each PLN amount in the explanation is one of those facts and that
the explanation cites the proposed limit.
"""

import json
import logging
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from fastapi import HTTPException

from .forecast import horizon, propose
from .models import AdviceRequest, AdviceResponse, Proposal, Transaction


DEMO_DIR = Path(__file__).resolve().parents[1] / "demo"
DEFAULT_TIMEOUT_SECONDS = 90
MAX_TOKENS = 450
ATTEMPTS = 2

log = logging.getLogger("autonomous_cfo.advice")

# Thousands separators: comma, no-break space and narrow no-break space. A plain
# space is left out so "November 27, 5,000 PLN" isn't read as 275,000.
_DIGITS = r"\d[\d,\u00a0\u202f]*(?:\.\d{1,2})?"
_AMOUNT = re.compile(
    rf"(?:PLN|zł|zl)\s*[-−]?\s*({_DIGITS})|({_DIGITS})\s*(?:PLN|zł|zl)\b",
    re.IGNORECASE,
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "explanation": {"type": "string"},
        "email_draft": {"type": "string"},
    },
    "required": ["explanation", "email_draft"],
}

SYSTEM_PROMPT = """You are the Liquidity Agent of a small company's finance assistant.
The application has already calculated every figure. You only explain them.
Rules:
- Use only the facts you are given. Copy amounts and dates exactly as written.
- Never calculate, round or invent an amount, date, transaction, fee, penalty or interest rate.
- Write plain English for a busy business owner. No markdown, no bullet points.
- Reply with JSON: {"explanation": "...", "email_draft": "..."}."""


class ModelError(RuntimeError):
    """The model is unreachable or its answer can't be used."""


@dataclass(frozen=True)
class ModelConfig:
    url: str
    name: str
    token: str | None
    timeout: float
    ssl_context: ssl.SSLContext | None = None

    @classmethod
    def from_env(cls) -> "ModelConfig":
        url = os.environ.get("CFO_MODEL_URL", "").strip()
        name = os.environ.get("CFO_MODEL_NAME", "").strip()
        if not url.startswith(("http://", "https://")) or not name:
            raise ModelError("The model endpoint isn't configured. Set CFO_MODEL_URL and CFO_MODEL_NAME.")
        raw_timeout = os.environ.get("CFO_MODEL_TIMEOUT") or os.environ.get("CFO_MODEL_TIMEOUT_SECONDS") or ""
        try:
            timeout = float(raw_timeout) if raw_timeout.strip() else DEFAULT_TIMEOUT_SECONDS
            if timeout <= 0:
                timeout = DEFAULT_TIMEOUT_SECONDS
        except ValueError:
            timeout = DEFAULT_TIMEOUT_SECONDS
        ca_bundle = os.environ.get("CFO_CA_BUNDLE", "").strip()
        ssl_context: ssl.SSLContext | None = None
        if ca_bundle:
            try:
                ssl_context = ssl.create_default_context(cafile=ca_bundle)
            except (OSError, ssl.SSLError) as exc:
                raise ModelError("Invalid CFO_CA_BUNDLE configuration.") from exc
        return cls(
            url=url,
            name=name,
            token=os.environ.get("CFO_MODEL_TOKEN") or None,
            timeout=timeout,
            ssl_context=ssl_context,
        )

    @classmethod
    def fallback_from_env(cls, *, timeout: float, ssl_context: ssl.SSLContext | None) -> "ModelConfig | None":
        url = os.environ.get("CFO_FALLBACK_MODEL_URL", "").strip()
        name = os.environ.get("CFO_FALLBACK_MODEL_NAME", "").strip()
        if not url.startswith(("http://", "https://")) or not name:
            return None
        return cls(
            url=url,
            name=name,
            token=os.environ.get("CFO_FALLBACK_MODEL_TOKEN") or os.environ.get("CFO_MODEL_TOKEN") or None,
            timeout=timeout,
            ssl_context=ssl_context,
        )


# ─── Facts ───────────────────────────────────────────────────────────────────


def pln(minor: int) -> str:
    sign = "-" if minor < 0 else ""
    whole, grosz = divmod(abs(minor), 100)
    return f"{sign}PLN {whole:,}.{grosz:02d}"


def day_name(day: date) -> str:
    return f"{day:%A}, {day:%B} {day.day}"


@dataclass(frozen=True)
class Facts:
    proposal: Proposal
    lines: list[str]
    reminder: str | None
    allowed_minor: frozenset[int]


def build_facts(request: AdviceRequest) -> Facts:
    baseline = request.baseline
    window = horizon(baseline.days[0].date)
    if [day.date for day in baseline.days] != window:
        raise HTTPException(422, "The baseline must list 14 consecutive days.")
    proposal = propose(baseline, request.transactions)
    if proposal is None:
        raise HTTPException(422, "The baseline never goes below zero, so there is nothing to explain.")

    first, deepest = proposal.first_shortfall, proposal.deepest_shortfall
    deepest_index = next(index for index, day in enumerate(baseline.days) if day.date == deepest.date)
    recovery = next((day for day in baseline.days[deepest_index + 1 :] if day.balance_minor >= 0), None)
    relevant = [t for t in sorted(request.transactions, key=lambda t: t.date) if t.id in proposal.relevant_transaction_ids]

    lines = [
        f"Forecast period: {day_name(window[0])} to {day_name(window[-1])}, {window[0].year}.",
        f"First day below zero: {day_name(first.date)}, balance {pln(-first.shortfall_minor)}.",
    ]
    if deepest.date == first.date:
        lines.append(f"This is also the deepest point of the forecast: a gap of {pln(deepest.shortfall_minor)}.")
    else:
        lines.append(f"Deepest point: {day_name(deepest.date)}, balance {pln(-deepest.shortfall_minor)}.")
    lines.append(
        f"Proposed credit facility limit: {pln(proposal.limit_minor)}. "
        "It equals the deepest projected gap, so it covers every day of the forecast."
    )
    if recovery:
        lines.append(f"The balance is back above zero on {day_name(recovery.date)} at {pln(recovery.balance_minor)}.")
    else:
        lines.append("The balance stays below zero until the end of the 14-day forecast.")
    lines.append("Transactions that cause and close the gap:")
    for t in relevant:
        direction = "incoming" if t.amount_minor > 0 else "outgoing"
        lines.append(f"- {day_name(t.date)}: {t.label} ({t.id}), {direction} {pln(abs(t.amount_minor))}.")

    reminder = _reminder_target(request.transactions, first.date, window)
    allowed = {proposal.limit_minor, first.shortfall_minor, deepest.shortfall_minor}
    allowed |= {abs(day.balance_minor) for day in baseline.days}
    allowed |= {abs(t.amount_minor) for t in request.transactions}
    return Facts(proposal=proposal, lines=lines, reminder=reminder, allowed_minor=frozenset(allowed))


def _reminder_target(transactions: list[Transaction], first_gap: date, window: list[date]) -> str | None:
    """The first incoming payment after the gap starts: the one worth asking for early."""
    late = [t for t in transactions if t.amount_minor > 0 and first_gap < t.date <= window[-1]]
    if not late:
        return None
    target = min(late, key=lambda t: (t.date, -t.amount_minor))
    pay_by = max(window[0], first_gap - timedelta(days=1))
    return (
        f"Ask the client to pay {target.label} {target.id} for {pln(target.amount_minor)}, "
        f"currently due {day_name(target.date)}, by {day_name(pay_by)} instead."
    )


def build_messages(facts: Facts) -> list[dict[str, str]]:
    limit = pln(facts.proposal.limit_minor)
    task = [
        "Facts:",
        *facts.lines,
        "",
        "Task 1, explanation: write exactly 3 sentences about the forecast, in the future tense "
        '("is projected to"). Sentence 1: when the balance first goes below zero and by how much, and the '
        "deepest point if it is a different day. Sentence 2: which transactions cause the gap and when money "
        f"comes back. Sentence 3: why a credit facility of {limit} covers the gap, and that the owner can "
        "approve or reject this proposal. Do not mention any email.",
    ]
    if facts.reminder:
        task.append(
            "Task 2, email_draft: a polite payment reminder to the client, under 70 words. Start with "
            f'"Hello,". {facts.reminder} Do not mention the credit facility, fees or penalties. '
            'End with "Kind regards,\nThe finance team".'
        )
    else:
        task.append('Task 2: there is no incoming payment to ask for, so set email_draft to "".')
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": "\n".join(task)}]


# ─── Checking the answer ─────────────────────────────────────────────────────


def cited_amounts(text: str) -> list[int]:
    amounts = []
    for match in _AMOUNT.finditer(text):
        raw = (match.group(1) or match.group(2)).replace(",", "").replace("\u00a0", "").replace("\u202f", "").strip(".")
        whole, _, fraction = raw.partition(".")
        if whole.isdigit():
            amounts.append(int(whole) * 100 + int((fraction + "00")[:2] or 0))
    return amounts


def check_explanation(text: str, facts: Facts) -> str | None:
    """Return a problem with the explanation's figures, or None when they match."""
    amounts = cited_amounts(text)
    unknown = [amount for amount in amounts if amount not in facts.allowed_minor]
    if unknown:
        return f"it cites {pln(unknown[0])}, which isn't in the forecast"
    if facts.proposal.limit_minor not in amounts:
        return f"it doesn't cite the proposed limit of {pln(facts.proposal.limit_minor)}"
    return None


# The reminder goes to a client, so it must not invent fees or reveal internal liquidity terms.
_OFF_LIMITS = re.compile(
    r"\b(fee|fees|penalt\w*|interest|credit|facility|forecast|balance|overdraft|shortfall|deficit)\b",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def clean_reminder(draft: str, facts: Facts) -> str:
    """Drop sentences that mention off-limits topics or amounts that aren't in the transactions."""
    lines = []
    for line in draft.splitlines():
        kept = [
            sentence
            for sentence in _SENTENCE_END.split(line)
            if not _OFF_LIMITS.search(sentence)
            and all(amount in facts.allowed_minor for amount in cited_amounts(sentence))
        ]
        lines.append(" ".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def parse_answer(content: str) -> tuple[str, str]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelError("The model didn't return JSON.") from exc
    explanation = data.get("explanation") if isinstance(data, dict) else None
    draft = data.get("email_draft", "") if isinstance(data, dict) else None
    if not isinstance(explanation, str) or not explanation.strip() or not isinstance(draft, str):
        raise ModelError("The model's answer is missing the explanation.")
    return explanation.strip(), draft.strip()


# ─── Model call ──────────────────────────────────────────────────────────────


def call_model(config: ModelConfig, messages: list[dict[str, str]]) -> str:
    body = {
        "model": config.name,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_schema", "json_schema": {"name": "advice", "schema": OUTPUT_SCHEMA}},
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if config.token:
        headers["Authorization"] = f"Bearer {config.token}"
    request = urllib.request.Request(config.url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=config.timeout, context=config.ssl_context) as response:
            payload = json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as exc:
        raise ModelError(f"The model endpoint answered HTTP {exc.code}.") from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
        raise ModelError("The model endpoint can't be reached or timed out.") from exc
    except json.JSONDecodeError as exc:
        raise ModelError("The model endpoint returned something other than JSON.") from exc
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelError("The model endpoint returned an unexpected response.") from exc


def _run_attempts(
    config: ModelConfig,
    facts: Facts,
    messages: list[dict[str, str]],
    started: float,
) -> AdviceResponse:
    problem = "no answer"
    for attempt in range(1, ATTEMPTS + 1):
        explanation, draft = parse_answer(call_model(config, messages))
        problem = check_explanation(explanation, facts)
        if problem is None:
            latency = round((time.monotonic() - started) * 1000)
            log.info("advice model=%s attempts=%d latency_ms=%d status=ok", config.name, attempt, latency)
            return AdviceResponse(
                explanation=explanation,
                email_draft=(clean_reminder(draft, facts) or None) if facts.reminder else None,
                model=config.name,
                latency_ms=latency,
            )
        log.warning("advice model=%s attempt=%d rejected: %s", config.name, attempt, problem)
    raise ModelError(f"The model's explanation didn't match the calculated figures: {problem}.")


def live_advice(request: AdviceRequest) -> AdviceResponse:
    facts = build_facts(request)
    primary = ModelConfig.from_env()
    messages = build_messages(facts)
    started = time.monotonic()
    try:
        return _run_attempts(primary, facts, messages, started)
    except ModelError as primary_exc:
        fallback = ModelConfig.fallback_from_env(
            timeout=primary.timeout,
            ssl_context=primary.ssl_context,
        )
        if fallback is None:
            raise
        log.warning(
            "advice primary model=%s failed (%s); falling back to model=%s",
            primary.name,
            primary_exc,
            fallback.name,
        )
        return _run_attempts(fallback, facts, messages, started)


# ─── API entry point ─────────────────────────────────────────────────────────


def get_advice(*, mode: str, request: AdviceRequest) -> AdviceResponse:
    if mode == "live":
        try:
            return live_advice(request)
        except ModelError as exc:
            log.warning("advice unavailable: %s", exc)
            raise HTTPException(503, f"The AI explanation is unavailable. {exc}") from exc

    forecast = json.loads((DEMO_DIR / "forecast.example.json").read_text(encoding="utf-8"))
    expected = {"baseline": forecast["baseline"], "transactions": forecast["transactions"]}
    if request.model_dump(mode="json") != expected:
        raise HTTPException(422, "Submit the bundled baseline forecast in demo mode.")

    return AdviceResponse.model_validate_json((DEMO_DIR / "advice.example.json").read_text(encoding="utf-8"))

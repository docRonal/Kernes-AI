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

from .currency import amount_markers, money
from .forecast import horizon, propose
from .models import (
    AdviceRequest,
    AdviceResponse,
    DelayPredictResponse,
    Proposal,
    ReminderSendRequest,
    ReminderSendResponse,
    Transaction,
)


DEMO_DIR = Path(__file__).resolve().parents[1] / "demo"
DEFAULT_TIMEOUT_SECONDS = 90
MAX_TOKENS = 450
ATTEMPTS = 2

log = logging.getLogger("autonomous_cfo.advice")

# Thousands separators: comma, no-break space and narrow no-break space. A plain
# space is left out so "November 27, 5,000 PLN" isn't read as 275,000.
_DIGITS = r"\d[\d,\u00a0\u202f]*(?:\.\d{1,2})?"
# Any EU currency code or local symbol, before or after the number.
_MARKERS = amount_markers()
_AMOUNT = re.compile(
    rf"(?<![A-Za-z])(?:{_MARKERS})\s*[-−]?\s*({_DIGITS})|({_DIGITS})\s*(?:{_MARKERS})(?![A-Za-z])",
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

DELAY_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "explanation": {"type": "string"},
        "email_draft": {"type": "string"},
        "delay_warning": {"type": "string"},
    },
    "required": ["explanation", "email_draft", "delay_warning"],
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


def _parse_timeout(raw: str, default: float) -> float:
    try:
        value = float(raw) if raw.strip() else default
        return value if value > 0 else default
    except ValueError:
        return default


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
        timeout = _parse_timeout(raw_timeout, DEFAULT_TIMEOUT_SECONDS)
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
        fallback_timeout = _parse_timeout(os.environ.get("CFO_FALLBACK_MODEL_TIMEOUT", ""), timeout)
        return cls(
            url=url,
            name=name,
            token=os.environ.get("CFO_FALLBACK_MODEL_TOKEN") or os.environ.get("CFO_MODEL_TOKEN") or None,
            timeout=fallback_timeout,
            ssl_context=ssl_context,
        )


# ─── Facts ───────────────────────────────────────────────────────────────────


def pln(minor: int) -> str:
    """Kept under its first name for the modules that import it; writes the request's currency."""
    return money(minor)


def day_name(day: date) -> str:
    return f"{day:%A}, {day:%B} {day.day}"


@dataclass(frozen=True)
class Facts:
    proposal: Proposal
    lines: list[str]
    reminder: str | None
    allowed_minor: frozenset[int]
    has_delay_prediction: bool = False


def _predict_delay_impact(
    request: AdviceRequest,
    window: list[date],
    baseline_limit_minor: int,
) -> tuple[list[str], set[int]]:
    """Calculate deterministic cash-flow impact of historical client payment delays."""
    if not request.client_delays:
        return [], set()

    delayed: list[tuple[Transaction, int, date]] = []
    for t in sorted(request.transactions, key=lambda item: (item.date, item.id)):
        if t.amount_minor <= 0:
            continue
        delay_days = request.client_delays.get(t.id)
        if delay_days is None:
            delay_days = request.client_delays.get(t.label)
        if delay_days and delay_days > 0:
            delayed.append((t, delay_days, t.date + timedelta(days=delay_days)))

    if not delayed:
        return [], set()

    balances = [day.balance_minor for day in request.baseline.days]
    date_to_idx = {d: idx for idx, d in enumerate(window)}
    for t, _days, new_date in delayed:
        if t.date in date_to_idx:
            for idx in range(date_to_idx[t.date], len(balances)):
                balances[idx] -= t.amount_minor
        if new_date in date_to_idx:
            for idx in range(date_to_idx[new_date], len(balances)):
                balances[idx] += t.amount_minor

    delayed_limit = max(0, -min(balances))
    delay_lines: list[str] = []
    for t, delay_days, new_date in delayed:
        delay_lines.append(
            f"Historical delay risk: {t.label} ({t.id}) for {pln(t.amount_minor)} was previously "
            f"delayed by {delay_days} day(s), shifting expected receipt from {day_name(t.date)} "
            f"to {day_name(new_date)}."
        )
    if delayed_limit > baseline_limit_minor:
        delay_lines.append(
            f"With the predicted delay, the deepest projected gap increases from "
            f"{pln(baseline_limit_minor)} to {pln(delayed_limit)}."
        )
    else:
        delay_lines.append(
            f"With the predicted delay, the deepest projected gap remains {pln(delayed_limit)}."
        )

    extra_allowed = {delayed_limit} | {abs(b) for b in balances}
    return delay_lines, extra_allowed


_FIXED_OBLIGATION_RE = re.compile(
    r"\b(rent|payroll|salar\w*|wage\w*|lease|utilit\w*|insur\w*|tax\w*|miete|gehalt|lohn|czynsz|wynagrodz\w*)\b",
    re.IGNORECASE,
)


def _recurring_expense_note(transactions: list[Transaction], window: list[date]) -> tuple[str | None, set[int]]:
    """Summarize recurring or fixed obligations (e.g. rent, payroll) that continue even during quiet revenue periods."""
    in_window = [t for t in transactions if window[0] <= t.date <= window[-1]]
    outflows = [t for t in in_window if t.amount_minor < 0]
    if not outflows:
        return None, set()

    label_counts: dict[str, int] = {}
    for t in transactions:
        if t.amount_minor < 0:
            key = t.label.strip().lower()
            label_counts[key] = label_counts.get(key, 0) + 1

    recurring = [
        t for t in outflows
        if _FIXED_OBLIGATION_RE.search(t.label) or label_counts.get(t.label.strip().lower(), 0) > 1
    ]
    if not recurring:
        return None, set()

    total_recurring = sum(-t.amount_minor for t in recurring)
    names = list(dict.fromkeys(t.label.strip() for t in recurring))
    inflows_before_last_out = any(
        t.amount_minor > 0 and t.date <= max(r.date for r in recurring)
        for t in in_window
    )
    context = (
        "even when incoming revenue pauses (e.g. during a closure or vacation)"
        if not inflows_before_last_out
        else "alongside scheduled receipts"
    )
    note = (
        f"Ongoing regular obligations ({', '.join(names)}) continue {context}, "
        f"totaling {pln(total_recurring)}."
    )
    return note, {total_recurring}


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
        f"First day below zero: {day_name(first.date)}. The balance that day is {pln(-first.shortfall_minor)}, "
        f"a gap of {pln(first.shortfall_minor)}. This gap is not a transaction amount.",
    ]
    if deepest.date == first.date:
        lines.append(f"This is also the deepest point of the forecast: a gap of {pln(deepest.shortfall_minor)}.")
    else:
        lines.append(
            f"Deepest point: {day_name(deepest.date)}. The balance that day is {pln(-deepest.shortfall_minor)}, "
            f"a gap of {pln(deepest.shortfall_minor)}."
        )
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
    day_totals = _same_day_outgoing_totals(relevant)
    for day, total in day_totals.items():
        lines.append(f"Outgoing payments on {day_name(day)} total {pln(total)}.")
    recurring_note, recurring_allowed = _recurring_expense_note(request.transactions, window)
    if recurring_note:
        lines.append(recurring_note)

    reminder = _reminder_target(request.transactions, first.date, window)
    delay_lines, extra_allowed = _predict_delay_impact(request, window, proposal.limit_minor)
    lines.extend(delay_lines)

    allowed = {proposal.limit_minor, first.shortfall_minor, deepest.shortfall_minor}
    allowed |= {abs(day.balance_minor) for day in baseline.days}
    allowed |= {abs(t.amount_minor) for t in request.transactions}
    allowed |= extra_allowed
    allowed |= set(day_totals.values())
    allowed |= recurring_allowed
    return Facts(
        proposal=proposal,
        lines=lines,
        reminder=reminder,
        allowed_minor=frozenset(allowed),
        has_delay_prediction=bool(delay_lines),
    )


def _same_day_outgoing_totals(transactions: list[Transaction]) -> dict[date, int]:
    """Totals for days with several outgoing payments, so the model never has to add them up."""
    by_day: dict[date, list[int]] = {}
    for t in transactions:
        if t.amount_minor < 0:
            by_day.setdefault(t.date, []).append(-t.amount_minor)
    return {day: sum(amounts) for day, amounts in sorted(by_day.items()) if len(amounts) > 1}


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
        '("is projected to"). Sentence 1: when the balance first goes below zero and the size of that gap, and the '
        "deepest point and its gap if it is a different day. Take the gap amounts from the facts, never from a "
        "transaction. Sentence 2: which transactions cause the gap (noting ongoing regular obligations like "
        "rent or payroll if listed) and when money comes back. Sentence 3: why a credit facility of "
        f"{limit} covers the gap, and that the owner can approve or reject this proposal. Do not mention any email.",
    ]
    if facts.reminder:
        task.append(
            "Task 2, email_draft: a polite payment reminder to the client, under 70 words. Start with "
            f'"Hello,". {facts.reminder} Do not mention the credit facility, fees or penalties. '
            'End with "Kind regards,\nThe finance team".'
        )
    else:
        task.append('Task 2: there is no incoming payment to ask for, so set email_draft to "".')
    if facts.has_delay_prediction:
        task.append(
            "Task 3, delay_warning: write 1-2 plain English sentences warning the business owner about "
            "the client's historical payment delay and its calculated impact on the cash gap, using only "
            "the delay facts above."
        )
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


_BELOW_ZERO = re.compile(r"below zero|negative|overdra\w*|in the red|shortfall|short\b", re.IGNORECASE)


def check_explanation(text: str, facts: Facts) -> str | None:
    """Return a problem with the explanation's figures, or None when they match.

    Every cited amount must come from the forecast. The first gap, the deepest gap
    and the limit must all be cited, and a sentence about going below zero may
    only quote gap or limit amounts, so a transaction amount can't pose as the gap.
    """
    amounts = cited_amounts(text)
    unknown = [amount for amount in amounts if amount not in facts.allowed_minor]
    if unknown:
        return f"it cites {pln(unknown[0])}, which isn't in the forecast"
    proposal = facts.proposal
    required = {
        "proposed limit": proposal.limit_minor,
        "first gap": proposal.first_shortfall.shortfall_minor,
        "deepest gap": proposal.deepest_shortfall.shortfall_minor,
    }
    for name, amount in required.items():
        if amount not in amounts:
            return f"it doesn't cite the {name} of {pln(amount)}"
    gap_amounts = set(required.values())
    for sentence in _SENTENCE_END.split(text):
        if _BELOW_ZERO.search(sentence):
            wrong = [amount for amount in cited_amounts(sentence) if amount not in gap_amounts]
            if wrong:
                return f"it calls {pln(wrong[0])} the gap, but that amount isn't a gap or the limit"
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


def parse_answer(content: str) -> tuple[str, str, str | None]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelError("The model didn't return JSON.") from exc
    explanation = data.get("explanation") if isinstance(data, dict) else None
    draft = data.get("email_draft", "") if isinstance(data, dict) else None
    delay_warning = data.get("delay_warning") if isinstance(data, dict) else None
    if not isinstance(explanation, str) or not explanation.strip() or not isinstance(draft, str):
        raise ModelError("The model's answer is missing the explanation.")
    clean_warning = delay_warning.strip() if isinstance(delay_warning, str) and delay_warning.strip() else None
    return explanation.strip(), draft.strip(), clean_warning


# ─── Model call ──────────────────────────────────────────────────────────────


def call_model(
    config: ModelConfig,
    messages: list[dict[str, str]],
    *,
    schema: dict = OUTPUT_SCHEMA,
) -> str:
    body = {
        "model": config.name,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_schema", "json_schema": {"name": "advice", "schema": schema}},
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
) -> tuple[AdviceResponse, str | None]:
    schema = DELAY_OUTPUT_SCHEMA if facts.has_delay_prediction else OUTPUT_SCHEMA
    problem = "no answer"
    for attempt in range(1, ATTEMPTS + 1):
        explanation, draft, delay_warning = parse_answer(call_model(config, messages, schema=schema))
        problem = check_explanation(explanation, facts)
        if problem is None and facts.has_delay_prediction and delay_warning:
            unknown = [a for a in cited_amounts(delay_warning) if a not in facts.allowed_minor]
            if unknown:
                problem = f"delay_warning cites {pln(unknown[0])}, which isn't in the forecast"
        if problem is None:
            latency = round((time.monotonic() - started) * 1000)
            log.info("advice model=%s attempts=%d latency_ms=%d status=ok", config.name, attempt, latency)
            return (
                AdviceResponse(
                    explanation=explanation,
                    email_draft=(clean_reminder(draft, facts) or None) if facts.reminder else None,
                    model=config.name,
                    latency_ms=latency,
                ),
                delay_warning if facts.has_delay_prediction else None,
            )
        log.warning("advice model=%s attempt=%d rejected: %s", config.name, attempt, problem)
    raise ModelError(f"The model's explanation didn't match the calculated figures: {problem}.")


def _live_advice_with_warning(request: AdviceRequest) -> tuple[AdviceResponse, str | None]:
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


def live_advice(request: AdviceRequest) -> AdviceResponse:
    response, _ = _live_advice_with_warning(request)
    return response


def predict_delays(*, mode: str, request: AdviceRequest) -> DelayPredictResponse:
    if mode == "live":
        try:
            response, delay_warning = _live_advice_with_warning(request)
        except ModelError as exc:
            log.warning("delay prediction unavailable: %s", exc)
            raise HTTPException(503, f"The AI explanation is unavailable. {exc}") from exc
        return DelayPredictResponse(
            explanation=response.explanation,
            email_draft=response.email_draft,
            delay_warning=delay_warning,
            model=response.model,
            latency_ms=response.latency_ms,
        )

    demo_response = get_advice(mode=mode, request=AdviceRequest(baseline=request.baseline, transactions=request.transactions))
    return DelayPredictResponse(
        explanation=demo_response.explanation,
        email_draft=demo_response.email_draft,
        delay_warning=None,
        model=demo_response.model,
        latency_ms=demo_response.latency_ms,
    )


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
    if request.model_dump(mode="json", exclude_none=True, exclude={"currency"}) != expected:
        raise HTTPException(422, "Submit the bundled baseline forecast in demo mode.")

    return AdviceResponse.model_validate_json((DEMO_DIR / "advice.example.json").read_text(encoding="utf-8"))


def send_reminder(request: ReminderSendRequest) -> ReminderSendResponse:
    """Simulate sending the reminder. The agent never sends messages; the user sends the draft themselves."""
    return ReminderSendResponse(
        status="simulated",
        recipient=request.to_email,
        subject=request.subject,
        message="Simulation only: nothing was sent. Copy the draft and send it from your own email.",
    )



def _probe_model(config: ModelConfig, *, probe_timeout: float = 2.5) -> dict:
    models_url = re.sub(r"/chat/completions/?$", "/models", config.url)
    headers = {"Accept": "application/json"}
    if config.token:
        headers["Authorization"] = f"Bearer {config.token}"
    req = urllib.request.Request(models_url, headers=headers, method="GET")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=probe_timeout, context=config.ssl_context) as resp:
            ok = 200 <= resp.status < 300
        return {
            "model": config.name,
            "reachable": ok,
            "timeout_seconds": config.timeout,
            "latency_ms": round((time.monotonic() - started) * 1000),
        }
    except Exception as exc:
        return {
            "model": config.name,
            "reachable": False,
            "timeout_seconds": config.timeout,
            "error": str(exc),
        }


def check_ai_health() -> dict:
    """Check reachability of configured OpenShift AI primary and fallback models."""
    try:
        primary = ModelConfig.from_env()
    except ModelError as exc:
        return {"status": "unconfigured", "detail": str(exc), "primary": None, "fallback": None}

    primary_status = _probe_model(primary)
    fallback = ModelConfig.fallback_from_env(timeout=primary.timeout, ssl_context=primary.ssl_context)
    fallback_status = _probe_model(fallback) if fallback else None

    if primary_status["reachable"]:
        overall = "ok"
    elif fallback_status and fallback_status["reachable"]:
        overall = "degraded"
    else:
        overall = "unavailable"
    return {"status": overall, "primary": primary_status, "fallback": fallback_status}

"""The model's part of the credit check and the ask-CFO chat.

Python works out every figure first (insights.py). The model only puts those
facts into words, and every PLN amount it writes must be one of them.
"""

import json
import logging
import math
import os
import re
import time
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException

from . import advice
from .advice import ATTEMPTS, ModelConfig, ModelError, cited_amounts, day_name, pln
from .forecast import ForecastInputError, propose
from .insights import credit_scorecard, optimize_payments, stress_test, what_if
from .telemetry import log_llm_call
from .models import (
    HORIZON_DAYS,
    MAX_ABS_MINOR,
    AdviceRequest,
    AskRequest,
    AskResponse,
    CreditCheckResponse,
    InsightRequest,
    Transaction,
    WhatIf,
)


log = logging.getLogger("autonomous_cfo.consultant")

EXPLANATION_SCHEMA = {
    "type": "object",
    "properties": {"explanation": {"type": "string"}},
    "required": ["explanation"],
}

CREDIT_PROMPT = """You are the credit analyst of a small company's finance assistant.
The application has already scored the credit facility and calculated every figure. You only explain them.
Rules:
- Use only the facts you are given. Copy amounts, dates, percentages and the score exactly as written.
- Never calculate, round or invent an amount, date, rate, fee or rule.
- Write plain English for the business owner and their bank. No markdown, no bullet points.
- Reply with JSON: {"explanation": "..."}"""

CREDIT_TASK = (
    "Task: write exactly 3 sentences. Sentence 1: the score and the risk level. Sentence 2: the main "
    "reasons, starting with the factors that cost the most points. Sentence 3: why the facility is safe, "
    "or what would make it safer."
)


def _parse(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelError("The model didn't return JSON.") from exc
    if not isinstance(data, dict):
        raise ModelError("The model didn't return a JSON object.")
    return data


def _ask_model_traced(
    messages: list[dict[str, str]],
    schema: dict,
    check: Callable[[dict], str | None],
) -> tuple[dict, str, int, bool]:
    """The first answer that passes check: ATTEMPTS tries on the primary model, then on the fallback."""
    primary = ModelConfig.from_env()
    fallback = ModelConfig.fallback_from_env(timeout=primary.timeout, ssl_context=primary.ssl_context)
    problem = "The model gave no answer."
    attempts_total = 0
    configs = [primary, fallback] if fallback else [primary]
    for idx, config in enumerate(configs):
        fallback_used = idx > 0
        try:
            for attempt in range(1, ATTEMPTS + 1):
                attempts_total += 1
                data = _parse(advice.call_model(config, messages, schema=schema))
                issue = check(data)
                if issue is None:
                    return data, config.name, attempts_total, fallback_used
                log.warning("model=%s attempt=%d rejected: %s", config.name, attempt, issue)
                problem = f"The model's answer didn't match the calculated figures: {issue}."
        except ModelError as exc:
            problem = str(exc)
    raise ModelError(problem)


def _ask_model(messages: list[dict[str, str]], schema: dict, check: Callable[[dict], str | None]) -> tuple[dict, str]:
    data, name, _attempts, _fallback_used = _ask_model_traced(messages, schema, check)
    return data, name


def _figures_problem(text: object, allowed: set[int]) -> str | None:
    if not isinstance(text, str) or not text.strip():
        return "the answer is empty"
    unknown = [amount for amount in cited_amounts(text) if amount not in allowed]
    return f"it cites {pln(unknown[0])}, which isn't in the facts" if unknown else None


def credit_check(*, mode: str, request: AdviceRequest) -> CreditCheckResponse:
    """The calculated scorecard, explained by the model. A model outage leaves the score in place."""
    try:
        result = credit_scorecard(request)
    except ForecastInputError as exc:
        raise HTTPException(422, str(exc)) from exc
    if mode != "live":
        return result.model_copy(update={"explanation_error": "The AI explanation runs only in live mode."})

    facts = "\n".join(
        [
            f"Credit facility under review: {pln(result.limit_minor)}.",
            f"Score: {result.score} out of 100. Risk level: {result.risk}.",
            "Points deducted from 100:",
            *(f"- {factor.reason} ({factor.points} points)" for factor in result.factors),
        ]
    )
    allowed = set(cited_amounts(facts))

    def check(data: dict) -> str | None:
        problem = _figures_problem(data.get("explanation"), allowed)
        if problem is None and not re.search(rf"\b{result.risk}\b", data["explanation"], re.IGNORECASE):
            problem = f"it doesn't say the risk is {result.risk}"
        return problem

    messages = [
        {"role": "system", "content": CREDIT_PROMPT},
        {"role": "user", "content": f"Facts:\n{facts}\n\n{CREDIT_TASK}"},
    ]
    started = time.monotonic()
    try:
        data, name, attempts_total, fallback_used = _ask_model_traced(messages, EXPLANATION_SCHEMA, check)
    except ModelError as exc:
        log.warning("credit check explanation unavailable: %s", exc)
        log_llm_call(
            endpoint="credit-check",
            model=os.environ.get("CFO_MODEL_NAME", "unconfigured"),
            latency_ms=round((time.monotonic() - started) * 1000),
            status="error",
            attempts=1,
            grounded=False,
            fallback_used=False,
        )
        return result.model_copy(update={"explanation_error": f"The AI explanation is unavailable. {exc}"})
    latency = round((time.monotonic() - started) * 1000)
    log.info("credit-check model=%s latency_ms=%d status=ok", name, latency)
    log_llm_call(
        endpoint="credit-check",
        model=name,
        latency_ms=latency,
        status="ok",
        attempts=attempts_total,
        grounded=True,
        fallback_used=fallback_used,
    )
    return result.model_copy(update={"explanation": data["explanation"].strip(), "model": name, "latency_ms": latency})


# ─── Ask the CFO ─────────────────────────────────────────────────────────────

WHAT_IF_SCHEMA = {
    "type": "object",
    "properties": {
        "transaction_id": {"type": "string"},
        "amount_change_pln": {"type": "number"},
        "days_later": {"type": "integer"},
    },
    "required": ["transaction_id", "amount_change_pln", "days_later"],
}

ANSWER_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}

WHAT_IF_PROMPT = """You read a business owner's question about their cash forecast and spot a change to one listed transaction.
Reply with JSON: {"transaction_id": "...", "amount_change_pln": 0, "days_later": 0}
- transaction_id: the id of the transaction the question changes, or "" if it changes none.
- amount_change_pln: how many EUR that payment grows by, negative if it shrinks, 0 if unchanged.
- days_later: how many days later it happens, negative if earlier, 0 if unchanged.
Calculate nothing else. Examples:
"What if payroll grows by 2,000 EUR?" -> {"transaction_id": "<the payroll id>", "amount_change_pln": 2000, "days_later": 0}
"What if the client pays 3 days late?" -> {"transaction_id": "<that invoice id>", "amount_change_pln": 0, "days_later": 3}"""

ASK_PROMPT = """You are the CFO assistant of a small company. The application has already calculated every figure.
Rules:
- Answer the owner's question in 1 to 3 plain English sentences, using only the facts you are given.
- Copy amounts and dates exactly as written. Never calculate, round or invent an amount, date or transaction.
- If the facts don't answer the question, say so and point to the figure that comes closest.
- No markdown. Reply with JSON: {"answer": "..."}"""


# Numbers the owner typed, such as "2,000", "2 000", "3" or "1500.50".
_NUMBER = re.compile(r"\d{1,3}(?:[,\u00a0\u202f ]\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?")
_LATER = re.compile(r"\b(late|later|delay\w*|postpone\w*|after)\b", re.IGNORECASE)
_EARLIER = re.compile(r"\b(early|earlier|sooner|ahead|advance|before)\b", re.IGNORECASE)


def _numbers(question: str) -> set[Decimal]:
    """The numbers in the question. A number followed by % is a rate, not a size."""
    return {
        Decimal(re.sub(r"[,\u00a0\u202f ]", "", match.group()))
        for match in _NUMBER.finditer(question)
        if not question[match.end() :].lstrip().startswith("%")
    }


def _window(request: InsightRequest) -> list[Transaction]:
    days = request.baseline.days
    inside = (t for t in request.transactions if days[0].date <= t.date <= days[-1].date)
    return sorted(inside, key=lambda t: (t.date, t.id))


def _describe(t: Transaction) -> str:
    direction = "incoming" if t.amount_minor > 0 else "outgoing"
    return f"{t.label} ({t.id}), {direction} {pln(abs(t.amount_minor))} on {day_name(t.date)}"


def _forecast_facts(request: InsightRequest) -> list[str]:
    """Everything the chat may quote: balances, transactions, the proposal, cheaper options, the stress test."""
    days = request.baseline.days
    by_id = {t.id: t for t in request.transactions}
    lines = [
        f"Forecast period: {day_name(days[0].date)} to {day_name(days[-1].date)}, {days[-1].date.year}.",
        "End-of-day balances:",
        *(f"- {day_name(day.date)}: {pln(day.balance_minor)}" for day in days),
        "Transactions in the forecast:",
        *([f"- {_describe(t)}" for t in _window(request)] or ["- none"]),
    ]
    proposal = propose(request.baseline, request.transactions)
    if proposal is None:
        lines.append("The balance never goes below zero, so no credit facility is needed.")
    else:
        first, deepest = proposal.first_shortfall, proposal.deepest_shortfall
        lines += [
            f"First day below zero: {day_name(first.date)}, balance {pln(-first.shortfall_minor)}.",
            f"Deepest point: {day_name(deepest.date)}, balance {pln(-deepest.shortfall_minor)}.",
            f"Proposed credit facility: {pln(proposal.limit_minor)}. It is a simulation: the owner approves or rejects it.",
        ]
        for action in optimize_payments(request).actions[:3]:
            t = by_id[action.transaction_id]
            move = (
                f"Ask the client to pay {t.label} ({t.id}) by {day_name(action.new_date)}"
                if action.kind == "collect_earlier"
                else f"Pay {t.label} ({t.id}) on {day_name(action.new_date)}"
            )
            lines.append(
                f"Option: {move} instead of {day_name(action.due_date)}; "
                f"the facility needed would be {pln(action.limit_after_minor)}."
            )
    stress = stress_test(request)
    if stress.buffer_minor:
        worst = max(stress.scenarios, key=lambda scenario: scenario.extra_needed_minor)
        lines.append(f"Worst stress case: {worst.description} A facility of {pln(stress.recommended_limit_minor)} would cover it.")
    else:
        lines.append("Stress test: clients paying 3 or 5 days late or costs 10% higher would need no more credit than proposed.")
    return lines


def _read_change(data: dict, request: AskRequest) -> tuple[str, int, int] | None:
    """The change the model read from the question, kept only where the owner's words back it up.

    The model picks the transaction. Each size must be a number the owner typed, and words like
    "late" or "early" decide which way a date moves: a 3B model easily flips the sign.
    """
    transaction_id, amount, later = data.get("transaction_id"), data.get("amount_change_pln"), data.get("days_later")
    if not isinstance(transaction_id, str) or transaction_id not in {t.id for t in _window(request)}:
        return None
    if isinstance(amount, bool) or not isinstance(amount, int | float) or isinstance(later, bool) or not isinstance(later, int):
        return None
    if isinstance(amount, float) and not math.isfinite(amount):
        return None
    numbers = _numbers(request.question)
    change = int((Decimal(str(amount)) * 100).to_integral_value(ROUND_HALF_UP))
    if Decimal(abs(change)) / 100 not in numbers:
        change = 0
    if abs(later) not in numbers:
        later = 0
    later_words, earlier_words = _LATER.search(request.question), _EARLIER.search(request.question)
    if later_words and not earlier_words:
        later = abs(later)
    elif earlier_words and not later_words:
        later = -abs(later)
    if abs(change) > MAX_ABS_MINOR or abs(later) > HORIZON_DAYS or (change == 0 and later == 0):
        return None
    return transaction_id, change, later


def _what_if_lines(request: InsightRequest, scenario: WhatIf) -> list[str]:
    days = request.baseline.days
    target = next(t for t in _window(request) if t.id == scenario.transaction_id)
    when = day_name(scenario.new_date)
    if scenario.new_date > days[-1].date:
        when += ", after the forecast ends"
    elif scenario.new_date < days[0].date:
        when += ", before the forecast starts"
    lines = [
        f"What-if from the question: {target.label} ({target.id}) {pln(abs(target.amount_minor))} on "
        f"{day_name(target.date)} becomes {pln(abs(scenario.new_amount_minor))} on {when}."
    ]
    if scenario.deepest_shortfall is None:
        lines.append("With that change the balance never goes below zero, so no credit facility would be needed.")
        return lines
    needed = scenario.deepest_shortfall.shortfall_minor
    lines.append(
        f"With that change the lowest balance would be {pln(-needed)} on {day_name(scenario.deepest_shortfall.date)}, "
        f"so a facility of {pln(needed)} would be needed."
    )
    proposed = max(0, -min(day.balance_minor for day in days))
    if proposed and needed != proposed:
        more_or_less = "more" if needed > proposed else "less"
        lines.append(f"That is {pln(abs(needed - proposed))} {more_or_less} than the proposed facility of {pln(proposed)}.")
    return lines


def ask_cfo(*, mode: str, request: AskRequest) -> AskResponse:
    """Answer a question about the forecast from calculated facts, recalculating any what-if first."""
    if mode != "live":
        raise HTTPException(503, "The AI consultant runs only in live mode.")
    started = time.monotonic()
    lines = _forecast_facts(request)
    listed = "\n".join(f"- {t.id}: {_describe(t)}" for t in _window(request))
    change = None
    if _numbers(request.question):  # without a number there is no size to change
        try:
            data, _ = _ask_model(
                [
                    {"role": "system", "content": WHAT_IF_PROMPT},
                    {"role": "user", "content": f"Transactions:\n{listed}\n\nQuestion: {request.question}"},
                ],
                WHAT_IF_SCHEMA,
                lambda data: None,
            )
            change = _read_change(data, request)
        except ModelError as exc:
            log.warning("ask-cfo couldn't read a what-if: %s", exc)
    scenario = what_if(request, *change) if change else None
    if scenario:
        lines += _what_if_lines(request, scenario)
    facts = "\n".join(lines)
    allowed = set(cited_amounts(facts))
    try:
        data, name, attempts_total, fallback_used = _ask_model_traced(
            [
                {"role": "system", "content": ASK_PROMPT},
                {"role": "user", "content": f"Facts:\n{facts}\n\nQuestion: {request.question}"},
            ],
            ANSWER_SCHEMA,
            lambda data: _figures_problem(data.get("answer"), allowed),
        )
    except ModelError as exc:
        log.warning("ask-cfo unavailable: %s", exc)
        log_llm_call(
            endpoint="ask-cfo",
            model=os.environ.get("CFO_MODEL_NAME", "unconfigured"),
            latency_ms=round((time.monotonic() - started) * 1000),
            status="error",
            attempts=1,
            grounded=False,
            fallback_used=False,
        )
        raise HTTPException(503, f"The AI consultant is unavailable. {exc}") from exc
    latency = round((time.monotonic() - started) * 1000)
    log.info("ask-cfo model=%s latency_ms=%d status=ok", name, latency)
    log_llm_call(
        endpoint="ask-cfo",
        model=name,
        latency_ms=latency,
        status="ok",
        attempts=attempts_total,
        grounded=True,
        fallback_used=fallback_used,
    )
    return AskResponse(answer=data["answer"].strip(), what_if=scenario, model=name, latency_ms=latency)

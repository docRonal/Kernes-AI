"""Financial consultant capabilities: credit scoring, stress testing, payment optimization, and Q&A.

All monetary calculations are deterministic integer grosz. In live mode, the
OpenShift AI model (with configured fallback) explains the calculated facts
and is checked against the supplied figures.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta

from fastapi import HTTPException

from .advice import ModelConfig, ModelError, call_model, cited_amounts, day_name, pln
from .forecast import horizon, propose
from .models import (
    AskCfoRequest,
    AskCfoResponse,
    CreditCheckRequest,
    CreditCheckResponse,
    OptimizePaymentsRequest,
    OptimizePaymentsResponse,
    PaymentAction,
    Projection,
    StressTestRequest,
    StressTestResponse,
    Transaction,
)


log = logging.getLogger("autonomous_cfo.consultant")

_TEXT_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}

_CONSULTANT_SYSTEM_PROMPT = (
    "You are an Autonomous CFO financial consultant. "
    "All figures have already been calculated by the backend. "
    "Use ONLY the exact amounts and dates provided in the facts. "
    "Never invent numbers, percentages, fees, or dates. "
    'Write concise plain English (2-4 sentences, no markdown). Reply with JSON: {"text": "..."}.'
)


def _validate_window(baseline: Projection) -> list[date]:
    window = horizon(baseline.days[0].date)
    if [day.date for day in baseline.days] != window:
        raise HTTPException(422, "The baseline must list 14 consecutive days.")
    return window


def _recompute_balances(
    baseline: Projection,
    transactions: list[Transaction],
    window: list[date],
    *,
    inflow_delay_days: int = 0,
    expense_shock_pct: int = 0,
    move_tx: tuple[str, date] | None = None,
) -> list[int]:
    """Recompute 14 daily balances in integer grosz from baseline and modified transactions."""
    date_to_idx = {d: idx for idx, d in enumerate(window)}
    # Recover starting balance before day 0's transactions
    day0_tx_sum = sum(t.amount_minor for t in transactions if t.date == window[0])
    running = baseline.days[0].balance_minor - day0_tx_sum

    daily_net = [0] * len(window)
    for t in transactions:
        tx_date = t.date
        amount = t.amount_minor
        if move_tx and t.id == move_tx[0]:
            tx_date = move_tx[1]
        elif amount > 0 and inflow_delay_days > 0:
            tx_date = tx_date + timedelta(days=inflow_delay_days)
        elif amount < 0 and expense_shock_pct > 0:
            amount = -((abs(amount) * (100 + expense_shock_pct)) // 100)

        idx = date_to_idx.get(tx_date)
        if idx is not None:
            daily_net[idx] += amount

    balances: list[int] = []
    for net in daily_net:
        running += net
        balances.append(running)
    return balances


def _ask_model_text(facts: list[str], task: str, allowed_minor: frozenset[int]) -> tuple[str, str, int]:
    """Call primary (and optional fallback) OpenShift AI model and verify cited PLN amounts."""
    primary = ModelConfig.from_env()
    messages = [
        {"role": "system", "content": _CONSULTANT_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(["Facts:", *facts, "", f"Task: {task}"])},
    ]
    started = time.monotonic()

    def _attempt(config: ModelConfig) -> tuple[str, str, int]:
        raw = call_model(config, messages, schema=_TEXT_SCHEMA)
        text_val = raw.strip()
        if text_val.startswith("```"):
            text_val = text_val.strip("`").removeprefix("json").strip()
        try:
            parsed = json.loads(text_val)
            text = parsed["text"].strip() if isinstance(parsed, dict) and isinstance(parsed.get("text"), str) else ""
        except json.JSONDecodeError as exc:
            raise ModelError("The model didn't return JSON.") from exc
        if not text:
            raise ModelError("The model returned an empty answer.")
        unknown = [amt for amt in cited_amounts(text) if amt not in allowed_minor]
        if unknown:
            raise ModelError(f"Model cited {pln(unknown[0])}, which isn't in the calculated facts.")
        latency = round((time.monotonic() - started) * 1000)
        log.info("consultant model=%s latency_ms=%d status=ok", config.name, latency)
        return text, config.name, latency

    try:
        return _attempt(primary)
    except ModelError as primary_exc:
        fallback = ModelConfig.fallback_from_env(timeout=primary.timeout, ssl_context=primary.ssl_context)
        if fallback is None:
            raise
        log.warning("consultant primary model=%s failed (%s); falling back to %s", primary.name, primary_exc, fallback.name)
        return _attempt(fallback)


# ─── 1. Credit Check & Borrower Scoring ──────────────────────────────────────


def run_credit_check(*, mode: str, request: CreditCheckRequest) -> CreditCheckResponse:
    window = _validate_window(request.baseline)
    proposal = propose(request.baseline, request.transactions)
    proposed_limit = proposal.limit_minor if proposal else 0
    balances = [day.balance_minor for day in request.baseline.days]
    deficit_days = sum(1 for b in balances if b < 0)

    recovery_date: date | None = None
    if proposal is not None:
        deepest_idx = next(i for i, d in enumerate(request.baseline.days) if d.date == proposal.deepest_shortfall.date)
        rec = next((d for d in request.baseline.days[deepest_idx + 1 :] if d.balance_minor >= 0), None)
        recovery_date = rec.date if rec else None

    total_inflows = sum(t.amount_minor for t in request.transactions if t.amount_minor > 0 and window[0] <= t.date <= window[-1])
    inflow_coverage_pct = 100 if proposed_limit == 0 else min(999, (total_inflows * 100) // proposed_limit)

    score = 100
    score -= min(35, deficit_days * 5)
    if proposed_limit > 0 and recovery_date is None:
        score -= 30
    if inflow_coverage_pct < 100:
        score -= 20
    elif inflow_coverage_pct < 150:
        score -= 10
    if request.client_delays:
        max_delay = max(request.client_delays.values(), default=0)
        score -= min(20, max_delay * 5)
    inflows = [t.amount_minor for t in request.transactions if t.amount_minor > 0 and window[0] <= t.date <= window[-1]]
    if len(inflows) == 1 and proposed_limit > 0:
        score -= 10  # single-client concentration risk
    score = max(0, min(100, score))

    if score >= 70:
        risk_level, action = "low", "approve"
    elif score >= 45:
        risk_level, action = "medium", "approve_with_caution"
    else:
        risk_level, action = "high", "review_required"

    facts = [
        f"Credit readiness score: {score}/100 (risk level: {risk_level}, action: {action}).",
        f"Proposed credit facility limit: {pln(proposed_limit)}.",
        f"Days below zero in 14-day horizon: {deficit_days}.",
        f"Recovery date back to >= 0: {day_name(recovery_date) if recovery_date else 'none within 14 days'}.",
        f"Incoming payments within horizon: {pln(total_inflows)} ({inflow_coverage_pct}% coverage of proposed limit).",
    ]
    if request.client_delays:
        facts.append(f"Known historical client delays (days): {request.client_delays}.")

    allowed = {proposed_limit, total_inflows} | {abs(b) for b in balances} | {abs(t.amount_minor) for t in request.transactions}

    if mode == "live":
        try:
            reasoning, model, latency = _ask_model_text(
                facts,
                "Explain this borrower creditworthiness verdict to the business owner and credit reviewer.",
                frozenset(allowed),
            )
        except ModelError as exc:
            raise HTTPException(503, f"The AI explanation is unavailable. {exc}") from exc
    else:
        reasoning = " ".join(facts[:4])
        model, latency = "demo-deterministic", None

    return CreditCheckResponse(
        score=score,
        risk_level=risk_level,
        recommended_action=action,
        deficit_days=deficit_days,
        recovery_date=recovery_date,
        proposed_limit_minor=proposed_limit,
        inflow_coverage_pct=inflow_coverage_pct,
        reasoning=reasoning,
        model=model,
        latency_ms=latency,
    )


# ─── 2. Liquidity Stress Test ────────────────────────────────────────────────


def run_stress_test(*, mode: str, request: StressTestRequest) -> StressTestResponse:
    window = _validate_window(request.baseline)
    baseline_limit = max(0, -min(d.balance_minor for d in request.baseline.days))
    stressed_balances = _recompute_balances(
        request.baseline,
        request.transactions,
        window,
        inflow_delay_days=request.delay_days,
        expense_shock_pct=request.expense_shock_pct,
    )
    stressed_min = min(stressed_balances)
    stressed_limit = max(0, -stressed_min)
    extra_buffer = max(0, stressed_limit - baseline_limit)
    first_def_idx = next((i for i, b in enumerate(stressed_balances) if b < 0), None)
    stressed_first_date = window[first_def_idx] if first_def_idx is not None else None

    facts = [
        f"Baseline proposed limit: {pln(baseline_limit)}.",
        f"Stress scenario: all incoming payments delayed by {request.delay_days} day(s) and outgoing expenses +{request.expense_shock_pct}%.",
        f"Stressed lowest balance: {pln(stressed_min)}.",
        f"Stressed required limit: {pln(stressed_limit)} (additional buffer needed: {pln(extra_buffer)}).",
        f"First deficit date under stress: {day_name(stressed_first_date) if stressed_first_date else 'none'}.",
    ]
    allowed = (
        {baseline_limit, stressed_limit, extra_buffer, abs(stressed_min)}
        | {abs(d.balance_minor) for d in request.baseline.days}
        | {abs(b) for b in stressed_balances}
        | {abs(t.amount_minor) for t in request.transactions}
    )

    if mode == "live":
        try:
            summary, model, latency = _ask_model_text(
                facts,
                "Summarize the liquidity stress-test result and whether an extra buffer is needed.",
                frozenset(allowed),
            )
        except ModelError as exc:
            raise HTTPException(503, f"The AI explanation is unavailable. {exc}") from exc
    else:
        summary = " ".join(facts)
        model, latency = "demo-deterministic", None

    return StressTestResponse(
        baseline_limit_minor=baseline_limit,
        stressed_limit_minor=stressed_limit,
        extra_buffer_minor=extra_buffer,
        stressed_min_balance_minor=stressed_min,
        stressed_first_deficit_date=stressed_first_date,
        summary=summary,
        model=model,
        latency_ms=latency,
    )


# ─── 3. Payment Optimization ─────────────────────────────────────────────────


def run_optimize_payments(*, mode: str, request: OptimizePaymentsRequest) -> OptimizePaymentsResponse:
    window = _validate_window(request.baseline)
    baseline_limit = max(0, -min(d.balance_minor for d in request.baseline.days))
    first_deficit = request.baseline.first_deficit
    actions: list[PaymentAction] = []

    if first_deficit is not None and baseline_limit > 0:
        first_gap_date = first_deficit.date
        target_early = max(window[0], first_gap_date - timedelta(days=1))
        # Candidate 1: accelerate incoming invoices arriving after first deficit
        for t in request.transactions:
            if t.amount_minor > 0 and first_gap_date <= t.date <= window[-1]:
                new_balances = _recompute_balances(request.baseline, request.transactions, window, move_tx=(t.id, target_early))
                new_limit = max(0, -min(new_balances))
                reduction = max(0, baseline_limit - new_limit)
                if reduction > 0:
                    actions.append(
                        PaymentAction(
                            transaction_id=t.id,
                            label=t.label,
                            action_type="accelerate_inflow",
                            suggested_date=target_early,
                            limit_reduction_minor=reduction,
                            new_limit_minor=new_limit,
                        )
                    )
            # Candidate 2: defer outgoing payments on/before deepest shortfall to after recovery or end of window
            elif t.amount_minor < 0 and window[0] <= t.date <= window[-1]:
                later_inflows = [tx.date for tx in request.transactions if tx.amount_minor > 0 and tx.date > t.date and tx.date <= window[-1]]
                target_late = min(later_inflows) if later_inflows else window[-1]
                if target_late > t.date:
                    new_balances = _recompute_balances(request.baseline, request.transactions, window, move_tx=(t.id, target_late))
                    new_limit = max(0, -min(new_balances))
                    reduction = max(0, baseline_limit - new_limit)
                    if reduction > 0:
                        actions.append(
                            PaymentAction(
                                transaction_id=t.id,
                                label=t.label,
                                action_type="defer_outflow",
                                suggested_date=target_late,
                                limit_reduction_minor=reduction,
                                new_limit_minor=new_limit,
                            )
                        )

    actions.sort(key=lambda a: (-a.limit_reduction_minor, a.new_limit_minor, a.transaction_id))
    actions = actions[:5]

    facts = [f"Current baseline credit limit needed: {pln(baseline_limit)}."]
    if actions:
        for a in actions:
            facts.append(
                f"- {a.action_type}: {a.label} ({a.transaction_id}) -> move to {day_name(a.suggested_date)}, "
                f"reduces credit needed by {pln(a.limit_reduction_minor)} (new limit {pln(a.new_limit_minor)})."
            )
    else:
        facts.append("No single payment date move reduces the baseline credit requirement.")

    allowed = (
        {baseline_limit}
        | {a.limit_reduction_minor for a in actions}
        | {a.new_limit_minor for a in actions}
        | {abs(t.amount_minor) for t in request.transactions}
    )

    if mode == "live":
        try:
            recommendation, model, latency = _ask_model_text(
                facts,
                "Recommend the single best payment action to minimize or eliminate the credit facility.",
                frozenset(allowed),
            )
        except ModelError as exc:
            raise HTTPException(503, f"The AI explanation is unavailable. {exc}") from exc
    else:
        recommendation = " ".join(facts[:2])
        model, latency = "demo-deterministic", None

    return OptimizePaymentsResponse(
        baseline_limit_minor=baseline_limit,
        actions=actions,
        recommendation=recommendation,
        model=model,
        latency_ms=latency,
    )


# ─── 4. Interactive CFO Q&A ──────────────────────────────────────────────────


def run_ask_cfo(*, mode: str, request: AskCfoRequest) -> AskCfoResponse:
    window = _validate_window(request.baseline)
    proposal = propose(request.baseline, request.transactions)
    min_day = min(request.baseline.days, key=lambda d: d.balance_minor)

    facts = [
        f"Forecast window: {day_name(window[0])} to {day_name(window[-1])}, {window[0].year}.",
        f"Lowest projected balance: {pln(min_day.balance_minor)} on {day_name(min_day.date)}.",
        f"Proposed credit facility limit: {pln(proposal.limit_minor) if proposal else pln(0)}.",
        "Transactions:",
    ]
    for t in sorted(request.transactions, key=lambda item: (item.date, item.id)):
        direction = "incoming" if t.amount_minor > 0 else "outgoing"
        facts.append(f"- {day_name(t.date)}: {t.label} ({t.id}), {direction} {pln(abs(t.amount_minor))}.")

    allowed = (
        {0, proposal.limit_minor if proposal else 0}
        | {abs(d.balance_minor) for d in request.baseline.days}
        | {abs(t.amount_minor) for t in request.transactions}
    )

    if mode == "live":
        try:
            answer, model, latency = _ask_model_text(
                facts,
                f"Answer the business owner's question concisely using only the facts above: {request.question}",
                frozenset(allowed),
            )
        except ModelError as exc:
            raise HTTPException(503, f"The AI explanation is unavailable. {exc}") from exc
    else:
        answer = f"Lowest balance is {pln(min_day.balance_minor)} on {day_name(min_day.date)}."
        model, latency = "demo-deterministic", None

    return AskCfoResponse(answer=answer, model=model, latency_ms=latency)

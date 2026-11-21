"""Extra financial consultant endpoints: anomaly detection and financing comparison.

All monetary math is deterministic integer grosz. In live mode, the OpenShift
AI model (with configured fallback) explains the calculated facts and is checked
against the supplied figures.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import date

from fastapi import HTTPException

from .advice import ModelConfig, ModelError, call_model, cited_amounts, day_name, pln
from .forecast import horizon, propose
from .insights import optimize_payments
from .models import (
    AnomalyDetectRequest,
    AnomalyDetectResponse,
    AnomalyFinding,
    CompareOptionsRequest,
    CompareOptionsResponse,
    FinancingOption,
    InsightRequest,
    Projection,
    Transaction,
)


log = logging.getLogger("autonomous_cfo.advisory_extras")

_TEXT_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}

_SYSTEM_PROMPT = (
    "You are an Autonomous CFO financial consultant. "
    "All figures have already been calculated by the backend. "
    "Use ONLY the exact amounts and dates provided in the facts. "
    "Never invent numbers, fees, or dates. "
    'Write concise plain English (2-3 sentences, no markdown). Reply with JSON: {"text": "..."}.'
)


def _validate_window(baseline: Projection) -> list[date]:
    window = horizon(baseline.days[0].date, len(baseline.days))
    if [day.date for day in baseline.days] != window:
        raise HTTPException(422, "The baseline must list 14 consecutive days.")
    return window


def _ask_model(facts: list[str], task: str, allowed_minor: frozenset[int]) -> tuple[str, str, int]:
    primary = ModelConfig.from_env()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
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
        log.info("advisory_extras model=%s latency_ms=%d status=ok", config.name, latency)
        return text, config.name, latency

    try:
        return _attempt(primary)
    except ModelError as primary_exc:
        fallback = ModelConfig.fallback_from_env(timeout=primary.timeout, ssl_context=primary.ssl_context)
        if fallback is None:
            raise
        log.warning("advisory_extras primary=%s failed (%s); falling back to %s", primary.name, primary_exc, fallback.name)
        return _attempt(fallback)


# ─── 1. Anomaly & Duplicate Payment Detector ─────────────────────────────────


def detect_anomalies(*, mode: str, request: AnomalyDetectRequest) -> AnomalyDetectResponse:
    window = _validate_window(request.baseline)
    in_window = sorted(
        [t for t in request.transactions if window[0] <= t.date <= window[-1]],
        key=lambda t: (t.date, t.id),
    )
    findings: list[AnomalyFinding] = []

    # 1) Duplicate amount within 3 days (same sign)
    for i, first in enumerate(in_window):
        for second in in_window[i + 1 :]:
            if (second.date - first.date).days > 3:
                break
            if first.amount_minor == second.amount_minor:
                findings.append(
                    AnomalyFinding(
                        kind="duplicate_payment",
                        date=second.date,
                        amount_minor=abs(second.amount_minor),
                        transaction_ids=[first.id, second.id],
                        detail=(
                            f"Possible duplicate of {pln(abs(first.amount_minor))}: "
                            f"{first.label} ({first.id}) on {day_name(first.date)} and "
                            f"{second.label} ({second.id}) on {day_name(second.date)}."
                        ),
                    )
                )

    # 2) Outlier single outflow (>= 2x average outflow when >= 3 outflows exist)
    outflows = [t for t in in_window if t.amount_minor < 0]
    if len(outflows) >= 3:
        total_out = sum(abs(t.amount_minor) for t in outflows)
        avg_out = total_out // len(outflows)
        for t in outflows:
            if abs(t.amount_minor) >= 2 * avg_out:
                findings.append(
                    AnomalyFinding(
                        kind="outlier_expense",
                        date=t.date,
                        amount_minor=abs(t.amount_minor),
                        transaction_ids=[t.id],
                        detail=(
                            f"Outlier expense {t.label} ({t.id}) of {pln(abs(t.amount_minor))} on "
                            f"{day_name(t.date)} is at least twice the average outflow ({pln(avg_out)})."
                        ),
                    )
                )

    # 3) Same-day outflow spike (>50% of total window outflows on one day with >= 2 outflows)
    total_window_out = sum(abs(t.amount_minor) for t in outflows)
    by_day: dict[date, list[Transaction]] = defaultdict(list)
    for t in outflows:
        by_day[t.date].append(t)
    if total_window_out > 0:
        for tx_date, day_txs in sorted(by_day.items()):
            day_sum = sum(abs(t.amount_minor) for t in day_txs)
            if len(day_txs) >= 2 and day_sum * 2 > total_window_out:
                findings.append(
                    AnomalyFinding(
                        kind="same_day_spike",
                        date=tx_date,
                        amount_minor=day_sum,
                        transaction_ids=[t.id for t in day_txs],
                        detail=(
                            f"Payment concentration on {day_name(tx_date)}: {len(day_txs)} outflows "
                            f"totaling {pln(day_sum)} out of {pln(total_window_out)} in the {len(window)}-day window."
                        ),
                    )
                )

    risk_flag = "review_recommended" if findings else "clean"
    facts = [f"Anomaly scan status: {risk_flag} ({len(findings)} finding(s))."]
    for f in findings:
        facts.append(f"- {f.detail}")
    if not findings:
        facts.append("No duplicate payments, outlier expenses, or same-day outflow spikes were detected.")

    allowed = (
        {0}
        | {f.amount_minor for f in findings}
        | {abs(t.amount_minor) for t in in_window}
        | {abs(d.balance_minor) for d in request.baseline.days}
    )
    if len(outflows) >= 3:
        allowed.add(sum(abs(t.amount_minor) for t in outflows) // len(outflows))
    if total_window_out > 0:
        allowed.add(total_window_out)

    if mode == "live":
        try:
            summary, model, latency = _ask_model(
                facts,
                "Summarize the anomaly scan findings for the business owner before they approve any credit facility.",
                frozenset(allowed),
            )
        except ModelError as exc:
            raise HTTPException(503, f"The AI explanation is unavailable. {exc}") from exc
    else:
        summary = " ".join(facts)
        model, latency = "demo-deterministic", None

    return AnomalyDetectResponse(
        findings=findings,
        risk_flag=risk_flag,
        summary=summary,
        model=model,
        latency_ms=latency,
    )


# ─── 2. Financing Options Cost Comparison ────────────────────────────────────


def compare_financing_options(*, mode: str, request: CompareOptionsRequest) -> CompareOptionsResponse:
    _validate_window(request.baseline)
    proposal = propose(request.baseline, request.transactions)
    if proposal is None:
        return CompareOptionsResponse(
            options=[],
            recommended_option="none_needed",
            explanation="The baseline forecast stays at or above zero, so no financing option is needed.",
            model="deterministic" if mode == "live" else "demo-deterministic",
            latency_ms=None,
        )

    deficit_days = max(1, sum(1 for d in request.baseline.days if d.balance_minor < 0))
    # Integer grosz interest: limit * annual_bps * deficit_days / (10000 * 365)
    credit_cost = (proposal.limit_minor * request.annual_rate_bps * deficit_days) // (10_000 * 365)
    options: list[FinancingOption] = [
        FinancingOption(
            option_kind="credit_facility",
            title="Short-term credit facility",
            estimated_cost_minor=credit_cost,
            credit_needed_minor=proposal.limit_minor,
            detail=(
                f"Borrow up to {pln(proposal.limit_minor)} for {deficit_days} deficit day(s) "
                f"(estimated interest {pln(credit_cost)})."
            ),
        )
    ]

    # Check invoice factoring / early collection
    tx_by_id = {t.id: t for t in request.transactions}
    opt = optimize_payments(InsightRequest(baseline=request.baseline, transactions=request.transactions))
    early = next((a for a in opt.actions if a.kind == "collect_early"), None)
    if early is not None:
        early_tx = tx_by_id[early.transaction_id]
        factoring_cost = (early_tx.amount_minor * request.factoring_fee_bps) // 10_000
        residual_interest = (early.limit_after_minor * request.annual_rate_bps * deficit_days) // (10_000 * 365)
        total_cost = factoring_cost + residual_interest
        options.append(
            FinancingOption(
                option_kind="invoice_factoring",
                title=f"Early collection / factoring on {early.transaction_id}",
                estimated_cost_minor=total_cost,
                credit_needed_minor=early.limit_after_minor,
                detail=(
                    f"Collect {early_tx.label} ({early.transaction_id}, {pln(early_tx.amount_minor)}) by {day_name(early.new_date)}; "
                    f"estimated fee {pln(total_cost)}, credit needed drops to {pln(early.limit_after_minor)}."
                ),
            )
        )

    # Check non-essential outflow deferral (0 financing fee)
    defer = next((a for a in opt.actions if a.kind == "pay_later"), None)
    if defer is not None:
        defer_tx = tx_by_id[defer.transaction_id]
        residual_interest = (defer.limit_after_minor * request.annual_rate_bps * deficit_days) // (10_000 * 365)
        options.append(
            FinancingOption(
                option_kind="defer_outflow",
                title=f"Defer {defer_tx.label} ({defer.transaction_id})",
                estimated_cost_minor=residual_interest,
                credit_needed_minor=defer.limit_after_minor,
                detail=(
                    f"Defer {defer_tx.label} ({defer.transaction_id}) to {day_name(defer.new_date)}; "
                    f"estimated cost {pln(residual_interest)}, credit needed drops to {pln(defer.limit_after_minor)}."
                ),
            )
        )

    options.sort(key=lambda o: (o.estimated_cost_minor, o.credit_needed_minor))
    best = options[0]

    facts = [f"Baseline credit facility needed: {pln(proposal.limit_minor)} over {deficit_days} deficit day(s)."]
    for idx, o in enumerate(options, start=1):
        facts.append(f"Option {idx} ({o.option_kind}): {o.detail}")

    allowed = (
        {0, proposal.limit_minor}
        | {o.estimated_cost_minor for o in options}
        | {o.credit_needed_minor for o in options}
        | {abs(t.amount_minor) for t in request.transactions}
    )

    if mode == "live":
        try:
            explanation, model, latency = _ask_model(
                facts,
                f"Compare the options and explain why Option 1 ({best.title}) is the most cost-effective choice.",
                frozenset(allowed),
            )
        except ModelError as exc:
            raise HTTPException(503, f"The AI explanation is unavailable. {exc}") from exc
    else:
        explanation = " ".join(facts[:2])
        model, latency = "demo-deterministic", None

    return CompareOptionsResponse(
        options=options,
        recommended_option=best.option_kind,
        explanation=explanation,
        model=model,
        latency_ms=latency,
    )

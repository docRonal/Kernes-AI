"""Full-year cash-flow pattern analysis and grounded AI forecast commentary.

All cadence detection, delay measurement, seasonality, volatility, and key chart
drivers are computed deterministically in integer minor units. In live mode,
kernes-qwen-7b (with kernes-qwen fallback) turns those verified facts into a
concise plain-English forecast brief guarded by cited_amounts().
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import defaultdict
from datetime import date

from fastapi import HTTPException, UploadFile

from .advice import (
    ATTEMPTS,
    ModelConfig,
    ModelError,
    call_model,
    cited_amounts,
    day_name,
    pln,
    use_currency,
)
from .forecast import MAX_CSV_BYTES, ForecastInputError, build_forecast, parse_transactions
from .history_forecast import analyze_statement_patterns
from .models import (
    ChartDriver,
    ForecastAnalysisResponse,
    ForecastPatternRow,
    ForecastResponse,
    Transaction,
)
from .telemetry import log_llm_call


log = logging.getLogger("autonomous_cfo.forecast_analysis")

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")

_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "trend_summary": {"type": "string"},
        "ai_callouts": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["trend_summary", "ai_callouts"],
}

_SYSTEM_PROMPT = (
    "You are the quantitative AI CFO analyst explaining a 14-day cash balance chart to an SME owner. "
    "All balances, recurring schedules, payment delays, seasonality percentages, and chart inflection days "
    "were already computed by the backend from the bank statement history. "
    "Use ONLY the exact amounts, dates, percentages, and counterparty names listed in the Facts section. "
    "Never invent figures, dates, or counterparties. Write clear plain English with no markdown. "
    'Reply with JSON: {"trend_summary": "...", "ai_callouts": ["...", "...", "..."]}.'
)


def _clean_text(value: str) -> str:
    return _CONTROL_CHARS.sub(" ", value).strip()


def _strip_estimate_prefix(label: str) -> str:
    return label.removeprefix("Estimated ").strip()


def _build_chart_drivers(forecast: ForecastResponse) -> list[ChartDriver]:
    """Identify the key verified dates driving the shape of the 14-day cash chart."""
    days = forecast.baseline.days
    if not days:
        return []
    start, end = days[0].date, days[-1].date
    in_window = [tx for tx in forecast.transactions if start <= tx.date <= end]
    by_day: dict[date, list[Transaction]] = defaultdict(list)
    for tx in in_window:
        by_day[tx.date].append(tx)

    drivers: list[ChartDriver] = []
    seen_dates: set[date] = set()

    # 1. Lowest projected cash point in the window
    min_day = min(days, key=lambda d: d.balance_minor)
    min_txs = sorted(by_day.get(min_day.date, []), key=lambda t: t.amount_minor)
    if min_txs and min_txs[0].amount_minor < 0:
        lead = _strip_estimate_prefix(min_txs[0].counterparty or min_txs[0].label)
        low_note = f"Lowest balance ({pln(min_day.balance_minor)}) led by {lead} ({pln(min_txs[0].amount_minor)})."
    else:
        low_note = f"Lowest balance in the 14-day window at {pln(min_day.balance_minor)}."
    drivers.append(
        ChartDriver(
            date=min_day.date,
            kind="low",
            amount_minor=min_day.balance_minor,
            label="Lowest cash point",
            note=low_note,
        )
    )
    seen_dates.add(min_day.date)

    # 2. Largest single-day net drop (excluding the lowest day if already captured)
    net_by_day = [(d.date, sum(t.amount_minor for t in by_day.get(d.date, []))) for d in days]
    biggest_drop = min(net_by_day, key=lambda pair: pair[1])
    if biggest_drop[1] < 0 and biggest_drop[0] not in seen_dates:
        day_txs = sorted((t for t in by_day[biggest_drop[0]] if t.amount_minor < 0), key=lambda t: t.amount_minor)
        top_names = ", ".join(_strip_estimate_prefix(t.counterparty or t.label) for t in day_txs[:2])
        drivers.append(
            ChartDriver(
                date=biggest_drop[0],
                kind="drop",
                amount_minor=biggest_drop[1],
                label=top_names or "Largest outflow day",
                note=f"Net {pln(biggest_drop[1])} outflow day ({top_names})." if top_names else f"Net {pln(biggest_drop[1])} outflow day.",
            )
        )
        seen_dates.add(biggest_drop[0])

    # 3. Largest single-day net inflow spike
    biggest_spike = max(net_by_day, key=lambda pair: pair[1])
    if biggest_spike[1] > 0 and biggest_spike[0] not in seen_dates:
        day_txs = sorted((t for t in by_day[biggest_spike[0]] if t.amount_minor > 0), key=lambda t: -t.amount_minor)
        top_names = ", ".join(_strip_estimate_prefix(t.counterparty or t.label) for t in day_txs[:2])
        drivers.append(
            ChartDriver(
                date=biggest_spike[0],
                kind="spike",
                amount_minor=biggest_spike[1],
                label=top_names or "Largest inflow day",
                note=f"Net +{pln(biggest_spike[1])} inflow led by {top_names}." if top_names else f"Net +{pln(biggest_spike[1])} inflow day.",
            )
        )
        seen_dates.add(biggest_spike[0])

    # 4. Notable fixed/tax/rent/payroll milestone inside the window not yet covered
    fixed_cats = {"rent", "tax_social", "staff_payroll", "utility", "owner_draw"}
    fixed_txs = sorted(
        (t for t in in_window if t.amount_minor < 0 and t.category in fixed_cats and t.date not in seen_dates),
        key=lambda t: t.amount_minor,
    )
    if fixed_txs:
        tx = fixed_txs[0]
        party = _strip_estimate_prefix(tx.counterparty or tx.label)
        drivers.append(
            ChartDriver(
                date=tx.date,
                kind="milestone",
                amount_minor=tx.amount_minor,
                label=party,
                note=f"Recurring bill: {party} ({pln(tx.amount_minor)}).",
            )
        )

    drivers.sort(key=lambda d: d.date)
    return drivers


def _deterministic_narrative(
    analysis: dict,
    forecast: ForecastResponse,
    patterns: list[ForecastPatternRow],
    drivers: list[ChartDriver],
) -> tuple[str, list[str]]:
    span_days = analysis["history_span_days"]
    tx_count = analysis["transactions_analyzed"]
    months = analysis["months_analyzed"]
    trend_note = analysis["trend_note"]
    seasonality_note = analysis["seasonality_note"]
    weekend_lift_note = analysis["weekend_lift_note"]
    closure_months = analysis["closure_months"]

    start_bal = forecast.baseline.days[0].balance_minor
    end_bal = forecast.baseline.days[-1].balance_minor
    min_day = min(forecast.baseline.days, key=lambda d: d.balance_minor)
    delayed = [p for p in patterns if p.max_delay_days > 0]

    callouts: list[str] = []

    if patterns and span_days >= 28:
        inflow_pats = [p for p in patterns if p.direction == "inflow"]
        outflow_pats = [p for p in patterns if p.direction == "outflow"]
        summary_parts = [
            f"Scanned {tx_count:,} bank transactions across {span_days} days ({months} months) to map "
            f"{len(patterns)} recurring payment schedules into this 14-day projection."
        ]
        if trend_note:
            summary_parts.append(trend_note)
        elif inflow_pats:
            top_in = inflow_pats[0]
            summary_parts.append(
                f"Primary cash inflow comes from {top_in.counterparty} ({top_in.cadence}, typical {pln(top_in.typical_amount_minor)})."
            )
        if forecast.proposal is not None:
            summary_parts.append(
                f"Cash reaches its lowest point on {day_name(min_day.date)} ({pln(min_day.balance_minor)}), "
                f"requiring up to {pln(forecast.proposal.limit_minor)} in temporary cover."
            )
        else:
            summary_parts.append(
                f"Projected cash stays positive throughout, ranging from {pln(min_day.balance_minor)} "
                f"on {day_name(min_day.date)} to {pln(end_bal)} by {day_name(forecast.baseline.days[-1].date)}."
            )
        trend_summary = " ".join(summary_parts)

        if trend_note:
            callouts.append(trend_note)
        if seasonality_note:
            callouts.append(seasonality_note)
        if weekend_lift_note:
            callouts.append(weekend_lift_note)
        if delayed:
            worst = max(delayed, key=lambda p: p.max_delay_days)
            callouts.append(
                f"Timing jitter: {worst.counterparty} showed {worst.regularity.lower()} across {worst.occurrences} entries."
            )
        else:
            callouts.append(
                f"Payment regularity: all {len(patterns)} recurring streams settled on schedule (±0d delay)."
            )
        if closure_months and len(callouts) < 4:
            callouts.append(
                f"Inactive revenue period detected in {', '.join(closure_months)} (excluded from daily run-rate)."
            )
        if outflow_pats and len(callouts) < 4:
            top_out = outflow_pats[0]
            callouts.append(
                f"Largest recurring outflow: {top_out.counterparty} ({top_out.cadence}, typical {pln(top_out.typical_amount_minor)})."
            )
    else:
        # Short / scheduled CSV with limited history (e.g. 3-row QA case or 2-week export)
        if forecast.proposal is not None:
            trend_summary = (
                f"Analyzed {tx_count} recorded transactions spanning {span_days} days. "
                f"Scheduled bills push cash to {pln(min_day.balance_minor)} on {day_name(min_day.date)} "
                f"(gap {pln(forecast.proposal.limit_minor)}); upload 90+ days of statement history to unlock full-year seasonality and delay detection."
            )
        else:
            trend_summary = (
                f"Analyzed {tx_count} recorded transactions spanning {span_days} days. "
                f"Cash moves from {pln(start_bal)} to {pln(end_bal)} with a low of {pln(min_day.balance_minor)} on {day_name(min_day.date)}; "
                f"upload 90+ days of statement history to unlock full-year seasonality and recurring delay scoring."
            )
        for drv in drivers[:3]:
            callouts.append(f"{day_name(drv.date)}: {drv.note}")
        if span_days < 60:
            callouts.append(
                f"History window is {span_days} days ({tx_count} entries) — recurring schedules need ≥3 cycles."
            )

    return trend_summary, callouts[:4]


def _clean_ai_callouts(raw: object, allowed_minor: frozenset[int], fallback: list[str]) -> list[str]:
    if not isinstance(raw, list):
        return fallback
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        text = _clean_text(item)
        if not text or len(text) > 180:
            continue
        if any(amt not in allowed_minor for amt in cited_amounts(text)):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
        if len(cleaned) == 4:
            break
    return cleaned if len(cleaned) >= 2 else fallback


def build_forecast_analysis(
    *,
    mode: str,
    raw: bytes,
    starting_balance_minor: int,
    start_date: date,
) -> ForecastAnalysisResponse:
    transactions, detected_currency = parse_transactions(raw)
    forecast = build_forecast(raw, starting_balance_minor, start_date)

    with use_currency(detected_currency):
        analysis = analyze_statement_patterns(transactions, start_date)
        patterns = [
            ForecastPatternRow(
                counterparty=p["counterparty"],
                direction=p["direction"],
                category=p["category"],
                cadence=p["cadence"],
                occurrences=p["occurrences"],
                typical_amount_minor=p["typical_amount_minor"],
                regularity=p["regularity"],
                avg_delay_days=p["avg_delay_days"],
                max_delay_days=p["max_delay_days"],
            )
            for p in analysis["patterns"]
        ]
        drivers = _build_chart_drivers(forecast)
        det_summary, det_callouts = _deterministic_narrative(analysis, forecast, patterns, drivers)

        base_response = ForecastAnalysisResponse(
            currency=detected_currency,
            history_span_days=analysis["history_span_days"],
            transactions_analyzed=analysis["transactions_analyzed"],
            months_analyzed=analysis["months_analyzed"],
            daily_volatility_minor=analysis["daily_volatility_minor"],
            trend_note=analysis["trend_note"],
            seasonality_note=analysis["seasonality_note"],
            weekend_lift_note=analysis["weekend_lift_note"],
            closure_months=analysis["closure_months"],
            trend_summary=det_summary,
            ai_callouts=det_callouts,
            chart_drivers=drivers,
            patterns=patterns,
            ai_error=None,
            model="demo-deterministic",
            latency_ms=0,
        )

        if mode != "live":
            return base_response

        fact_lines = [
            f"Statement history: {analysis['transactions_analyzed']} transactions over {analysis['history_span_days']} days ({analysis['months_analyzed']} months), currency={detected_currency}.",
            f"Forecast window: {day_name(forecast.baseline.days[0].date)} to {day_name(forecast.baseline.days[-1].date)} ({'history-based recurrence projection' if forecast.forecast_basis == 'history' else 'recorded scheduled transactions'}).",
            f"Opening balance: {pln(starting_balance_minor)}. Ending balance: {pln(forecast.baseline.days[-1].balance_minor)}.",
            f"Typical daily cash swing (MAD): {pln(analysis['daily_volatility_minor'])}.",
        ]
        if forecast.proposal is not None:
            fact_lines.append(
                f"Projected shortfall: first on {day_name(forecast.proposal.first_shortfall.date)} "
                f"({pln(forecast.proposal.first_shortfall.shortfall_minor)}), deepest on "
                f"{day_name(forecast.proposal.deepest_shortfall.date)} ({pln(forecast.proposal.deepest_shortfall.shortfall_minor)})."
            )
        if analysis["trend_note"]:
            fact_lines.append(f"Full-year trend: {analysis['trend_note']}")
        if analysis["seasonality_note"]:
            fact_lines.append(f"Seasonality: {analysis['seasonality_note']}")
        if analysis["weekend_lift_note"]:
            fact_lines.append(f"Weekly pattern: {analysis['weekend_lift_note']}")
        if analysis["closure_months"]:
            fact_lines.append(f"Zero-revenue closure months: {', '.join(analysis['closure_months'])}.")
        if drivers:
            fact_lines.append("Key chart inflection days:")
            fact_lines.extend(f"- {day_name(d.date)} ({d.kind}): {d.note}" for d in drivers)
        if patterns:
            fact_lines.append("Top detected recurring schedules & payment regularity:")
            fact_lines.extend(
                f"- {p.counterparty} ({p.direction}, {p.cadence}, {p.occurrences}x, typical {pln(p.typical_amount_minor)}, {p.regularity})"
                for p in patterns[:8]
            )

        facts_text = "\n".join(fact_lines)
        allowed_minor = frozenset(
            {0, abs(starting_balance_minor), analysis["daily_volatility_minor"]}
            | set(cited_amounts(facts_text))
            | {abs(d.balance_minor) for d in forecast.baseline.days}
            | {abs(t.amount_minor) for t in forecast.transactions}
            | {p.typical_amount_minor for p in patterns}
            | {abs(d.amount_minor) for d in drivers}
            | (
                {
                    forecast.proposal.limit_minor,
                    forecast.proposal.first_shortfall.shortfall_minor,
                    forecast.proposal.deepest_shortfall.shortfall_minor,
                }
                if forecast.proposal is not None
                else set()
            )
        )

        task_instruction = (
            "Write JSON with keys trend_summary (2-3 plain-English sentences explaining the full-year trend, "
            "seasonality/regularity, and what drives the 14-day chart curve using ONLY exact figures from the facts) "
            "and ai_callouts (array of 3 concise plain-English bullets under 130 characters each highlighting "
            "the biggest curve driver, seasonality/trend signal, and payment timing/delay regularity)."
        )
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Facts:\n{facts_text}\n\n{task_instruction}"},
        ]

        started = time.monotonic()
        try:
            primary = ModelConfig.from_env()
        except ModelError as exc:
            log.warning("forecast-analysis model unconfigured: %s", exc)
            return base_response.model_copy(
                update={
                    "model": "deterministic-fallback",
                    "ai_error": f"AI commentary unavailable ({exc}); showing verified statistical scan.",
                    "latency_ms": round((time.monotonic() - started) * 1000),
                }
            )

        def _run_model(config: ModelConfig, *, fallback_used: bool) -> ForecastAnalysisResponse:
            problem = "no valid response"
            for attempt in range(1, ATTEMPTS + 1):
                raw_reply = call_model(config, messages, schema=_ANALYSIS_SCHEMA)
                text = raw_reply.strip()
                if text.startswith("```"):
                    text = text.strip("`").removeprefix("json").strip()
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ModelError("The model didn't return JSON.") from exc
                if not isinstance(parsed, dict):
                    raise ModelError("The model returned a non-object JSON payload.")

                llm_summary = parsed.get("trend_summary")
                if not isinstance(llm_summary, str) or not llm_summary.strip():
                    problem = "missing trend_summary"
                    continue
                llm_summary = _clean_text(llm_summary)
                unknown = [amt for amt in cited_amounts(llm_summary) if amt not in allowed_minor]
                if unknown:
                    problem = f"it cites {pln(unknown[0])}, which isn't in the calculated facts"
                    log.warning("forecast_analysis model=%s attempt=%d rejected: %s", config.name, attempt, problem)
                    continue

                llm_callouts = _clean_ai_callouts(parsed.get("ai_callouts"), allowed_minor, det_callouts)
                latency = round((time.monotonic() - started) * 1000)
                log.info(
                    "forecast_analysis model=%s attempts=%d latency_ms=%d status=ok",
                    config.name,
                    attempt,
                    latency,
                )
                log_llm_call(
                    endpoint="forecast-analysis",
                    model=config.name,
                    latency_ms=latency,
                    status="ok",
                    attempts=attempt,
                    grounded=True,
                    fallback_used=fallback_used,
                )
                return base_response.model_copy(
                    update={
                        "trend_summary": llm_summary,
                        "ai_callouts": llm_callouts,
                        "ai_error": None,
                        "model": config.name,
                        "latency_ms": latency,
                    }
                )

            raise ModelError(f"The model's forecast analysis didn't match the calculated figures: {problem}.")

        try:
            return _run_model(primary, fallback_used=False)
        except ModelError as primary_exc:
            fallback = ModelConfig.fallback_from_env(timeout=primary.timeout, ssl_context=primary.ssl_context)
            if fallback is not None:
                log.warning(
                    "forecast_analysis primary=%s failed (%s); falling back to %s",
                    primary.name,
                    primary_exc,
                    fallback.name,
                )
                try:
                    return _run_model(fallback, fallback_used=True)
                except ModelError as fallback_exc:
                    err_msg = str(fallback_exc)
                    model_used = fallback.name
                    attempts_used = ATTEMPTS * 2
                    fb_flag = True
            else:
                err_msg = str(primary_exc)
                model_used = primary.name
                attempts_used = ATTEMPTS
                fb_flag = False

            latency = round((time.monotonic() - started) * 1000)
            log_llm_call(
                endpoint="forecast-analysis",
                model=model_used,
                latency_ms=latency,
                status="error",
                attempts=attempts_used,
                grounded=False,
                fallback_used=fb_flag,
            )
            return base_response.model_copy(
                update={
                    "model": "deterministic-fallback",
                    "ai_error": f"AI commentary unavailable ({err_msg}); showing verified statistical scan.",
                    "latency_ms": latency,
                }
            )


async def get_forecast_analysis(
    *,
    mode: str,
    file: UploadFile,
    starting_balance_minor: int,
    start_date: date,
) -> ForecastAnalysisResponse:
    raw = await file.read(MAX_CSV_BYTES + 1)
    try:
        return build_forecast_analysis(
            mode=mode,
            raw=raw,
            starting_balance_minor=starting_balance_minor,
            start_date=start_date,
        )
    except ForecastInputError as exc:
        raise HTTPException(422, str(exc)) from exc

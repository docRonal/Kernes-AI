"""Guided CFO action plan composition for Chat-First survival and growth flows.

All cash numbers, anomalies, payment move rankings, stress buffers, and safe
reinvestment limits are calculated deterministically in integer minor units. In
live mode, the OpenShift AI model translates those verified facts and the owner's
business profile into plain-English guidance guarded by cited_amounts().
"""

from __future__ import annotations

import json
import logging
import re
import time

from fastapi import HTTPException

from .advice import (
    ATTEMPTS,
    ModelConfig,
    ModelError,
    _OFF_LIMITS,
    _SENTENCE_END,
    call_model,
    cited_amounts,
    day_name,
    pln,
)
from .advisory_extras import _validate_window, compare_financing_options, detect_anomalies
from .forecast import classify_transaction, propose
from .insights import evaluate_stress, optimize_payments
from .models import (
    ActionPlanRequest,
    ActionPlanResponse,
    ActionPlanStep,
    AnomalyDetectRequest,
    CompareOptionsRequest,
    InsightRequest,
    Transaction,
    TransactionActionability,
    TransactionCategory,
)
from .telemetry import log_llm_call


log = logging.getLogger("autonomous_cfo.action_plan")

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")

_ACTION_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "email_draft": {"type": "string"},
    },
    "required": ["headline", "summary", "email_draft"],
}

_SYSTEM_PROMPT = (
    "You are an approachable AI CFO advisor speaking directly to an SME business owner. "
    "All numbers, dates, counterparties, and action steps are already calculated by the backend. "
    "Use ONLY the exact amounts, dates, and names listed in the Facts section. "
    "Never invent figures, fees, dates, or counterparties, and never use finance jargon unless quoting a supplied fact. "
    'No markdown. Reply with JSON: {"headline": "...", "summary": "...", "email_draft": "..."}.'
)


def _clean_prompt_text(value: str) -> str:
    return _CONTROL_CHARS.sub(" ", value).strip()


def _effective_classification(tx: Transaction) -> tuple[TransactionCategory, TransactionActionability]:
    if tx.category is not None and tx.actionability is not None:
        return tx.category, tx.actionability
    return classify_transaction(
        tx.transaction_type or "",
        tx.counterparty or tx.label,
        tx.payment_reference or "",
        tx.amount_minor,
    )


def _clean_email_draft(draft: str, allowed_minor: frozenset[int]) -> str:
    lines: list[str] = []
    for line in draft.splitlines():
        kept = [
            sentence
            for sentence in _SENTENCE_END.split(line)
            if not _OFF_LIMITS.search(sentence)
            and all(amount in allowed_minor for amount in cited_amounts(sentence))
        ]
        lines.append(" ".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _template_email_draft(
    email_kind: str,
    counterparty: str,
    tx: Transaction,
    due_date,
    new_date,
) -> str:
    amt = pln(abs(tx.amount_minor))
    ref_part = f" ({tx.payment_reference})" if tx.payment_reference else ""
    if email_kind == "collect_early":
        return (
            f"Hello,\n\nWe hope all is well. Could you arrange payment for {counterparty}{ref_part} "
            f"({tx.id}) of {amt}, currently scheduled for {day_name(due_date)}, by {day_name(new_date)} "
            "instead? Please let us know if that works for you.\n\nKind regards,\nThe finance team"
        )
    return (
        f"Hello,\n\nWe hope all is well. Regarding {tx.payment_reference or counterparty} ({tx.id}) "
        f"for {amt} payable to {counterparty}, would it be possible to shift payment from "
        f"{day_name(due_date)} to {day_name(new_date)}? Please let us know if that works on your side."
        "\n\nKind regards,\nThe finance team"
    )


def _suggested_questions(plan_mode: str, currency: str) -> list[str]:
    if currency == "EUR":
        oven_amt = "€3,000"
    else:
        oven_amt = f"{currency} 3,000"
    if plan_mode == "survival":
        return [
            "What is the riskiest day in this forecast?",
            "What happens if a client pays 3 days late?",
            "Which regular bills leave even if sales slow down?",
        ]
    return [
        f"Can I safely spend {oven_amt} on new equipment?",
        "What happens to my cash if sales drop or payments are delayed?",
        "Which day has the lowest cash balance?",
    ]


def build_action_plan(*, mode: str, request: ActionPlanRequest) -> ActionPlanResponse:
    _validate_window(request.baseline)
    insight_req = InsightRequest(
        baseline=request.baseline,
        transactions=request.transactions,
        currency=request.currency,
    )
    proposal = propose(request.baseline, request.transactions)
    anomalies = detect_anomalies(
        mode="demo",
        request=AnomalyDetectRequest(
            baseline=request.baseline,
            transactions=request.transactions,
            currency=request.currency,
        ),
    )
    opt = optimize_payments(insight_req)
    stress, stressed_low = evaluate_stress(insight_req)
    comparison = compare_financing_options(
        mode="demo",
        request=CompareOptionsRequest(
            baseline=request.baseline,
            transactions=request.transactions,
            currency=request.currency,
        ),
    )

    tx_by_id = {t.id: t for t in request.transactions}
    class_by_id = {t.id: _effective_classification(t) for t in request.transactions}

    steps_raw: list[ActionPlanStep] = []
    email_step_index: int | None = None

    if anomalies.findings:
        top_finding = anomalies.findings[0]
        first_tx = tx_by_id.get(top_finding.transaction_ids[0])
        party = (first_tx.counterparty or first_tx.label) if first_tx else None
        title = (
            f"Check duplicate payment for {party}"
            if top_finding.kind == "duplicate_payment" and party
            else f"Review large payment to {party}"
            if party
            else "Review unusual payment activity"
        )
        steps_raw.append(
            ActionPlanStep(
                step_number=1,
                title=title,
                detail=top_finding.detail,
                autonomy_level="analyzed",
                action_kind="review_anomaly",
                impact_minor=top_finding.amount_minor,
                counterparty=party,
            )
        )

    if proposal is not None:
        plan_mode = "survival"
        collect_early = [
            a
            for a in opt.actions
            if a.kind == "collect_earlier" and class_by_id[a.transaction_id][1] == "email_collect_early"
        ]
        defer_supplier = [
            a
            for a in opt.actions
            if a.kind == "pay_later" and class_by_id[a.transaction_id][1] == "email_defer_supplier"
        ]
        owner_draws = [
            a
            for a in opt.actions
            if a.kind == "pay_later" and class_by_id[a.transaction_id][1] == "owner_draw_flexible"
        ]

        if owner_draws:
            top_owner = owner_draws[0]
            owner_tx = tx_by_id[top_owner.transaction_id]
            owner_party = owner_tx.counterparty or owner_tx.label
            steps_raw.append(
                ActionPlanStep(
                    step_number=1,
                    title=f"Delay owner withdrawal for {owner_party}",
                    detail=(
                        f"Shifting {owner_party} ({owner_tx.id}, {pln(abs(owner_tx.amount_minor))}) from "
                        f"{day_name(top_owner.due_date)} to {day_name(top_owner.new_date)} cuts the facility needed "
                        f"by {pln(top_owner.saves_minor)} (leaving {pln(top_owner.limit_after_minor)})."
                    ),
                    autonomy_level="recommended",
                    action_kind="shift_payment",
                    impact_minor=top_owner.saves_minor,
                    counterparty=owner_party,
                )
            )

        best_email: tuple[str, object] | None = None
        if collect_early:
            best_email = ("collect_early", collect_early[0])
        elif defer_supplier:
            best_email = ("defer_supplier", defer_supplier[0])

        if best_email is not None:
            email_kind, email_action = best_email
            target_tx = tx_by_id[email_action.transaction_id]
            party = target_tx.counterparty or target_tx.label
            template_draft = _template_email_draft(
                email_kind,
                party,
                target_tx,
                email_action.due_date,
                email_action.new_date,
            )
            if email_kind == "collect_early":
                step_title = f"Ask {party} to pay earlier"
                step_detail = (
                    f"Asking {party} ({target_tx.id}, {pln(abs(target_tx.amount_minor))}) to pay by "
                    f"{day_name(email_action.new_date)} instead of {day_name(email_action.due_date)} saves "
                    f"{pln(email_action.saves_minor)} (credit needed after move: {pln(email_action.limit_after_minor)})."
                )
            else:
                step_title = f"Ask {party} for a short payment extension"
                step_detail = (
                    f"Moving {party} ({target_tx.id}, {pln(abs(target_tx.amount_minor))}) from "
                    f"{day_name(email_action.due_date)} to {day_name(email_action.new_date)} saves "
                    f"{pln(email_action.saves_minor)} (credit needed after move: {pln(email_action.limit_after_minor)})."
                )
            email_step_index = len(steps_raw)
            steps_raw.append(
                ActionPlanStep(
                    step_number=1,
                    title=step_title,
                    detail=step_detail,
                    autonomy_level="recommended",
                    action_kind="shift_payment",
                    impact_minor=email_action.saves_minor,
                    counterparty=party,
                    email_kind=email_kind,
                    email_draft=template_draft,
                )
            )

        credit_opt = next((o for o in comparison.options if o.option_kind == "credit_facility"), None)
        cost_note = (
            f" (estimated short-term interest {pln(credit_opt.estimated_cost_minor)})"
            if credit_opt is not None
            else ""
        )
        steps_raw.append(
            ActionPlanStep(
                step_number=1,
                title="Cover remaining gap with a simulated credit line",
                detail=(
                    f"Approve or reject a temporary {pln(proposal.limit_minor)} facility{cost_note} to cover "
                    f"the deepest dip on {day_name(proposal.deepest_shortfall.date)}. Simulation only."
                ),
                autonomy_level="requires_approval",
                action_kind="credit_facility",
                impact_minor=proposal.limit_minor,
            )
        )

        # Preserve order while respecting max_length=4 (drop optional anomaly first if >4).
        if len(steps_raw) > 4:
            steps_raw = steps_raw[-4:]
            if email_step_index is not None:
                email_step_index = next(
                    (idx for idx, s in enumerate(steps_raw) if s.email_draft is not None),
                    None,
                )

        headline = (
            f"Cash dips by {pln(proposal.deepest_shortfall.shortfall_minor)} on "
            f"{day_name(proposal.deepest_shortfall.date)}"
        )
        first = proposal.first_shortfall
        deepest = proposal.deepest_shortfall
        if first.date == deepest.date:
            summary = (
                f"Your balance is projected to drop below zero on {day_name(first.date)} by "
                f"{pln(first.shortfall_minor)}. Follow the steps below to shrink the gap first, then "
                f"cover up to {pln(proposal.limit_minor)} with a simulated credit line."
            )
        else:
            summary = (
                f"Cash first goes below zero on {day_name(first.date)} ({pln(first.shortfall_minor)}) and "
                f"reaches {pln(-deepest.shortfall_minor)} on {day_name(deepest.date)}. Follow the action steps "
                f"below to cut the gap or cover up to {pln(proposal.limit_minor)} in simulation."
            )
    else:
        plan_mode = "growth"
        min_day = min(request.baseline.days, key=lambda d: d.balance_minor)
        min_bal = min_day.balance_minor
        growth_headroom = max(0, stressed_low)
        safety_buffer = min_bal - growth_headroom

        steps_raw.append(
            ActionPlanStep(
                step_number=1,
                title="Keep a cash buffer for the tested stresses",
                detail=(
                    f"The baseline low is {pln(min_bal)} on {day_name(min_day.date)}. "
                    f"The lowest balance in the tested scenarios is {pln(stressed_low)}."
                ),
                autonomy_level="analyzed",
                action_kind="growth_buffer",
                impact_minor=safety_buffer,
            )
        )
        steps_raw.append(
            ActionPlanStep(
                step_number=1,
                title="Projected budget under the tested scenarios",
                detail=(
                    f"The tested scenarios leave {pln(growth_headroom)} above zero for equipment or savings."
                    if stressed_low > 0
                    else "The tested scenarios leave no room for extra spending."
                ),
                autonomy_level="recommended",
                action_kind="growth_buffer",
                impact_minor=growth_headroom,
            )
        )
        if len(steps_raw) > 4:
            steps_raw = steps_raw[:4]

        headline = f"Projected cash headroom under stress: {pln(growth_headroom)}"
        summary = (
            f"Your lowest projected balance is {pln(min_bal)}. Delayed income and higher expenses "
            f"bring the lowest tested balance to {pln(stressed_low)}."
        )

    steps = [step.model_copy(update={"step_number": idx}) for idx, step in enumerate(steps_raw, start=1)]
    questions = _suggested_questions(plan_mode, request.currency)

    if mode == "demo":
        return ActionPlanResponse(
            mode=plan_mode,
            headline=headline,
            summary=summary,
            steps=steps,
            suggested_questions=questions,
            model="demo-deterministic",
            latency_ms=0,
        )

    allowed_minor = frozenset(
        {0}
        | {abs(d.balance_minor) for d in request.baseline.days}
        | {abs(t.amount_minor) for t in request.transactions}
        | {s.impact_minor for s in steps}
        | {stress.proposed_limit_minor, stress.buffer_minor, stress.recommended_limit_minor}
        | {o.estimated_cost_minor for o in comparison.options}
        | {o.credit_needed_minor for o in comparison.options}
        | {a.amount_minor for a in anomalies.findings}
        | (
            {
                proposal.limit_minor,
                proposal.first_shortfall.shortfall_minor,
                proposal.deepest_shortfall.shortfall_minor,
            }
            if proposal is not None
            else {min_bal, abs(stressed_low), growth_headroom}
        )
    )

    business_type = _clean_prompt_text(request.profile.business_type)
    goal = _clean_prompt_text(request.profile.goal)
    fact_lines = [
        f"Owner profile: business={business_type}; goal={goal}; mode={plan_mode}; currency={request.currency}.",
        f"Forecast period: {day_name(request.baseline.days[0].date)} to {day_name(request.baseline.days[-1].date)}.",
        f"Deterministic summary: {summary}",
        "Calculated action steps:",
        *(f"- Step {s.step_number} ({s.action_kind}): {s.title} — {s.detail}" for s in steps),
    ]
    email_step = steps[email_step_index] if email_step_index is not None else None
    if email_step is not None:
        fact_lines.append(
            f"Email target: counterparty={email_step.counterparty}; kind={email_step.email_kind}; "
            f"template_draft={email_step.email_draft}"
        )
    else:
        fact_lines.append('There is no email draft needed for this plan, so set email_draft to "".')

    task_instruction = (
        "Write JSON with keys headline (under 14 words), summary (2-3 plain-English sentences tailored to this "
        "owner's business and goal using ONLY exact amounts and dates from the facts above), and email_draft "
        "(either a polite <70 word email matching template_draft with zero credit/facility/shortfall terms, or empty string if none needed)."
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join([*fact_lines, "", task_instruction])},
    ]

    try:
        primary = ModelConfig.from_env()
    except ModelError as exc:
        raise HTTPException(503, f"The AI action plan is unavailable. {exc}") from exc

    started = time.monotonic()

    def _run_model(config: ModelConfig, *, fallback_used: bool) -> ActionPlanResponse:
        problem = "no valid response"
        for attempt in range(1, ATTEMPTS + 1):
            raw = call_model(config, messages, schema=_ACTION_PLAN_SCHEMA)
            text = raw.strip()
            if text.startswith("```"):
                text = text.strip("`").removeprefix("json").strip()
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ModelError("The model didn't return JSON.") from exc

            if not isinstance(parsed, dict):
                raise ModelError("The model returned a non-object JSON payload.")

            llm_headline = parsed.get("headline")
            llm_summary = parsed.get("summary")
            llm_email = parsed.get("email_draft", "")

            if not isinstance(llm_headline, str) or not llm_headline.strip():
                problem = "missing headline"
                continue
            if not isinstance(llm_summary, str) or not llm_summary.strip():
                problem = "missing summary"
                continue

            unknown = [
                amt
                for amt in (cited_amounts(llm_headline) + cited_amounts(llm_summary))
                if amt not in allowed_minor
            ]
            if unknown:
                problem = f"it cites {pln(unknown[0])}, which isn't in the calculated facts"
                log.warning("action_plan model=%s attempt=%d rejected: %s", config.name, attempt, problem)
                continue

            updated_steps = list(steps)
            if email_step is not None and isinstance(llm_email, str) and llm_email.strip():
                cleaned_email = _clean_email_draft(llm_email, allowed_minor)
                if cleaned_email:
                    updated_steps[email_step_index] = email_step.model_copy(update={"email_draft": cleaned_email})

            latency = round((time.monotonic() - started) * 1000)
            log.info(
                "action_plan model=%s mode=%s attempts=%d latency_ms=%d status=ok",
                config.name,
                plan_mode,
                attempt,
                latency,
            )
            log_llm_call(
                endpoint="action-plan",
                model=config.name,
                latency_ms=latency,
                status="ok",
                attempts=attempt,
                grounded=True,
                fallback_used=fallback_used,
            )
            return ActionPlanResponse(
                mode=plan_mode,
                headline=llm_headline.strip(),
                summary=llm_summary.strip(),
                steps=updated_steps,
                suggested_questions=questions,
                model=config.name,
                latency_ms=latency,
            )

        raise ModelError(f"The model's action plan didn't match the calculated figures: {problem}.")

    try:
        return _run_model(primary, fallback_used=False)
    except ModelError as primary_exc:
        fallback = ModelConfig.fallback_from_env(timeout=primary.timeout, ssl_context=primary.ssl_context)
        if fallback is None:
            latency = round((time.monotonic() - started) * 1000)
            log_llm_call(
                endpoint="action-plan",
                model=primary.name,
                latency_ms=latency,
                status="error",
                attempts=ATTEMPTS,
                grounded=False,
                fallback_used=False,
            )
            raise HTTPException(503, f"The AI action plan is unavailable. {primary_exc}") from primary_exc
        log.warning("action_plan primary=%s failed (%s); falling back to %s", primary.name, primary_exc, fallback.name)
        try:
            return _run_model(fallback, fallback_used=True)
        except ModelError as fallback_exc:
            latency = round((time.monotonic() - started) * 1000)
            log_llm_call(
                endpoint="action-plan",
                model=fallback.name,
                latency_ms=latency,
                status="error",
                attempts=ATTEMPTS * 2,
                grounded=False,
                fallback_used=True,
            )
            raise HTTPException(503, f"The AI action plan is unavailable. {fallback_exc}") from fallback_exc

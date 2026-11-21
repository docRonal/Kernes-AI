"""Risk checks on top of the forecast: stress test, payment optimization, credit
scorecard and what-if.

Like forecast.py, every amount is integer grosz and nothing here calls the
network or the model. Moves are worked out in day offsets from the first
forecast day, so no date arithmetic can run past the calendar.
"""

import re
from datetime import timedelta

from .advice import day_name, pln
from .forecast import ForecastInputError, propose, suggest_earlier_payments
from .history_forecast import ESTIMATED_ID_PREFIX
from .models import (
    AdviceRequest,
    CreditCheckResponse,
    DailyBalance,
    Deficit,
    InsightRequest,
    PaymentAction,
    PaymentOptimizationResponse,
    ScoreFactor,
    StressScenario,
    StressTestResponse,
    WhatIf,
)

# (old offset, old amount, new offset, new amount): one movement moved or resized.
Change = tuple[int, int, int, int]

# Obligations an owner can't just pay later: wages, taxes, social insurance, loans.
_NOT_POSTPONABLE = re.compile(r"\b(payroll|salary|salaries|wages?|tax(es)?|vat|zus|pensions?|loans?)\b", re.IGNORECASE)


def _balances_after(days: list[DailyBalance], changes: list[Change]) -> list[int]:
    """End-of-day balances after the changes. Offsets outside the window don't count."""
    balances = []
    for index, day in enumerate(days):
        delta = 0
        for old, old_amount, new, new_amount in changes:
            if 0 <= old <= index:
                delta -= old_amount
            if 0 <= new <= index:
                delta += new_amount
        balances.append(day.balance_minor + delta)
    return balances


def _deepest(days: list[DailyBalance], balances: list[int]) -> Deficit | None:
    lowest = min(balances)
    if lowest >= 0:
        return None
    return Deficit(date=days[balances.index(lowest)].date, shortfall_minor=-lowest)  # index() keeps the earliest day


def stress_test(request: InsightRequest) -> StressTestResponse:
    """How much more credit the bad cases would need: clients paying late, costs rising."""
    days = request.baseline.days
    proposed = max(0, -min(day.balance_minor for day in days))
    window = [
        ((t.date - days[0].date).days, t.amount_minor)
        for t in request.transactions
        if days[0].date <= t.date <= days[-1].date
    ]

    def late(days_late: int) -> list[Change]:
        return [(at, amount, at + days_late, amount) for at, amount in window if amount > 0]

    # 10% more, rounded half up to the grosz.
    costlier = [(at, amount, at, amount - (-amount * 10 + 50) // 100) for at, amount in window if amount < 0]
    cases = [
        ("inflows_3_days_late", "Every incoming payment arrives 3 days later.", late(3)),
        ("inflows_5_days_late", "Every incoming payment arrives 5 days later.", late(5)),
        ("outflows_10_percent_higher", "Every outgoing payment is 10% higher.", costlier),
        ("combined", "Incoming payments arrive 5 days later and outgoing payments are 10% higher.", late(5) + costlier),
    ]
    scenarios = []
    for name, description, changes in cases:
        deepest = _deepest(days, _balances_after(days, changes))
        needed = deepest.shortfall_minor if deepest else 0
        scenarios.append(
            StressScenario(
                name=name,
                description=description,
                deepest_shortfall=deepest,
                extra_needed_minor=max(0, needed - proposed),
            )
        )
    buffer = max(scenario.extra_needed_minor for scenario in scenarios)
    return StressTestResponse(
        proposed_limit_minor=proposed,
        scenarios=scenarios,
        buffer_minor=buffer,
        recommended_limit_minor=proposed + buffer,
    )


def optimize_payments(request: InsightRequest) -> PaymentOptimizationResponse:
    """Ways to need less credit, best first: collect an invoice earlier or pay a bill later.

    An invoice uses the pay-by date of earlier_payments. A bill moves to the earliest
    later day that does the most good, so the ask stays small; wages, taxes, social
    insurance and loan repayments are never moved. Ranked by the facility still
    needed, then by how many days the payment moves.
    """
    baseline, transactions = request.baseline, request.transactions
    proposal = propose(baseline, transactions)
    if proposal is None:
        return PaymentOptimizationResponse(proposed_limit_minor=0, actions=[])
    days, limit = baseline.days, proposal.limit_minor
    due = {t.id: t.date for t in transactions}
    actions = [
        PaymentAction(
            kind="collect_earlier",
            transaction_id=option.transaction_id,
            due_date=due[option.transaction_id],
            new_date=option.pay_by,
            limit_after_minor=option.limit_after_minor,
            saves_minor=limit - option.limit_after_minor,
        )
        for option in suggest_earlier_payments(baseline, transactions, proposal)
    ]
    for t in transactions:
        # A bill due after the deepest day can't lift it.
        if t.amount_minor >= 0 or not days[0].date <= t.date <= proposal.deepest_shortfall.date:
            continue
        if t.id.startswith(ESTIMATED_ID_PREFIX) or _NOT_POSTPONABLE.search(t.label):
            continue
        at = (t.date - days[0].date).days
        best: tuple[int, int] | None = None
        for later in range(at + 1, len(days)):
            after = max(0, -min(_balances_after(days, [(at, t.amount_minor, later, t.amount_minor)])))
            if best is None or after < best[0]:
                best = (after, later)
        if best is not None and best[0] < limit:
            actions.append(
                PaymentAction(
                    kind="pay_later",
                    transaction_id=t.id,
                    due_date=t.date,
                    new_date=days[best[1]].date,
                    limit_after_minor=best[0],
                    saves_minor=limit - best[0],
                )
            )
    actions.sort(key=lambda a: (a.limit_after_minor, abs((a.new_date - a.due_date).days), a.transaction_id))
    return PaymentOptimizationResponse(proposed_limit_minor=limit, actions=actions)


def credit_scorecard(request: AdviceRequest) -> CreditCheckResponse:
    """Score the proposed facility from 100 down, one deduction per risk, each with its reason.

    The point values are this app's illustrative scorecard, not a bank's credit model.
    The explanation fields stay empty; consultant.py asks the model to fill them.
    """
    baseline, transactions = request.baseline, request.transactions
    proposal = propose(baseline, transactions)
    if proposal is None:
        raise ForecastInputError("The baseline never goes below zero, so there is no credit facility to check.")
    days, limit = baseline.days, proposal.limit_minor
    window = [t for t in transactions if days[0].date <= t.date <= days[-1].date]
    money_in = [t for t in window if t.amount_minor > 0 and t.date >= proposal.first_shortfall.date]
    incoming = sum(t.amount_minor for t in money_in)
    outgoing = -sum(t.amount_minor for t in window if t.amount_minor < 0)
    short = [index for index, day in enumerate(days) if day.balance_minor < 0]

    def factor(name, points, reason):
        return ScoreFactor(name=name, points=points, reason=reason)

    if days[-1].balance_minor < 0:
        repayment = factor(
            "repayment",
            30,
            f"The balance is still {pln(days[-1].balance_minor)} on {day_name(days[-1].date)}, "
            "so the facility would not be repaid within the forecast.",
        )
    else:
        back = days[short[-1] + 1].date
        repayment = factor("repayment", 0, f"The balance is back above zero from {day_name(back)} to the end of the forecast.")
    coverage = factor(
        "coverage",
        25 if incoming < limit else 10 if incoming < 2 * limit else 0,
        f"Payments due in from the first shortfall on add up to {pln(incoming)}, "
        f"{incoming * 100 // limit}% of the {pln(limit)} facility.",
    )
    duration = factor(
        "duration",
        20 if len(short) >= 8 else 10 if len(short) >= 4 else 0,
        f"The balance is below zero on {len(short)} of the {len(days)} days.",
    )
    depth = factor(
        "depth",
        15 if limit * 100 > 50 * outgoing else 5 if limit * 100 >= 25 * outgoing else 0,
        f"The facility is {limit * 100 // outgoing}% of the {pln(outgoing)} going out during the forecast."
        if outgoing
        else "Nothing goes out during the forecast, so the gap comes from the opening balance.",
    )
    if money_in:
        top = max(money_in, key=lambda t: t.amount_minor)
        concentration = factor(
            "concentration",
            15 if top.amount_minor * 100 > 80 * incoming else 5 if top.amount_minor * 100 > 50 * incoming else 0,
            f"The largest payment due in, {top.label} ({top.id}) for {pln(top.amount_minor)}, "
            f"is {top.amount_minor * 100 // incoming}% of that money.",
        )
    else:
        concentration = factor("concentration", 0, "No payment is due in after the first shortfall.")
    if request.client_delays:
        late = []
        for t in window:
            delay = request.client_delays.get(t.id, request.client_delays.get(t.label))
            if t.amount_minor > 0 and delay:
                at = (t.date - days[0].date).days
                late.append((at, t.amount_minor, at + delay, t.amount_minor))
        delayed = max(0, -min(_balances_after(days, late)))
        delays = (
            factor("delays", 15, f"Clients who paid late before would push the gap to {pln(delayed)}.")
            if delayed > limit
            else factor("delays", 0, f"The late payments seen before don't deepen the gap beyond {pln(limit)}.")
        )
    else:
        delays = factor("delays", 0, "No payment delay history was given.")

    factors = [repayment, coverage, duration, depth, concentration, delays]
    score = max(0, 100 - sum(f.points for f in factors))
    return CreditCheckResponse(
        score=score,
        risk="low" if score >= 70 else "medium" if score >= 40 else "high",
        limit_minor=limit,
        factors=factors,
        explanation=None,
        explanation_error=None,
        model=None,
        latency_ms=None,
    )


def what_if(request: InsightRequest, transaction_id: str, amount_change_minor: int, days_later: int) -> WhatIf | None:
    """The forecast with one transaction in the window resized or moved, as the owner asked.

    A positive change makes the payment bigger, whichever way the money flows.
    None when the transaction isn't in the window or the new date runs off the calendar.
    """
    days = request.baseline.days
    target = next(
        (t for t in request.transactions if t.id == transaction_id and days[0].date <= t.date <= days[-1].date), None
    )
    if target is None:
        return None
    try:
        new_date = target.date + timedelta(days=days_later)
    except OverflowError:
        return None
    sign = 1 if target.amount_minor > 0 else -1
    new_amount = sign * max(0, abs(target.amount_minor) + amount_change_minor)
    at = (target.date - days[0].date).days
    # Money moved before the forecast starts is already in by day one, like the opening balance.
    moved_to = max(0, at + days_later)
    deepest = _deepest(days, _balances_after(days, [(at, target.amount_minor, moved_to, new_amount)]))
    return WhatIf(transaction_id=target.id, new_amount_minor=new_amount, new_date=new_date, deepest_shortfall=deepest)

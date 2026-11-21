"""Cross-validation of the cash forecast on the organizers' Pizzeria Amalfi statement.

The thresholds sit a little below the measured values in evaluation/RESULTS.md, so
a change that makes the forecast clearly worse fails here.
"""

from datetime import date, timedelta

import pytest

from backend.models import Transaction
from evaluation.backtest import (
    BUFFER,
    FORECASTERS,
    WARMED_UP,
    actual_balances,
    average_net,
    evaluate,
    flat,
    leaks_future,
    load_statement,
    recurring,
)


@pytest.fixture(scope="module")
def statement():
    return load_statement()


def test_ground_truth_matches_the_organizers_figures(statement):
    transactions, opening = statement
    assert opening == 250_000  # EUR 2,500.00 on 1 January 2025
    _, balances = actual_balances(transactions, opening, date(2025, 1, 1), 365)
    lowest = min(range(365), key=balances.__getitem__)
    # The organizers' chart: "Lowest Balance (Jul 03): -€22,097.60", year end EUR 33,266.35.
    assert (date(2025, 1, 1) + timedelta(days=lowest), balances[lowest]) == (date(2025, 7, 3), -2_209_760)
    assert balances[-1] == 3_326_635


@pytest.mark.parametrize("name", FORECASTERS)
@pytest.mark.parametrize("start", [date(2025, 3, 1), date(2025, 6, 1), date(2025, 9, 1)])
def test_forecasters_use_only_the_past(statement, name, start):
    transactions, opening = statement
    assert not leaks_future(FORECASTERS[name], transactions, opening, start, 30)


@pytest.mark.parametrize("days", [14, 30])
def test_history_forecast_beats_the_naive_baselines(statement, days):
    transactions, opening = statement
    learned = evaluate(recurring, "recurring", transactions, opening, days).mae_eur
    naive = min(evaluate(f, "baseline", transactions, opening, days).mae_eur for f in (flat, average_net))
    assert learned < 0.65 * naive


def test_shortfall_warnings_after_three_months_of_history(statement):
    transactions, opening = statement
    two_weeks = evaluate(recurring, "recurring", transactions, opening, 14, since=WARMED_UP)
    month = evaluate(recurring, "recurring", transactions, opening, 30, since=WARMED_UP)
    assert two_weeks.precision >= 0.95 and two_weeks.recall >= 0.95
    assert month.precision >= 0.95 and month.recall >= 0.9
    assert two_weeks.mae_eur < 1_500


def test_a_ten_percent_buffer_covers_most_real_gaps(statement):
    transactions, opening = statement
    report = evaluate(recurring, "recurring", transactions, opening, 14, since=WARMED_UP)
    assert report.coverage() < report.coverage(BUFFER)
    assert report.coverage(BUFFER) >= 0.8


def test_a_perfectly_regular_business_is_forecast_exactly():
    start = date(2026, 1, 1)
    history = []
    for month in range(6):
        history.append(Transaction(id=f"R{month}", date=date(2025, 7 + month, 1), amount_minor=-300_000, label="Rent"))
        history.append(Transaction(id=f"P{month}", date=date(2025, 7 + month, 28), amount_minor=-500_000, label="Payroll"))
    day = date(2025, 7, 4)
    while day < start:  # a Friday supplier
        history.append(Transaction(id=f"S{day}", date=day, amount_minor=-80_000, label="Supplier"))
        day += timedelta(days=7)
    day = date(2025, 7, 1)
    while day < start:  # the same card takings every day
        history.append(Transaction(id=f"C{day}", date=day, amount_minor=40_000, label="Card takings"))
        day += timedelta(days=1)

    expected, balance = [], 1_000_000
    for offset in range(30):
        today = start + timedelta(days=offset)
        balance += 40_000
        balance -= 300_000 if today.day == 1 else 0
        balance -= 500_000 if today.day == 28 else 0
        balance -= 80_000 if today.weekday() == 4 else 0
        expected.append(balance)
    assert recurring(history, 1_000_000, start, 30) == expected

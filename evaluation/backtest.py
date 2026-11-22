"""Rolling-origin cross-validation of cash forecasts on a real bank statement.

For every origin date (weekly through the statement), each forecaster sees only
the rows dated before that origin and predicts the next 14 or 30 end-of-day
balances. The prediction is compared with what the statement actually shows.

The metrics answer the questions the Liquidity Agent has to get right:
- How far off is the balance? Mean absolute error over the horizon, in EUR.
- Does it warn about a shortfall that really happens? Precision, recall, F1.
- Would the proposed facility (the predicted deepest gap) have covered the real
  deepest gap?
- Does it peek at the future? A forecaster is fed the same history with the
  future rows changed. Its prediction must not move.

Run from the repository root:
    uv run --locked python -m evaluation.backtest            # print the report
    uv run --locked python -m evaluation.backtest --write    # also write evaluation/RESULTS.md
"""

from __future__ import annotations

import argparse
import statistics
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

from backend.forecast import parse_transactions
from backend.models import Transaction

ROOT = Path(__file__).resolve().parents[1]
STATEMENT = ROOT / "red-hat-examples" / "pizzeria-amalfi-bank-statement-2025-v6.csv"
RESULTS = Path(__file__).resolve().parent / "RESULTS.md"
# The organizers' info sheet gives the closing balance on 31 December 2025 (EUR 33,266.35). Subtracting
# the year's movements gives the 1 January opening balance the statement implies.
YEAR_END_BALANCE_MINOR = 3_326_635
AVERAGE_DAYS = 28
MIN_REPEATS = 3
BUFFER = Fraction(1, 10)
# Monthly payments need 3 months of history before they are recognised.
WARMED_UP = date(2025, 4, 1)

# A forecaster gets the history before `start`, the true opening balance at
# `start`, and returns `days` predicted end-of-day balances.
Forecaster = Callable[[list[Transaction], int, date, int], list[int]]


# ─── Forecasters ─────────────────────────────────────────────────────────────


def flat(history: list[Transaction], opening: int, start: date, days: int) -> list[int]:
    """Naive baseline: the balance never changes."""
    return [opening] * days


def average_net(history: list[Transaction], opening: int, start: date, days: int) -> list[int]:
    """Baseline: the average daily net movement of the last 28 days, every day."""
    since = start - timedelta(days=AVERAGE_DAYS)
    recent = sum(t.amount_minor for t in history if since <= t.date < start)
    span = min(AVERAGE_DAYS, (start - history[0].date).days) if history else AVERAGE_DAYS
    per_day = round(Fraction(recent, max(span, 1)))
    return [opening + per_day * (offset + 1) for offset in range(days)]


def _add_months(day: date, months: int) -> date:
    import calendar

    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _streak(rows: list[Transaction], follows: Callable[[date, date], bool]) -> list[Transaction]:
    latest = rows[-1]
    chain = [latest]
    for row in reversed(rows[:-1]):
        if not follows(row.date, chain[-1].date) or abs(row.amount_minor - latest.amount_minor) * 4 > abs(
            latest.amount_minor
        ):
            break
        chain.append(row)
    return chain


def _monthly(earlier: date, later: date) -> bool:
    return (later.year - earlier.year) * 12 + later.month - earlier.month == 1 and earlier.day == later.day


def _weekly(earlier: date, later: date) -> bool:
    return (later - earlier).days == 7


def expected_payments(history: list[Transaction], start: date, days: int) -> list[tuple[date, int]]:
    """Payments expected in the window, learned only from `history`.

    The rule follows the statement forecaster on Andrii's feat/backend branch:
    a payee paid on the same day of the month 3 months in a row, or on the same
    weekday 3 weeks in a row, at an amount within 25% of the latest, repeats at
    the average of that streak. Everything else in the last 28 days becomes a
    usual daily income and a usual daily spending.
    """
    history = [t for t in history if t.date < start]  # never learn from the window itself
    end = start + timedelta(days=days - 1)
    groups: dict[tuple[str, bool], list[Transaction]] = defaultdict(list)
    for t in sorted(history, key=lambda t: t.date):
        groups[(t.label, t.amount_minor > 0)].append(t)

    expected: list[tuple[date, int]] = []
    explained: set[tuple] = set()
    for group, rows in groups.items():
        chain = _streak(rows, _monthly)
        latest = rows[-1]
        if len(chain) >= MIN_REPEATS and _add_months(latest.date, 1) >= start:
            explained.add((group, None))
            amount = round(Fraction(sum(t.amount_minor for t in chain), len(chain)))
            month = 1
            while (day := _add_months(latest.date, month)) <= end:
                expected.append((day, amount))
                month += 1
            continue
        for weekday in range(7):
            on_weekday = [t for t in rows if t.date.weekday() == weekday]
            if not on_weekday:
                continue
            chain = _streak(on_weekday, _weekly)
            latest = on_weekday[-1]
            if len(chain) < MIN_REPEATS or latest.date + timedelta(days=7) < start:
                continue
            explained.add((group, weekday))
            amount = round(Fraction(sum(t.amount_minor for t in chain), len(chain)))
            day = latest.date + timedelta(days=7)
            while day <= end:
                expected.append((day, amount))
                day += timedelta(days=7)

    since = max(start - timedelta(days=AVERAGE_DAYS), history[0].date) if history else start
    span = max((start - since).days, 1)
    rest = [
        t
        for t in history
        if t.date >= since
        and ((t.label, t.amount_minor > 0), None) not in explained
        and ((t.label, t.amount_minor > 0), t.date.weekday()) not in explained
    ]
    for total in (sum(t.amount_minor for t in rest if t.amount_minor > 0), sum(t.amount_minor for t in rest if t.amount_minor < 0)):
        per_day = round(Fraction(total, span))
        if per_day:
            expected += [(start + timedelta(days=offset), per_day) for offset in range(days)]
    return expected


def recurring(history: list[Transaction], opening: int, start: date, days: int) -> list[int]:
    """History-based forecast: recurring payments plus the usual daily amounts."""
    movement: dict[date, int] = defaultdict(int)
    for day, amount in expected_payments(history, start, days):
        movement[day] += amount
    balance, balances = opening, []
    for offset in range(days):
        balance += movement[start + timedelta(days=offset)]
        balances.append(balance)
    return balances


FORECASTERS: dict[str, Forecaster] = {
    "flat (baseline)": flat,
    "average net (baseline)": average_net,
    "recurring (history)": recurring,
}


# ─── Evaluation ──────────────────────────────────────────────────────────────


@dataclass
class Window:
    start: date
    predicted: list[int]
    actual: list[int]

    @property
    def mae(self) -> float:
        return sum(abs(p - a) for p, a in zip(self.predicted, self.actual)) / len(self.actual)

    @property
    def end_error(self) -> int:
        return abs(self.predicted[-1] - self.actual[-1])

    @property
    def predicted_gap(self) -> int:
        return max(0, -min(self.predicted))

    @property
    def actual_gap(self) -> int:
        return max(0, -min(self.actual))


@dataclass
class Report:
    name: str
    days: int
    windows: list[Window] = field(default_factory=list)
    leaks: bool = False

    def _counts(self) -> tuple[int, int, int, int]:
        tp = sum(1 for w in self.windows if w.predicted_gap and w.actual_gap)
        fp = sum(1 for w in self.windows if w.predicted_gap and not w.actual_gap)
        fn = sum(1 for w in self.windows if not w.predicted_gap and w.actual_gap)
        tn = len(self.windows) - tp - fp - fn
        return tp, fp, fn, tn

    @property
    def mae_eur(self) -> float:
        return statistics.mean(w.mae for w in self.windows) / 100

    @property
    def end_error_eur(self) -> float:
        return statistics.median(w.end_error for w in self.windows) / 100

    @property
    def precision(self) -> float:
        tp, fp, _, _ = self._counts()
        return tp / (tp + fp) if tp + fp else 0.0

    @property
    def recall(self) -> float:
        tp, _, fn, _ = self._counts()
        return tp / (tp + fn) if tp + fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def coverage(self, buffer: Fraction = Fraction(0)) -> float:
        """Share of windows with a real shortfall where the predicted limit, plus a buffer, covered it."""
        real = [w for w in self.windows if w.actual_gap]
        return sum(1 for w in real if w.predicted_gap * (1 + buffer) >= w.actual_gap) / len(real) if real else 0.0


def load_statement(path: Path = STATEMENT) -> tuple[list[Transaction], int]:
    transactions, _ = parse_transactions(path.read_bytes())
    opening = YEAR_END_BALANCE_MINOR - sum(t.amount_minor for t in transactions)
    return transactions, opening


def actual_balances(transactions: list[Transaction], opening_year: int, start: date, days: int) -> tuple[int, list[int]]:
    """The real balance before `start` and at the end of each of the next `days` days."""
    before = opening_year + sum(t.amount_minor for t in transactions if t.date < start)
    movement: dict[date, int] = defaultdict(int)
    for t in transactions:
        movement[t.date] += t.amount_minor
    balance, balances = before, []
    for offset in range(days):
        balance += movement[start + timedelta(days=offset)]
        balances.append(balance)
    return before, balances


def origins(transactions: list[Transaction], days: int, step: int = 7, warmup: int = AVERAGE_DAYS) -> list[date]:
    first, last = transactions[0].date, transactions[-1].date
    day, result = first + timedelta(days=warmup), []
    while day + timedelta(days=days - 1) <= last:
        result.append(day)
        day += timedelta(days=step)
    return result


def leaks_future(forecaster: Forecaster, transactions: list[Transaction], opening_year: int, start: date, days: int) -> bool:
    """True if changing rows on or after `start` changes the forecast."""
    history = [t for t in transactions if t.date < start]
    opening, _ = actual_balances(transactions, opening_year, start, days)
    tampered = history + [
        t.model_copy(update={"amount_minor": t.amount_minor * 10}) for t in transactions if t.date >= start
    ]
    honest = forecaster(history, opening, start, days)
    # Hand the forecaster the tampered future too: an honest one must ignore it.
    peeking = forecaster(sorted(tampered, key=lambda t: t.date), opening, start, days)
    return honest != peeking


def evaluate(
    forecaster: Forecaster,
    name: str,
    transactions: list[Transaction],
    opening_year: int,
    days: int,
    since: date | None = None,
) -> Report:
    report = Report(name=name, days=days)
    for start in origins(transactions, days):
        if since and start < since:
            continue
        history = [t for t in transactions if t.date < start]
        opening, actual = actual_balances(transactions, opening_year, start, days)
        report.windows.append(Window(start, forecaster(history, opening, start, days), actual))
    report.leaks = leaks_future(forecaster, transactions, opening_year, date(2025, 6, 1), days)
    return report


def current_api_forecast(transactions: list[Transaction]) -> Forecaster:
    """What /api/forecast does today with a statement: it sums the statement rows dated in the window.

    Fed only the history, it predicts no movement at all; fed the whole statement,
    it reproduces the future exactly. Either way it isn't a forecast.
    """
    from backend.forecast import project

    def forecast(history: list[Transaction], opening: int, start: date, days: int) -> list[int]:
        return [day.balance_minor for day in project(history, opening, start).days][:days]

    return forecast


# ─── Report ──────────────────────────────────────────────────────────────────


def table(reports: list[Report]) -> str:
    lines = [
        "| Forecaster | Horizon | Windows | Mean abs error | Median error on last day | Shortfall precision | Recall | F1 "
        "| Limit covered real gap | With +10% buffer | Uses only the past |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in reports:
        lines.append(
            f"| {r.name} | {r.days} days | {len(r.windows)} | EUR {r.mae_eur:,.0f} | EUR {r.end_error_eur:,.0f} | "
            f"{r.precision:.0%} | {r.recall:.0%} | {r.f1:.2f} | {r.coverage():.0%} | {r.coverage(BUFFER):.0%} | "
            f"{'no, it peeks' if r.leaks else 'yes'} |"
        )
    return "\n".join(lines)


def run() -> tuple[list[Report], str]:
    transactions, opening_year = load_statement()
    sections = []
    every: list[Report] = []
    for title, since in (("Every weekly origin from February", None), (f"Origins from {WARMED_UP:%d %B} (3 months of history)", WARMED_UP)):
        reports = [
            evaluate(forecaster, name, transactions, opening_year, days, since)
            for days in (14, 30)
            for name, forecaster in FORECASTERS.items()
        ]
        api = evaluate(
            current_api_forecast(transactions), "current /api/forecast, history only", transactions, opening_year, 14, since
        )
        reports.insert(3, api)
        every += reports
        sections.append(f"### {title}\n\n{table(reports)}")
    return every, "\n\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--write", action="store_true", help="also write evaluation/RESULTS.md")
    args = parser.parse_args()
    reports, text = run()
    print(text)
    if args.write:
        body = RESULTS.read_text(encoding="utf-8") if RESULTS.exists() else ""
        marker_start, marker_end = "<!-- backtest:start -->", "<!-- backtest:end -->"
        if marker_start in body:
            before, _, rest = body.partition(marker_start)
            _, _, after = rest.partition(marker_end)
            RESULTS.write_text(f"{before}{marker_start}\n{text}\n{marker_end}{after}", encoding="utf-8")
        else:
            RESULTS.write_text(f"{marker_start}\n{text}\n{marker_end}\n", encoding="utf-8")
        print(f"\nWrote {RESULTS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""Estimate future cash movements from the transactions already on a statement."""

from calendar import monthrange
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from fractions import Fraction

from .models import MAX_ABS_MINOR, MAX_LABEL_LENGTH, Transaction, TransactionCategory


ESTIMATED_ID_PREFIX = "FC-"
AVERAGE_DAYS = 28
MIN_REPEATS = 3


def _monthly(earlier: date, later: date) -> bool:
    months_apart = (later.year - earlier.year) * 12 + later.month - earlier.month
    return months_apart == 1 and earlier.day == later.day


def _weekly(earlier: date, later: date) -> bool:
    return (later - earlier).days == 7


def _add_months(day: date, months: int) -> date | None:
    year, month_index = divmod(day.year * 12 + day.month - 1 + months, 12)
    if year > date.max.year:
        return None
    month = month_index + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def _streak(rows: list[Transaction], follows: Callable[[date, date], bool]) -> list[Transaction]:
    """The latest occurrence and the consecutive ones within 25% of its amount."""
    latest = rows[-1]
    chain = [latest]
    for row in reversed(rows[:-1]):
        if not follows(row.date, chain[-1].date):
            break
        if abs(row.amount_minor - latest.amount_minor) * 4 > abs(latest.amount_minor):
            break
        chain.append(row)
    return chain


def _average_amount(rows: list[Transaction]) -> int:
    return round(Fraction(sum(row.amount_minor for row in rows), len(rows)))


def estimate_transactions(transactions: list[Transaction], window: list[date]) -> list[Transaction]:
    """Estimate recurring payments and typical daily receipts and expenses from recent history."""
    start, end = window[0], window[-1]
    history = sorted((row for row in transactions if row.date < start), key=lambda row: row.date)
    if not history:
        return []

    groups: dict[tuple[str, bool], list[Transaction]] = defaultdict(list)
    for row in history:
        if row.amount_minor:
            groups[(row.label, row.amount_minor > 0)].append(row)

    expected: list[tuple[date, int, str, TransactionCategory]] = []
    explained: set[tuple[tuple[str, bool], int | None]] = set()
    for group, rows in groups.items():
        latest = rows[-1]
        label = f"Estimated {latest.label}"[:MAX_LABEL_LENGTH]
        category = latest.category or "other"
        monthly = _streak(rows, _monthly)
        next_month = _add_months(latest.date, 1)
        if len(monthly) >= MIN_REPEATS and next_month is not None and next_month >= start:
            explained.add((group, None))
            amount = _average_amount(monthly)
            month = 1
            while next_month is not None and next_month <= end:
                expected.append((next_month, amount, label, category))
                month += 1
                next_month = _add_months(latest.date, month)
            continue

        for weekday in range(7):
            on_weekday = [row for row in rows if row.date.weekday() == weekday]
            if len(on_weekday) < MIN_REPEATS:
                continue
            latest_weekly = on_weekday[-1]
            next_offset = (latest_weekly.date - start).days + 7
            weekly = _streak(on_weekday, _weekly)
            if len(weekly) < MIN_REPEATS or next_offset < 0:
                continue
            explained.add((group, weekday))
            amount = _average_amount(weekly)
            category = latest_weekly.category or "other"
            for offset in range(next_offset, len(window), 7):
                expected.append((window[offset], amount, label, category))

    span = min(AVERAGE_DAYS, (start - history[0].date).days)
    recent = [row for row in history if (start - row.date).days <= span]
    rest = [
        row
        for row in recent
        if ((row.label, row.amount_minor > 0), None) not in explained
        and ((row.label, row.amount_minor > 0), row.date.weekday()) not in explained
    ]
    for label, total in (
        ("Estimated daily income", sum(row.amount_minor for row in rest if row.amount_minor > 0)),
        ("Estimated daily spending", sum(row.amount_minor for row in rest if row.amount_minor < 0)),
    ):
        per_day = round(Fraction(total, span))
        if abs(per_day) > MAX_ABS_MINOR:
            raise ValueError(f"The {label.lower()} is out of range.")
        if per_day:
            expected.extend((day, per_day, label, "other") for day in window)

    expected.sort(key=lambda payment: (payment[0], payment[2], payment[1]))
    return [
        Transaction(
            id=f"{ESTIMATED_ID_PREFIX}{number:04d}",
            date=day,
            amount_minor=amount,
            label=label,
            transaction_type="ESTIMATE",
            category=category,
            actionability="retail_non_contactable" if amount > 0 else "fixed_mandatory",
        )
        for number, (day, amount, label, category) in enumerate(expected, start=1)
    ]

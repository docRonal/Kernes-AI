"""Liquidity Agent cash forecast.

Every amount is integer grosz (1 PLN = 100). This module has no floats, no
network and no model calls: the figures the user sees, the proposed credit
facility and the simulated decision all come from here. The model only explains
them afterwards.
"""

import csv
import io
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .currency import current_currency
from .models import (
    HORIZON_DAYS,
    MAX_ABS_MINOR,
    MAX_ID_LENGTH,
    MAX_LABEL_LENGTH,
    MAX_TRANSACTIONS,
    NO_CONTROL_CHARACTERS,
    DailyBalance,
    DecisionDay,
    DecisionRequest,
    DecisionResponse,
    Deficit,
    EarlierPayment,
    ForecastResponse,
    Projection,
    Proposal,
    Transaction,
)


DEMO_DIR = Path(__file__).resolve().parents[1] / "demo"
DEMO_FILE = DEMO_DIR / "transactions.csv"
DEMO_START = date(2026, 11, 23)
DEMO_STARTING_BALANCE_MINOR = 1_200_000
DEMO_MOVE = ("INV-001", date(2026, 11, 26))

CSV_HEADER = ("id", "date", "amount_minor", "label")
MAX_CSV_BYTES = 1_000_000

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_WHOLE_NUMBER = re.compile(r"[+-]?\d{1,15}")
_NO_CONTROL = re.compile(NO_CONTROL_CHARACTERS)


class ForecastInputError(ValueError):
    """Input the user can fix. The API reports it as HTTP 422 with this message."""


# ─── CSV ─────────────────────────────────────────────────────────────────────


def parse_transactions(raw: bytes) -> list[Transaction]:
    """Read the uploaded CSV, or explain the first problem with its line number."""
    if len(raw) > MAX_CSV_BYTES:
        raise ForecastInputError("The CSV is larger than 1 MB.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ForecastInputError("The CSV must use UTF-8 encoding.") from exc

    reader = csv.reader(io.StringIO(text, newline=""))
    transactions: list[Transaction] = []
    seen: set[str] = set()
    try:
        header = next(reader, None)
        columns = [name.strip() for name in header] if header else []
        if sorted(columns) != sorted(CSV_HEADER):
            raise ForecastInputError("The first line must be the header id,date,amount_minor,label.")
        position = {name: columns.index(name) for name in CSV_HEADER}

        for row in reader:
            line = reader.line_num
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(CSV_HEADER):
                raise ForecastInputError(f"Line {line}: expected 4 values, found {len(row)}.")
            if len(transactions) == MAX_TRANSACTIONS:
                raise ForecastInputError(f"The CSV has more than {MAX_TRANSACTIONS} transactions.")
            values = {name: row[index].strip() for name, index in position.items()}
            transaction = _read_row(values, line)
            if transaction.id in seen:
                raise ForecastInputError(f"Line {line}: the id {transaction.id} appears more than once.")
            seen.add(transaction.id)
            transactions.append(transaction)
    except csv.Error as exc:
        raise ForecastInputError(f"Line {reader.line_num}: the CSV can't be read ({exc}).") from exc

    if not transactions:
        raise ForecastInputError("The CSV has no transactions.")
    return transactions


def _read_row(values: dict[str, str], line: int) -> Transaction:
    transaction_id = values["id"]
    if not transaction_id:
        raise ForecastInputError(f"Line {line}: the id is empty.")
    if len(transaction_id) > MAX_ID_LENGTH:
        raise ForecastInputError(f"Line {line}: the id is longer than {MAX_ID_LENGTH} characters.")
    if not _NO_CONTROL.fullmatch(transaction_id):
        raise ForecastInputError(f"Line {line}: the id contains a line break or another control character.")

    if not _ISO_DATE.fullmatch(values["date"]):
        raise ForecastInputError(f"Line {line}: the date must look like 2026-11-27.")
    try:
        day = date.fromisoformat(values["date"])
    except ValueError as exc:
        raise ForecastInputError(f"Line {line}: {values['date']} is not a real date.") from exc

    if not _WHOLE_NUMBER.fullmatch(values["amount_minor"]):
        raise ForecastInputError(
            f"Line {line}: amount_minor must be a whole number of cents, for example -1100000 for -11,000.00."
        )
    amount = int(values["amount_minor"])
    if abs(amount) > MAX_ABS_MINOR:
        raise ForecastInputError(f"Line {line}: the amount is out of range.")

    label = values["label"]
    if not label:
        raise ForecastInputError(f"Line {line}: the label is empty.")
    if len(label) > MAX_LABEL_LENGTH:
        raise ForecastInputError(f"Line {line}: the label is longer than {MAX_LABEL_LENGTH} characters.")
    if not _NO_CONTROL.fullmatch(label):
        raise ForecastInputError(f"Line {line}: the label contains a line break or another control character.")

    return Transaction(id=transaction_id, date=day, amount_minor=amount, label=label)


# ─── Forecast ────────────────────────────────────────────────────────────────


def horizon(start: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range(HORIZON_DAYS)]


def project(transactions: list[Transaction], opening_minor: int, start: date) -> Projection:
    """End-of-day balances for 14 days. The opening balance comes before the first day's movements.

    Rows dated outside the window don't move the balance.
    """
    movement: dict[date, int] = defaultdict(int)
    for transaction in transactions:
        movement[transaction.date] += transaction.amount_minor

    balance = opening_minor
    days: list[DailyBalance] = []
    first_deficit: Deficit | None = None
    for day in horizon(start):
        balance += movement.get(day, 0)
        days.append(DailyBalance(date=day, balance_minor=balance))
        if first_deficit is None and balance < 0:
            first_deficit = Deficit(date=day, shortfall_minor=-balance)
    return Projection(days=days, first_deficit=first_deficit)


def propose(baseline: Projection, transactions: list[Transaction]) -> Proposal | None:
    """Credit facility sized to the deepest gap: max(0, -min(balances)).

    The earliest day wins a tie. Relevant transactions are the ones in the window
    up to the day the balance recovers from that deepest gap, or the window's end.
    Both shortfalls come from the balances: a baseline sent back by the browser
    can't change them through its first_deficit field.
    """
    days = baseline.days
    first = next((day for day in days if day.balance_minor < 0), None)
    if first is None:
        return None
    deepest = min(days, key=lambda day: day.balance_minor)  # min keeps the first of equal values

    after_deepest = days[days.index(deepest) + 1 :]
    recovery = next((day.date for day in after_deepest if day.balance_minor >= 0), None)
    window_end = recovery or days[-1].date
    relevant = [
        transaction.id
        for transaction in sorted(transactions, key=lambda transaction: transaction.date)
        if days[0].date <= transaction.date <= window_end
    ]
    gap = -deepest.balance_minor
    return Proposal(
        limit_minor=gap,
        first_shortfall=Deficit(date=first.date, shortfall_minor=-first.balance_minor),
        deepest_shortfall=Deficit(date=deepest.date, shortfall_minor=gap),
        relevant_transaction_ids=relevant,
    )


def suggest_earlier_payments(
    baseline: Projection, transactions: list[Transaction], proposal: Proposal | None
) -> list[EarlierPayment]:
    """Incoming payments worth asking for early instead of borrowing, best first.

    Each one is due after the first shortfall. Paid by the day before that shortfall
    (or on the first day of the forecast), it would leave limit_after_minor of the
    facility still needed. Ranked by that amount, then by the soonest due date, which
    is the smallest ask. Payments that wouldn't lower the limit are left out.
    """
    if proposal is None:
        return []
    days = baseline.days
    first_gap = proposal.first_shortfall.date
    # Not max(start, first_gap - 1 day): that subtraction fails when the forecast starts on 0001-01-01.
    pay_by = first_gap - timedelta(days=1) if first_gap > days[0].date else days[0].date
    ranked = []
    for transaction in transactions:
        if transaction.amount_minor <= 0 or not first_gap < transaction.date <= days[-1].date:
            continue
        # Paid on pay_by instead of its due date, the money lifts every balance in between.
        lowest = min(
            day.balance_minor + (transaction.amount_minor if pay_by <= day.date < transaction.date else 0)
            for day in days
        )
        limit_after = max(0, -lowest)
        if limit_after < proposal.limit_minor:
            ranked.append((limit_after, transaction.date, -transaction.amount_minor, transaction.id))
    return [
        EarlierPayment(transaction_id=transaction_id, pay_by=pay_by, limit_after_minor=limit_after)
        for limit_after, _, _, transaction_id in sorted(ranked)
    ]


def move_payment(transactions: list[Transaction], transaction_id: str, to_date: date, start: date) -> list[Transaction]:
    """A copy of the transactions with one incoming payment on another date. The input stays unchanged."""
    window = horizon(start)
    target = next((transaction for transaction in transactions if transaction.id == transaction_id), None)
    if target is None:
        raise ForecastInputError(f"There is no transaction with the id {transaction_id}.")
    if target.amount_minor <= 0:
        raise ForecastInputError(f"{transaction_id} is not an incoming payment. Only incoming payments can be moved.")
    if not window[0] <= target.date <= window[-1]:
        raise ForecastInputError(f"{transaction_id} is due on {target.date}, outside the 14-day forecast.")
    if not window[0] <= to_date <= window[-1]:
        raise ForecastInputError(f"Choose a new date between {window[0]} and {window[-1]}.")
    return [
        transaction.model_copy(update={"date": to_date}) if transaction.id == transaction_id else transaction
        for transaction in transactions
    ]


def build_forecast(
    raw: bytes,
    opening_minor: int,
    start: date,
    move_transaction_id: str | None = None,
    move_to_date: date | None = None,
) -> ForecastResponse:
    if abs(opening_minor) > MAX_ABS_MINOR:
        raise ForecastInputError("The opening balance is out of range.")
    if (move_transaction_id is None) != (move_to_date is None):
        raise ForecastInputError("Send both move_transaction_id and move_to_date, or neither.")

    transactions = parse_transactions(raw)
    baseline = project(transactions, opening_minor, start)
    scenario = None
    if move_transaction_id is not None and move_to_date is not None:
        moved = move_payment(transactions, move_transaction_id, move_to_date, start)
        scenario = project(moved, opening_minor, start)

    proposal = propose(baseline, transactions)
    return ForecastResponse(
        currency=current_currency(),
        transactions=transactions,
        baseline=baseline,
        proposal=proposal,
        earlier_payments=suggest_earlier_payments(baseline, transactions, proposal),
        scenario=scenario,
    )


# ─── Human decision (simulation only) ────────────────────────────────────────


def simulate_decision(request: DecisionRequest) -> DecisionResponse:
    """What approving or rejecting the proposed facility would mean, day by day.

    The limit is recalculated from the baseline, so the client can't change it.
    Balances stay as forecast; the facility only covers the gaps. The Projection
    model has already checked for 14 consecutive days.
    """
    days = request.baseline.days
    deepest = min(days, key=lambda day: day.balance_minor)
    if deepest.balance_minor >= 0:
        raise ForecastInputError("The baseline never goes below zero, so there is no credit facility to decide on.")

    limit = -deepest.balance_minor
    available = limit if request.decision == "approved" else 0
    outcome: list[DecisionDay] = []
    for day in days:
        gap = max(0, -day.balance_minor)
        used = min(gap, available)
        outcome.append(
            DecisionDay(
                date=day.date,
                balance_minor=day.balance_minor,
                facility_used_minor=used,
                uncovered_minor=gap - used,
            )
        )

    worst = max(outcome, key=lambda day: day.uncovered_minor)  # max keeps the first of equal values
    largest = Deficit(date=worst.date, shortfall_minor=worst.uncovered_minor) if worst.uncovered_minor else None
    return DecisionResponse(
        decision=request.decision,
        simulated=True,
        limit_minor=limit,
        days=outcome,
        largest_uncovered=largest,
    )


# ─── API entry point ─────────────────────────────────────────────────────────


async def get_forecast(
    *,
    mode: str,
    file: UploadFile,
    starting_balance_minor: int,
    start_date: date,
    move_transaction_id: str | None,
    move_to_date: date | None,
) -> ForecastResponse | dict:
    if mode == "live":
        raw = await file.read(MAX_CSV_BYTES + 1)
        try:
            return build_forecast(raw, starting_balance_minor, start_date, move_transaction_id, move_to_date)
        except ForecastInputError as exc:
            raise HTTPException(422, str(exc)) from exc

    scenario = (move_transaction_id, move_to_date)
    if scenario not in ((None, None), DEMO_MOVE):
        raise HTTPException(422, "Demo scenario: move INV-001 to 2026-11-26.")

    if (starting_balance_minor, start_date) != (DEMO_STARTING_BALANCE_MINOR, DEMO_START):
        raise HTTPException(422, "Use 12000 EUR and start date 2026-11-23 in demo mode.")

    sample = DEMO_FILE.read_text(encoding="utf-8")
    raw = await file.read(len(sample.encode("utf-8")) + 32)
    try:
        actual = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "The CSV must use UTF-8 encoding.") from exc
    if actual.splitlines() != sample.splitlines():
        raise HTTPException(422, "Use the bundled transactions.csv in demo mode.")

    result = json.loads((DEMO_DIR / "forecast.example.json").read_text(encoding="utf-8"))
    if scenario == (None, None):
        result["scenario"] = None
    result["currency"] = current_currency()
    return result


def get_decision(request: DecisionRequest) -> DecisionResponse:
    """Pure calculation, so demo and live modes behave the same."""
    try:
        return simulate_decision(request)
    except ForecastInputError as exc:
        raise HTTPException(422, str(exc)) from exc

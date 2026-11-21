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
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .models import (
    HORIZON_DAYS,
    MAX_ABS_MINOR,
    MAX_LABEL_LENGTH,
    MAX_TRANSACTIONS,
    NO_CONTROL_CHARACTERS,
    SUPPORTED_CURRENCIES,
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
AMALFI_DEMO_FILE = DEMO_DIR / "pizzeria_amalfi_sample.csv"
DEMO_FILE = AMALFI_DEMO_FILE

REQUIRED_BANK_HEADERS = (
    "Account Number",
    "Booking Date",
    "Value Date",
    "Transaction Type",
    "Payment Reference",
    "Beneficiary/Payer",
    "Amount",
    "Currency",
)
MAX_CSV_BYTES = 1_000_000

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_BANK_DATE_DOT = re.compile(r"^(\d{2})\.(\d{2})\.(\d{2}|\d{4})$")
_GERMAN_AMOUNT = re.compile(r"^([+-]?)(\d+)(?:,(\d{1,2})|\.(\d{1,2}))?$")
_CONTROL_RUN = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")
_DEFAULT_FX_RATES: dict[tuple[str, str], Decimal] = {
    ("EUR", "CHF"): Decimal("1.047"),
    ("CHF", "EUR"): Decimal("0.955"),
}


class ForecastInputError(ValueError):
    """Input the user can fix. The API reports it as HTTP 422 with this message."""


# ─── CSV ─────────────────────────────────────────────────────────────────────


def _parse_bank_date(raw: str, line: int) -> date:
    trimmed = raw.strip()
    dot_match = _BANK_DATE_DOT.fullmatch(trimmed)
    if dot_match:
        day_s, month_s, year_s = dot_match.groups()
        year = int(f"20{year_s}") if len(year_s) == 2 else int(year_s)
        try:
            return date(year, int(month_s), int(day_s))
        except ValueError as exc:
            raise ForecastInputError(f"Line {line}: '{trimmed}' is not a real date.") from exc
    if _ISO_DATE.fullmatch(trimmed):
        try:
            return date.fromisoformat(trimmed)
        except ValueError as exc:
            raise ForecastInputError(f"Line {line}: '{trimmed}' is not a real date.") from exc
    raise ForecastInputError(f"Line {line}: unsupported bank date format '{trimmed}'. Expected DD.MM.YY.")


def _parse_decimal_amount_minor(raw: str, line: int) -> int:
    cleaned = re.sub(r"\.(?=\d{3}(?:,|$))", "", raw.strip().replace(" ", "").replace("\u00a0", ""))
    match = _GERMAN_AMOUNT.fullmatch(cleaned)
    if not match:
        raise ForecastInputError(
            f"Line {line}: invalid amount format '{raw}'. Expected decimal amount like -3800,00 or 457.56."
        )
    sign, whole, comma_frac, dot_frac = match.groups()
    frac = (comma_frac if comma_frac is not None else (dot_frac or "")).ljust(2, "0")
    minor = int(whole) * 100 + int(frac)
    return -minor if sign == "-" else minor


def _extract_fx_rate(reference: str, primary_currency: str, row_currency: str) -> Decimal | None:
    pattern = re.compile(
        rf"@\s*(\d+(?:[.,]\d+)?)\s*{re.escape(primary_currency)}/{re.escape(row_currency)}\b",
        re.IGNORECASE,
    )
    match = pattern.search(reference or "")
    if match:
        try:
            rate = Decimal(match.group(1).replace(",", "."))
            if rate > 0:
                return rate
        except InvalidOperation:
            pass
    return _DEFAULT_FX_RATES.get((primary_currency, row_currency))


def _clean_text(raw: str, fallback: str, max_len: int) -> str:
    cleaned = _CONTROL_RUN.sub(" ", raw).strip() or fallback
    return cleaned[:max_len]


def _parse_bank_statement_csv(text: str) -> tuple[list[Transaction], str]:
    """Parse a German MT940-style semicolon-delimited bank export and auto-detect statement currency."""
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
    try:
        header = next(reader, None)
        columns = [name.strip() for name in header] if header else []
        col_index = {name: idx for idx, name in enumerate(columns)}
        missing = [name for name in REQUIRED_BANK_HEADERS if name not in col_index]
        if missing:
            raise ForecastInputError(
                f"The bank CSV is missing required columns: {', '.join(missing)}."
            )

        def cell(row: list[str], col: str) -> str:
            idx = col_index[col]
            return row[idx].strip() if idx < len(row) else ""

        parsed_rows: list[tuple[int, int, date, str, int, str, str]] = []
        row_seq = 0
        for row in reader:
            line = reader.line_num
            if not any(item.strip() for item in row):
                continue
            if len(row) < len(REQUIRED_BANK_HEADERS):
                raise ForecastInputError(f"Line {line}: expected at least 8 semicolon-separated values.")
            if len(parsed_rows) == MAX_TRANSACTIONS:
                raise ForecastInputError(f"The CSV has more than {MAX_TRANSACTIONS} transactions.")
            row_seq += 1

            raw_value = cell(row, "Value Date") or cell(row, "Booking Date")
            tx_date = _parse_bank_date(raw_value, line)
            raw_currency = cell(row, "Currency").upper()
            if not raw_currency:
                raise ForecastInputError(f"Line {line}: missing currency.")
            if raw_currency not in SUPPORTED_CURRENCIES:
                raise ForecastInputError(f"Line {line}: unsupported or unknown currency '{raw_currency}'.")
            original_minor = _parse_decimal_amount_minor(cell(row, "Amount"), line)
            reference = cell(row, "Payment Reference")
            tx_type = cell(row, "Transaction Type") or "TRANSFER"
            label = _clean_text(cell(row, "Beneficiary/Payer"), tx_type, MAX_LABEL_LENGTH)
            parsed_rows.append((line, row_seq, tx_date, raw_currency, original_minor, reference, label))
    except csv.Error as exc:
        raise ForecastInputError(f"Line {reader.line_num}: the CSV can't be read ({exc}).") from exc

    if not parsed_rows:
        raise ForecastInputError("The CSV has no transactions.")

    # Auto-detect primary currency by frequency, breaking ties by first appearance.
    counts = Counter(row[3] for row in parsed_rows)
    first_seen: dict[str, int] = {}
    for idx, row in enumerate(parsed_rows):
        first_seen.setdefault(row[3], idx)
    primary_currency = max(counts, key=lambda cur: (counts[cur], -first_seen[cur]))

    transactions: list[Transaction] = []
    for line, row_seq, tx_date, row_currency, original_minor, reference, label in parsed_rows:
        if row_currency == primary_currency:
            amount_minor = original_minor
        else:
            rate = _extract_fx_rate(reference, primary_currency, row_currency)
            if rate is None:
                raise ForecastInputError(
                    f"Line {line}: mixed currency '{row_currency}' in a {primary_currency} statement "
                    f"requires an '@ <rate> {primary_currency}/{row_currency}' rate in Payment Reference."
                )
            amount_minor = int((Decimal(original_minor) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        if abs(amount_minor) > MAX_ABS_MINOR:
            raise ForecastInputError(f"Line {line}: the amount is out of range.")

        transactions.append(
            Transaction(
                id=f"TX-{row_seq:04d}",
                date=tx_date,
                amount_minor=amount_minor,
                label=label,
            )
        )

    transactions.sort(key=lambda tx: (tx.date, tx.id))
    return transactions, primary_currency


def parse_transactions(raw: bytes) -> tuple[list[Transaction], str]:
    """Read the uploaded bank statement CSV (Pizzeria Amalfi standard) and auto-detect currency."""
    if len(raw) > MAX_CSV_BYTES:
        raise ForecastInputError("The CSV is larger than 1 MB.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ForecastInputError("The CSV must use UTF-8 encoding.") from exc

    first_line = next((line for line in text.splitlines() if line.strip()), "")
    if ";" not in first_line:
        raise ForecastInputError(
            "Unsupported CSV format. Upload a semicolon-delimited bank statement CSV "
            "(Pizzeria Amalfi standard) with columns: Account Number, Booking Date, Value Date, "
            "Transaction Type, Payment Reference, Beneficiary/Payer, Amount, Currency."
        )
    return _parse_bank_statement_csv(text)


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

    transactions, detected_currency = parse_transactions(raw)
    baseline = project(transactions, opening_minor, start)
    scenario = None
    if move_transaction_id is not None and move_to_date is not None:
        moved = move_payment(transactions, move_transaction_id, move_to_date, start)
        scenario = project(moved, opening_minor, start)

    proposal = propose(baseline, transactions)
    return ForecastResponse(
        currency=detected_currency,
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
    raw = await file.read(MAX_CSV_BYTES + 1)
    try:
        return build_forecast(raw, starting_balance_minor, start_date, move_transaction_id, move_to_date)
    except ForecastInputError as exc:
        raise HTTPException(422, str(exc)) from exc


def get_decision(request: DecisionRequest) -> DecisionResponse:
    """Pure calculation, so demo and live modes behave the same."""
    try:
        return simulate_decision(request)
    except ForecastInputError as exc:
        raise HTTPException(422, str(exc)) from exc

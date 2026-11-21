import csv
import io
from datetime import date


BANK_COLUMNS = [
    "Account Number",
    "Booking Date",
    "Value Date",
    "Transaction Type",
    "Payment Reference",
    "Beneficiary/Payer",
    "Counterparty Account",
    "Bank Code",
    "Amount",
    "Currency",
    "Info",
]


def _dmy(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime("%d.%m.%y")


def _fmt_amount(amount_minor: int) -> str:
    sign = "-" if amount_minor < 0 else ""
    whole, cents = divmod(abs(amount_minor), 100)
    return f"{sign}{whole},{cents:02d}"


def amalfi_csv(
    *rows: tuple[str, str, int] | tuple[str, str, int, str],
    iban: str = "DE89370400440532013000",
) -> bytes:
    """Build semicolon-delimited Pizzeria Amalfi bank statement CSV bytes from (iso_date, label, amount_minor[, currency])."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(BANK_COLUMNS)
    for idx, row in enumerate(rows, start=1):
        iso_date, label, amount_minor = row[0], row[1], row[2]
        currency = row[3] if len(row) > 3 else "EUR"
        bdate = _dmy(iso_date)
        ttype = "INCOMING PAYMENT" if amount_minor > 0 else "PAYMENT"
        writer.writerow(
            [
                iban,
                bdate,
                bdate,
                ttype,
                f"Ref-{idx:04d} {label}",
                label,
                "DE92500500000959561143",
                "COBADEFFXXX",
                _fmt_amount(amount_minor),
                currency,
                "Transaction booked",
            ]
        )
    return buf.getvalue().encode("utf-8")


STARTER_AMALFI_CSV = amalfi_csv(
    ("2026-11-27", "Payroll", -1_100_000),
    ("2026-11-27", "Office rent", -600_000),
    ("2026-11-30", "Client invoice", 900_000),
)

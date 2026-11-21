"""Currencies of the European Union and how the app writes amounts in them.

One forecast uses one account currency. The app never converts between
currencies. Amounts stay integer minor units: every currency here has two
decimal places in ISO 4217, so 1 unit = 100 minor units.

The request's currency is set for the duration of the request with
`use_currency`, so every module that writes an amount for the model or the
user uses the same code without passing it through each function.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal, get_args

# The euro plus the national currencies of EU members outside the euro area.
# Bulgaria adopted the euro on 1 January 2026, so the lev is no longer listed.
Currency = Literal["EUR", "PLN", "CZK", "HUF", "RON", "SEK", "DKK"]
CURRENCIES: tuple[str, ...] = get_args(Currency)
DEFAULT_CURRENCY: Currency = "EUR"

# Local symbols the model may use instead of the ISO code.
SYMBOLS: dict[str, tuple[str, ...]] = {
    "EUR": ("€",),
    "PLN": ("zł", "zl"),
    "CZK": ("Kč",),
    "HUF": ("Ft",),
    "RON": ("lei",),
    "SEK": ("kr",),
    "DKK": ("kr.", "kr"),
}

_current: ContextVar[str] = ContextVar("currency", default=DEFAULT_CURRENCY)


@contextmanager
def use_currency(code: str) -> Iterator[None]:
    """Write amounts in `code` until the block ends."""
    token = _current.set(code)
    try:
        yield
    finally:
        _current.reset(token)


def current_currency() -> str:
    return _current.get()


def money(minor: int) -> str:
    """-EUR 5,000.00 style, in the request's currency."""
    sign = "-" if minor < 0 else ""
    whole, fraction = divmod(abs(minor), 100)
    return f"{sign}{_current.get()} {whole:,}.{fraction:02d}"


def amount_markers() -> str:
    """A regex alternation of every code and symbol, longest first so 'kr.' wins over 'kr'."""
    markers = set(CURRENCIES) | {symbol for symbols in SYMBOLS.values() for symbol in symbols}
    return "|".join(re.escape(marker) for marker in sorted(markers, key=len, reverse=True))

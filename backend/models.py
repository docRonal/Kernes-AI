from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, StrictInt, field_validator


# Shared by the CSV parser and the JSON endpoints, so neither path accepts what the other refuses.
HORIZON_DAYS = 14
MAX_TRANSACTIONS = 5_000
MAX_ID_LENGTH = 64
MAX_LABEL_LENGTH = 200
# PLN 1 billion per amount keeps every total below 2**53, so browsers read it exactly.
MAX_ABS_MINOR = 100_000_000_000
MAX_DELAY_DAYS = 365
# Line breaks and other control characters would let a label add fake lines to the model prompt.
NO_CONTROL_CHARACTERS = r"^[^\x00-\x1f\x7f-\x9f\u2028\u2029]*$"


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: UploadFile
    starting_balance_minor: int
    # A later start would push the 14-day window past the last date Python can represent.
    start_date: date = Field(le=date.max - timedelta(days=HORIZON_DAYS - 1))
    move_transaction_id: str | None = None
    move_to_date: date | None = None


class Transaction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=MAX_ID_LENGTH, pattern=NO_CONTROL_CHARACTERS)
    date: date
    amount_minor: StrictInt = Field(ge=-MAX_ABS_MINOR, le=MAX_ABS_MINOR)
    label: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH, pattern=NO_CONTROL_CHARACTERS)


class Deficit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    shortfall_minor: PositiveInt


class DailyBalance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    balance_minor: StrictInt


class Projection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: list[DailyBalance] = Field(min_length=HORIZON_DAYS, max_length=HORIZON_DAYS)
    first_deficit: Deficit | None

    @field_validator("days")
    @classmethod
    def _consecutive(cls, days: list[DailyBalance]) -> list[DailyBalance]:
        if any((later.date - earlier.date).days != 1 for earlier, later in zip(days, days[1:])):
            raise ValueError("the days must be consecutive dates")
        return days


class Proposal(BaseModel):
    """Credit facility the Liquidity Agent proposes for a baseline shortfall."""

    model_config = ConfigDict(extra="forbid")
    limit_minor: PositiveInt
    first_shortfall: Deficit
    deepest_shortfall: Deficit
    relevant_transaction_ids: list[str]


class ForecastResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transactions: list[Transaction]
    baseline: Projection
    proposal: Proposal | None
    scenario: Projection | None


class AdviceRequest(BaseModel):
    """The baseline and transactions from the forecast response.

    The server recalculates the proposal from them, so the model always explains
    the deterministic figures.
    """

    model_config = ConfigDict(extra="forbid")
    baseline: Projection
    transactions: list[Transaction] = Field(min_length=1, max_length=MAX_TRANSACTIONS)
    # Larger delays would move a payment date past the end of the calendar.
    client_delays: dict[str, Annotated[int, Field(ge=0, le=MAX_DELAY_DAYS)]] | None = None


class AdviceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanation: str = Field(min_length=1)
    email_draft: str | None
    model: str
    latency_ms: NonNegativeInt | None


class DelayPredictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanation: str = Field(min_length=1)
    email_draft: str | None
    delay_warning: str | None
    model: str
    latency_ms: NonNegativeInt | None


class ReminderSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_email: str = Field(min_length=3, max_length=254)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


class ReminderSendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["simulated"]
    recipient: str
    subject: str
    message: str


DecisionKind = Literal["approved", "rejected"]


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: DecisionKind
    baseline: Projection


class DecisionDay(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    balance_minor: StrictInt
    facility_used_minor: NonNegativeInt
    uncovered_minor: NonNegativeInt


class DecisionResponse(BaseModel):
    """Outcome of a simulated human decision. Nothing is applied for, sent or moved."""

    model_config = ConfigDict(extra="forbid")
    decision: DecisionKind
    simulated: Literal[True]
    limit_minor: PositiveInt
    days: list[DecisionDay] = Field(min_length=14, max_length=14)
    largest_uncovered: Deficit | None

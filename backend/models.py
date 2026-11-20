from datetime import date
from typing import Literal

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, StrictInt


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: UploadFile
    starting_balance_minor: int
    start_date: date
    move_transaction_id: str | None = None
    move_to_date: date | None = None


class Transaction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    date: date
    amount_minor: StrictInt
    label: str


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
    days: list[DailyBalance] = Field(min_length=14, max_length=14)
    first_deficit: Deficit | None


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
    transactions: list[Transaction] = Field(min_length=1)
    client_delays: dict[str, NonNegativeInt] | None = None


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
    status: Literal["simulated", "sent"]
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

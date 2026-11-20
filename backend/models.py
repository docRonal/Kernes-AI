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
    model_config = ConfigDict(extra="forbid")
    first_deficit: Deficit
    transactions: list[Transaction]


class AdviceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanation: str
    email_draft: str


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

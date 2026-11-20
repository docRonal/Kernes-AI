from datetime import date

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, StrictInt


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


class ForecastResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transactions: list[Transaction]
    baseline: Projection
    scenario: Projection | None


class AdviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_deficit: Deficit
    transactions: list[Transaction]


class AdviceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanation: str
    email_draft: str

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import UploadFile
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveInt,
    StrictInt,
    StringConstraints,
    field_validator,
)


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

SUPPORTED_CURRENCIES = frozenset(
    {"EUR", "PLN", "CHF", "USD", "GBP", "CZK", "SEK", "DKK", "HUF", "RON", "BGN", "NOK"}
)
CurrencyCode = Literal[
    "EUR", "PLN", "CHF", "USD", "GBP", "CZK", "SEK", "DKK", "HUF", "RON", "BGN", "NOK"
]


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


class EarlierPayment(BaseModel):
    """An incoming payment that would shrink the proposed facility if the client paid it by pay_by."""

    model_config = ConfigDict(extra="forbid")
    transaction_id: str
    pay_by: date
    limit_after_minor: NonNegativeInt


class ForecastResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: CurrencyCode = "EUR"
    transactions: list[Transaction]
    baseline: Projection
    proposal: Proposal | None
    earlier_payments: list[EarlierPayment]
    scenario: Projection | None


class AdviceRequest(BaseModel):
    """The baseline and transactions from the forecast response.

    The server recalculates the proposal from them, so the model always explains
    the deterministic figures.
    """

    model_config = ConfigDict(extra="forbid")
    baseline: Projection
    transactions: list[Transaction] = Field(min_length=1, max_length=MAX_TRANSACTIONS)
    currency: CurrencyCode = "EUR"
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


class InsightRequest(BaseModel):
    """The baseline and transactions from the forecast response. Every figure is recalculated from them."""

    model_config = ConfigDict(extra="forbid")
    baseline: Projection
    transactions: list[Transaction] = Field(min_length=1, max_length=MAX_TRANSACTIONS)
    currency: CurrencyCode = "EUR"


class StressScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    deepest_shortfall: Deficit | None
    extra_needed_minor: NonNegativeInt


class StressTestResponse(BaseModel):
    """Worst cases for the forecast and the extra credit they would need. Calculated, never from the model."""

    model_config = ConfigDict(extra="forbid")
    proposed_limit_minor: NonNegativeInt
    scenarios: list[StressScenario]
    buffer_minor: NonNegativeInt
    recommended_limit_minor: NonNegativeInt


class PaymentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["collect_earlier", "pay_later"]
    transaction_id: str
    due_date: date
    new_date: date
    limit_after_minor: NonNegativeInt
    saves_minor: PositiveInt


class PaymentOptimizationResponse(BaseModel):
    """Ways to need less credit, best first. Calculated, never from the model."""

    model_config = ConfigDict(extra="forbid")
    proposed_limit_minor: NonNegativeInt
    actions: list[PaymentAction]


class ScoreFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["repayment", "coverage", "duration", "depth", "concentration", "delays"]
    points: NonNegativeInt
    reason: str


class CreditCheckResponse(BaseModel):
    """A transparent scorecard for the proposed facility. The score is calculated; the model only explains it."""

    model_config = ConfigDict(extra="forbid")
    score: int = Field(ge=0, le=100)
    risk: Literal["low", "medium", "high"]
    limit_minor: PositiveInt
    factors: list[ScoreFactor]
    explanation: str | None
    explanation_error: str | None
    model: str | None
    latency_ms: NonNegativeInt | None


class AskRequest(InsightRequest):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class WhatIf(BaseModel):
    """The change the question asked about, recalculated by the application."""

    model_config = ConfigDict(extra="forbid")
    transaction_id: str
    new_amount_minor: StrictInt
    new_date: date
    deepest_shortfall: Deficit | None


class AskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    what_if: WhatIf | None
    model: str
    latency_ms: NonNegativeInt


class AnomalyFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["duplicate_payment", "outlier_expense", "same_day_spike"]
    date: date
    amount_minor: NonNegativeInt
    transaction_ids: list[str] = Field(min_length=1)
    detail: str


class AnomalyDetectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline: Projection
    transactions: list[Transaction] = Field(min_length=1)
    currency: CurrencyCode = "EUR"


class AnomalyDetectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[AnomalyFinding]
    risk_flag: Literal["clean", "review_recommended"]
    summary: str = Field(min_length=1)
    model: str
    latency_ms: NonNegativeInt | None


class FinancingOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_kind: Literal["credit_facility", "invoice_factoring", "defer_outflow"]
    title: str
    estimated_cost_minor: NonNegativeInt
    credit_needed_minor: NonNegativeInt
    detail: str


class CompareOptionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline: Projection
    transactions: list[Transaction] = Field(min_length=1)
    currency: CurrencyCode = "EUR"
    annual_rate_bps: NonNegativeInt = Field(default=1200, le=10000)
    factoring_fee_bps: NonNegativeInt = Field(default=150, le=5000)


class CompareOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    options: list[FinancingOption]
    recommended_option: Literal["credit_facility", "invoice_factoring", "defer_outflow", "none_needed"]
    explanation: str = Field(min_length=1)
    model: str
    latency_ms: NonNegativeInt | None

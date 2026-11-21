"""Descriptions for each API route. contracts/openapi.json is generated from them.

Run `uv run --locked python scripts/export_openapi.py` after changing a route,
a model or a description. A test fails while the committed contract differs
from what the app serves.
"""

from typing import Any

CURRENCY_NOTE = (
    " Every request takes an optional currency: EUR (default), PLN, CZK, HUF, RON, SEK or DKK."
    " Amounts are integer minor units (1 unit = 100) in that currency; the app never converts."
)

MODEL_503 = {
    "description": "The model is unavailable, timed out, or its answer didn't match the calculated figures "
    "after a retry and the fallback model. The forecast and proposal stay valid."
}


def route(description: str, ok: str, **errors: str) -> dict[str, Any]:
    responses: dict[int | str, dict[str, Any]] = {200: {"description": ok}}
    for code, text in errors.items():
        responses[int(code.removeprefix("e"))] = MODEL_503 if text == "model" else {"description": text}
    return {"description": description + CURRENCY_NOTE, "responses": responses}


ROUTES: dict[str, dict[str, Any]] = {
    "forecast": route(
        "Compute 14 end-of-day balances including start_date from a UTF-8 CSV with the header "
        "id,date,amount_minor,label. The opening balance comes before any start_date movement. Rows outside "
        "the window don't move the balance and are returned unchanged in transactions. first_deficit is the "
        "first strictly negative day. When the baseline goes below zero, proposal is a credit facility whose "
        "limit is the deepest gap, max(0, -min(balances)); the earliest day wins a tie. earlier_payments lists "
        "incoming payments that would shrink the facility if collected earlier. Send move_transaction_id and "
        "move_to_date together to move one incoming payment inside the window: scenario then holds that "
        "projection and the baseline and proposal stay unchanged. The response echoes the currency.",
        "Computed forecast",
        e422="Invalid CSV, fields, currency, transaction ID or scenario date. detail is a readable message, "
        "with the CSV line number where it applies.",
    ),
    "decision": route(
        "Simulate the owner's decision on the proposed facility. The server recalculates the limit from the "
        "baseline. Approved: each day uses up to the limit to cover a negative balance and reports what is "
        "still uncovered. Rejected: the original gap stays uncovered. Balances are returned unchanged. Nothing "
        "is applied for, transferred or sent.",
        "Simulated outcome",
        e422="Unknown decision, a baseline that isn't 14 consecutive days, or a baseline without a shortfall",
    ),
    "advice": route(
        "Explain the proposal with the model served on OpenShift AI and draft an editable payment reminder. "
        "The server recalculates the proposal, gives the model only formatted facts, and rejects an answer "
        "whose amounts aren't those facts or that misses the first gap, the deepest gap or the limit. It "
        "retries once, then tries the fallback model. Demo mode returns demo/advice.example.json.",
        "Explanation and editable draft",
        e422="Invalid request, or a baseline with no shortfall to explain",
        e503="model",
    ),
    "predict_delays": route(
        "The advice answer plus a warning about how a client's historical payment delay would change the gap. "
        "The delayed limit is calculated in Python; the model only words it.",
        "Explanation, draft and delay warning",
        e422="Invalid request",
        e503="model",
    ),
    "send_reminder": route(
        "Simulate sending the reminder draft. Nothing is sent: the owner copies the draft and sends it "
        "from their own email.",
        "Simulated send, status is always simulated",
        e422="Invalid address, subject or body",
    ),
    "stress_test": route(
        "Recalculate the deepest gap when incoming payments arrive 3 or 5 days later, outgoing payments are "
        "10% higher, or both, and suggest a limit with a buffer for the worst case. Deterministic, no model.",
        "Stress scenarios and recommended limit",
        e422="Invalid request",
    ),
    "optimize_payments": route(
        "Ways to need less credit, best first: collect an invoice earlier or pay a bill later. Wages, taxes, "
        "social insurance and loan repayments are never moved. Deterministic, no model.",
        "Ranked payment moves with the limit each one leaves",
        e422="Invalid request",
    ),
    "credit_check": route(
        "Score the proposed facility from 100 down, one deduction per risk with its reason. The points are an "
        "illustrative scorecard, not a bank's credit model. The model explains the calculated score.",
        "Score, risk band and factors",
        e422="Invalid request, or a baseline without a shortfall",
        e503="model",
    ),
    "ask_cfo": route(
        "Answer the owner's question about the forecast. If the question changes one transaction (amount or "
        "date), Python recalculates the forecast first; the model answers only from calculated facts.",
        "Answer and the recalculated what-if, if any",
        e422="Invalid request or question",
        e503="model",
    ),
    "detect_anomalies": route(
        "Flag unusual payments: same-day spikes, outlier expenses and duplicate payments. The findings are "
        "calculated in Python; in live mode the model writes the summary.",
        "Findings and a risk flag",
        e422="Invalid request",
    ),
    "compare_options": route(
        "Compare ways to cover the gap: the credit facility with its estimated interest, invoice factoring, or "
        "deferring a bill. Costs are calculated in Python; in live mode the model explains the recommendation.",
        "Options with estimated cost and the recommended one",
        e422="Invalid request",
    ),
}

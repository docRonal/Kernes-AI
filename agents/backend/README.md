# Cash Flow Backend

**Owner** Andrii · **Tool** Claude Code · **Branch** `feat/backend`

## Scope

Own `backend/forecast.py`, `backend/main.py`, `backend/models.py`, and `tests/test_forecast.py`. Coordinate changes to the [API contract](../../contracts/openapi.json) and shared dependencies with Mikhail. See the [team workflow and tech stack](../../README.md).

## Deliverables

1. Implement `POST /api/forecast` in `live` mode. Parse UTF-8 CSV, validate headers, dates, amounts, and unique transaction IDs, and return HTTP 422 for invalid input.
2. Calculate 14 end-of-day balances in integer grosz, starting from the opening balance before the first day's transactions. Identify the first negative balance.
3. Recalculate the alternative forecast when an incoming payment moves to a new date. Preserve the original transactions and baseline forecast.
4. Cover the demo case, invalid input, same-day transactions, and cases with no shortfall in the forecast tests. Keep local `demo` mode runnable.

Tell Timur when the forecast matches the contract so he can test integration. If Ivan needs changes to advice routing or shared models, agree on those changes before editing.

## Starter prompt

> Read AGENTS.md, agents/backend/README.md, and contracts/openapi.json. Work on feat/backend. Implement the live forecast and payment-date scenario, run the forecast tests, and use forecast-reviewer if available. Report the results and any API changes.

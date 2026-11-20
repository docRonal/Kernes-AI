# Cash Flow Backend

**Owner** Andrii · **Tool** Claude Code · **Branch** `feat/backend`

## Scope

Own `backend/forecast.py`, `backend/main.py`, `backend/models.py`, and `tests/test_forecast.py`. Coordinate changes to the [API contract](../../contracts/openapi.json) and shared dependencies with Mikhail. See the [team workflow and tech stack](../../README.md).

## Deliverables

1. Implement `POST /api/forecast` in `live` mode. Parse UTF-8 CSV, validate headers, dates, amounts, and unique transaction IDs, and return HTTP 422 for invalid input.
2. Calculate 14 end-of-day balances in integer grosz, starting from the opening balance before the first day's transactions. Identify the first shortfall and the deepest baseline shortfall. When there is a shortfall, propose a facility limit equal to the peak projected gap, `max(0, -min(projected_balances))`. Use the earliest date for tied minima and omit the proposal when every balance is nonnegative.
3. Recalculate the alternative forecast when an incoming payment moves to a new date. Preserve the original transactions and baseline forecast.
4. Implement the approved and rejected simulations under the agreed contract. On each day the approved outcome shows any amount still uncovered after accounting for the facility limit. The rejected outcome shows the original uncovered gap. Keep the forecast intact and the workflow simulation-only.
5. Cover the starter example, a deeper shortfall later in the horizon, invalid input, same-day transactions, no shortfall, and both decision outcomes in tests. Keep local `demo` mode runnable.

Work with Mikhail and the other owners to agree on the new forecast, proposal, explanation, and decision data through one contract PR. Hand the agreed deterministic facts to Ivan for model grounding, and share forecast and simulation examples with Timur and Yuri.

## Starter prompt

> Read AGENTS.md, agents/backend/README.md, and contracts/openapi.json. Work on feat/backend. Follow the shared contract PR when implementing the live forecast, credit facility limit, human decision simulation, and payment-date comparison. Run the forecast tests, use forecast-reviewer if available, and report the results.

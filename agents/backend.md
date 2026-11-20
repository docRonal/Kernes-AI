# Forecasting and API with Claude Code

Work on `feat/backend`. Your files are `backend/forecast.py`, input validation in `backend/main.py`, and the forecast tests. Coordinate changes to shared data models and dependencies with the integration owner. Integrate with the Codex work through the public function in `backend/advice.py`.

## Task

1. Implement the calculation in `live` mode according to the [API contract](../contracts/openapi.json). Parse UTF-8 CSV and validate the headers, dates, amounts, and unique IDs. Return HTTP 422 for invalid input.
2. Calculate 14 end-of-day balances. Apply the opening balance before the first day's transactions. Sum transactions in whole grosz. Find the first date with a negative balance.
3. Recalculate the alternative forecast when an incoming payment moves to a new date. Preserve the original transactions and the baseline forecast.
4. Test the scenario in `demo/`, invalid input, multiple transactions on the same day, and cases with no shortfall. Keep the fixture-based local demo runnable until the implementation is merged.

## Starter prompt

> Read AGENTS.md, agents/backend.md, and contracts/openapi.json. Work on feat/backend. Implement the forecast and payment rescheduling, then run the tests. Ask forecast-reviewer to review the diff if available. List your changes and the commands you ran to verify them.

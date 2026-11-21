# Cash Flow Backend

**Owner** Andrii · **Tool** Claude Code · **Branch** `feat/backend`

## Scope

Own `backend/forecast.py`, `backend/insights.py`, `backend/advisory_extras.py`, `backend/main.py`, `backend/models.py`, and their unit tests (`tests/test_forecast.py`, `tests/test_insights.py`, `tests/test_advisory_extras.py`, `tests/test_stress_csvs.py`). Coordinate changes to [contracts/openapi.json](../../contracts/openapi.json) and shared dependencies via PRs reviewed by Yurii and Mikhail. See [README.md](../../README.md).

## Deliverables

1. Parse semicolon-delimited MT940-style UTF-8 bank CSVs in `live` mode, validate headers, dates, amounts, currencies (`EUR`, `PLN`, `USD`, `CHF`, `GBP`), and unique transaction IDs, and return HTTP 422 for invalid input.
2. Calculate 14 end-of-day balances in integer minor units, starting from the opening balance before the first day's transactions. Identify the first shortfall and the deepest baseline shortfall, proposing `max(0, -min(projected_balances))` (earliest date on ties; omit proposal if all balances are nonnegative).
3. Classify every transaction deterministically via `classify_transaction()` (`transaction_type`, `counterparty`, `payment_reference`, `category`, `actionability`) so walk-in retail card customers (`retail_non_contactable`) and mandatory taxes/social/staff payroll (`fixed_mandatory`) are never targeted for email outreach.
4. Preserve original transactions and baseline when simulating payment-date shifts, approved/rejected credit facility outcomes, stress tests, payment optimization, and anomaly detection. Keep local `demo` mode runnable.

Work with Mikhail, Ivan, Tsimur, and Yurii via Pull Requests to `main` (never push directly or force-push to `main`).

## Starter prompt

> Read AGENTS.md, agents/backend/README.md, and contracts/openapi.json. Work on a feature branch for PR into main. Maintain integer minor-unit forecast arithmetic, MT940-style CSV validation, counterparty classification, and simulation-only decision endpoints. Run pytest and report the results.

# QA, Demo & Evaluation

**Owner** Yuri · **Tool** Antigravity · **Branch** `feat/qa-demo`

## Scope

Own `tests/test_smoke.py`, the synthetic demo cases in `demo/`, and `notebooks/` if the team takes the notebook bonus. Coordinate fixture changes with everyone who uses them. See the [team workflow and tech stack](../../README.md).

## Deliverables

1. Agree on shared fixture expectations in Mikhail's contract PR. Use at least two synthetic cases. Use the starter sample and the second case in [README.md](../../README.md), where the peak shortfall exceeds the first. Include a no-shortfall check and keep the starter's payment date scenario. Any exploration of the optional Amalfi EUR/CHF semicolon-delimited data stays local.
2. Test the complete flow locally and at the deployed URL Mikhail shares. Verify the automatic facility proposals and show both human decision paths. For the starter, approval shows a simulated uncovered gap of PLN 0 and rejection leaves the PLN 5,000 gap. Verify that the model grounds its explanation in the forecast and transactions, and check that the UI preserves the forecast if advice is unavailable.
3. Verify that the starter comparison still shows −PLN 5,000 on Friday and +PLN 4,000 if the incoming payment moves earlier. Prepare a demo that shows the proposal, live model explanation, human decisions, and their simulated outcomes. Record the deployed URL, commit SHA, model name, live inference evidence, checks passed, and remaining blockers.
4. If the team pursues the Jupyter bonus and an OpenShift AI workbench is available, evaluate the synthetic cases there. Compare the model's stated dates, amounts, and facility limit against expected values.

## Starter prompt

> Read AGENTS.md, agents/qa/README.md, and contracts/openapi.json. Work on feat/qa-demo. Prepare the synthetic cases and verify the full workflow through both simulation decisions. Report what passed locally, what passed on the assigned OpenShift environment, and any blockers.

## Latest QA Suite & Handoff Notes

- **Multi-core QA Runner (`scripts/qa_runner.py`)**:
  - `uv run --locked python scripts/qa_runner.py --local` — shards local `pytest` suites across CPU threads (~13–15 s).
  - `uv run --locked python scripts/qa_runner.py --remote` — runs `test_remote_deployment_workflow` across all 12 endpoints and 5 synthetic cases on OpenShift.
  - `uv run --locked python scripts/qa_runner.py --browser` — runs Playwright browser E2E (`tests/test_e2e_browser.py`, `CFO_RUN_BROWSER_E2E=1`).
- **Expanded QA Coverage (`tests/test_advisory_extras.py`, `tests/test_smoke.py`)**:
  - Added anomaly-detector, `none_needed` compare-options, factoring fee scaling, and 14-day window validation tests built on `demo/stress_cases/amalfi_duplicate_anomaly_eur.csv` and `demo/no_shortfall_case.csv`.
  - Fixed `_assert_explanation_grounded` in `tests/test_smoke.py` to use numeric-boundary matching (`_matches_amount_token`) instead of plain substring matching (`'200'` no longer matches `'1,200.00'`).
- **Frontend Race-Condition Finding (for Ivan — `frontend/assets/app.js`)**:
  - In `showSetupScreen()` (`frontend/assets/app.js`), when the user clicks `← Change file` (`#change-file-btn`) while `loadInsights()` is still awaiting background `/api/*` responses, `showSetupScreen()` sets `state.forecast = null` and increments `state.adviceRequestId += 1`, but does **not** increment `state.insightsRequestId += 1`. When `Promise.allSettled` in `loadInsights()` resolves afterwards, `reqId === state.insightsRequestId` stays true and `renderOptimizePayments(..., state.forecast.transactions, ...)` throws `TypeError: Cannot read properties of null (reading 'transactions')`.
  - **Fix**: Add `state.insightsRequestId += 1;` inside `showSetupScreen()` (and guard `if (!state.forecast) return;` after `await Promise.allSettled(...)` in `loadInsights()`).

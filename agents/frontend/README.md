# Frontend & UX

**Owner** Timur · **Tool** Antigravity · **Branch** `feat/frontend`

## Scope

Own `web/` (React, TypeScript, and Vite) and its build output in `frontend/`. Run `npm run build` in `web/` before committing so `frontend/` matches the source. Follow the [API contract](../../contracts/openapi.json) and coordinate proposed contract changes with Mikhail. See the [team workflow and tech stack](../../README.md).

## Deliverables

1. Build one page for CSV upload, opening balance, start date, and loading the sample scenario.
2. Show 14 daily balances in a chart or clear table. Highlight the first shortfall and let the user move an incoming payment to compare the baseline and adjusted forecasts.
3. Automatically display the credit facility proposal when the baseline has a shortfall. Show the deterministic limit and shortfall facts, and load the model explanation automatically using the agreed contract. Provide approval and rejection controls labeled as simulations, then show the resulting uncovered gap. Keep the editable reminder draft available on request.
4. Handle loading, invalid input, and model outages. Keep the forecast and calculated proposal figures visible if the explanation request fails. Clear the proposal and decision for a new baseline, and show no proposal for a forecast with no shortfall. Keep the baseline and the payment-date comparison accessible throughout both decision paths.

Agree on the proposal, advice, and decision flow in Mikhail's shared contract PR. Start with the agreed sample responses in `demo` mode. Test with the live API after Andrii and Ivan verify their implementations, then share the browser steps with Yuri.

## Starter prompt

> Read AGENTS.md, agents/frontend/README.md, and contracts/openapi.json. Work on feat/frontend and edit web/. Implement the automatic explanatory proposal and the human decision simulation within the CSV-to-forecast flow. Preserve the what-if comparison and verify both decisions in a browser.

# Frontend & UX

**Owner** Timur · **Tool** Antigravity · **Branch** `feat/frontend`

## Scope

Own `frontend/`. Use the starter's HTML, CSS, and JavaScript and run the app from the repository root. Follow the [API contract](../../contracts/openapi.json) and coordinate proposed contract changes with Mikhail. See the [team workflow and tech stack](../../README.md).

## Deliverables

1. Build one page for CSV upload, opening balance, start date, and loading the sample scenario.
2. Show 14 daily balances in a chart or clear table. Highlight the first shortfall and let the user move an incoming payment to compare the baseline and adjusted forecasts.
3. When requested, call `POST /api/advice` with the baseline shortfall and transactions returned by the forecast. Display the explanation and editable email draft.
4. Handle loading, invalid input, and model outages. Keep the forecast visible if the advice request fails.

Use `demo` mode and the sample responses first. Test with the live API once Andrii and Ivan have verified their endpoints, then share the browser steps with Yuri.

## Starter prompt

> Read AGENTS.md, agents/frontend/README.md, and contracts/openapi.json. Work on feat/frontend and edit frontend/. Improve the CSV-to-forecast flow and advice display. Verify the demo in a browser and share the steps with QA.

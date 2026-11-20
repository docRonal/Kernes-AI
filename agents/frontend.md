# User interface with Antigravity

Work on `feat/frontend`. Your files are in `frontend/`. Run the application from the repository root. Coordinate changes to the HTTP contract with the integration owner.

## Task

1. Build one page with a CSV upload, an opening balance, a start date, and a button to load the scenario from `demo/`.
2. Show 14 days in a chart or a clear table, along with the date and amount of the first shortfall. Let users move an incoming payment to another date and compare the baseline and updated forecasts side by side.
3. When requested, call `POST /api/advice` with the first shortfall from the baseline forecast and the transactions returned by the forecast. Show the explanation and an editable email draft.
4. Handle loading states, input errors, and model outages. Keep the forecast on screen if the advice request fails. Test the page in a browser with the demo CSV.

## Starter prompt

> Read AGENTS.md, agents/frontend.md, and contracts/openapi.json. Work on feat/frontend and edit files under frontend/. Use local demo mode, improve the interface, and verify the full scenario in a browser. Explain how to repeat the check manually.

# Frontend & UX

**Owner** Tsimur · **Tool** Antigravity · **Branch** `feat/frontend`

## Scope

Own the HTML, CSS, and ES modules in `frontend/` (`index.html`, `assets/app.js`, `assets/chart.js`, `assets/styles.css`, `assets/css/*.css`, `assets/js/*.js`). Run FastAPI from the repository root and verify edits in the browser against [contracts/openapi.json](../../contracts/openapi.json). See [README.md](../../README.md).

## Deliverables

1. Deliver the Progressive Disclosure UX: 2 quick onboarding context questions (*business type* + *main goal*) + CSV upload / 1-click *Pizzeria Amalfi* demo on `#setup-screen`.
2. Show the top-level verdict, 14-day interactive SVG cash chart (with Forecast / Stress Test / What-If overlays), grounded briefing, and `POST /api/action-plan` steps (`frontend/assets/js/action_plan.js`, `frontend/assets/css/progressive.css`) with all 4 autonomy badges.
3. Provide simulation-only Approve/Reject credit buffer controls, payment-date comparison, and editable B2B email drafts (`Simulate send` / `Copy email`) that never trigger real transfers or messages.
4. Tuck deeper analytical tools (*What-If Simulator & Q&A*, *Client Pays Late*, *Compare Options*, *Cash Health Score & Stress Test*, *Smart Payment Moves*, *Anomaly Detector*) inside collapsible `#advanced-details-section` accordions, keeping forecast/proposal visible during HTTP 503 model outages and guarding async requests against `← Change file` race conditions.

Share UI and DOM selector updates with Yurii for end-to-end QA and merge via Pull Request into `main`.

## Starter prompt

> Read AGENTS.md, agents/frontend/README.md, and contracts/openapi.json. Work on a feature branch for PR into main. Maintain the Progressive Disclosure UI, Action Plan cards, autonomy badges, and simulation-only controls in frontend/.

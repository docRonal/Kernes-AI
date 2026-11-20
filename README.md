# Autonomous CFO

Our Autonomous CFO entry for the Red Hat challenge at Collabothon focuses on the **Liquidity Agent**. The current starter covers CSV upload, cash forecasting, moving an incoming payment earlier, and draft reminder advice. The complete challenge scenario includes an automatic credit facility proposal, a human decision, and a simulated outcome. The steps below define the target the team will implement and verify.

## Liquidity Agent demo scope

1. The user uploads synthetic upcoming payments and enters an opening balance and start date. The app projects 14 end-of-day cash balances in PLN and identifies the first day below zero.
2. If the baseline forecast shows a shortfall, the app automatically shows a proposed credit facility. Calculate its limit as `max(0, -min(projected_balances))` over the baseline horizon in integer grosz. Show the first shortfall date and amount, the date and size of the deepest shortfall, and the relevant transactions. Use the earliest date if the deepest shortfall spans multiple days. A baseline that stays at or above zero needs no facility.
3. The open-source or open-weight model explains why the limit would cover the projected gap, using the forecast figures and relevant transaction facts supplied by the backend. The deterministic calculation supplies the amount. During a model outage, show the forecast and proposal figures with a clear explanation error so the user can still review them.
4. The user chooses **Approve simulation** or **Reject simulation**. For approval, show the projected uncovered gap after simulated access to the facility limit on each day. For rejection, show the original unfunded gap. Keep the underlying balances intact. Both decisions are simulations and trigger zero real applications, transfers, or messages.
5. Keep the what-if comparison for moving an incoming payment earlier. The separate scenario shows how the cash position changes and keeps the baseline and its proposal available. The user can still request an editable payment reminder draft.

Run the complete solution on the team's assigned OpenShift AI environment, with the app on its OpenShift cluster and an open-source or open-weight model served on that OpenShift AI deployment for all model inference. Record the model name and evidence of a live inference call. MaaS and an OpenShift AI Jupyter workbench evaluation are optional bonus paths if available.

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run this command from the repository root.

```sh
uv run --locked uvicorn backend.main:app --host 127.0.0.1 --port 8080
```

Open the [app](http://127.0.0.1:8080) or the [Swagger UI](http://127.0.0.1:8080/docs). Run the tests in a separate terminal.

```sh
uv run --locked pytest -q
```

In `demo` mode, the app accepts [demo/transactions.csv](demo/transactions.csv) and returns a saved response. The starter includes two forecast outcomes and a sample model response. The `live` mode is the integration point for live forecasting and calls to OpenShift AI. See the [deployment guide](deploy/README.md).

For local configuration, copy `.env.example` to `.env` and add `--env-file .env` immediately after `uv run --locked`. The app starts in `demo` mode by default.

## Tech stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12+, FastAPI, Pydantic, Uvicorn, and `python-multipart` for CSV uploads. The container uses Python 3.12. |
| Frontend | HTML, CSS, and vanilla JavaScript. FastAPI serves the page and assets. The browser calls the API with `fetch`. |
| Forecast data | Python's `csv` module, integer grosz amounts, and in-memory request processing. Synthetic CSVs and example responses live in `demo/`. |
| AI inference | An open-source or open-weight model served on the team's assigned Red Hat OpenShift AI environment. Use Python's `urllib.request` for server-side JSON calls to the configured endpoint. MaaS is an optional bonus path if available. |
| Deployment | One container built from `Containerfile`. Red Hat OpenShift runs it through a Deployment, Service, and HTTPS Route. Store the model token in an OpenShift Secret. |
| Tooling and verification | `uv` and `uv.lock` for dependencies, `pytest` for automated tests, and GitHub for branches and PRs. Use an OpenShift AI Jupyter workbench for the optional evaluation notebook. |

## Team roles

Each folder contains the owner's responsibilities, file scope, checks, and starter prompt. Application files stay in their component directories, so each role works against the same runnable app.

| Owner | Tool | Role | Branch |
| --- | --- | --- | --- |
| Mikhail | Codex | [Deployment & Integration](agents/deployment/README.md) | `feat/openshift` |
| Andrii | Claude Code | [Cash Flow Backend](agents/backend/README.md) | `feat/backend` |
| Timur | Antigravity | [Frontend & UX](agents/frontend/README.md) | `feat/frontend` |
| Ivan | Antigravity | [AI Model Integration](agents/ai-integration/README.md) | `feat/advice` |
| Yuri | Antigravity | [QA, Demo & Evaluation](agents/qa/README.md) | `feat/qa-demo` |

## How we stay in sync

1. Fetch `origin` and check out your assigned role branch. Open the repository root in your coding tool and use your role's starter prompt. On a shared laptop, use one Git worktree per branch.
2. Treat [the OpenAPI contract](contracts/openapi.json) and the examples in [demo/](demo/) as shared. The checked-in contract describes the current scaffold. Mikhail, Andrii, Timur, Ivan, and Yuri agree on the proposal data, explanation, decision and simulation flow, and fixture expectations through one coordinated contract PR. Use the agreed contract for the feature branches. Coordinate dependency changes with Mikhail and the affected owners.
3. Open a PR with what changed, the checks you ran, and anything another role needs to pick up. Mikhail coordinates reviews and merges. When a dependency merges, bring the latest `main` into your branch and rerun your checks.
4. Deploy the starter early while the frontend uses the saved HTTP responses and the backend and AI owners build their implementations. Deploy the complete scenario in `live` after the forecast, model explanation, and simulation are integrated. Yuri runs the end-to-end demo check on that same deployment.

On your first checkout from a personal clone, track the remote branch listed above. For example:

```sh
git fetch origin
git switch --track origin/feat/backend
```

## Instructions and subagents

All role sessions use the shared rules in [AGENTS.md](AGENTS.md). [CLAUDE.md](CLAUDE.md) imports the same file for Claude Code. Open the root of the relevant clone or worktree in each tool.

- `forecast-reviewer` checks the calculations, input validation, and payment-date scenario.
- `integration-reviewer` checks how the UI, API, and OpenShift fit together.

The configurations are in `.codex/agents/`, `.claude/agents/`, and `.agents/agents/`, respectively. In Codex and Antigravity App or CLI, ask the primary agent to delegate the review by name and pass the list of changed files. In Claude Code, mention `@agent-forecast-reviewer` or `@agent-integration-reviewer`. If your installed version does not show a subagent, give the primary agent the [review checklists](agents/reviewer.md). [Codex](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents) · [Claude Code](https://code.claude.com/docs/en/sub-agents#invoke-subagents-explicitly) · [Antigravity](https://antigravity.google/docs/subagents#custom-subagents)

## Verify before the demo

Use at least two synthetic cases on the deployed live app. The official Amalfi dataset is optional and for local exploration only. Its EUR/CHF values and semicolon-delimited fields are incompatible with the MVP's PLN comma-delimited input.

1. Upload the starter sample, enter PLN 12,000 as the opening balance, and select November 23, 2026. The baseline reaches **−PLN 5,000** on November 27. It should show a **PLN 5,000** credit facility automatically. Verify that the live OpenShift AI explanation matches the dates, limit, and transactions.
2. Approve the proposal and verify that the simulated uncovered gap drops to **PLN 0**. Reload the original case, reject the proposal, and verify that the uncovered gap stays **PLN 5,000** on November 27. Verify that the UI makes the simulation status clear in both cases.
3. Move payment `INV-001` to November 26. Verify that the alternative Friday balance is **PLN 4,000** and the baseline still shows **−PLN 5,000**. Request the editable reminder draft if demonstrating that feature.
4. Use [the peak-shortfall fixture](demo/credit_peak_case.csv) with a November 23 start date. It starts with PLN 1,000, projects a PLN 1,200 outflow on day 2 and a PLN 500 outflow on day 4, and receives PLN 1,000 on day 7. Verify that the explanation distinguishes the **PLN 200** first shortfall from the **PLN 700** peak shortfall and that the app proposes **PLN 700**. Check a no-shortfall forecast separately and verify that it shows no proposal.

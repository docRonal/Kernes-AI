# Autonomous CFO

Our Autonomous CFO entry for the Red Hat challenge at Collabothon focuses on the **Liquidity Agent**. The current starter covers CSV upload, cash forecasting, moving an incoming payment earlier, and draft reminder advice. The complete challenge scenario includes an automatic credit facility proposal, a human decision, and a simulated outcome. The steps below define the target the team will implement and verify.

## Liquidity Agent demo scope

1. The user uploads a bank CSV and enters an opening balance and start date. The app projects 14 end-of-day cash balances in the statement currency and identifies the first day below zero. When the start date is after the last transaction in the CSV, the app estimates recurring payments and typical daily movements from the earlier rows.
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

Edit the HTML, CSS, and JavaScript in `frontend/`, then refresh the browser. FastAPI serves these files directly in local development and in the OpenShift container.

The forecast uses the uploaded CSV in both modes. The built-in example uses the full Amalfi statement for 2025. The `demo` mode has a saved explanation for the shortfall fixture, and `live` calls OpenShift AI for explanations. See the [deployment guide](deploy/README.md).

For local configuration, copy `.env.example` to `.env` and add `--env-file .env` immediately after `uv run --locked`. The app starts in `demo` mode by default.

## Tech stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12+, FastAPI, Pydantic, Uvicorn, and `python-multipart` for CSV uploads. The container uses Python 3.12. |
| Frontend | HTML, CSS, and vanilla JavaScript in `frontend/`. FastAPI serves the UI and the browser calls the API with `fetch`. |
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

Start with **Check my cash** on the built-in Amalfi example. This uses the full 2025 statement, with EUR 33,266.35 as the opening balance on 1 January 2026. On the chart, recorded balances for 18–31 December appear before the forecast for 1–14 January. The estimates use recurring payments and recent average cash movements. For the separate known-payment example below, use the [26-row Amalfi CSV](demo/pizzeria_amalfi_sample.csv).

1. Upload the 26-row sample, enter EUR 5,000 and choose 22 June 2025. The first shortfall is EUR 6,250 on 28 June. The suggested limit covers the deepest gap of EUR 8,248.91 on 3 July.
2. Preview both credit decisions. Approval covers the full gap, and rejection leaves EUR 8,248.91 uncovered.
3. Move TX-0005 to 27 June in the earlier-payment scenario. The first shortfall falls to EUR 2,088.36. The original forecast is still available for comparison.
4. Check [the no-shortfall fixture](demo/no_shortfall_case.csv) and verify that no credit facility is proposed.

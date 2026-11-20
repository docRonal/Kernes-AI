# Autonomous CFO

A starter project for the Red Hat challenge at Collabothon. A small-business owner uploads upcoming payments, sees when their cash balance could fall below zero, and checks what changes if a customer pays earlier.

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run this command from the repository root.

```sh
uv run --locked uvicorn backend.main:app --host 127.0.0.1 --port 8080
```

Open the [app](http://127.0.0.1:8080) or the [Swagger UI](http://127.0.0.1:8080/docs). Run the tests in a separate terminal.

```sh
uv run --locked pytest -q
```

In `demo` mode, the app accepts [demo/transactions.csv](demo/transactions.csv) and returns a saved response. The starter includes two forecast outcomes and a sample model response. The `live` mode has entry points for forecasting from any valid CSV and calling OpenShift AI. See the [deployment guide](deploy/README.md).

For local configuration, copy `.env.example` to `.env` and add `--env-file .env` immediately after `uv run --locked`. The app starts in `demo` mode by default.

## Tech stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12+, FastAPI, Pydantic, Uvicorn, and `python-multipart` for CSV uploads. The container uses Python 3.12. |
| Frontend | HTML, CSS, and vanilla JavaScript. FastAPI serves the page and assets. The browser calls the API with `fetch`. |
| Forecast data | Python's `csv` module, integer grosz amounts, and in-memory request processing. Synthetic CSVs and example responses live in `demo/`. |
| AI inference | A model deployed on Red Hat OpenShift AI. Use Python's `urllib.request` for server-side JSON calls to the configured endpoint. Use the OpenShift AI model gateway (MaaS) if it is available for the bonus. |
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

1. Start your role branch from the latest `origin/main`. Open the repository root in your coding tool and use your role's starter prompt. On a shared laptop, use one Git worktree per branch.
2. Treat [the OpenAPI contract](contracts/openapi.json) and the examples in [demo/](demo/) as shared. Propose changes to the contract, dependency files, or shared fixtures in the PR and coordinate them with Mikhail and the affected owners.
3. Open a PR with what changed, the checks you ran, and anything another role needs to pick up. Mikhail coordinates reviews and merges. When a dependency merges, bring the latest `main` into your branch and rerun your checks.
4. Deploy the starter early while the frontend uses the saved HTTP responses and the backend and AI owners build their implementations. Switch the deployed app to `live` after the real forecast and model call are integrated. Yuri runs the end-to-end demo check on that same deployment.

To start a branch from a personal clone, use the branch name from the table. For example:

```sh
git fetch origin
git switch -c feat/backend origin/main
```

## Instructions and subagents

All role sessions use the shared rules in [AGENTS.md](AGENTS.md). [CLAUDE.md](CLAUDE.md) imports the same file for Claude Code. Open the root of the relevant clone or worktree in each tool.

- `forecast-reviewer` checks the calculations, input validation, and payment-date scenario.
- `integration-reviewer` checks how the UI, API, and OpenShift fit together.

The configurations are in `.codex/agents/`, `.claude/agents/`, and `.agents/agents/`, respectively. In Codex and Antigravity App or CLI, ask the primary agent to delegate the review by name and pass the list of changed files. In Claude Code, mention `@agent-forecast-reviewer` or `@agent-integration-reviewer`. If your installed version does not show a subagent, give the primary agent the [review checklists](agents/reviewer.md). [Codex](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents) · [Claude Code](https://code.claude.com/docs/en/sub-agents#invoke-subagents-explicitly) · [Antigravity](https://antigravity.google/docs/subagents#custom-subagents)

## Verify before the demo

1. Open the OpenShift app URL. Upload the sample CSV, enter PLN 12,000 as the opening balance, and set the start date to November 23, 2026.
2. Verify that the balance on Friday, November 27, is **−PLN 5,000**.
3. Move payment `INV-001` to November 26. Verify that the new Friday balance is **PLN 4,000** and the baseline still shows the original balance.
4. Request a shortfall explanation. Verify that the OpenShift AI model handles the request and returns an explanation and a draft email.

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

## Team branches

Clone the team repository and create a branch from `main` for each contributor. Use the first prompt in the corresponding role file.

| Tool | Branch | First prompt |
| --- | --- | --- |
| Claude Code | `feat/backend` | [Cash flow forecast and API](agents/backend.md) |
| Antigravity | `feat/frontend` | [UI and browser checks](agents/frontend.md) |
| Codex | `feat/openshift` | [Model client, container, and cluster](agents/openshift.md) |

On separate laptops, each contributor works in their own clone. On a shared computer, open each agent in its own Git worktree. Run these commands from the main clone.

```sh
git fetch origin
git worktree add ../cfo-backend -b feat/backend origin/main
git worktree add ../cfo-frontend -b feat/frontend origin/main
git worktree add ../cfo-openshift -b feat/openshift origin/main
```

Assign one person to coordinate integration. They review changes to `contracts/openapi.json`, look after shared dependencies, and verify the final `main`. Each contributor opens a PR with their changes and local test results. Update your branch from `main` before the final check.

## Instructions and subagents

All three primary agents use the shared rules in [AGENTS.md](AGENTS.md). [CLAUDE.md](CLAUDE.md) imports the same file. Open the root of the relevant clone or worktree in each tool.

- `forecast-reviewer` checks the calculations, input validation, and payment-date scenario.
- `integration-reviewer` checks how the UI, API, and OpenShift fit together.

The configurations are in `.codex/agents/`, `.claude/agents/`, and `.agents/agents/`, respectively. In Codex and Antigravity App or CLI, ask the primary agent to delegate the review by name and pass the list of changed files. In Claude Code, mention `@agent-forecast-reviewer` or `@agent-integration-reviewer`. If your installed version does not show a subagent, give the primary agent the [review checklists](agents/reviewer.md). [Codex](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents) · [Claude Code](https://code.claude.com/docs/en/sub-agents#invoke-subagents-explicitly) · [Antigravity](https://antigravity.google/docs/subagents#custom-subagents)

## Verify before the demo

1. Open the OpenShift app URL. Upload the sample CSV, enter PLN 12,000 as the opening balance, and set the start date to November 23, 2026.
2. Verify that the balance on Friday, November 27, is **−PLN 5,000**.
3. Move payment `INV-001` to November 26. Verify that the new Friday balance is **PLN 4,000** and the baseline still shows the original balance.
4. Request a shortfall explanation. Verify that the OpenShift AI model handles the request and returns an explanation and a draft email.

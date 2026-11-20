# Autonomous CFO

Help small-business owners spot cash shortfalls early, compare payment dates, and draft a payment reminder. The final demo runs on Red Hat OpenShift and calls a model on OpenShift AI.

## Shared files

- [README.md](README.md) defines the tech stack, role owners, branches, and integration workflow.
- [contracts/openapi.json](contracts/openapi.json) defines the API. [demo/](demo/) contains synthetic CSV data and sample responses for frontend development.
- Each role has a folder in [agents/](agents/) with its scope and starter prompt. Read your role guide before editing. Review subagents use [agents/reviewer.md](agents/reviewer.md).

## Working in parallel

- Work from the repository root on your assigned branch. Edit the files listed in your assignment. Coordinate changes to the API contract, shared dependencies, and files owned by another role with the person merging PRs.
- Start new tasks from the latest `main`. Before integration, update your branch from `main`, run the tests, and review the diff. Start a fresh agent session after shared instructions change.
- In your PR, summarize what changed, list the checks that passed, and identify any checks that still need cluster access. Merge PRs one at a time so `main` stays runnable.
- Use synthetic data. Store model tokens in environment variables or an OpenShift Secret. Keep tokens out of Git, agent prompts, and logs.

## API contract and verification

- Calculate balances in Python using integer grosz amounts. The model explains the calculated risk and drafts a reminder. Display amounts with two decimal places. The user decides whether to send the reminder and sends it themselves.
- Use separate requests for forecasts and advice. Keep the forecast available if the model call fails. The `demo` mode uses sample responses for local development. The `live` mode requires a working forecast and model client.
- The sample starts on November 23, 2026, with PLN 12,000. The first shortfall is PLN 5,000 on November 27. Move `INV-001` to November 26 and the projected Friday balance becomes PLN 4,000. The baseline keeps its original values.
- Before the demo, repeat the sample flow at the OpenShift URL and verify that the live OpenShift AI model responds.

# Autonomous CFO

Build the Liquidity Agent scenario in [README.md](README.md). The user sees an automatic, explainable credit facility proposal for a projected shortfall, approves or rejects it, and sees a simulated outcome. Keep the payment-date comparison and draft reminder. Run the complete demo in the assigned OpenShift AI environment using an open-source or open-weight model served there. The current scaffold is the starting point.

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

- Calculate balances in Python using integer grosz amounts. For a baseline shortfall, propose the limit that covers the deepest projected gap. The model explains the calculated proposal using forecast figures and transaction facts. Display amounts with two decimal places. Human approval or rejection drives a simulation only. The reminder remains an editable draft that the user sends themselves.
- Agree on the extension to the existing API contract and sample responses through one PR with all affected owners before wiring the new behavior across components.
- Use separate requests for forecasts and advice. Keep the forecast available if the model call fails. The `demo` mode uses sample responses for local development. The `live` mode requires a working forecast and model client.
- The sample starts on November 23, 2026, with PLN 12,000. The first shortfall is PLN 5,000 on November 27. Move `INV-001` to November 26 and the projected Friday balance becomes PLN 4,000. The baseline keeps its original values.
- Before the demo, verify at least two synthetic cases on the deployed app. Verify the automatic proposal, both simulation decisions, the payment-date comparison, and the live explanation from the model served on OpenShift AI.

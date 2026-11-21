# Autonomous CFO

Build and maintain the **KERNES CFO** Liquidity Agent in [README.md](README.md). The user sees an immediate, plain-English Action Plan (`POST /api/action-plan`), an automatic credit facility proposal for a projected shortfall, simulation-only Approve/Reject controls, payment-date comparison, editable B2B email drafts, and collapsible Advanced CFO tools. Run the complete demo on Red Hat OpenShift AI using `kernes-qwen-7b` (vLLM GPU) with `kernes-qwen` (CPU) fallback.

## Shared files

- [README.md](README.md) holds the Collabothon 2026 Project Card submission answers, tech stack, demo cases, and team roster (**Mikhail**, **Andrii**, **Tsimur**, **Ivan**, **Yurii**). Do **not** add a `LICENSE` file.
- [contracts/openapi.json](contracts/openapi.json) defines the API. [demo/qa_cases.json](demo/qa_cases.json) and [demo/](demo/) hold the canonical semicolon-delimited MT940-style CSV fixtures and sample responses.
- [docs/CHAT_FIRST_STRATEGY.md](docs/CHAT_FIRST_STRATEGY.md) and [docs/DEMO_SCRIPT_5MIN.md](docs/DEMO_SCRIPT_5MIN.md) document the current product scope and 5-minute live demo flow.
- Each role has a folder in [agents/](agents/) with its scope and starter prompt. Review subagents use [agents/reviewer.md](agents/reviewer.md).

## Working in parallel

- Work from the repository root on your assigned feature branch. Merge into `main` **strictly via Pull Request** — never push directly or force-push to `main`.
- Start new tasks from the latest `main`. Before integration, update your branch from `main`, run `uv run --locked pytest -q`, and review the diff.
- In your PR, summarize what changed, list the checks that passed, and note any checks requiring cluster access.
- Use synthetic data only. Store model tokens in environment variables or an OpenShift Secret (`CFO_MODEL_TOKEN`). Keep tokens out of Git, agent prompts, and logs.

## API contract and verification

- Calculate all balances in Python using integer minor units (`EUR`, `PLN`, `USD`, `CHF`, `GBP` cents/grosz). For a baseline shortfall, propose `max(0, -min(projected_balances))`. The LLM (`kernes-qwen-7b` primary, `kernes-qwen` fallback) explains verified backend facts guarded by `cited_amounts()`. Human approval or rejection drives a simulation only; reminder drafts stay editable and are never sent automatically.
- Use separate requests for forecasts, action plans, and insights. Keep deterministic forecast and proposal figures visible if any model call fails (HTTP 503).
- Canonical demo case (`demo/pizzeria_amalfi_sample.csv`): starts on `2025-06-22` with `EUR 5,000.00` (known-payments scenario; separate from the reconstructed full-statement balance `−EUR 8,848.69` evaluated in PR #17), first shortfall `−EUR 6,250.00` on `2025-06-28`, deepest shortfall `−EUR 8,248.91` on `2025-07-03`. Also verify `demo/credit_peak_case.csv` and `demo/no_shortfall_case.csv` from [demo/qa_cases.json](demo/qa_cases.json).
- Never recommend emailing walk-in retail card customers (`retail_non_contactable`) or deferring mandatory taxes, social security, or staff payroll (`fixed_mandatory`) — rely on `classify_transaction()` in `backend/forecast.py`.

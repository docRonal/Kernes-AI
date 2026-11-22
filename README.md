# KERNES CFO — Autonomous Liquidity Assistant for SMEs

> **Collabothon 2026 — Red Hat & Commerzbank Challenge: Autonomous CFO (Liquidity Agent)**

---

## Project Name

**KERNES CFO — Autonomous Liquidity Assistant for SMEs**

## One-Line Summary

An AI CFO on Red Hat OpenShift AI that forecasts an SME's cash 14 days ahead from its own bank statement and turns shortfalls into plain-English plans, credit simulations and email drafts.

## Technology Stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, Uvicorn, `python-multipart` (deterministic integer minor-unit arithmetic across 12 supported currencies including `EUR`, `PLN`, `USD`, `CHF`, `GBP`)
- **Frontend:** HTML5, CSS3 (Bento, 5-Tab Workspace & Progressive Disclosure UI), Vanilla ES Modules JavaScript, interactive SVG cash-flow & dual donut charts
- **AI & Inference:** Open-weight **Qwen2.5 7B Instruct** (`kernes-qwen-7b`) served via **vLLM** on Red Hat OpenShift AI (**NVIDIA L4 GPU**), with automatic fallback to **Qwen2.5 1.5B Instruct** (`kernes-qwen`, `llama.cpp` CPU)
- **Platform & OpenShift Bonus Paths:** Red Hat OpenShift Container Platform & OpenShift AI (`Containerfile`, KServe `InferenceService`, Deployment, Service, HTTPS Route, Secrets), **vLLM** GPU serving, **Model Context Protocol (MCP)** JSON-RPC 2.0 server (`POST /mcp`, `GET /api/mcp/tools`) exposing all 8 CFO tools, **Jupyter Notebooks on OpenShift AI** ([evaluate_liquidity_agent.ipynb](notebooks/evaluate_liquidity_agent.ipynb) + historical forecast validation in PR #17), optional **MLflow** latency & grounding telemetry
- **Testing & Workflow:** `uv` + `uv.lock`, `pytest` (220 automated tests across 12 suites + 5 Node.js CSV parser tests), rolling-origin backtest on the real 2025 statement (PR #17), GitHub Pull Request workflow

## Source Code Repository

- **GitHub Repository:** `https://github.com/docRonal/Kernes-AI`
- **Live OpenShift Deployment:** `https://autonomous-cfo-kernes-ai.apps.ocp.9hpps.sandbox580.opentlc.com`

---

## Project Overview

### THE PROBLEM

Small and medium-sized enterprises (SMEs) are often run by hands-on founders who have no dedicated Chief Financial Officer—for example, **Luigi**, a former pizzaiolo who opened *Pizzeria Amalfi* with a small starting capital. When rent, payroll, taxes, and wholesale supplier invoices hit in the same week before card payouts clear, SME owners discover cash shortfalls too late. Traditional financial dashboards overwhelm non-financial owners with raw tables and jargon instead of telling them in plain language what is happening and what to do next.

### YOUR SOLUTION

**KERNES CFO** pairs a **deterministic Python liquidity engine** with a **grounded open-weight LLM (`kernes-qwen-7b`)** inside a **Progressive Disclosure UI** built for *"Innovations for all generations"*:

1. **Simple Guided Entry:** Two quick context taps (*business type* + *main goal*) and a bank CSV upload (or one-click *Pizzeria Amalfi* demo) produce an immediate, jargon-free diagnosis and a 2–4 step **AI Action Plan** (`POST /api/action-plan`) tailored to either **Survival Mode** (closing a cash gap) or **Growth Mode** (safe reinvestment buffer).
2. **Full-Year Pattern Forecast & AI Intelligence:** Upload a bank statement and the engine analyzes up to a full year of history—splitting distinct streams per counterparty (e.g., monthly wage tax vs. quarterly tax), detecting exact/delayed monthly, quarterly, biweekly, and weekday schedules with realistic empirical variation (`backend/history_forecast.py`)—while `POST /api/forecast-analysis` pairs full-year trend, seasonality, closure-month, and payment-delay analytics with grounded AI commentary (`Forecast Intelligence`) directly beneath the chart.
3. **Counterparty-Aware Outreach:** A deterministic **Transaction & Counterparty Classifier** (`classify_transaction()`) inspects `Transaction Type`, `Beneficiary/Payer`, and `Payment Reference` so walk-in card customers (`retail_non_contactable`) and mandatory taxes, social security, or staff payroll (`fixed_mandatory`) are **never** suggested as deferral/email targets—only real B2B clients (`email_collect_early`) or B2B suppliers/landlord (`email_defer_supplier`) receive polite, editable email drafts.
4. **Strict 4-Level Autonomy Boundaries:** Every card and action in the UI explicitly distinguishes:
   - `1 · Analyzed by agent` (14-day forecast, full-year pattern & delay scan, shortfall detection, anomaly scan, stress test, cash health score)
   - `2 · Agent recommends` (peak-gap safety buffer, actionable payment timing moves, financing comparison)
   - `3 · Your decision needed` (human Approve / Reject credit buffer preview, editable email drafts)
   - `4 · Simulation only — nothing sent` (zero real bank transfers, loan applications, or emails)
5. **Clean 4-Tab Workspace & Progressive Disclosure:** A glanceable **Signal Strip** and **Active Simulations** bar sit above four focused workspaces (*Overview & Cash*, *Fix & Decide*, *What-If & AI Chat*, *Health & Audit*, plus *Show all sections* and printable *Export brief*), keeping deep CFO tools (*Planned Purchase Sandbox*, *What-If Q&A* with AI-suggested questions, *Client-Pays-Late Predictor*, *Compare Financing Options*, *Cash Health Score & Stress Test*, *Smart Payment Moves*, *Anomaly Detector*) one click away without overwhelming non-financial owners.

**Proposed Business Model (B2B2C Embedded Banking + Freemium Pro):**
- **Layer 1 — White-Label Embedded Banking (Commerzbank):** Offered free inside the bank's SME portal to reduce SME cash-flow defaults and generate high-intent, pre-qualified credit-line and factoring leads at the exact moment a temporary cash dip is detected.
- **Layer 2 — Optional Pro Tier (€19–€49/month):** Unlocks multi-currency branch forecasting, automated PSD2/bank-feed sync, custom stress scenarios, and recurring accountant-ready exports.

### THE WORKING PROTOTYPE

**Implemented & Live on OpenShift AI today:**
- **Multi-currency MT940-style semicolon CSV parser & classifier** (12 currencies including `EUR`, `PLN`, `USD`, `CHF`, `GBP`) with strict HTTP 422 validation.
- **14-day integer minor-unit cash forecast** (`POST /api/forecast`) identifying first shortfall, deepest shortfall, and what-if payment-date shifts without mutating the baseline—built from known scheduled payments, or learned from full-year statement history (splitting counterparty streams, quarterly/monthly/weekday schedules, and empirical variation) when the forecast starts after the statement's last day.
- **One-click real-data demo:** the organizers' full 2025 Pizzeria Amalfi statement (1,125 rows across 365 days) forecasts 1–14 January 2026 from the `EUR 33,266.35` year-end balance: lowest projected balance `EUR 28,965.00`, with `EUR 23,754.98` still above zero after the stress test (Growth Mode).
- **Peak-gap credit facility proposal & simulation** (`POST /api/decision` — `Approve preview` reduces uncovered gap to `0.00`; `Reject preview` preserves the baseline gap).
- **Grounded AI Action Plan, Forecast Intelligence & Briefing** (`POST /api/action-plan` with dynamic AI `suggested_questions`, `POST /api/forecast-analysis` for full-year trend/seasonality/delay commentary, `POST /api/advice`) running on OpenShift AI (`kernes-qwen-7b` GPU primary + `kernes-qwen` CPU fallback) with HTTP 503 / graceful deterministic fallback resilience.
- **Full Interactive CFO Suite:** Unified SVG chart (`Recorded balance` → `Projected +14d` with post-divider Stress Test / What-If / Purchase / Early-Pay overlays), **Dual Income/Expense Donut Charts**, **Smart Cash Calendar**, **"Can I Afford It?" Planned Purchase Sandbox**, **What-If Q&A** (`POST /api/ask-cfo`), **Client-Pays-Late Predictor** (`POST /api/predict-delays`), **Compare Financing Options** (`POST /api/compare-options`), **Cash Health Score** (`POST /api/credit-check`), **Stress Test** (`POST /api/stress-test`), **Smart Payment Moves** (`POST /api/optimize-payments`), and **Anomaly Detector** (`POST /api/detect-anomalies`).
- **Full 4-Agent Autonomous CFO Suite (`CFO Agents & MCP` tab):** Covers all 4 Challenge Card agents — **Liquidity Agent** (14-day forecast + above suite), **FX Hedging Agent** (`POST /api/fx-hedging` — cross-border exposure & ±5% shock hedging), **Tax & Reserve Agent** (`POST /api/tax-agent` — tax obligations, quarterly VAT/advance reserve & deductible expense totals), and **Investment & Capex Agent** (`POST /api/investments` — Liquidity-First protection during shortfalls or Festgeld / Money Market yield optimization during surplus), orchestrated via `POST /api/multi-agent`.
- **MCP (Model Context Protocol) Tool Server (Red Hat Bonus):** Standard JSON-RPC 2.0 MCP endpoint (`POST /mcp`) and REST discovery manifest (`GET /api/mcp/tools`) exposing all 8 deterministic CFO tools with Pydantic JSON Schemas and 4-level autonomy annotations, plus an interactive **MCP Tool Inspector** inside the dashboard.

**Simulated by Design (Zero Real Execution):**
- Credit facility approval/rejection and payment reminder sending (`POST /api/send-reminder`) are 100% simulated.
- **Demo Scenario Framing:** Besides the January forecast learned from history, the survival scenario (`demo/pizzeria_amalfi_sample.csv`) starts with `EUR 5,000.00` on `2025-06-22` as a **scenario with known/scheduled payments** (dropping to `−EUR 6,250.00` on `2025-06-28` and peaking at `−EUR 8,248.91` on `2025-07-03`). The reconstructed real balance on `2025-06-22` was `−EUR 8,848.69`, so this opening balance is a stated scenario assumption.

### BEHIND THE BUILD

- **Single-Container Deployment:** FastAPI serves both the REST API and the static `frontend/` bundle from one container (`Containerfile`) behind an OpenShift Deployment, Service, and HTTPS Route.
- **Deterministic Math vs. LLM Narrative:** All monetary totals, dates, anomalies, stress cushions, and action rankings are computed deterministically in Python using integer minor units. The LLM never calculates money—it only translates verified backend facts into plain-English explanations and polite B2B emails.
- **Anti-Hallucination Grounding (`cited_amounts()`):** Every monetary token produced by the LLM is validated against exact boundary-matched backend numbers before reaching the user, retrying once and falling back cleanly if validation fails.
- **Security & Telemetry:** API tokens live strictly in OpenShift Secrets (`CFO_MODEL_TOKEN`); logs record model name, attempt count, and latency without ever logging prompts, PII, or credentials.

### CHALLENGES AND DISCOVERIES

1. **Eliminating LLM Numeric Hallucinations & Substring False Positives:** Early grounding checks matched `'200'` inside `'1,200.00'`. We replaced substring checks with regex numeric-boundary matching (`_matches_amount_token`) and added dual-model fallback (`kernes-qwen-7b` GPU → `kernes-qwen` CPU).
2. **Pivoting from Telemetry Overload to Guided Workspaces:** Mid-hackathon mentor feedback highlighted that non-financial SME owners like Luigi get lost in dense analytics. We restructured the experience around a 2-question setup + `POST /api/action-plan` + counterparty classifier + 4 focused workspaces (*Overview & Cash*, *Fix & Decide*, *What-If & AI Chat*, *Health & Audit*) with an **Active Simulations** toggle bar.
3. **Preventing Impossible AI Suggestions:** Generic payment-move optimizers initially risked suggesting emailing walk-in card customers or delaying mandatory taxes/payroll. Adding deterministic `classify_transaction()` rules fixed this at the source.
4. **From Replaying Known Payments to Full-Year Pattern Forecasting:** Backtesting on the full 2025 Pizzeria Amalfi statement (rolling-origin cross-validation, PR #17) showed that a forecast built from rows inside the window only replays the future it is given. We built a history-only forecaster (`backend/history_forecast.py`) that splits distinct streams per counterparty (separating monthly and quarterly tax bills), detects exact/delayed monthly, quarterly, biweekly, and weekday schedules with empirical variation, and powers the grounded `POST /api/forecast-analysis` readout. With at least 3 months of history, rolling-origin evaluation caught every real 14-day shortfall across 38 weekly windows with no false alarms, cutting mean daily balance error to `EUR 1,267` from about `EUR 3,850` for naive flat or average forecasts. One-off events such as the June closure cannot be learned from history.

### RESULTS AND NEXT STEPS

- **Results Achieved:** Live end-to-end deployment on Red Hat OpenShift AI (`kernes-qwen-7b` on NVIDIA L4 GPU + `kernes-qwen` fallback), all 4 Autonomous CFO Challenge Card agents (Liquidity, FX Hedging, Tax, Investment) + standard MCP JSON-RPC 2.0 server (`POST /mcp`, `GET /api/mcp/tools`), 220 automated `pytest` tests across 12 suites (+ 5 Node.js CSV tests) covering math, CSV validation, counterparty classification, full-year pattern & AI forecast analysis, action plans, grounding, backtesting (PR #17), and error paths, plus a Jupyter evaluation notebook ([evaluate_liquidity_agent.ipynb](notebooks/evaluate_liquidity_agent.ipynb)).
- **Current Limitations:** Uses uploaded CSV exports rather than live PSD2 bank feeds; the free-text `/api/ask-cfo` chat shifts or scales existing scheduled transactions (new capex items are simulated via the dedicated *Can I Afford It?* Purchase Sandbox rather than free-text chat); all banking actions are simulated.
- **Next Steps:** Connect Commerzbank / PSD2 APIs for real-time account sync, let owners add planned multi-day closures/holidays on top of the learned forecast, unify free-text What-If chat with the Purchase Sandbox for ad-hoc capex queries, and connect the MCP server directly to external IDE / Red Hat OpenShift AI agent orchestrators.

---

## Run Locally & Verify

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run from the repository root:

```sh
uv run --locked uvicorn backend.main:app --host 127.0.0.1 --port 8080
```

Open the [app](http://127.0.0.1:8080) or [Swagger UI](http://127.0.0.1:8080/docs). Run the automated test suite:

```sh
uv run --locked pytest -q
```

For `live` mode against a local or OpenShift model endpoint, copy `.env.example` to `.env` and pass `--env-file .env` immediately after `uv run --locked`. See [deploy/README.md](deploy/README.md) for OpenShift AI deployment instructions.

### Canonical Demo & Verification Cases ([demo/qa_cases.json](demo/qa_cases.json))

1. **Pizzeria Amalfi (`demo/pizzeria_amalfi_sample.csv`):** Opening balance `EUR 5,000.00` on `2025-06-22` (known-payments scenario) → first shortfall `−EUR 6,250.00` on `2025-06-28`, peak shortfall `−EUR 8,248.91` on `2025-07-03`, proposed buffer `EUR 8,248.91`.
2. **Peak Shortfall (`demo/credit_peak_case.csv`):** Opening balance `EUR 1,000.00` on `2026-11-23` → first shortfall `−EUR 200.00` (`2026-11-24`), deepens to `−EUR 700.00` (`2026-11-26`) before `EUR 1,000.00` B2B invoice arrives (`2026-11-29`).
3. **Healthy Surplus (`demo/no_shortfall_case.csv`):** Opening balance `EUR 15,000.00` on `2026-11-23` → stays positive across all 14 days (triggers Growth Mode checklist).
4. **Multi-Currency & Stress Cases (`demo/stress_cases/`):** Includes `PLN` branch, mixed FX, duplicate-payment anomaly, and invalid-CSV HTTP 422 cases.

---

## Team & Workflow

| Owner | Tool | Role | Branch |
| --- | --- | --- | --- |
| Mikhail | Codex | [Deployment & Integration](agents/deployment/README.md) | `feat/openshift` |
| Andrii | Claude Code | [Cash Flow Backend](agents/backend/README.md) | `feat/backend` |
| Tsimur | Antigravity | [Frontend & UX](agents/frontend/README.md) | `feat/frontend` |
| Ivan | Antigravity | [AI Model Integration](agents/ai-integration/README.md) | `feat/advice` |
| Yurii | Antigravity | [QA, Demo & Evaluation](agents/qa/README.md) | `feat/qa-demo` |

- **Git Discipline:** Merge all changes into `main` **strictly via Pull Request**; never force-push to `main`.
- **Key Docs:** [5-Minute Live Demo Script](docs/DEMO_SCRIPT_5MIN.md) · [Shared Agent Rules](AGENTS.md) · [OpenAPI Contract](contracts/openapi.json) · [OpenShift Deploy Guide](deploy/README.md) · [Chat-First Strategy](docs/CHAT_FIRST_STRATEGY.md)

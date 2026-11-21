# Hackathon Requirements (Reference Folder)

> Reference folder so the team can inspect the official Collabothon 2026 Red Hat Autonomous CFO Challenge specification and submission card directly inside the repository.

## Included Files

- [Challenge Card - Autonomous CFO.pdf](Challenge%20Card%20-%20Autonomous%20CFO.pdf) — Official Red Hat & Commerzbank challenge specification, autonomy boundaries, OpenShift AI deployment mandate, and optional bonus challenges.
- [Collabothon_2026_Project_Card_Fillable 1.pdf](Collabothon_2026_Project_Card_Fillable%201.pdf) — Collabothon 2026 Project Card template (`Project Name`, `One-Line Summary` <= 200 chars, `Technology Stack`, `Project Overview`, `Source Code Repository`).

> **Official Discord Submission Rules:** Do **not** submit the fillable PDF separately — put all Project Card answers directly in the root [README.md](../README.md), and do **not** add any `LICENSE` file to the repository.

## Key Requirements Summary

1. **End-to-End Use Case (Liquidity Agent)**: Bank CSV input → 14-day cash flow forecast → automatic credit facility proposal → explainable reasoning & plain-English Action Plan via Open Source / Open Weights LLM (`Qwen2.5 7B Instruct` via vLLM on GPU, with `Qwen2.5 1.5B Instruct` CPU fallback) → human approval/rejection simulation.
2. **4 Autonomy Boundaries** (explicitly differentiated in UI & live demo):
   - `1 · Analyzed by agent` (forecast, shortfall detection, anomalies, stress test, cash health score)
   - `2 · Agent recommends` (credit buffer size, actionable B2B payment moves, financing options)
   - `3 · Your decision needed` (Approve/Reject buffer preview, editable email drafts)
   - `4 · Simulation only — nothing sent` (100% simulation only)
3. **OpenShift AI Mandate**: Deploy and run the full solution (FastAPI app + agent logic + open-weight models) on Red Hat OpenShift AI.
4. **Bonus Paths Implemented**: **vLLM** GPU serving (`deploy/model-gpu.yaml`), **Jupyter Notebooks on OpenShift AI** ([../notebooks/evaluate_liquidity_agent.ipynb](../notebooks/evaluate_liquidity_agent.ipynb) + historical forecast evaluation in PR #17), optional **MLflow** latency & grounding telemetry.

## Canonical Sample Data

- All backend and `demo/` fixtures use semicolon-delimited MT940-style bank statements (`"Account Number";"Booking Date";"Value Date";"Transaction Type";"Payment Reference";"Beneficiary/Payer";...;"Amount";"Currency";"Info"`) supporting multi-currency integer minor units (`EUR`, `PLN`, `USD`, `CHF`, `GBP`).
- Canonical demo fixtures live in [../demo/qa_cases.json](../demo/qa_cases.json) (`pizzeria_amalfi_sample.csv`, `credit_peak_case.csv`, `no_shortfall_case.csv`) plus stress cases in [../demo/stress_cases/](../demo/stress_cases/).
- Source Red Hat materials remain in [../red-hat-examples/](../red-hat-examples/).

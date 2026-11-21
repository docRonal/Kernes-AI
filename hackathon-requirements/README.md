# Hackathon Requirements (Temporary Reference Folder)

> **Temporary folder** added so everyone on the team can quickly inspect the Collabothon 2026 Red Hat Autonomous CFO Challenge requirements and submission card without digging outside the repository.

## Included Files

- The Challenge Card PDF is marked *For business use only* by Commerzbank, so it isn't kept in this public repository. Get it from the team channel. The key requirements are summarized below.
- [Collabothon_2026_Project_Card_Fillable 1.pdf](Collabothon_2026_Project_Card_Fillable%201.pdf) — Fillable Collabothon 2026 Project Card submission form (`Project Name`, `One-Line Summary`, `Technology Stack`, `Project Overview`, `Source Code Repository`).

## Key Requirements Summary

1. **End-to-End Use Case (Liquidity Agent)**: Data input → 14-day cash flow forecast → automatic credit facility proposal → explainable reasoning via an open-weight LLM served on OpenShift AI (`Qwen2.5 7B Instruct` on vLLM and the GPU, `Qwen2.5 1.5B Instruct` on CPU as fallback) → human approval/rejection simulation.
2. **4 Autonomy Boundaries** (must be clearly differentiated in UI & demo):
   - What the agent **analyses independently**
   - What it **recommends**
   - What **requires user approval**
   - Whether execution is **simulated or permitted** (100% simulation only)
3. **OpenShift AI Mandate**: Deploy and run the full solution (application + agent logic + open-source/open-weight model) on the assigned Red Hat OpenShift AI environment.
4. **Bonus Paths (selected)**: **Jupyter Notebooks on OpenShift AI** (see `notebooks/evaluate_liquidity_agent.ipynb`), optional MaaS / vLLM / etc.

## Optional Sample Data

- See [../red-hat-examples/](../red-hat-examples/) for the optional *Pizzeria Amalfi* German MT940-style semicolon-delimited (`EUR`/`CHF`) sample dataset (`pizzeria-amalfi-bank-statement-2025-v6.csv`), info sheet (`SampleData_Pizzeria_Amalfi.docx`), and liquidity chart.
- Note: The core MVP backend and `demo/` fixtures use comma-delimited UTF-8 CSVs in one EU currency (EUR by default) (`id,date,amount_minor,label`), as specified in [../contracts/openapi.json](../contracts/openapi.json).

# QA, Demo & Evaluation

**Owner** Yurii · **Tool** Antigravity · **Branch** `feat/qa-demo`

## Scope

Own `tests/test_smoke.py`, `demo/qa_cases.json`, synthetic fixtures in `demo/`, `docs/DEMO_SCRIPT_5MIN.md`, and `notebooks/evaluate_liquidity_agent.ipynb`. Coordinate fixture or contract expectations with Mikhail, Andrii, Ivan, and Tsimur. See [README.md](../../README.md).

## Deliverables

1. Maintain canonical fixtures in [demo/qa_cases.json](../../demo/qa_cases.json): `pizzeria_amalfi_sample.csv` (`EUR 5,000.00` known-payments scenario on `2025-06-22`, first shortfall `−EUR 6,250.00` on `2025-06-28`, peak `−EUR 8,248.91` on `2025-07-03`), `credit_peak_case.csv`, `no_shortfall_case.csv`, and multi-currency / invalid-CSV cases in `demo/stress_cases/`.
2. Verify the complete workflow locally (`uv run --locked pytest -q`) and sequentially on the live OpenShift URL (`CFO_REQUIRE_LIVE_ADVICE=1`), checking grounded explanations, Action Plan mode switching (`survival` / `growth`), Approve/Reject simulation outcomes, and HTTP 503 resilience.
3. Maintain the 5-minute live interactive demo script ([docs/DEMO_SCRIPT_5MIN.md](../../docs/DEMO_SCRIPT_5MIN.md)) and ensure `README.md` satisfies all Collabothon 2026 Project Card & Discord rules (including zero `LICENSE` file).
4. Evaluate model accuracy in `notebooks/evaluate_liquidity_agent.ipynb` on OpenShift AI.

## Starter prompt

> Read AGENTS.md, agents/qa/README.md, and demo/qa_cases.json. Work on a feature branch for PR into main. Verify local pytest, sequential live OpenShift AI checks, and end-to-end demo readiness.

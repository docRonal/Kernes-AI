# AI Model Integration

**Owner** Ivan · **Tool** Antigravity · **Branch** `feat/advice`

## Scope

Own `backend/advice.py`, `backend/action_plan.py`, `backend/consultant.py`, `backend/telemetry.py`, and their tests (`tests/test_advice.py`, `tests/test_action_plan.py`, `tests/test_telemetry.py`). Follow [contracts/openapi.json](../../contracts/openapi.json) and coordinate shared schema changes with Andrii, Tsimur, Mikhail, and Yurii via PR. See [README.md](../../README.md).

## Deliverables

1. Integrate with OpenShift AI endpoints configured by Mikhail: `kernes-qwen-7b` (vLLM GPU primary) with automatic fallback to `kernes-qwen` (CPU).
2. Ground all LLM outputs (`POST /api/advice`, `POST /api/action-plan`, `POST /api/ask-cfo`, `POST /api/predict-delays`, `POST /api/credit-check`, `POST /api/detect-anomalies`, `POST /api/compare-options`) in verified backend calculations using `cited_amounts()` with numeric-boundary matching (`_matches_amount_token`). Keep all monetary calculations and simulation decisions in Python.
3. Support both B2B email draft kinds (`collect_early` for B2B clients before deadline and `defer_supplier` for B2B suppliers/landlord), strictly excluding `retail_non_contactable` and `fixed_mandatory` transactions.
4. Keep `demo` mode deterministic responses runnable, return HTTP 503 cleanly when upstream models fail (so the UI preserves deterministic numbers), and log only telemetry metadata (never secrets or PII).

## Starter prompt

> Read AGENTS.md, agents/ai-integration/README.md, and contracts/openapi.json. Work on a feature branch for PR into main. Maintain grounded live explanations, POST /api/action-plan, and fallback handling on OpenShift AI. Keep credentials out of Git and logs.

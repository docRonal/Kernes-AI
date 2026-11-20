# QA, Demo & Evaluation

**Owner** Yuri · **Tool** Antigravity · **Branch** `feat/qa-demo`

## Scope

Own `tests/test_smoke.py`, the synthetic demo cases in `demo/`, and `notebooks/` if the team takes the notebook bonus. Coordinate fixture changes with everyone who uses them. See the [team workflow and tech stack](../../README.md).

## Deliverables

1. Prepare synthetic cases for a forecast with no shortfall, a forecast with a shortfall, and a payment moved earlier. Verify that the baseline remains available next to the adjusted result.
2. Test the complete flow locally and then at the deployed URL Mikhail shares. Verify the Friday balances of −PLN 5,000 and +PLN 4,000, the model explanation and editable draft, and the UI's behavior when advice is unavailable.
3. Prepare a two-minute demo that shows the shortfall, the changed payment date, and the live model output. Record the URL, commit SHA, checks passed, and remaining blockers.
4. For the Jupyter bonus, run a notebook in an OpenShift AI workbench against the synthetic cases. Check the model's stated shortfall amount and date against the expected values.

## Starter prompt

> Read AGENTS.md, agents/qa/README.md, and contracts/openapi.json. Work on feat/qa-demo. Prepare the synthetic cases, smoke checks, and demo steps. Report what passed locally, what passed on OpenShift, and any blockers.

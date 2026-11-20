# AI Model Integration

**Owner** Ivan · **Tool** Antigravity · **Branch** `feat/advice`

## Scope

Own `backend/advice.py` and `tests/test_advice.py`. Follow the [API contract](../../contracts/openapi.json) and coordinate changes to shared routes and models with Andrii. See the [team workflow and tech stack](../../README.md).

## Deliverables

1. Get the inference URL, model name, and authentication method from Mikhail. Verify one request against the team's OpenShift AI endpoint as soon as access is available. Use the model gateway if it is available and fits the bonus plan.
2. Implement the `live` advice call with a timeout and validate the model's response against the contract. Supply the already calculated shortfall and relevant transactions so the model can explain the numbers and draft a reminder.
3. Keep the saved advice response available in `demo` mode. Handle unavailable or invalid upstream responses with HTTP 503 and exercise the error paths in tests.
4. Share the configuration requirements with Mikhail, the response structure with Timur, and a test case for checking the model's figures with Yuri.

## Starter prompt

> Read AGENTS.md, agents/ai-integration/README.md, and contracts/openapi.json. Work on feat/advice. Implement and test the live model call in backend/advice.py. Report which endpoint path and response behavior you verified. Keep credentials out of the report.

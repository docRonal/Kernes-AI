# AI Model Integration

**Owner** Ivan · **Tool** Antigravity · **Branch** `feat/advice`

## Scope

Own `backend/advice.py` and `tests/test_advice.py`. Follow the [API contract](../../contracts/openapi.json) and coordinate changes to shared routes and models with Andrii. See the [team workflow and tech stack](../../README.md).

## Deliverables

1. Get the endpoint configuration, model name, and authentication method from Mikhail. Verify one request to the open-source or open-weight model served on the team's assigned OpenShift AI environment. Use MaaS if available and the team pursues the bonus.
2. Implement the `live` advice call with a timeout and validate the response against the agreed contract. Ground the facility explanation in the backend's recommended limit, first and deepest shortfall dates and amounts, and relevant transactions. Keep monetary calculations and simulation decisions in application code. Keep the existing reminder draft available on request.
3. Keep the saved advice response available in `demo` mode. Handle unavailable or invalid upstream responses with HTTP 503 and exercise the error paths in tests.
4. Coordinate the explanation request and response in Mikhail's shared contract PR. Share configuration requirements with Mikhail, response fields and error behavior with Timur, and synthetic cases for checking the model's figures with Yuri.

## Starter prompt

> Read AGENTS.md, agents/ai-integration/README.md, and contracts/openapi.json. Work on feat/advice. Implement and test live explanations grounded in the forecast and proposal facts. Report which model and response behavior you verified. Keep credentials out of the report.

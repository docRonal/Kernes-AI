# Model integration and OpenShift with Codex

Work on `feat/openshift`. Your files are `backend/advice.py`, the model client tests, `Containerfile`, `.dockerignore`, and `deploy/`. Discuss changes to dependencies and `backend/main.py` with the backend owner.

## Task

1. Get the full inference API URL, model name, authentication method, and available container registry from the team. Confirm the response format for that endpoint.
2. In `live` mode, call the model with a timeout. Pass the calculated shortfall and the relevant transactions. Request a brief explanation and an email draft. Validate the result against the contract. Return HTTP 503 when the model is unavailable.
3. Set up the build and verify the OpenShift Deployment, Service, Route, and health check. Pass `CFO_MODEL_URL`, `CFO_MODEL_NAME`, and `CFO_MODEL_TOKEN` if needed through environment variables. Store the token in a Secret.
4. Verify the starter container in `demo` mode first. After the forecast and model client are merged, verify `live` mode at the deployed URL. Share the URL and test results with the integration owner. Keep credentials private.

## Starter prompt

> Read AGENTS.md, agents/openshift.md, contracts/openapi.json, and deploy/README.md. Work on feat/openshift. Build the model client, then verify the build and deployment steps you can access. Ask integration-reviewer to review the changes if available. State whether you verified a call to the live model.

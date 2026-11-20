# Deployment & Integration

**Owner** Mikhail · **Tool** Codex · **Branch** `feat/openshift`

## Scope

Own `Containerfile`, `.dockerignore`, and `deploy/`. Coordinate changes to `contracts/openapi.json`, `pyproject.toml`, and `uv.lock` with the affected owners. See the [team workflow and tech stack](../../README.md) and the [deployment guide](../../deploy/README.md).

## Deliverables

1. Confirm cluster access, the team namespace, and an image registry. Deploy the starter in `demo` mode early and verify the HTTPS Route and `/health`.
2. Confirm an open-source or open-weight model is served in the team's assigned OpenShift AI environment. Share the model name and connection details with Ivan through the team's private channel. Set the model configuration for all live inference and keep any token in an OpenShift Secret. Check MaaS availability only if pursuing the bonus.
3. Coordinate one OpenAPI extension PR with Andrii, Timur, Ivan, and Yuri so the proposal, explanation, decision, and fixture expectations are agreed before integration. Merge team PRs into a runnable `main` and deploy the complete Liquidity Agent workflow in `live` mode on the assigned environment.
4. Give Yuri the deployed URL and commit SHA for the final smoke test. Verify the rollout and record the served model name, evidence of a live inference call, and which checks ran on OpenShift.

## Starter prompt

> Read AGENTS.md, agents/deployment/README.md, and deploy/README.md. Work on feat/openshift. Deploy the starter, verify its Route and health endpoint, and coordinate the contract PR and complete live rollout. Use integration-reviewer if available and report the deployment and model checks.

# Deployment & Integration

**Owner** Mikhail · **Tool** Codex · **Branch** `feat/openshift`

## Scope

Own `Containerfile`, `.dockerignore`, and `deploy/`. Coordinate changes to `contracts/openapi.json`, `pyproject.toml`, and `uv.lock` with the affected owners. See the [team workflow and tech stack](../../README.md) and the [deployment guide](../../deploy/README.md).

## Deliverables

1. Confirm cluster access, the team namespace, and an image registry. Deploy the starter in `demo` mode early and verify the HTTPS Route and `/health`.
2. Give Ivan the model endpoint, model name, and authentication method. Set up model settings in the deployment environment and keep any token in an OpenShift Secret.
3. Coordinate contract changes and merge team PRs into a runnable `main`. Once the forecast and model client are ready, deploy the merged version in `live` mode.
4. Give Yuri the deployed URL and commit SHA for the final smoke test. Verify the rollout and record which checks ran on OpenShift.

## Starter prompt

> Read AGENTS.md, agents/deployment/README.md, and deploy/README.md. Work on feat/openshift. Deploy the starter, verify its Route and health endpoint, and coordinate the live rollout with the other owners. Use integration-reviewer if available and report which checks passed.

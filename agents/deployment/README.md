# Deployment & Integration

**Owner** Mikhail · **Tool** Codex · **Branch** `feat/openshift`

## Scope

Own `Containerfile`, `.dockerignore`, and `deploy/` (`build-template.yaml`, `openshift-template.yaml`, `model.yaml`, `model-gpu.yaml`, `README.md`). Coordinate changes to `contracts/openapi.json`, `pyproject.toml`, and `uv.lock` with affected owners. See [README.md](../../README.md) and [deploy/README.md](../../deploy/README.md).

## Deliverables

1. Build and deploy `autonomous-cfo` in the `kernes-ai` OpenShift namespace, exposing the HTTPS Route and `/health` + `/health/ai`.
2. Serve `kernes-qwen-7b` (Qwen2.5 7B Instruct via vLLM on NVIDIA L4 GPU) as primary and `kernes-qwen` (Qwen2.5 1.5B Instruct CPU) as fallback, storing any `CFO_MODEL_TOKEN` / `MLFLOW_TRACKING_TOKEN` strictly in OpenShift Secrets.
3. Coordinate PR integration into `main` (PR-only, no force-push) and deploy the unified `live` build on OpenShift AI.
4. Provide Yurii with the deployed URL and commit SHA for end-to-end verification, and record model readiness, latency logs, and historical Jupyter validation evidence (PR #17).

## Starter prompt

> Read AGENTS.md, agents/deployment/README.md, and deploy/README.md. Work on a feature branch for PR into main. Verify OpenShift build, vLLM GPU + CPU fallback model serving, and live rollout telemetry.

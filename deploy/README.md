# Deploy to OpenShift

Use the team project `kernes-ai` on the assigned OpenShift cluster. Sign in with the team credentials through the OpenShift console or `oc login --web`. Use the cluster's API CA when the API uses a private signer. Keep the kubeconfig outside the repository.

## Build the app on OpenShift

From the repository root, push the Git commit you want to deploy, then build it in the cluster. The build reads `Containerfile` and writes a tagged image to the internal registry.

```sh
SOURCE_REF="$(git rev-parse HEAD)"
IMAGE_TAG="app-$(git rev-parse --short HEAD)"

oc process --local -f deploy/build-template.yaml \
  -p "SOURCE_REF=${SOURCE_REF}" -p "IMAGE_TAG=${IMAGE_TAG}" |
  oc -n kernes-ai apply -f -
oc -n kernes-ai start-build autonomous-cfo --follow
APP_IMAGE="$(oc -n kernes-ai get istag "autonomous-cfo:${IMAGE_TAG}" \
  -o jsonpath='{.image.dockerImageReference}')"
```

## Start the project model

The [model manifest](model.yaml) provides a namespaced KServe runtime and an internal inference service for Qwen2.5 1.5B Instruct. It uses a pinned GGUF revision and a pinned llama.cpp image on CPU. The cluster's existing GPU model stays available independently.

```sh
oc -n kernes-ai apply -f deploy/model.yaml
oc -n kernes-ai wait --for=condition=Ready inferenceservice/kernes-qwen --timeout=6m
```

The model service is internal. Configure the app with the full chat completions URL and the model alias.

```sh
CFO_MODEL_URL=http://kernes-qwen-predictor.kernes-ai.svc.cluster.local:8080/v1/chat/completions
CFO_MODEL_NAME=kernes-qwen
```

## Serve the main model with vLLM on the GPU

The live app uses our own Qwen2.5 7B Instruct, served by vLLM on the cluster's single NVIDIA L4 GPU. The [GPU manifest](model-gpu.yaml) pulls the model from Red Hat's modelcar catalog. The CPU Qwen2.5 1.5B above stays running as the fallback model. Stop any other GPU model first, because the cluster has one GPU. For example, stop the preinstalled Llama example in `my-first-model`.

```sh
oc -n my-first-model annotate inferenceservice llama-32-3b-instruct serving.kserve.io/stop=true --overwrite
oc -n kernes-ai apply -f deploy/model-gpu.yaml
oc -n kernes-ai wait --for=condition=Ready inferenceservice/kernes-qwen-7b --timeout=20m
```

Point the app at it and keep the CPU model as the fallback.

```sh
CFO_MODEL_URL=http://kernes-qwen-7b-predictor.kernes-ai.svc.cluster.local:8080/v1/chat/completions
CFO_MODEL_NAME=kernes-qwen-7b
CFO_FALLBACK_MODEL_URL=http://kernes-qwen-predictor.kernes-ai.svc.cluster.local:8080/v1/chat/completions
CFO_FALLBACK_MODEL_NAME=kernes-qwen
```

Both models appear under the `kernes-ai` project in the OpenShift AI dashboard.

## Start the app and verify it

The starter uses `demo` mode. It exercises the interface and sample data while the team builds the live forecast, model call, and approval simulation. The app exposes an HTTPS Route.

```sh
oc process --local -f deploy/openshift-template.yaml \
  -p "APP_IMAGE=${APP_IMAGE}" -p CFO_MODE=demo \
  -p "CFO_MODEL_URL=${CFO_MODEL_URL}" -p "CFO_MODEL_NAME=${CFO_MODEL_NAME}" |
  oc -n kernes-ai apply -f -
oc -n kernes-ai rollout status deployment/autonomous-cfo
oc -n kernes-ai get route autonomous-cfo -o jsonpath='{.spec.host}{"\n"}'
```

Check `/health`, then run the [browser demo](../README.md) with the synthetic CSV. The health check covers the app process. Verify inference separately in the cluster, then through the app once the live flow lands.

### Check the model inside the cluster

The model service is internal, so call it from a short-lived pod. The answer should name `kernes-qwen` and include a short reply.

```sh
oc -n kernes-ai run model-check --rm -i --restart=Never \
  --image=registry.access.redhat.com/ubi9/ubi-minimal -- \
  curl -sS -m 120 "${CFO_MODEL_URL}" -H 'Content-Type: application/json' \
  -d '{"model":"kernes-qwen","messages":[{"role":"user","content":"Reply with OK."}],"max_tokens":8}'
```

## Deploy the live app

Build the integrated Git commit, then rerun the app deployment with `CFO_MODE=live`. If the selected endpoint requires authentication, create the `autonomous-cfo-model` Secret in the team namespace with key `CFO_MODEL_TOKEN` before the rollout.

```sh
oc process --local -f deploy/openshift-template.yaml \
  -p "APP_IMAGE=${APP_IMAGE}" -p CFO_MODE=live \
  -p "CFO_MODEL_URL=${CFO_MODEL_URL}" -p "CFO_MODEL_NAME=${CFO_MODEL_NAME}" |
  oc -n kernes-ai apply -f -
oc -n kernes-ai rollout status deployment/autonomous-cfo
```

The Route allows 240 seconds per request and the app waits up to `CFO_MODEL_TIMEOUT` seconds (default 90) for each model answer. The app checks every PLN amount in the explanation against the calculation. It retries once if the explanation misquotes a figure, then returns HTTP 503 and the UI keeps the forecast and proposal on screen.

Run the full forecast, live explanation, and both simulated decisions at the deployed URL. Each model call writes one log line with the model name, attempts, and latency, but never the prompt or the token. Save those lines with the commit SHA as evidence of live inference.

```sh
oc -n kernes-ai logs deployment/autonomous-cfo | grep 'autonomous_cfo.advice'
git rev-parse HEAD
```

The UI also shows the model name and response time under each live explanation.

## Run the live flow locally

The same pinned GGUF runs on a laptop with [llama.cpp](https://github.com/ggml-org/llama.cpp) (`brew install llama.cpp`). Download the file from the model card link in [model.yaml](model.yaml), then start the server and the app in live mode.

```sh
llama-server -m qwen2.5-1.5b-instruct-q4_k_m.gguf --alias kernes-qwen --port 8081 --ctx-size 4096
CFO_MODE=live CFO_MODEL_URL=http://127.0.0.1:8081/v1/chat/completions CFO_MODEL_NAME=kernes-qwen \
  uv run --locked uvicorn backend.main:app --host 127.0.0.1 --port 8080
```

[OpenShift templates](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/building_applications/creating-applications) · [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) · [llama.cpp server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)

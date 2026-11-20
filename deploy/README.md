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

For the final deploy, build the integrated Git commit and rerun the app deployment with `CFO_MODE=live`. If the selected endpoint requires authentication, create the `autonomous-cfo-model` Secret in the team namespace with key `CFO_MODEL_TOKEN`. Run the full forecast, live recommendation, and human approval simulation at the deployed URL. [OpenShift templates](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/building_applications/creating-applications) · [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) · [llama.cpp server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)

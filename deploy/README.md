# Deploy to OpenShift

From the repository root, build an image that can run in your cluster. Confirm the registry, node architecture, and namespace with the organizers. Configure registry credentials using the method required by your cluster.

```sh
docker build -f Containerfile -t autonomous-cfo:local .
docker run --rm -p 8080:8080 autonomous-cfo:local
```

In a second terminal, run `curl -fsS http://localhost:8080/health` and open the app in a browser. Push the image to the registry with a unique tag for the current commit, then set `APP_IMAGE` to that image reference. Select your team's OpenShift namespace and run an initial check.

```sh
oc process --local -f deploy/openshift-template.yaml -p "APP_IMAGE=${APP_IMAGE}" |
  oc apply -f -
oc rollout status deployment/autonomous-cfo
oc get route autonomous-cfo -o jsonpath='{.spec.host}{"\n"}'
```

The template defaults to `demo` mode. The `/health` endpoint confirms that the web process is ready. Verify model access separately by making a request through the app.

For the final deployment, select `CFO_MODE=live` after the forecast and model client have both been merged. If the endpoint requires a token, use the OpenShift console to create a Secret named `autonomous-cfo-model` with the key `CFO_MODEL_TOKEN` in the target namespace. Set `CFO_MODEL_URL` to the full inference API URL and `CFO_MODEL_NAME` to the model name, then process the template again.

```sh
oc process --local -f deploy/openshift-template.yaml \
  -p "APP_IMAGE=${APP_IMAGE}" -p CFO_MODE=live \
  -p "CFO_MODEL_URL=${CFO_MODEL_URL}" -p "CFO_MODEL_NAME=${CFO_MODEL_NAME}" |
  oc apply -f -
oc rollout status deployment/autonomous-cfo
```

Repeat the flow from the [README](../README.md) at the HTTPS route. Verify the baseline forecast, the adjusted payment scenario, and the model response. Confirm the URL, request body, and authentication with the organizers. These depend on how the cluster exposes the model. [OpenShift templates](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/building_applications/creating-applications) · [Call a MaaS model in OpenShift AI](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/govern_llm_access_with_models-as-a-service/use-models-as-a-service_maas-deploy)

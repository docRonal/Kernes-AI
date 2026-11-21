# Deployment evidence

What runs on the team's OpenShift AI cluster and which checks passed there. Recorded on 21 November 2026 against commit `54e395b` (PR #14).

## Hard criteria

| Criterion | Evidence |
| --- | --- |
| The app runs on OpenShift | Deployment `autonomous-cfo` in project `kernes-ai`, built in the cluster from `Containerfile` (image tag `app-54e395b`), served at https://autonomous-cfo-kernes-ai.apps.ocp.9hpps.sandbox580.opentlc.com over an edge-terminated HTTPS Route. OpenShift 4.20.46, Red Hat OpenShift AI 3.5.3. |
| A model we deployed on OpenShift AI is used by the app | KServe InferenceService `kernes-qwen-7b`: Qwen2.5 7B Instruct from Red Hat's modelcar catalog, served by vLLM (`registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.2.4`) on the node's NVIDIA L4 GPU with FP8. Manifest: [model-gpu.yaml](model-gpu.yaml). The app's `CFO_MODEL_NAME` is `kernes-qwen-7b`. |

## Models

| InferenceService | Model | Runtime | Role |
| --- | --- | --- | --- |
| `kernes-qwen-7b` | Qwen2.5 7B Instruct | vLLM on the NVIDIA L4 GPU, FP8 | Primary |
| `kernes-qwen` | Qwen2.5 1.5B Instruct (GGUF Q4_K_M) | llama.cpp on CPU ([model.yaml](model.yaml)) | Fallback when the primary fails or misquotes a figure twice |

The preinstalled example `my-first-model/llama-32-3b-instruct` came from the environment's provisioning, not from us. It is stopped (`serving.kserve.io/stop=true`) so that our model can use the only GPU. Both projects are visible in the OpenShift AI dashboard.

## Live inference

Each model call writes one log line with the model name, attempts and latency. The line never contains the prompt or a token. These lines are from `oc -n kernes-ai logs deployment/autonomous-cfo` during the checks below:

```text
2026-11-21 12:27:53 INFO autonomous_cfo.advice advice model=kernes-qwen-7b attempts=1 latency_ms=6688 status=ok
2026-11-21 12:28:04 INFO autonomous_cfo.advice advice model=kernes-qwen-7b attempts=1 latency_ms=6604 status=ok
2026-11-21 12:28:16 INFO autonomous_cfo.advice advice model=kernes-qwen-7b attempts=1 latency_ms=7342 status=ok
2026-11-21 12:28:19 INFO autonomous_cfo.advisory_extras advisory_extras model=kernes-qwen-7b latency_ms=1698 status=ok
2026-11-21 12:28:24 INFO autonomous_cfo.consultant credit-check model=kernes-qwen-7b latency_ms=4181 status=ok
2026-11-21 12:28:28 INFO autonomous_cfo.advisory_extras advisory_extras model=kernes-qwen-7b latency_ms=1905 status=ok
2026-11-21 12:28:32 INFO autonomous_cfo.consultant ask-cfo model=kernes-qwen-7b latency_ms=2993 status=ok
```

The UI shows the model name under each explanation.

## Checks on the deployed app

All 18 checks below passed at the deployed URL through the API. A browser walkthrough is still owned by QA.

| Check | Result |
| --- | --- |
| Starter (EUR 12,000 opening, 23 Nov 2026): automatic proposal | Limit EUR 5,000.00, first and deepest gap on 27 Nov |
| Starter: live explanation | `kernes-qwen-7b`, 8.0 s, cites -EUR 5,000.00 on Friday, November 27 |
| Starter: approve (simulated) | No uncovered gap |
| Starter: reject (simulated) | EUR 5,000.00 uncovered on 27 Nov |
| Starter: move INV-001 to 26 Nov | Friday -EUR 5,000.00 in the baseline, +EUR 4,000.00 in the scenario, proposal kept |
| Peak case (EUR 1,000 opening): proposal | First gap EUR 200.00, limit EUR 700.00 |
| Peak case: live explanation | Separates the EUR 200.00 first gap from the EUR 700.00 deepest gap, 7.6 s |
| Peak case: approve and reject (simulated) | None / EUR 700.00 uncovered on 26 Nov |
| No-shortfall case | No proposal |
| PLN account | Forecast and explanation in PLN, no EUR in the text |
| Non-EU currency (USD) | Refused with HTTP 422 |
| Compare options, credit check, stress test, payment optimization, anomalies | HTTP 200, 0.8 to 4.8 s |
| Ask the CFO ("What if the client pays 3 days late?") | Recalculated answer from `kernes-qwen-7b` |

## Reproduce

Run the checks again after logging in with `oc` (see [README](README.md)):

```sh
oc -n kernes-ai get inferenceservice
oc -n kernes-ai set env deployment/autonomous-cfo --list | grep MODEL_NAME
oc -n kernes-ai logs deployment/autonomous-cfo | grep 'model='
```

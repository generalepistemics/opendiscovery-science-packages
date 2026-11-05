---
name: monarch-serving-inference
description: Inspect available models, test sandbox inference and run approved live inference.
---

# Run Monarch model inference

Use `list_inference_models` or `list_models` to select a model. `run_model_inference` defaults to `sandbox=true`, which provides a simulated response without billable compute. Before setting `sandbox=false`, explain costs and obtain explicit approval, then set `confirm_billable=true`. Inspect live returned status before claiming completion; never automatically retry an uncertain billable request.

## Safety and scope
- All account data and actions require the signed-in Monarch account. Use only the tools explicitly present in this customer MCP; do not invent unlisted operations.
- Never infer compute availability, GPU pricing, deployment status, resource ownership or results that the API has not returned.
- Confirm budget and expected effects before real inference, model training or cancellation. Sandbox inference is simulated rather than a live model completion.
- Do not initiate purchases, top-ups, payouts, external publications or irreversible infrastructure changes from this plugin.
- Do not request or output passwords, credentials, access tokens, or private connection secrets.
- When the requested action is not implemented as a listed tool, state the limitation instead of using a generic executor.

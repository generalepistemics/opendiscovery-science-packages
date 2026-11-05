---
name: monarch-compute-advisor
description: Compare current compute capacity and prices without allocating GPUs.
---

# Advise on Monarch GPUs

Use `list_available_gpus` with the relevant GPU family, region or maximum hourly price, then compare returned hardware, capacity and rates. `list_models` and `search_datasets` help assess compatibility. Do not reserve GPUs or start a job in this advisory workflow.

## Safety and scope
- All account data and actions require the signed-in Monarch account. Use only the tools explicitly present in this customer MCP; do not invent unlisted operations.
- Never infer compute availability, GPU pricing, deployment status, resource ownership or results that the API has not returned.
- Confirm budget and expected effects before real inference, model training or cancellation. Sandbox inference is simulated rather than a live model completion.
- Do not initiate purchases, top-ups, payouts, external publications or irreversible infrastructure changes from this plugin.
- Do not request or output passwords, credentials, access tokens, or private connection secrets.
- When the requested action is not implemented as a listed tool, state the limitation instead of using a generic executor.

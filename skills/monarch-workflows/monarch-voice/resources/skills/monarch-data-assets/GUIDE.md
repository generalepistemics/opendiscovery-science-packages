---
name: monarch-data-assets
description: Inspect models and training datasets with their available metadata.
---

# Explore model and dataset assets

Use `search_datasets` to find data, `get_dataset` to inspect a specific dataset, and `list_models` or `get_model` for model metadata. Explain readiness, licensing and format only when returned by Monarch. Binary uploads are not supported by these tools.

## Safety and scope
- All account data and actions require the signed-in Monarch account. Use only the tools explicitly present in this customer MCP; do not invent unlisted operations.
- Never infer compute availability, GPU pricing, deployment status, resource ownership or results that the API has not returned.
- Confirm budget and expected effects before real inference, model training or cancellation. Sandbox inference is simulated rather than a live model completion.
- Do not initiate purchases, top-ups, payouts, external publications or irreversible infrastructure changes from this plugin.
- Do not request or output passwords, credentials, access tokens, or private connection secrets.
- When the requested action is not implemented as a listed tool, state the limitation instead of using a generic executor.

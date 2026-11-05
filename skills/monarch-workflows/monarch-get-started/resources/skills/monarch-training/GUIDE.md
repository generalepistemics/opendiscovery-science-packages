---
name: monarch-training
description: Start and monitor authorized fine-tuning jobs with explicit cost approval.
---

# Manage Monarch training jobs

Use `list_available_gpus`, `search_datasets` and `list_models` to choose inputs. `list_training_jobs` and `get_training_job` inspect existing training state. Use `start_training_job` only after confirming the model, dataset and expected costs; the tool requires `confirm_billable=true`. `cancel_training_job` requires a specific job ID and explicit `confirm_cancel=true`. If submission is uncertain, inspect jobs before retrying.

## Safety and scope
- All account data and actions require the signed-in Monarch account. Use only the tools explicitly present in this customer MCP; do not invent unlisted operations.
- Never infer compute availability, GPU pricing, deployment status, resource ownership or results that the API has not returned.
- Confirm budget and expected effects before real inference, model training or cancellation. Sandbox inference is simulated rather than a live model completion.
- Do not initiate purchases, top-ups, payouts, external publications or irreversible infrastructure changes from this plugin.
- Do not request or output passwords, credentials, access tokens, or private connection secrets.
- When the requested action is not implemented as a listed tool, state the limitation instead of using a generic executor.

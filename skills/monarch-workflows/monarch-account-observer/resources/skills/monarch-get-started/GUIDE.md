---
name: monarch-get-started
description: Connect Monarch and discover the public AI compute workflows the account can actually use.
---

# Get started with Monarch

After OAuth sign-in, use `get_monarch_profile` to verify account identity, `list_available_gpus` for capacity, `list_models` for models, `list_training_jobs` for existing jobs, and `get_account_balance` for credits. Choose an explicit tool for every action. Real model inference uses `run_model_inference`; model training uses `start_training_job` only with informed confirmation.

## Safety and scope
- All account data and actions require the signed-in Monarch account. Use only the tools explicitly present in this customer MCP; do not invent unlisted operations.
- Never infer compute availability, GPU pricing, deployment status, resource ownership or results that the API has not returned.
- Confirm budget and expected effects before real inference, model training or cancellation. Sandbox inference is simulated rather than a live model completion.
- Do not initiate purchases, top-ups, payouts, external publications or irreversible infrastructure changes from this plugin.
- Do not request or output passwords, credentials, access tokens, or private connection secrets.
- When the requested action is not implemented as a listed tool, state the limitation instead of using a generic executor.

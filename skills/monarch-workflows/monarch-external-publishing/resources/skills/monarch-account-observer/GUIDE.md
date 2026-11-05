---
name: monarch-account-observer
description: Read the connected person’s own Monarch account, balance, usage and training status.
---

# Observe Monarch accounts

Use `get_monarch_profile` when account identity matters; use `get_account_balance` and `get_compute_usage` for finances and `list_training_jobs` or `get_training_job` for jobs. Report credits and usage separately. All operations in this skill are read-only.

## Safety and scope
- All account data and actions require the signed-in Monarch account. Use only the tools explicitly present in this customer MCP; do not invent unlisted operations.
- Never infer compute availability, GPU pricing, deployment status, resource ownership or results that the API has not returned.
- Confirm budget and expected effects before real inference, model training or cancellation. Sandbox inference is simulated rather than a live model completion.
- Do not initiate purchases, top-ups, payouts, external publications or irreversible infrastructure changes from this plugin.
- Do not request or output passwords, credentials, access tokens, or private connection secrets.
- When the requested action is not implemented as a listed tool, state the limitation instead of using a generic executor.

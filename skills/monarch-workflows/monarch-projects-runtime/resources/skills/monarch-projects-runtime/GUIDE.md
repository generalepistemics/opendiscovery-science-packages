---
name: monarch-projects-runtime
description: Explore existing Monarch Cloud projects and deployment records without altering infrastructure.
---

# Inspect Monarch Cloud projects

Use `list_projects` to select a project, then `get_project` and `list_project_deployments` for details. This plugin exposes project inspection, not project creation, migration, credential rotation or infrastructure deletion.

## Safety and scope
- All account data and actions require the signed-in Monarch account. Use only the tools explicitly present in this customer MCP; do not invent unlisted operations.
- Never infer compute availability, GPU pricing, deployment status, resource ownership or results that the API has not returned.
- Confirm budget and expected effects before real inference, model training or cancellation. Sandbox inference is simulated rather than a live model completion.
- Do not initiate purchases, top-ups, payouts, external publications or irreversible infrastructure changes from this plugin.
- Do not request or output passwords, credentials, access tokens, or private connection secrets.
- When the requested action is not implemented as a listed tool, state the limitation instead of using a generic executor.

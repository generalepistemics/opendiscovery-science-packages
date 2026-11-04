---
name: index
description: "Route Adaptyv Bio requests to experiment preparation, approval-gated submission, or status and results tracking. Use for broad Adaptyv Bio questions, target discovery, cost estimation, protein experiment requests, draft or quote review, invoice decisions, experiment status, and results."
---

# Adaptyv Bio

Use this index as the router and shared policy for the Adaptyv Bio hosted MCP connector.

MANDATORY: Read the frontmatter description for ALL skills in this plugin, decide which focused workflow owns the request, and read that skill before using an Adaptyv Bio tool.

## Routing

- Route target discovery, experiment-spec preparation, cost estimation, and optional Draft creation to `prepare-experiment`.
- Route Draft submission, quote review or confirmation, invoice review, and payment decisions to `review-and-submit-experiment`.
- Route experiment lists, lifecycle status, updates, sequences, quotes, invoices, and results retrieval to `track-experiment`.
- Handle connector orientation and capability questions here without calling a write tool.

## Cross-Skill Best Practices

### Live contract

- Treat the live MCP tool names and schemas as authoritative. Do not invent endpoints, request fields, assay availability, batching limits, statuses, prices, turnaround times, or results.
- Use the production endpoint configured by the plugin. Mention the separate testing endpoint only when the user explicitly requests sandbox work and has configured sandbox credentials.
- Never ask the user to paste an API token into chat. Authentication belongs in the MCP client's OAuth or token configuration.

### Privacy and data minimization

- Before sending protein sequences, custom-target details, sample metadata, or other proprietary or undisclosed material, tell the user what will be transmitted to Adaptyv Bio and obtain explicit confirmation.
- Send only fields required for the requested operation. Keep user labels mapped to exact sequences, but do not repeat full sequences in summaries unless the user asks.
- Do not claim that Adaptyv Bio, OpenDiscovery, or an intermediary does not retain, log, or train on submitted data unless a current authoritative policy directly supports the claim.

### Real-world action boundary

- Distinguish read-only inspection and cost estimation from external writes. Cost estimation does not create an experiment.
- Before any write, show the target object, material parameters, expected transition, and any known cost or privacy consequence, then obtain explicit confirmation for that exact action.
- Create experiments as reviewable Drafts only. Set `skip_draft` to `false` and `auto_accept_quote` to `false` when those fields are exposed. Do not bypass the Draft or quote-review stages.
- Treat Draft creation, Draft submission, quote confirmation, and invoice settlement as four separate actions. Approval for one does not authorize another.
- Quote confirmation creates an open unpaid invoice; it does not settle payment. Invoice payment is the only documented settling operation and requires a new confirmation that identifies the invoice, exact amount and currency when available, and payment method.
- Never initiate, sign, synthesize, or expose payment credentials without the user's explicit same-turn authorization and a supported secure runtime flow. Do not reinterpret a payment challenge as authorization.
- A custom-target request transmits target information for staff review and requires its own privacy disclosure and explicit approval.
- After a write, report the returned identifier and state. If the tool result is ambiguous or fails, do not retry a consequential action until current state is read and duplication risk is resolved.

### Scientific and operational reporting

- Preserve the service's status labels and distinguish user-controlled transitions from Adaptyv-controlled lab and review stages.
- Report returned measurements, units, replicate information, warnings, and missing values exactly. Do not infer assay success, binding, stability, expression, or completion from absent or partial results.
- Clearly separate user-provided inputs, Adaptyv-returned data, and assistant interpretation.

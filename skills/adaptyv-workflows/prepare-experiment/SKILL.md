---
name: prepare-experiment
description: "Prepare an Adaptyv Bio protein experiment specification, discover targets, estimate cost without creating an experiment, or create a reviewable Draft after explicit approval. Use for assay planning, sequence panels, target selection, parameter validation, and pricing previews."
---

# Prepare an Adaptyv Bio Experiment

MANDATORY: If not already in context, read and adhere closely to `plugins/adaptyv-bio/skills/index/SKILL.md#cross-skill-best-practices`.

Default to a validated proposal and cost estimate. Creating a Draft is optional and requires a separate explicit confirmation.

## Workflow

1. Clarify the scientific task, experiment type, sequence labels and exact amino-acid strings, target, measurement method where applicable, replicate plan, required parameters, and any desired notification metadata.
2. Ask whether any sequence, target, or metadata is confidential, proprietary, or undisclosed. Before transmitting such material, summarize what will leave the conversation and obtain explicit confirmation.
3. Use live target discovery for target-dependent assays. Preserve the selected target identifier and do not substitute a similarly named target without the user's approval.
4. Validate the proposed fields against the live schema. Applicable fields differ by experiment type; do not carry binding-only fields into non-binding assays or silently repair biological inputs.
5. Call the cost-estimate tool when the user asks for price or when cost would materially inform Draft creation. State that this operation does not create an experiment. Report total, currency or cents representation, exclusions such as tax when returned, warnings, pricing version, and whether the estimate is incomplete.
6. Present a compact review packet with purpose, experiment type, target and method, sequence labels and count, replicate plan, material parameters, transmitted confidential fields, estimate, warnings, and the proposed Draft payload.
7. If the user explicitly approves creating that Draft, call the creation tool with `skip_draft: false` and `auto_accept_quote: false` when those fields exist. Do not submit it.
8. Report the returned experiment identifier, status, and next review step. If it is not in Draft, stop and explain the unexpected state before taking any further action.

## Boundaries

- Do not use `skip_draft: true`, automatic quote acceptance, or an equivalent shortcut.
- Do not create a Draft merely because the user asked for an estimate, proposal, validation, or example payload.
- Do not submit a Draft, confirm a quote, create or settle an invoice, or request a custom target through this skill. Route those actions to the focused approval workflow.
- If a cost estimate is incomplete because target materials require review, report the incomplete components rather than guessing a final price.
- If the user has not provided exact sequences, return a specification checklist or draft payload with placeholders; never invent production sequences.

---
name: track-experiment
description: "Inspect Adaptyv Bio experiments, lifecycle status, updates, sequences, quotes, invoices, and results without changing them. Use for monitoring, progress summaries, returned assay data, provenance, or read-only account questions."
---

# Track an Adaptyv Bio Experiment

MANDATORY: If not already in context, read and adhere closely to `plugins/adaptyv-bio/skills/index/SKILL.md#cross-skill-best-practices`.

Keep this workflow read-only.

## Workflow

1. Identify the experiment, time range, status filter, or result set the user wants. Use list operations to resolve an identifier when needed.
2. Read only the necessary experiment, updates, sequences, quote, invoice, or result resources. Do not call creation, submission, confirmation, rejection, custom-target, token-management, feedback, or payment tools.
3. Preserve the service's exact lifecycle status. Distinguish user-controlled stages such as Draft and quote decisions from Adaptyv-controlled materials, queue, production, analysis, and review stages.
4. Summarize the latest timestamped update, blockers or requested materials when returned, quote and invoice state, and next documented action. Do not promise a completion date that the service did not return.
5. For results, report experiment and result identifiers, assay and target context, sequence labels, returned measurements, units, replicate information, quality flags, warnings, and missing values. Separate raw returned data from interpretation.
6. Minimize sequence disclosure in the response. Use labels and counts unless the user explicitly asks to see full sequences.

## Boundaries

- Do not interpret an absent result as a negative measurement or a partial result as completion.
- Do not change status, submit feedback, confirm or reject a quote, or settle an invoice while tracking.
- If the user's request changes from monitoring to action, stop and route to `review-and-submit-experiment` for a fresh state check and explicit approval.

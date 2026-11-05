---
name: review-and-submit-experiment
description: "Review and execute one explicitly approved Adaptyv Bio experiment transition at a time: submit a Draft, confirm a quote to create an unpaid invoice, reject a quote, or settle an invoice. Use for experiment submission, quote decisions, invoice review, or payment requests."
---

# Review and Submit an Adaptyv Bio Experiment

MANDATORY: If not already in context, read and adhere closely to `plugins/adaptyv-bio/skills/index/SKILL.md#cross-skill-best-practices`.

This workflow owns consequential transitions. Inspect current state first and execute at most the exact step the user approves.

## Review current state

1. Read the experiment, latest updates, quote, and invoice metadata relevant to the request. Do not infer current state from an earlier message.
2. Summarize the experiment identifier and status, assay and target, sequence labels and count, material parameters, quote or invoice identifier, amount and currency when available, and the next documented transition.
3. Explain the effect of the proposed action:
   - Submitting a Draft advances it for Adaptyv review and quote preparation.
   - Confirming a quote creates or finalizes an open unpaid invoice and does not settle payment.
   - Rejecting a quote cancels that quote and may return the experiment to Draft according to the live response.
   - Paying an invoice is the settling operation and can move funds through the selected payment method.
4. Ask for explicit confirmation naming the one action, target identifier, and known financial consequence. Do not accept a prior approval for a different transition.

## Execute one approved transition

- For Draft submission, call the documented submit tool only when the current state is Draft and the user has approved that experiment identifier.
- For quote confirmation, call the documented confirmation tool only after showing the exact quote and amount when available. Stop after the unpaid invoice is returned.
- For quote rejection, call the documented rejection tool only after the user approves the quote identifier and understands the resulting state change.
- For invoice settlement, require same-turn confirmation of the invoice identifier, exact amount and currency when available, and payment method. Use only a supported secure runtime payment flow; never request credentials in chat or construct a credential outside that flow.

After any write, report the returned identifier, state, amount, and next step. Do not chain the next transition. If a response is missing or ambiguous, read current state before considering any retry.

## Boundaries

- Do not combine Draft submission, quote confirmation, and invoice settlement into one approval or tool sequence.
- Do not use `skip_draft`, automatic quote acceptance, or any action that bypasses human review.
- Do not call a payment tool to discover its challenge or supported method unless the user has explicitly authorized attempting payment for that invoice.
- Do not imply that quote confirmation paid an invoice.
- Do not submit or pay from the testing environment as evidence that production authorization exists.

---
name: predict-properties
description: Predict currently available molecular properties for one or more exact SMILES with Inductive Bio. Use when the user requests property values for compounds rather than a ranked analog comparison.
---

# Predict molecular properties

Follow the shared requirements in the `inductive-workflows` skill. Do not use this skill without applying those requirements.

## Inputs

Collect:

- A user label and exact SMILES for each compound.
- The requested properties, or permission to show the currently available choices.
- The relevant pH when the user asks about charge state, ionization, absorption, or permeability.

If a structure is identified as confidential, obtain explicit confirmation before sending it to the connector.

If the user supplies compound names without SMILES, resolve each structure from an authoritative source, show the exact SMILES used, and flag stereochemistry, protonation, or salt-form ambiguity. Do not attribute name-to-structure resolution to Inductive Bio's connector.

## Workflow

1. Call `list_available_models`.
2. Match the requested properties to the returned model identifiers, property or assay names, and units. If the request is ambiguous, present the matching choices before predicting.
3. Call `predict_properties` using the exact live MCP schema, the exact submitted SMILES, and only selected model identifiers returned by model discovery.
4. Read the per-call SMILES and model-id limits from the live `predict-properties` tool schema/description and split large inputs into batches that fit those limits, preserving input order and labels. Do not hardcode specific limit values, since they are set server-side and may change.
5. Return a compact table with one row per compound and property. Include label, exact SMILES, model identifier, property or assay, predicted value, units, and status.
6. Add a short interpretation section only when useful. Keep predictions distinct from experimental data and state material limitations.

## Supported analysis patterns

- **Named compound sets:** use the same selected model for every structure, preserve the input order and labels, then sort only when the user requests it. Show the exact resolved SMILES in the output.
- **Charge state from pKa:** report acidic and basic predictions separately, identify likely ionizable groups as assistant interpretation, state the pH under discussion, and keep the charge-state conclusion qualitative.
- **LogD-informed brain exposure:** identify the compounds most compatible with the requested single-property heuristic, but explicitly decline to call LogD a brain-permeability prediction. Name the additional evidence required.
- **pKa-informed passive absorption:** discuss how ionization could affect passive absorption at the stated pH while making clear that pKa alone does not predict oral absorption or bioavailability.
- **Combined LogD and pKa:** place the returned properties side by side, describe tensions or hypotheses, and list missing assays rather than issuing a development recommendation.
- **Fragment-level LogD:** propose chemically intelligible fragment SMILES, label them as assistant-generated, predict the parent and fragments with the same live model, and explain that fragment values are not additive and cannot uniquely assign the parent property's cause.

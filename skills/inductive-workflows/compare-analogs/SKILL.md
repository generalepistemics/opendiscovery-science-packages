---
name: compare-analogs
description: Compare molecular-property predictions across analogs with Inductive Bio using matched models, explicit deltas, and cautious interpretation. Use for analog ranking, property trends, or reference-relative comparisons.
---

# Compare molecular analogs

Follow the shared requirements in the `inductive-workflows` skill. Do not use this skill without applying those requirements.

## Inputs

Collect:

- At least two compounds with distinct labels and exact SMILES.
- Requested properties.
- A reference compound when deltas are requested.
- A direction or target range for each ranking criterion.
- Any project pH, diversity constraint, or maximum shortlist size relevant to the decision.

If the user asks for the best compound without defining the desired direction or range, ask for the decision criterion. Do not assume that higher or lower is universally better.

If any structure is identified as confidential, obtain explicit confirmation before sending the structures to the connector.

## Workflow

1. Call `list_available_models` and resolve the requested properties to live model identifiers.
2. Call `predict_properties` with the same selected model set for every analog, using the exact live MCP schema.
3. Preserve the returned values and units. Do not compare values across different model identifiers or incompatible units as if they were directly equivalent.
4. Build a comparison table containing label, exact SMILES, model identifier, property or assay, prediction, units, and status.
5. When a reference is defined, compute signed deltas as `analog prediction - reference prediction` within each matched model and unit. State that convention.
6. Rank only against criteria supplied by the user. Show ties and missing values explicitly, and do not rank failed or missing predictions as though they were numeric.
7. Separate the result into returned predictions, derived deltas or rankings, and scientific interpretation.

## Compound-series analysis

- **Triage:** state the exact rules before applying them. If the user gives a qualitative rule such as "moderate LogD," translate it into a clearly labeled provisional criterion or ask for a project-specific range when the distinction could change the decision. Keep every input compound and failed prediction visible.
- **Shortlisting:** use only completed, comparable results; honor the requested maximum; preserve structural diversity when the structures support that assessment; and explain that the shortlist is assistant-side reasoning rather than an additional Inductive Bio prediction.
- **Relationship and grouping analysis:** include only matched, nonmissing values in each comparison, report the number of compounds used, and identify apparent trends or clusters as descriptive. Do not claim mechanistic causality or statistical significance without an appropriate analysis.
- **Results handoff:** organize completed results with compound ID, input SMILES, model name or property, model ID, predicted value, units, and status. Add assumptions, failures, and open questions separately. Do not claim a native export endpoint.

## Interpretation boundary

Describe observed model trends without assigning causality to a structural change unless the comparison supports it and relevant confounders are acknowledged. Do not treat a favorable LogD, pKa, or other isolated prediction as proof of permeability, absorption, safety, efficacy, brain penetration, or candidate quality. If a user asks which analog has the "best chance" of brain exposure or improved absorption from LogD or pKa alone, report the single-property ranking they requested but explicitly decline the broader conclusion and list the missing evidence.

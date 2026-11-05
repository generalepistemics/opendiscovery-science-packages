---
name: inductive-workflows
description: Route Inductive Bio molecular-property requests to model discovery, prediction, or analog comparison. Use when a user asks generally about the Inductive Bio connector or wants help choosing the appropriate workflow.
---

# Inductive Bio

Use the Inductive Bio MCP connector for molecular-property prediction from exact SMILES.

## Route the request

- Use `predict-properties` for one or more independent property predictions, named-compound panels, fragment-level prediction, or cautious interpretation of LogD and pKa.
- Use `compare-analogs` when the user wants matched comparisons, reference-relative deltas, ranking, triage, shortlisting, or relationship and grouping analysis across two or more compounds.
- For a connector or model-availability question, call `list_available_models` and report the returned model identifiers, property or assay names, and units without making a prediction.
- For privacy preflight or packaging of already completed results, handle the request here. Do not make another prediction call unless a required result is missing.

## Shared operating rules

1. Call `list_available_models` before every prediction workflow. Treat its live response as authoritative and do not hardcode model identifiers or assume a property is available.
2. If OAuth authorization is required, tell the user it must be completed before any connector tool call — model discovery or prediction — can succeed.
3. Use only the live MCP tool schema. Do not invent REST endpoints, request fields, batching limits, or undocumented properties.
4. Require an exact SMILES for every submitted compound. Preserve user labels separately from SMILES. If the user supplies only a chemical name, obtain an exact structure from an authoritative source when one is available; show the resolved SMILES and any stereochemistry, protonation, or salt-form assumption. Ask the user when the intended structure is ambiguous rather than silently choosing one.
5. If the user identifies any structure as confidential, proprietary, or undisclosed, explain that the structure will be sent to an external service and obtain explicit confirmation before calling a prediction tool.
6. For large inputs, read the per-call SMILES and model-id limits from the live `predict-properties` tool schema/description and split the request into batches that fit those limits. Do not hardcode specific limit values, since they are set server-side and may change.
7. Report the exact submitted SMILES, model identifier, property or assay name, value, and units. Preserve missing values and tool errors rather than filling or guessing.
8. Label predictions as model outputs. Separate returned values from interpretation and from any user-provided experimental measurements.
9. Do not infer efficacy, permeability, absorption, safety, brain penetration, or overall candidate quality from LogD, pKa, or any single modeled property alone.
10. If the requested property is unavailable, say so and show the available properties. Do not silently substitute a related property.
11. If the user asks for every available property, select only the models returned by the current `list_available_models` response. Do not expand that request to undocumented ADMET or PK endpoints.
12. Reuse completed predictions already present in the conversation for downstream sorting, grouping, shortlisting, or packaging. Make clear which content is returned by Inductive Bio and which content is assistant-side analysis.
13. Do not imply that the connector has a native export, download, structure-resolution, fragment-generation, correlation, or ranking tool unless live discovery shows one.

## Privacy context

Inductive Bio does not retain submitted chemical structures after a request completes, and the MCP server does not collect user prompts, inputs, or queries. Inductive Bio does not use submitted structures or predictions to train, tune, or improve its models. Access logs are retained only as long as necessary for security, compliance, and internal analytics. Client-side handling by OpenDiscovery or other software is separate from this policy.

## Scientific interpretation rules

- For pKa-based charge-state discussion, state the pH being considered and keep the conclusion qualitative unless the required assumptions are explicit.
- For brain-exposure discussion, frame LogD as one physicochemical input and identify missing evidence such as size, polarity, ionization, permeability, transporter effects, protein binding, and clearance.
- For passive-absorption discussion, identify missing evidence such as solubility, dissolution, permeability, transporter effects, and metabolic stability.
- For fragment analysis, label the proposed fragments as assistant-generated and do not treat fragment LogD values as additive contributions to whole-molecule LogD.
- For correlations or groupings, report the compounds and properties included, preserve missing results, and describe associations without claiming mechanism or statistical significance that was not evaluated.

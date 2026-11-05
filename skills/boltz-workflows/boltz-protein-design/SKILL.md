---
name: boltz-protein-design
description: Design new protein binders with Boltz. Use when generating protein, peptide, antibody, nanobody, or custom binder candidates for a target. Not for screening existing proteins or small molecules.
---

# Protein Design

Use the installed OpenDiscovery Boltz MCP server. Its tools are namespaced by the host; discover the available tool aliases instead of assuming CLI commands exist.

Use `boltz_protein_design` for this workflow. Read `boltz_get_guidance` for the corresponding payload and input requirements before preparing a job. Check setup before submitting work. If setup reports missing components or authentication, show that requirement and use the explicit setup/sign-in tools only with the user's authorization.

Estimate with `start=false` before starting a workflow. Present the estimate and intended inputs; obtain approval before `start=true`. Never treat installation as permission to create a paid job. Results download under the Boltz server's configured output directory. After downloading, use the returned artifact paths and the engine's file tools to copy requested results into the selected project; do not guess paths. Retrieve status and downloaded result paths rather than inventing successful outputs.

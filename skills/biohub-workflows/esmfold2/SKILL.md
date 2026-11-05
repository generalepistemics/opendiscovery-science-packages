---
name: esmfold2
description: Use when the user needs ESMFold2 all-atom folding for proteins, DNA, RNA, modified residues, or ligands, including Fast/full routing, MSA, confidence, structures, and provenance. Not for dynamics, experimental truth, or Atlas discovery.
license: MIT
compatibility: Hosted MCP works through the connected service. Shared Python helpers require a POSIX engine host; managed ESM workflows require the pinned Python 3.12 environment.
---

The shared Python helper library uses POSIX file locks. On a Windows engine host, use the connected MCP capabilities or a selected POSIX remote engine for helper workflows. Do not run the helper through an unsupported interpreter or report a failed import as a missing credential. Provider accounts, managed inference credentials and compute permissions remain separate.

# ESMFold2

The user's instructions take precedence over guidelines provided in a skill.
If explicit user instructions conflict with a skill's instructions, prioritize the user's instructions.

## Choose the model

| Need | Managed | Hugging Face |
| --- | --- | --- |
| accuracy, difficult complexes, or optional MSA | `esmfold2-2026-05` | `biohub/ESMFold2` |
| fast single-sequence throughput | `esmfold2-fast-2026-05` | `biohub/ESMFold2-Fast` |

Fast is not MSA-conditioned. If the user supplies or requires an MSA, route to full ESMFold2 and validate query alignment. Missing MSA is not an error for a single-sequence fold unless the user explicitly required MSA conditioning.

For `Show me what GB1 looks like.`, resolve the thin launcher through `resources/examples/starter-examples.json`; do not ask the user to paste the bundled sequence. Validate the pinned fixture and exact one-request contract in `resources/examples/gb1-esmfold2-fast-fold-request.json`, then run it. Complete `preflight --endpoint fold` with the provisioned Python 3.12 runtime first and any `$biohub-esm-setup` work if access is missing or `unverified`, then execute one managed `POST /api/v1/fold` request with `include_pae=true`, the Fast parameters, and the `prediction.pdb`, `presentation-request.json`, `result.json`, `raw-response.json`, and `provenance.json` outputs. A single managed fold at this scale needs no confirmation. Managed requests may incur cost. Report provider-returned credit or token usage when available; otherwise state that the API did not report usage or cost, and never invent an estimate. Continue through local artifact recovery without repeating the provider request.

Also recognize the official-tutorial-shaped launchers in `resources/examples/tutorial-use-cases.json`: an RNase H1 complex with an RNA/DNA hybrid, ubiquitin with a user-supplied A3M, a modified peptide-receptor complex with a covalent linker, and an antibody-antigen complex with user-supplied paired A3Ms. The exact plugin-page launcher `Model how a modified GLP-1 peptide with a lipid linker might engage GLP-1R, then show me the complex.` may resolve the pinned tutorial construct only after disclosing the tagged receptor construct, representative non-therapeutic linker, chemistry, covalent indices, route, model, request count, artifacts, and available cost information in the frozen plan. After that disclosure, run preflight and its exact one-request managed fold without asking first. For every other tutorial fold (RNase H1, ubiquitin, and paired antibody-antigen), disclose the exact route, model, request count, parameters, construct, artifacts, and available cost information, then run that exact managed fold without asking first. Outside that exact launcher or an explicitly named tutorial example, retain the user's sequences/MSAs or pause for missing biological input; never silently substitute the tutorial target. Modal and self-hosted GPU work also requires a frozen scope, cost ceiling, and plain yes/no confirmation. Present a successful structure by default without making the user translate the request into SDK objects, and lead with the structure rather than with a description of what you are about to do.

## Recover an accepted response

Use recovery only when a saved response proves the provider accepted and returned the request but local conversion or materialization failed. It makes zero provider calls. Never use it for an indeterminate submission, and always choose a new output directory that does not exist.

```bash
<python-3.12-with-pinned-esm> <skill-directory>/resources/scripts/biohub_esm.py managed-recover \
  --endpoint fold_all_atom \
  --input /absolute/path/frozen-request.json \
  --raw-response /absolute/path/raw-response.json \
  [--source-provenance /absolute/path/provenance.json] \
  --output-dir /absolute/path/new-recovery-output
```

Use `--endpoint fold` for a saved sequence-fold response. Omit `--source-provenance` only when no matching incomplete provenance exists. Consume the new directory's validated `presentation-request.json` exactly; it retains the artifact identity and `openIntentId` for the presentation handoff.

## Build and validate input

Use the official pinned SDK's `StructurePredictionInput` with `ProteinInput`, `DNAInput`, `RNAInput`, `LigandInput`, and zero-based `Modification` positions. The managed wire schema permits omitted/null entity IDs; local/Hugging Face SDK execution requires explicit IDs. In either route, use unique explicit IDs for every entity referenced by pocket, distogram, or covalent-bond conditioning. A ligand uses either SMILES or CCD identifiers. Managed `/fold_all_atom` accepts either this `all_atom_input` shape or `sequence` with optional MSA, never both.

Load tutorial A3M input with `MSA.from_a3m(resources/skills/., remove_insertions=True, max_sequences=1000)`, keep the insertion-removed query as row zero, and verify its ungapped sequence against the corresponding chain. Reject a tutorial MSA deeper than 1,000 rows before execution. The pinned SDK serializes non-empty A3M headers, and Biohub's paired-MSA tutorial requires standalone `key=<positive-decimal-taxonomy-id>` tokens in non-query headers to pair rows across chains. Preserve them on all-atom per-chain full-model requests and describe a row as paired only when the same exact key occurs in at least two chain MSAs. Top-level single-chain managed MSA requests omit headers because cross-chain pairing cannot apply there. Fast remains invalid whenever an MSA is supplied, even if a notebook initialized one Fast client before later MSA examples.

For modified/covalent complexes, the packaged validator checks zero-based residue bounds and nonnegative integer atom-index shape; it does not prove atom existence, valence, bond chemistry, or tutorial atom-index identity. Before execution, independently verify atom indices against the parsed residue templates and molecular graph. A SMILES atom index is not a character offset into the SMILES string. Preserve the exact construct and chemistry supplied; a tagged receptor or representative linker must not be described as the exact therapeutic molecule.

```bash
python3 <skill-directory>/resources/scripts/biohub_esm.py validate-fold \
  --model esmfold2-2026-05 \
  --input /absolute/path/fold-input.json \
  --config /absolute/path/folding-config.json
```

For an official tutorial MSA workflow, use the stricter contract before showing the execution plan:

```bash
python3 <skill-directory>/resources/scripts/biohub_esm.py validate-fold \
  --model esmfold2-2026-05 \
  --input /absolute/path/fold-input.json \
  --config /absolute/path/folding-config.json \
  --require-msa \
  --require-msa-insertions-removed \
  --msa-max-depth 1000
```

Add `--require-paired-msa-keys` for the paired antibody-antigen workflow.

Do not universalize the Biohub web UI's 700-residue entry cap as an architectural model limit. For managed model IDs, validate hosted parameters exactly: loops 0-20, sampling steps 1-100, LM dropout/mask fraction 0-1, MSA depth 1-16,384 or null, and MSA column mask fraction 0-1. For Hugging Face model IDs, validate the pinned local `ESMFold2InputBuilder.fold` contract instead; its sampling-step default is 200 and it additionally supports diffusion sample count, seed, sampler overrides, early exit, and complex ID. Do not apply hosted caps to self-hosted runs.

## Outputs

Prefer mmCIF for all-atom complexes; PDB can be lossy for complex chemistry. Preserve coordinates, pLDDT, pAE, pTM, iPTM, pair-chain iPTM, and requested distograms/embeddings when returned. The current managed API documents `include_pair_chains_iptm` for both `/fold` and `/fold_all_atom`; use the validated direct request when an SDK convenience method exposes a narrower signature. Record pLDDT on its current 0-1 scale and pAE in angstroms. For sequence `/fold`, their scopes are per-residue and residue-pair. For `/fold_all_atom`, their scopes are per-token and token-pair over the returned `complex.sequence` entries aligned by `complex.token_to_atoms`, including non-protein entity tokens. Record pTM/iPTM on their current 0-1 scale; PDB B-factors may encode pLDDT after an explicit SDK scale conversion.

Explain that the result is a static model hypothesis, not dynamics, affinity, or experimental truth. Low confidence, disorder, interfaces, ligands, modified residues, and unexpected topology require special caution and experimental validation.


Visibly report every returned `quality_warnings` item. Never silently repair coordinates, and never let high pLDDT override a chemistry or geometry warning.

## Present the result

- After every successful fold, present the result without waiting for another request.
- Choose the viewer from the input and the user's request before calling it.

1. For one unmodified protein sequence of 1 to 4,000 residues, call the Biohub MCP's `ui_show_protein_structure` once with the exact sequence unless the user requests the exact prediction file.
   Hosts that render MCP Apps show the interactive Mol* viewer, and other hosts get a PNG preview when available.
   The view shows stored Atlas coordinates or the server's own on-demand fold for that sequence, not this ESMFold2 prediction.
   Label it that way, and take pLDDT, pAE, pTM, and iPTM only from this fold's artifacts.
   Pass `color_by: confidence` only to show the view's own pLDDT, and highlight residues using the shared [MCP view contract](resources/references/structure-viewer-handoff.md#show-a-protein-with-the-biohub-mcp).
2. For multiple chains, modified residues, ligands, DNA/RNA, a sequence outside the MCP input limits, or a request to see the exact prediction file, use the separately installed OpenDiscovery Structure Viewer.
   Skip the MCP call for these inputs; never concatenate chains, remove modifications, or substitute a receptor-only view.
   Consume the validated `presentation-request.json` and open its verified absolute mmCIF or PDB once with its exact retained `openIntentId`.
   Retain the returned same-task session, verify the primary object, and request predicted-confidence styling only when ready.
   Generate a new ID only for a legacy artifact set without that request file.
   Discover the viewer's file-opening capability; if unavailable, render an image from the verified coordinate artifact using the shared rendered-image fallback below.
3. A missing MCP tool, denied approval, timeout, server error, or unavailable preview does not change the input's compatibility.
   Report the failure without switching viewers or repeating the fold.
   On `sequence_too_long_to_fold`, report the 700-residue Atlas-miss fold limit and returned `actual_length`, then hand the already-generated prediction to the OpenDiscovery Structure Viewer without retrying the MCP call.
   Preserve pending or unavailable presentation separately from successful inference.

- Use the shared [result presentation handoff](resources/references/structure-viewer-handoff.md) for the exact open, readiness, verification, and timeout-reconciliation contract.
- A follow-up asking to open an existing prediction uses that artifact without another provider request.

- Always return the checksummed artifacts.
- For structures unsupported by the MCP app, including exact prediction files, an agent-generated rendering image is allowed when the OpenDiscovery Structure Viewer is unavailable.
- Follow the [rendered-image fallback](resources/references/structure-viewer-handoff.md#rendered-image-fallback) to render the actual saved coordinates, display the image, and verify it.
- Do not generate a replacement viewer for supported sequence requests or MCP operational failures.
When the user asks to see a protein that `$esmc` analyzed in this conversation, do not fold it: `$esmc` shows it again with its highlights.
Presentation status never changes scientific success.
Read [Show a protein with the Biohub MCP](resources/references/structure-viewer-handoff.md#show-a-protein-with-the-biohub-mcp) for the full contract of the view.

Read the [managed/SDK contract](resources/skills/esmfold2/references/api.md), [inputs and results](resources/skills/esmfold2/references/inputs-and-results.md), and [self-hosting/Modal guidance](resources/skills/esmfold2/references/self-hosted.md).

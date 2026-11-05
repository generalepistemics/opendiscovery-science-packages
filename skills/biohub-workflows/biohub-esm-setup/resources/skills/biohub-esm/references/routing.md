# Routing details

The product distinctions come from the [Biohub protein world model](https://biohub.ai/esm/protein), [get-started guide](https://biohub.ai/esm/protein/get-started), and [Biohub/esm source](https://github.com/Biohub/esm).

## Decision order

1. If the goal is lookup/discovery across existing proteins, the existing Atlas feature catalog, or cluster context, choose Atlas through the public Biohub MCP. Use anonymous S3 only for bulk datasets. If the goal is to extract or interpret SAE activations for a supplied sequence, choose ESMC; a combined workflow may then query Atlas descriptions only for the exact compatible SAE dictionary.
2. If the goal is binder, minibinder, or scFv design, stop: it is not offered in this plugin. Say so, name the covered workflows, and route it nowhere.
3. If privacy, offline execution, data residency, custom heads, fine-tuning, or sustained ownership is required, choose pinned Hugging Face weights on user-owned compute. Public weights need no `HF_TOKEN`.
4. For public ESMC inference, choose the Biohub managed API and use `ESM_API_KEY`, including bounded concurrent calls that the managed backend can auto-batch. The plugin ships no ESMC Modal function. If the user specifically wants owned compute, choose pinned self-hosted weights instead.
5. If folding work is many independent calls or long running, use pinned weights on suitable user-owned GPUs when they are available; otherwise choose Modal. Public weights on owned compute need no key, and Modal needs Modal auth but no `ESM_API_KEY`.
6. Otherwise, choose Biohub managed ESMFold2 and use `ESM_API_KEY`.

Small public Atlas API reads need no spend confirmation. Bulk anonymous-S3 access is different: before any multi-gigabyte or multi-terabyte transfer, freeze the exact source prefix, destination, estimated bytes, storage and egress impact, and cost ceiling, then obtain separate explicit current-turn confirmation.

## ESMFold2 variant

- Full: accuracy-priority targets, difficult complexes, optional MSA.
- Fast: single-sequence latency and throughput; never promise MSA conditioning.

## Examples

| Request | Result |
| --- | --- |
| "What might W43F do to GB1?" | Resolve the pinned GB1 fixture, validate W43F numbering, run preflight, make one managed `esmc-600m-2024-12` request, and display the resulting score card. Managed requests may incur cost. Report provider-returned credit or token usage when available; otherwise state that the API did not report usage or cost, and never invent an estimate. |
| "Show me what GB1 looks like." | Resolve the pinned single-chain fixture, run `preflight --endpoint fold` in the provisioned Python 3.12 runtime, make one managed `esmfold2-fast-2026-05` request, show GB1 first with `ui_show_protein_structure` labeled as the Biohub MCP's coordinates, and open the prediction in the Structure Viewer with pLDDT coloring only if that view fails |
| "Show me the ESM Atlas structure for P69905." | Hand off to `$esm-atlas`: resolve the accession with `esm_atlas_search_uniprot`, then call `ui_show_protein_structure` once with the returned sequence; no managed call |
| "Find proteins similar to GB1." | Call `esm_atlas_search_similar_protein_clusters` once through the Biohub MCP, return the ranked hits, and show the top hit with `ui_show_protein_structure` |
| "Map the mutational landscape of PETase and show me where it is most constrained or tolerant." | Disclose the pinned CaPETase tutorial sequence, then run all 259 masked contexts against managed `esmc-600m-2024-12` concurrently through a bounded pool, and summarize the separately named tutorial entropy and 19 genuine substitutions per site. Then show the literal once with `ui_show_protein_structure`, with the most constrained and the most tolerant positions highlighted. Managed requests may incur cost. Report provider-returned credit or token usage when available; otherwise state that the API did not report usage or cost, and never invent an estimate. |
| "Show me what ESMC has learned about ATP synthase and map the strongest features onto its structure." | Disclose the pinned RCSB FASTA sequence of PDB 2XND chain A plus the calls it makes: one RCSB FASTA, one managed encode, one managed logits, five Atlas feature fetches, and one `ui_show_protein_structure` view. Run them without asking first, then use normalized exact-dictionary activations, the strict `> 0.01` predicate, top-10 maximum and prevalence rankings, and top-five descriptions. Show the top three features as colored highlights in the Biohub MCP view of that exact sequence, never as a self-drawn figure, with named raw/derived/provenance artifacts |
| "Model how a modified GLP-1 peptide with a lipid linker might engage GLP-1R, then show me the complex." | Disclose the tagged receptor construct, representative non-therapeutic linker, exact fold, and artifacts; run the one managed fold without asking first; then preserve covalent indexing and open the model hypothesis automatically |
| "Reproduce the official Biohub RNase H1 RNA-DNA hybrid ESMFold2 tutorial example." | Resolve the pinned tutorial literals and disclose the exact fold and artifacts; then run the managed all-atom call, preserve chain-aware confidence, and open the result automatically |
| "Using my supplied ubiquitin A3M, follow the official Biohub ESMFold2 tutorial example and show the structure and confidence." | Retain the user's A3M, apply the pinned query-first insertion-removal preprocessing, route to full managed ESMFold2, and disclose the exact fold; then run it, show the single chain first with `ui_show_protein_structure`, and open the result with pLDDT coloring only if that view fails |
| "Fold 500 designs" | pinned `biohub/ESMFold2-Fast` on suitable owned GPUs when available; otherwise Modal; use full for accuracy/MSA |
| "Design minibinders" | Not offered in this plugin. Say so and stop; no route, no handoff, no script call |
| "My sequence cannot leave our VPC" | pinned self-hosted weights |

The `item_count > 32` code branch is a conservative folding-orchestration heuristic to surface scale-out early. It does not apply to ESMC and is not an account quota or provider guarantee.

The expanded use-case details are pinned to Biohub's official notebooks in [`examples/tutorial-use-cases.json`](../../../examples/tutorial-use-cases.json). The PETase prompt authorizes only its exact shipped 259-request managed runtime and its one Biohub MCP structure view, the ATP-synthase prompt only its exact disclosed RCSB FASTA, managed, and Atlas requests and its one Biohub MCP structure view, and the GLP-1R prompt only its exact one-request managed fold; every other managed ESMFold2 tutorial fold runs its exact disclosed fold without a separate confirmation. Planning-only or no-network requests override, and Modal, self-hosted, and bulk-transfer work requires route-specific confirmation.

## Structure presentation routing

- Use the Biohub MCP app first for a supported unmodified protein sequence.
- Use the separately installed OpenDiscovery Structure Viewer for complexes, modified residues, ligands, DNA/RNA, structures outside MCP input limits, and requests for exact prediction files.
- Choose by compatibility; a missing MCP connection, denied approval, timeout, server error, or unavailable preview does not authorize switching viewers.
- A returned `sequence_too_long_to_fold` can route an already-generated artifact to the OpenDiscovery Structure Viewer without a new fold.
- Follow the [shared presentation contract](../../../references/structure-viewer-handoff.md) for discovery, the retained opening intent, ready-only styling, and unavailable-viewer reporting.

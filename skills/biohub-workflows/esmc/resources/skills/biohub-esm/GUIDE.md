---
name: biohub-esm
description: Route Biohub ESM requests to ESMC, ESMFold2, ESM Atlas, Modal, or private open weights. Use for explicitly ESM/Biohub work, ESM protein representations or mutation scoring, ESMFold2 folding, Atlas discovery, showing a protein's 3D structure in the Biohub MCP's Mol* viewer, or choosing an ESM compute route. Do not use for unrelated non-ESM models, generic sequence alignment, or opening a local structure file in a non-Biohub viewer unless the user explicitly asks to compare it with Biohub ESM.
license: MIT
compatibility: Hosted MCP works through the connected service. Shared Python helpers require a POSIX engine host; managed ESM workflows require the pinned Python 3.12 environment.
---

The shared Python helper library uses POSIX file locks. On a Windows engine host, use the connected MCP capabilities or a selected POSIX remote engine for helper workflows. Do not run the helper through an unsupported interpreter or report a failed import as a missing credential. Provider accounts, managed inference credentials and compute permissions remain separate.

# Biohub ESM router

The user's instructions take precedence over guidelines provided in a skill.
If explicit user instructions conflict with a skill's instructions, prioritize the user's instructions.

Use this as the implicit entry point. Identify the scientific goal before choosing a model or provider; ESMC, ESMFold2, and Atlas are different artifacts.

## Route first

| User need | Default | Escalation |
| --- | --- | --- |
| Existing-protein discovery, functional neighborhoods, clusters, Atlas structure views | public Biohub MCP | plugin script for the feature catalog, thumbnails, and batch; anonymous Atlas S3 for bulk data |
| Show one protein's ESM Atlas structure or Biohub MCP view | public Biohub MCP `ui_show_protein_structure` | ESMFold2 for a plain structure request, a new prediction, a complex, or a non-protein entity; `$esmc` for a follow-up on a protein it analyzed in this conversation |
| SAE activation extraction or interpretation for an input sequence | Biohub managed ESMC | pinned ESMC weights for private or custom work |
| Public ESMC inference, including bounded concurrent calls | Biohub managed API | self-host for private, custom, sustained, or owned-compute work |
| One or modest structure predictions | Biohub managed ESMFold2 | full + MSA for difficult targets; Modal for bulk |
| Many independent folds or sweeps | Modal open weights | user-owned GPUs |
| Private, offline, air-gapped, data-resident, customized, fine-tuned, sustained | Hugging Face weights on user-owned compute | user owns capacity and operations |

Binder, minibinder, and scFv design are not offered in this plugin. Answer that plainly, name what the plugin does cover, and stop. Do not hand the request to another skill, run the router or any other script for it, and do not propose a Modal, self-hosted, or managed route for it.

Run the deterministic router when the route is not already explicit:

```bash
python3 <skill-directory>/resources/scripts/biohub_esm.py route --task fold --item-count 500
```

The 32-item scale-out threshold applies to folding. It is a planning heuristic, not a Biohub account quota. Public ESMC calls stay on the managed API; the plugin ships no ESMC Modal function. Do not hardcode account-specific capacity limits.

## Natural starter experiences

Treat the plugin page's exact prompts as outcome-rich launchers into the official tutorial contracts in `../../examples/tutorial-use-cases.json`:

- `Map the mutational landscape of PETase and show me where it is most constrained or tolerant.`
- `Show me what ESMC has learned about ATP synthase and map the strongest features onto its structure.`
- `Model how a modified GLP-1 peptide with a lipid linker might engage GLP-1R, then show me the complex.`

Resolve their hidden scientific inputs, select the specialist and model, produce the tutorial-shaped analysis, and present the visual result without making the user translate the request into sequences or SDK objects. The focused GB1 regression launchers in `../../examples/starter-examples.json` remain supported:

- `What might W43F do to GB1?`
- `Show me what GB1 looks like.`
- `Find proteins similar to GB1.`

The three exact plugin-page prompts are curated official-tutorial launchers. Before adopting their pinned target or construct, disclose its exact identity together with the execution route, model, item and call counts, parameters, artifact plan, and available cost information. Each prompt authorizes only its disclosed exact calls once access is configured: the PETase 259-request managed runtime and its one Biohub MCP structure view, the ATP-synthase RCSB FASTA, managed, and Atlas requests and its one Biohub MCP structure view, and the GLP-1R one-request managed fold. No prompt authorizes a substituted target, a different request scope, or Modal, self-hosted, or bulk-transfer work. An explicit planning-only or no-network request overrides execution. Outside those three exact prompts, resolve a bundled literal only for an explicitly named tutorial example. A generic target request, or a prompt that says “my A3M/MSA,” must use the user's supplied biological input or pause for the missing input; never substitute a tutorial fixture. The 259-context PETase landscape runs on the managed API through the shipped replay-safe command, fanned out through a bounded pool of concurrent managed calls as the quickstart documents.

Do not ask the user to paste the bundled GB1 sequence or recite implementation details already owned by the contract. Resolve these launchers to the pinned RCSB 1PGA chain-A record, then validate the internal literal sequence, digest, and mutation numbering. For other named targets, prefer a user-provided file or stable identifier; otherwise resolve an authoritative sequence source and ask one question only when ambiguity would change the biological input.

For a managed route, run status-only preflight first; it reads no credential value and costs nothing. If it reports `missing`, load `$biohub-esm-setup` and give the user its key message with the returned `obtain_key_url` (on macOS, the Terminal steps with the returned `macos_keychain_command`), not a plan they cannot run, then resume automatically once the key is configured. If it reports `unverified`, a sandbox blocked the macOS Keychain; rerun preflight outside the sandbox before any key message, as `$biohub-esm-setup` describes. Otherwise resolve and validate the input locally, then follow that workflow's authorization boundary and execute only its exact pinned request count without implicit retries. The focused GB1 starters, the three exact plugin-page prompts (PETase, ATP-synthase, and GLP-1R), and every other managed ESMFold2 tutorial fold run without separate confirmation once their exact scope is disclosed. Managed requests may incur cost. Report provider-returned credit or token usage when available; otherwise state that the API did not report usage or cost, and never invent an estimate. Continue automatically through local recovery and result presentation after successful artifact creation. Lead with the result, not with a description of what you are about to do. Small public Atlas API reads need no spend confirmation, but still obey a caller's explicit no-network or planning-only boundary. Before a bulk anonymous-S3 transfer, freeze the exact source prefix, destination, estimated bytes, storage and egress impact, and cost ceiling, then obtain separate explicit current-turn confirmation.

## Hand off

After choosing the route, explicitly load exactly the focused specialist(s) needed for the request. These specialists are explicit-only so the router stays the single implicit entry point.

- Representation, logits, entropy, mutation, SAE activation extraction/interpretation, fitted-head, or fine-tuning requests: use `$esmc`.
- Protein/DNA/RNA/modified-residue/ligand folding: use `$esmfold2`.
- Similar proteins, protein names or accessions, MD5 records, clusters, Atlas structure views, the existing Atlas feature catalog, thumbnails, or Atlas batch data: use `$esm-atlas`. It answers through the Biohub MCP tools, so run no router script first, and never choose a chain, isoform, organism, or accession for a protein name before it resolves the name.
- Install, authentication, environment, or preflight problems: use `$biohub-esm-setup`.
- Showing a single protein's structure: every skill can show one with the Biohub MCP's `ui_show_protein_structure`, so the user sees the interactive Mol* viewer where the host renders MCP Apps, or its PNG preview elsewhere.
  A request to see a protein's ESM Atlas structure or its Biohub MCP view, such as `Show me the ESM Atlas structure for P69905.`, needs no new prediction, so hand it to `$esm-atlas`.
  A plain request to show or display a protein's 3D structure, such as `Could you display the 3D structure of GB1?`, stays with `$esmfold2`, except the follow-up below.
  The PETase landscape and the ATP-synthase feature map finish with the protein shown and the residues they singled out highlighted, as `$esmc` describes.
  That Biohub MCP view is their only structure presentation.
  A follow-up request to see the structure of a protein that `$esmc` analyzed in this conversation, such as `show me the structure`, stays with `$esmc`, which shows the same sequence and highlights again.
  An ESMFold2 fold of one unmodified protein chain, including `Show me what GB1 looks like.`, is shown first with the Biohub MCP view, labeled as the server's coordinates rather than the prediction.
  Unsupported structures and requests for the exact prediction file use the separately installed OpenDiscovery Structure Viewer through the result presentation handoff.
  A missing MCP connection, denied approval, error, or unavailable preview is reported without switching viewers.
  A returned `sequence_too_long_to_fold` may hand an existing prediction to the OpenDiscovery Structure Viewer without another fold.
  The tool takes one protein chain and folds an Atlas miss only up to 700 residues, so the GLP-1R complex and other multi-chain ESMFold2 results open only through the OpenDiscovery Structure Viewer handoff.
  Never concatenate chains, strip modifications, or show only the receptor to make a complex fit the MCP tool.
  Read [Show a protein with the Biohub MCP](../../references/structure-viewer-handoff.md#show-a-protein-with-the-biohub-mcp) for highlights, residue numbering, labels, and failures.

## Invariants

- Atlas is a public data/discovery API and anonymous dataset, not a model to deploy on Modal or Hugging Face.
- Biohub managed inference needs `ESM_API_KEY`.
- Modal public-weight workflows need Modal authentication, not `ESM_API_KEY`.
- Public Hugging Face weights do not require `HF_TOKEN`; it is optional for authenticated Hub access.
- Do not ask for credentials in chat or print, persist, screenshot, or commit them. Preflight reports only configured, missing, or unverified.
- Script and provider routes preserve machine-readable artifacts and provenance, not UI-only results; Biohub MCP answers write no files and cite their tools and source in the answer instead.
- Finish successful workflows with the default [result presentation](../../references/structure-viewer-handoff.md): show supported protein sequences with the Biohub MCP first, use the OpenDiscovery Structure Viewer only for unsupported structures or exact prediction files, open each verified artifact once, and keep pending or unavailable presentation separate from scientific artifact success.
- For structures unsupported by the MCP app or exact prediction files, use the [rendered-image fallback](../../references/structure-viewer-handoff.md#rendered-image-fallback) when the OpenDiscovery Structure Viewer is unavailable.
- Supported sequence requests and MCP operational failures never use a custom replacement viewer.

Read [routing details](references/routing.md), [failure handling](references/failures.md), and the shared [safety/provenance contract](../../references/safety-and-provenance.md).

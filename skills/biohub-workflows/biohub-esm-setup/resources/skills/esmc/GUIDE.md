---
name: esmc
description: Use when the user needs ESMC embeddings, hidden states, logits, entropy, zero-shot mutation scoring, SAE features, fitted heads, or fine-tuning, or wants to see an analyzed protein's highlighted residues again in the Biohub MCP structure view. Sequence only; not for folding, Atlas lookup, or calling an untrained classifier predictive.
license: MIT
compatibility: Hosted MCP works through the connected service. Shared Python helpers require a POSIX engine host; managed ESM workflows require the pinned Python 3.12 environment.
---

The shared Python helper library uses POSIX file locks. On a Windows engine host, use the connected MCP capabilities or a selected POSIX remote engine for helper workflows. Do not run the helper through an unsupported interpreter or report a failed import as a missing credential. Provider accounts, managed inference credentials and compute permissions remain separate.

# ESMC

The user's instructions take precedence over guidelines provided in a skill.
If explicit user instructions conflict with a skill's instructions, prioritize the user's instructions.

ESMC is a sequence-only masked protein language model. Validate the input before inference:

```bash
python3 <skill-directory>/resources/scripts/biohub_esm.py validate-sequence \
  --target esmc --sequence-file /absolute/path/query.fasta
```

The context is 2,048 tokens. Because current tokenizers add BOS/EOS, the helper uses a conservative 2,046-residue raw-sequence cap unless a pinned tokenizer probe proves a different count. Do not pass structures, DNA, RNA, or ligands.

## Model and route

| Route | IDs |
| --- | --- |
| Biohub managed | `esmc-300m-2024-12`, `esmc-600m-2024-12`, `esmc-6b-2024-12` |
| Hugging Face | `biohub/ESMC-300M`, `biohub/ESMC-600M`, `biohub/ESMC-6B` |

Default to managed ESMC for public inference, including bounded concurrent calls that the managed backend can auto-batch. The plugin ships no ESMC Modal function. Use pinned Hugging Face weights on user-owned compute for private, offline, custom-head, fine-tuned, sustained, or explicitly owned-compute workloads.

## Analysis contract

1. Preserve the normalized sequence digest and exact model/revision.
2. Request only the outputs needed: sequence logits, per-residue embedding, mean embedding, selected hidden states, or named SAE models.
3. For the default biological residue-entropy metric, mask the evaluated residue, predeclare the allowed residue-token set, exclude special/control tokens, and renormalize over only those residue tokens. Keep full-vocabulary log probabilities separate. When explicitly reproducing the official PETase notebook, report its complete-vocabulary entropy in bits as a separately named tutorial metric with its token set and log base; never relabel it as residue entropy.
4. For zero-shot mutation scoring, report the documented score definition, typically `log P(mutant | masked context) - log P(wild type | masked context)`. Keep raw log probabilities and residue numbering.
5. Treat embeddings and SAE activations as features, not biological labels.
6. A downstream classifier/regressor becomes a prediction only after fitting on appropriate labeled data and validating on held-out, leakage-controlled data. Never run an untrained classification head and name its random output.
7. Record outputs and provenance atomically; large tensors should be files with checksums, not pasted into chat.

Biohub's pinned official mutation-landscape and SAE tutorials define two page-facing workflows in `../../examples/tutorial-use-cases.json`:

- `Map the mutational landscape of PETase and show me where it is most constrained or tolerant.` is a curated tutorial launcher. Disclose the pinned CaPETase literal before adopting it, run status-only preflight, then execute the exact `runtime.command` from the tutorial contract using the verified Python 3.12 environment; do not recreate the analysis in generated code. The shipped `esmc-landscape --tutorial petase` path validates the literal digest, uses a bounded 16-worker `ThreadPoolExecutor` for all 259 host-pinned managed logits calls, and writes exact-request-bound per-position checkpoints before producing `raw-responses.json`, `mutation-landscape.json`, `mutation-landscape.csv`, and `provenance.json`. If interrupted, use only `runtime.resume_command`; never replay an indeterminate submission. Present its constrained/tolerant summary, separately named full-vocabulary tutorial entropy, genuine-substitution fraction, and canonical-amino-acid LLRs. Then show the protein with the Biohub MCP view, as [Show residues on the structure](#show-residues-on-the-structure) describes, and include that one view in the disclosure. Do not route this to Modal: the plugin ships no ESMC Modal function.
- `Show me what ESMC has learned about ATP synthase and map the strongest features onto its structure.` is a curated launcher for the RCSB FASTA sequence of PDB 2XND chain A, using managed `esmc-6b-2024-12` with SAE `esmc-6b-2024-12-sae-layer60-k64-codebook16384`. Disclose that identity and the calls it makes: one RCSB FASTA fetch, one managed encode request, one managed logits request, five Atlas feature-detail fetches, and one Biohub MCP `ui_show_protein_structure` view. Reproduce managed rather than local tokenization, normalized features, the strict `activation > 0.01` predicate, top 10 rankings by both maximum activation and prevalence, and descriptions for the top five maximum-activation features. Map the top three maximum-activation features onto the structure with the Biohub MCP view, as [Show residues on the structure](#show-residues-on-the-structure) describes; do not fetch the experimental 2XND coordinates. Preserve the named raw, feature, ranking, structure-view, and provenance artifacts. After the exact disclosure, run preflight and then the RCSB, managed, Atlas, and Biohub MCP requests without asking first.

Lead with the science. Order every answer this way:

1. The result: the Biohub MCP structure view, the ranked features, or the score card. Show it
   automatically; never ask permission to show a result.
2. Two or three sentences a scientist can react to: which positions or regions are
   constrained, which are tolerant, what stands out.
3. One line of scientific status: this is a model hypothesis, not an experimental
   measurement, and it needs validation.
4. The artifact paths, listed briefly.
5. Provenance, collapsed: pinned model revision, SDK revisions, input digest, checksums,
   and the exact route.
6. A link back to the relevant model card, such as <https://biohub.ai/models/esmc>.

Do not open with a plan, a list of the calls you intend to make, a cost estimate, or a
request for permission. If the user explicitly asks for a dry run or a planning-only answer, describe
the plan and say plainly that no provider call was made; that is the only case where a
no-call answer is correct.

The two exact page-facing prompts above may resolve their disclosed pinned tutorial targets. Otherwise resolve a bundled sequence only when the user explicitly names the official tutorial example. A generic PETase, ATP-synthase, A3M, or MSA request uses the user's supplied inputs or pauses for them; never silently substitute tutorial literals. Keep mutation analysis in the ESMC model family. For SAE interpretation, ESMC owns activation extraction; Atlas is an optional description lookup for the exact compatible feature dictionary, not a substitute inference route.

Run status-only preflight first; it reads no credential value and costs nothing. If managed access is missing, hand the user the key page from `$biohub-esm-setup` instead of a plan, then resume automatically once it is configured. If it is `unverified`, a sandbox blocked the macOS Keychain; rerun preflight outside the sandbox before any key handoff, as `$biohub-esm-setup` describes. The focused GB1 starter, the exact PETase runtime, and the exact ATP-synthase workflow run without separate confirmation. Managed requests may incur cost. Report provider-returned credit or token usage when available; otherwise state that the API did not report usage or cost, and never invent an estimate. Self-hosted GPU work and bulk data transfers are different: freeze the exact route, model/revision, item and call counts, input digest, output paths, persistence plan, and cost ceiling, show that scope, and ask a plain yes/no question before spending. Never require the user to repeat a specific phrase back to you.

For `What might W43F do to GB1?`, resolve the pinned fixture through `../../examples/starter-examples.json`; do not ask the user to paste the bundled sequence. Its managed path performs exactly one no-retry logits request and writes `raw-response.json`, `mutation-score.json`, `mutation-score.svg`, and `provenance.json`. The score records the masked context, both natural-log probabilities, one-based residue and zero-based tensor indices, exact model and SDK revisions, and checksums. After successful materialization, display `mutation-score.svg` inline by default; it is a visual summary of the model score, not evidence of fitness, stability, activity, binding, or function.

## Show residues on the structure

ESMC takes sequence only, so show its results on a structure with the Biohub MCP's `ui_show_protein_structure`.
Hosts that render MCP Apps show its interactive Mol* viewer, and other hosts get its PNG preview.
It is the only structure presentation for this skill.
Never draw a structure image or an activation map yourself with plotting, rendering, or viewer code, such as matplotlib, SVG, PyMOL, or py3Dmol.
Never show other coordinates, such as an experimental PDB entry, in place of the view.

After a successful analysis of one protein that singles out residues, call it once with the exact analyzed sequence:

- PETase landscape: highlight every position in `summary.most_constrained` of `mutation-landscape.json` in `#D55E00`, and every position in `summary.most_tolerant` in `#009E73`.
- ATP-synthase feature map: for each of the top three maximum-activation features in rank order, highlight its 10 highest-activation residues with `activation > 0.01` that no higher-ranked feature already highlights, and break a tie by the lower position.
  Color the first, second, and third feature `#D55E00`, `#009E73`, and `#CC79A7`, and name each color with its feature in the answer.
  Record the exact call arguments, the returned `descriptor`, and `preview_status` in `structure-view.json`.
  The view shows a stored Atlas prediction or an on-demand fold of the 2XND chain A sequence, not the experimental 2XND coordinates, so say that in the answer.
  The view highlights residues and cannot color by a value, so `per-residue-activations.csv` keeps every activation value.
  Say that each color marks only the feature's 10 strongest residues, not its full extent, and give the feature's count of residues with `activation > 0.01`.
  Name each residue by its position in the analyzed sequence, and say so.
  The 2XND chain A author number of a residue is its position plus 18, so give that number too when the answer links or compares with the 2XND entry or the literature.
  Never pass a 2XND author number as a highlight.
- A single mutation score, such as W43F in GB1: highlight the mutated residue when the user asks where it sits.

The PETase and ATP-synthase tutorial contracts name this call, so include it in their disclosures.
For other pinned workflows, name the view only in the answer's source line.
Highlight each residue on chain `A` by its one-based position in the analyzed sequence, and set `expected_residue` to the three-letter code of its wild-type residue.
This numbering needs no sequence-to-coordinate alignment, because the view folds or looks up the exact sequence passed.
If the call returns `invalid_input` because a highlighted residue identity does not match, correct the numbering one time; never remove `expected_residue`.
Highlight at most 32 residues: keep the 32 that the analysis ranks highest, and state how many it left out.
Describe the PNG preview in words, and if `preview_status` is not `available`, say that visual inspection is unresolved.
The highlights show where the model score or activation is, not a measured effect.
Name `ui_show_protein_structure` in the answer's source line.

When the user asks to see the structure again, call the view again with the same sequence and highlights, such as the arguments in `structure-view.json`.
This is not a refresh or a poll, so the one-call rule does not block it.
Do not fold the protein with ESMFold2 for that request.
An on-demand fold can compute again, so compare the new `descriptor.sha256` with the recorded one, and say when the coordinates differ.
When the user asks for the experimental 2XND structure, say that the Biohub MCP view cannot open a PDB entry, and link <https://www.rcsb.org/structure/2XND>.
Give the 2XND author numbers of the highlighted residues with that link.
If the tool is not in the catalog, returns an error code, or reports a `preview_status` other than `available`, give the analysis without a structure view and name the tool and the reason.
When the view could not run, write `structure-view.json` with the planned arguments, `called: false`, and the reason.
When the tool is not in the catalog, also say that the Biohub MCP is not connected and point to `$biohub-esm-setup`.
After the user connects it, make only the recorded view call, and never repeat the RCSB, managed, or Atlas requests.
The analysis result stands without the view, and a failed view never permits a self-drawn replacement.
Read [Show a protein with the Biohub MCP](../../references/structure-viewer-handoff.md#show-a-protein-with-the-biohub-mcp) for the full contract.

Read the exact [managed/SDK contract](references/api.md), [analysis guidance](references/analysis.md), and [self-hosting guidance](references/self-hosted.md).

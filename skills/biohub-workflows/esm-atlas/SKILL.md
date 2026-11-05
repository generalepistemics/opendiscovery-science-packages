---
name: esm-atlas
description: Use when the user wants proteins similar to a protein, a protein name or accession resolved to a sequence, an Atlas record, SAE feature profile, or cluster context for a sequence, one Atlas SAE feature explained, or a protein structure viewed, all through the public Biohub MCP. Also use for the full Atlas feature catalog, thumbnails, batch jobs, MD5-only records, or anonymous S3 data, which stay on the plugin script. Use ESMC instead to extract SAE activations with a chosen ESMC checkpoint. Atlas is public data, not a model to deploy, and uses the connected provider account.
license: MIT
compatibility: Hosted MCP works through the connected service. Shared Python helpers require a POSIX engine host; managed ESM workflows require the pinned Python 3.12 environment.
---

The shared Python helper library uses POSIX file locks. On a Windows engine host, use the connected MCP capabilities or a selected POSIX remote engine for helper workflows. Do not run the helper through an unsupported interpreter or report a failed import as a missing credential. Provider accounts, managed inference credentials and compute permissions remain separate.

# ESM Atlas

The user's instructions take precedence over guidelines provided in a skill.
If explicit user instructions conflict with a skill's instructions, prioritize the user's instructions.

Atlas is public data and discovery infrastructure, not a model to run on Modal or Hugging Face.
Answer Atlas questions through the public Biohub MCP, which uses provider sign-in when challenged and is separate from managed inference credentials, and never through the plugin script, `curl`, or another HTTP client.
The plugin script remains only for the work the MCP does not cover: the full feature catalog, thumbnails, batch jobs, MD5-only records, and anonymous S3 data.
Every reply, including a clarifying question, states limits and choices as facts about the Atlas and never mentions, quotes, or links this skill, its rules, or its file.

## Tools

Resolve these logical tool names in the connected catalog.
A host may show a server prefix around a name, so match the logical name and never hard-code a prefix.

| Need | Tool |
| --- | --- |
| Protein name or UniProt accession to sequence | `esm_atlas_search_uniprot` |
| UniParc, MGnify, or IMG accession to sequence | `esm_atlas_lookup_accession` |
| Similar proteins | `esm_atlas_search_similar_protein_clusters` |
| Atlas record and top SAE features | `esm_atlas_get_protein_details` |
| Cluster context for a sequence | `esm_atlas_get_cluster_info` |
| One SAE feature | `esm_atlas_get_sae_feature_detail` |
| Structure view | `ui_show_protein_structure` |

If these tools are not in the catalog, say the Biohub MCP is not connected and point to `$biohub-esm-setup`.
Read [the MCP tool reference](resources/skills/esm-atlas/references/mcp-tools.md) for arguments, returned fields, and error codes.

## Resolve the input

- Raw sequence or FASTA: drop the header and whitespace, keep every residue letter, and pass it on unchanged.
- UniProt accession, such as `P69905`: call `esm_atlas_search_uniprot` once with the accession as `query` and `size=1`, and accept only a record whose accession matches exactly.
- Protein name, such as `hemoglobin`: call `esm_atlas_search_uniprot` once with the name verbatim as `query` and `size=6`; never rewrite it, field it, or guess an accession first.
  When several candidates return, list their accessions, protein names, and organisms, and ask the user to choose without recommending one, even one you already mentioned.
- UniParc, MGnify, or IMG accession: call `esm_atlas_lookup_accession`, which does not accept UniProt accessions.
- A 32-character MD5 protein hash with no sequence: the MCP is keyed by sequence, so read the stored record with the script's `atlas protein --protein-hash` command and continue with its returned sequence.
- Starter launcher `Find proteins similar to GB1.`: resolve the pinned fixture in `resources/examples/starter-examples.json`; never ask the user to paste the bundled sequence.

Function text returned while resolving an input describes the input, not the Atlas result, so never present it as Atlas evidence.

## Length limits

Never clip, truncate, or window a sequence yourself.

- Similarity search and SAE features take at most 2,048 residues.
  For a longer sequence, do not call the search; name the limit and the sequence length, and ask the user for a domain or residue range.
  A `sequence_too_long_for_features` error from `esm_atlas_get_protein_details` gets the same answer.
- `ui_show_protein_structure` returns stored Atlas coordinates at any supported length, and folds a miss only up to 700 residues.
  On `sequence_too_long_to_fold`, explain the 700-residue fold limit with the returned `actual_length`, and ask for a domain of at most 700 residues without retrying.

## Find similar proteins

For `Find proteins similar to GB1.`, or any similar-protein request:

1. Call `esm_atlas_search_similar_protein_clusters` exactly once with the resolved sequence, `top_k=10`, and `uncharacterized_only=false`, unless the user asked only for uncharacterized clusters.
2. Report up to ten hits in the returned order with accession, protein name, length, similarity score, and cluster size, and never manufacture missing hits.
3. For a non-empty result, call `ui_show_protein_structure` once with the top-ranked hit's returned `sequence`.
4. Make zero script calls, and make no cluster, protein-detail, or feature-detail follow-up calls unless the user asks what the neighbors are or do.

Read hits correctly:

- `similarity_score` is cosine similarity between sparse-autoencoder (SAE) feature vectors, not sequence identity, alignment, or homology.
- The search runs over cluster representatives only, so a missing relative can reflect index coverage rather than absence.
- A short or empty hit list means nothing cleared the service's unreported similarity floor, never that nothing exists.
- A nonzero `restricted_count` means results were withheld; say so without guessing what they held.
- `top_features_across_results` lists SAE features shared across hits; report counts as `occurrence_count` out of the returned hit count.
- A hit that scores far above the rest, is very short yet scores high, or has a `cluster_size` of one may be lab contamination such as an expression construct; flag it rather than feature it.

When the user asks what a protein does or which neighbors are informative, call `esm_atlas_get_cluster_info` for every hit, in parallel where the host allows, with each hit's returned `sequence`.
Rank neighbors by `cluster_pct_characterized`, then by how specific `top_pfam_domains` is, then by `cluster_size`, and never by similarity score alone.
Every cluster field describes the neighbor's cluster, never the query, and characterized means Pfam-annotated, not experimentally studied.

## Read a protein's record and features

Call `esm_atlas_get_protein_details` once with the exact sequence.
Report `sae_features` in returned order, copying each `label` verbatim.
Report `value` with its `label_reliability` band as signal strength only; the band is never a judgement of the label's quality.
Report `residue_regions` positions as returned, and never compare their raw `mean_activation` with the normalized `value`.
When `features_computed_on_miss` is true, say the sequence is not in the Atlas and its features were computed on demand; infer nothing more.
For a feature-profile request, call `esm_atlas_get_sae_feature_detail` once for each of the three features with the highest `value`, breaking ties by lowest `feature_index`, and use its `label`, `summary`, and `description` as the only biological wording; skip it for a plain record lookup.

Atlas features come from the fixed 16,384-feature dictionary of `esmc-6b-2024-12-sae-layer60-k64-codebook16384`.
Never apply them to another checkpoint, model, layer, or codebook; extract activations for a different SAE with `$esmc`.

## Show a structure

Call `ui_show_protein_structure` once with the exact sequence; pass `view_options` only when the user asks for a representation, confidence coloring, or highlighted residues.
Highlight a residue on chain `A` by its one-based position in that sequence, and set `expected_residue` to its three-letter code.
In a host that renders MCP Apps, the result opens the interactive Mol* viewer (`ui://biohub-public/structure-viewer/v1`).
Every host also receives a PNG preview and a text descriptor; describe what the preview shows in words, and never say a structure is shown above, write viewer code, draw your own image of the structure, or hand the result to a different viewer.
If `preview_status` is not `available`, say visual inspection is unresolved.
Atlas coordinates and on-demand folds are model hypotheses, not experimental structures.
When the user asks for an experimental method, resolution, or citation, say the Atlas does not provide one.
The other Biohub ESM skills use this same tool, as [Show a protein with the Biohub MCP](resources/references/structure-viewer-handoff.md#show-a-protein-with-the-biohub-mcp) describes.

## Write the answer

Report only what the tools returned; never add proteins, structures, PDB entries, or literature from memory.
MCP answers write no files.
End every MCP answer with one source line naming each tool called, the Atlas version, and the license, for example:

`Source: Biohub MCP esm_atlas_search_similar_protein_clusters, ui_show_protein_structure; ESM Atlas v1 through the v1alpha1 API; CC-BY-4.0.`

Follow it with one link to <https://biohub.ai/esm/protein/atlas>.

## When a tool fails

Branch on the returned `code`, not on the message text.
`rate_limited` means wait as the error advises before one retry.
`indeterminate` means the compute outcome is unknown, so never retry it automatically.
`invalid_input`, `not_found`, `restricted`, `dependency_unavailable`, `resource_too_large`, and `internal_error` on the search or input resolution stop the answer without a biological conclusion.
A call the host blocks, for example by denying approval, is a failure too.
Name the failed tool and code, never retry with different arguments or switch to the script, and never fill the gap with results from memory, literature, or your own sequence comparison.

## Script route

The script needs no client key and writes `raw-response.json`, `result.json`, and `provenance.json` with each result.

```bash
# Full 16,384-feature catalog
python3 <skill-directory>/resources/scripts/biohub_esm.py atlas features \
  --output-dir /absolute/path/features

# Stored record for an MD5 protein hash with no known sequence
python3 <skill-directory>/resources/scripts/biohub_esm.py atlas protein \
  --protein-hash <md5> --output-dir /absolute/path/protein

# pLDDT or pct-characterized thumbnail for an MD5 protein hash
python3 <skill-directory>/resources/scripts/biohub_esm.py atlas thumbnail \
  --protein-hash <md5> --thumbnail-type plddt \
  --output /absolute/path/thumbnail.png

# Batch of up to 500 unique MD5 hashes, with atomic resumable state
python3 <skill-directory>/resources/scripts/biohub_esm.py atlas batch-submit \
  --hashes /absolute/path/hashes.json \
  --state /absolute/path/batch-state.json \
  --output /absolute/path/batch.zip
python3 <skill-directory>/resources/scripts/biohub_esm.py atlas batch-status \
  --state /absolute/path/batch-state.json
python3 <skill-directory>/resources/scripts/biohub_esm.py atlas batch-wait \
  --state /absolute/path/batch-state.json \
  --output /absolute/path/batch.zip
python3 <skill-directory>/resources/scripts/biohub_esm.py atlas batch-cancel \
  --state /absolute/path/batch-state.json
```

Never pass `--fold-on-miss` to `atlas protein`; structures go through `ui_show_protein_structure`.
Small batches may return a zip immediately, and larger batches return resumable job state.
An interrupted submit without a durably captured `job_id` becomes `submission-indeterminate`: preserve it, reconcile manually with Atlas operators, and never resume or resubmit that state.
A definitive `400`, `401`, `402`, `403`, `404`, `422`, or `429` becomes `submission-rejected`, and only a new `batch-submit` for the exact same request may retry, never before the persisted `Retry-After` deadline.
To adopt an older job once, pass both `--state <new-path>` and `--job-id <id>`.
Cancellation is idempotent, and completed results can remain available.

Read the [script-route HTTP contract](resources/skills/esm-atlas/references/api.md), the shared [safety and provenance contract](resources/references/safety-and-provenance.md), and the [batch and S3 guidance](resources/skills/esm-atlas/references/bulk-data.md), whose confirmation rules apply before any multi-gigabyte or multi-terabyte S3 transfer.

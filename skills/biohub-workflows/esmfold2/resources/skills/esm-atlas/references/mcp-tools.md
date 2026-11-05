# Public Biohub MCP tool contract

The public Biohub MCP is a Streamable HTTP server with provider OAuth discovery at `https://biohub.ai/mcp`, declared as server `biohub`.
It needs no client key, and it forwards Atlas calls to the ESM Atlas v1alpha1 API.
Results are response-local: the server keeps no saved IDs or persistent URLs, and a separate call may compute again.
Every tool returns structured JSON, and errors come back as a JSON object with a stable `code`.

Matches the server's `tools/list` after the 2026-09-25 rename of the ESM Atlas tools to `esm_atlas_*`.

## Input resolution

### `esm_atlas_search_uniprot`

- Arguments: `query` (1 to 500 characters, text or fielded UniProt query) and `size` (1 to 6, default 6).
- Returns `query_label`, `num_results`, `total_results`, and `proteins`, each with `accession`, `protein_name`, `gene`, `organism`, `function`, `sequence`, and `sequence_length`.
- A UniProt accession such as `P69905` goes here as the query verbatim; accept only a record whose `accession` matches it exactly.

### `esm_atlas_lookup_accession`

- Argument: `accession` (1 to 128 characters) from UniParc, MGnify, or IMG.
- Returns `accession`, `database`, `sequence`, and `sequence_length`.
- A UniProt accession returns `invalid_input`.

## ESM Atlas discovery

### `esm_atlas_search_similar_protein_clusters`

- Arguments: `sequence` (1 to 2,048 characters), `top_k` (1 to 12, default 10), and `uncharacterized_only` (default false).
- A longer sequence fails schema validation with a generic `invalid_input`, so check the length before calling.
- Returns `query_sequence_length`, `hits`, `top_features_across_results`, and `restricted_count`.
- Each hit carries `protein_accession`, `sequence`, `sequence_length`, `similarity_score`, `cluster_size`, and `protein_name`.
- Hits carry their raw `sequence` so it can be passed straight to the other tools; do not show sequences unless the user asks.
- The service may compute features for the query and fold missing hit structures internally, with a current upstream cap of six folds.
- `uncharacterized_only=true` restricts hits to clusters with no characterized Pfam annotations; it is not proof of unknown function.

### `esm_atlas_get_protein_details`

- Argument: `sequence` (1 to 4,000 characters).
- Returns `sequence`, `sequence_length`, `accession`, `header`, `source`, `sae_features`, `ptm`, `mean_plddt`, structure availability flags, `features_computed_on_miss`, and `folded_on_miss`.
- A catalog miss computes SAE features up to 2,048 residues and never folds; longer misses return `sequence_too_long_for_features`.
- Each `sae_features` entry carries `feature_index`, `label`, `description`, a normalized `value`, a `label_reliability` band, and optional `residue_regions` with raw `mean_activation`.
- The profile holds the top features only, never every feature that fires.

### `esm_atlas_get_cluster_info`

- Argument: `sequence` (1 to 4,000 characters), normally a hit's returned `sequence`.
- Returns `accession`, `source`, `protein_name`, `cluster_size`, `cluster_pct_characterized`, `cluster_mean_domain_coverage`, `top_pfam_domains`, `representative_features`, `taxonomy_info`, and `top_phyla`.
- `taxonomy_info` is the cluster's lowest common ancestor and `top_phyla` counts members, so neither names the query organism.
- `not_found` means the Atlas has no cluster for that exact sequence.

### `esm_atlas_get_sae_feature_detail`

- Argument: `feature_index` (0 to 16,383).
- Returns `feature_index`, `label`, `summary`, `description`, `category`, `activation_pattern`, `exemplar_protein_families`, `uniref90_frequency`, `top_swissprot_activations`, and `decoder_nearest_neighbors`.
- `top_swissprot_activations` entries pair a UniProt ID with an activation; they share a feature with the query and are not its relatives.

## Structure view

### `ui_show_protein_structure`

- Arguments: `sequence` (1 to 4,000 characters) and optional `view_options` with `representation` (`cartoon` or `surface`), `orientation`, `color_by` (`chain` or `confidence`), up to 32 residue `highlights`, `visible_chain_ids`, and `camera`.
- Returns stored ESM Atlas coordinates, or folds a miss of up to 700 residues; a longer miss returns `sequence_too_long_to_fold`.
- Each highlight takes `chain_id`, `author_residue_number`, an optional `expected_residue` three-letter code, and an optional `color`.
  The coordinates use chain `A` and residue numbers 1 to N of the sequence passed.
  A highlight whose `expected_residue` does not match returns `invalid_input` with the message `A highlighted residue identity does not match the structure.`
- The result carries a PNG preview image plus a `descriptor` naming the coordinate file, its SHA-256, and its `source` (`atlas` catalog or on-demand fold), with `preview_status`, `inspection_status`, and `warnings`.
- `descriptor.source` carries `provider`, `protein_hash`, `kind`, `folded_on_miss`, and `model`, which can be `null`.
- Hosts that render MCP Apps show the interactive Mol* viewer from resource `ui://biohub-public/structure-viewer/v1`.
- Camera and selection gestures inside the viewer do not call the server again.

## Error codes

The skill's failure and length-limit sections say how to act on each code.

| Code | Meaning |
| --- | --- |
| `invalid_input` | Malformed arguments or an out-of-schema value |
| `not_found` | No Atlas record or cluster for that input |
| `restricted` | Atlas restricted this request |
| `rate_limited` | Too many requests |
| `dependency_unavailable` | An upstream service failed or changed its schema |
| `indeterminate` | A compute outcome is unknown |
| `sequence_too_long_to_fold` | A structure miss exceeds 700 residues |
| `sequence_too_long_for_features` | A feature miss exceeds 2,048 residues |
| `resource_too_large` | The complete result exceeds the public response limit |
| `internal_error` | An unexpected server failure |

Length errors also return `actual_length` and `max_length`.

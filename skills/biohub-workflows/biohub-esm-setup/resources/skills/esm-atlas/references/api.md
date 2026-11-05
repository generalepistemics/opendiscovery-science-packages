# Script route: ESM Atlas v1alpha1 HTTP contract

This contract covers only the plugin script's Atlas commands.
Similarity search, sequence-keyed protein and cluster records, feature detail, and structure views go through the [public Biohub MCP](mcp-tools.md) instead.
The script remains for the full feature catalog, MD5-keyed records, thumbnails, and batch jobs.

Primary official sources:

- [API reference](https://biohub.ai/esm/protein/atlas/api-docs/api_reference.html)
- [OpenAPI 3.1 schema](https://biohub.ai/esm/protein/atlas/api-docs/_static/openapi.json)
- [protein and cluster example](https://biohub.ai/esm/protein/atlas/api-docs/examples/protein_lookup.html)
- [feature examples](https://biohub.ai/esm/protein/atlas/api-docs/examples/feature_browse.html)
- [API overview](https://biohub.ai/esm/protein/atlas/api-docs/overview.html)

Verified against source code and all linked reference, example, concept, FAQ, and Swagger sections on 2026-07-31.
Base URL: `https://biohub.ai`.
Atlas currently requires no client-side authentication.
It is an alpha API, so the script preserves the complete decoded response and validates its schema before deriving artifacts.

## Script-route operations

| Method and path | Request | Success contract |
| --- | --- | --- |
| `GET /esm/protein/api/v1alpha1/features` | no parameters | `200` JSON containing the complete 16,384-item feature catalog |
| `GET /esm/protein/api/v1alpha1/features/{feature_index}` | path index 0 to 16,383 | `200` JSON feature detail; `422` validation error |
| `GET /esm/protein/api/v1alpha1/proteins/{protein_hash}` | MD5 plus protein query fields below | `200` JSON protein record; `422` validation error |
| `GET /esm/protein/api/v1alpha1/proteins/{protein_hash}/thumbnail/{thumbnail_type}` | type `plddt` or `pct-characterized` | `200` PNG, immutable for one year; `422` validation error |
| `POST /esm/protein/api/v1alpha1/proteins/batch` | JSON batch request below | small batch: `200` ZIP; large batch: `202` JSON job handle |
| `GET /esm/protein/api/v1alpha1/proteins/batch/jobs/{job_id}` | job ID | `202` pending, `200` terminal and download-ready, `410` expired |
| `DELETE /esm/protein/api/v1alpha1/proteins/batch/jobs/{job_id}` | job ID | idempotent `204`; an unknown job may return `404` |

## Protein lookup by MD5

Query fields are `topk_features` 1 to 100 (default 10), `fold_on_miss` (provider default true), `normalize_features` (default true), and repeated integer `feature_indices` capped at 100.
The script always sends `fold_on_miss=false`; the skill never opts in, because structures go through the MCP's `ui_show_protein_structure`.
The script rejects an explicit empty `feature_indices` list, because an omitted query means top-K mode.
Nonempty `feature_indices` returns those features in request order, uses value 0 for no recorded activation, and skips indices outside the catalog.
The script then requires the returned `sae_features` indices to equal the requested in-catalog indices in caller order, and without explicit indices it rejects a response with more than `topk_features` entries.

The response requires only `protein_hash`.
Documented optional fields are `header`, `source`, `accession`, `sequence`, `sequence_length`, `ptm`, `mean_plddt`, `residues_plddt`, `sae_features`, `protein_activations`, `per_residue_activations`, `pdb`, `cluster_rep_protein_hash`, and `folded_on_demand`.
Pass the returned `sequence` to the MCP tools for any further discovery.

`sae_features` entries require `feature_index`, `label`, `description`, and `value`; each residue region requires `start`, `end`, `peak_residue`, and `mean_activation`.
Sparse activations use COO objects with `indices`, `values`, and `shape`; every coordinate must be within its axis extent, and complete coordinate tuples must be unique.

For `esmc-6b-2024-12-sae-layer60-k64-codebook16384`, k64 is the SAE sparsifier, not API truncation.
It leaves at most 64 positive activations per residue, and the returned COO entries are the complete stored post-sparsification representation.
Omitted coordinates are zero in that representation, and uint8 storage quantization can round small positive values to zero.

## Features

The list endpoint has no pagination or filtering and returns all 16,384 entries in `data`.
Every item requires `feature_index`, `label`, and `description`.

Feature detail requires `feature_index`, `label`, `summary`, `description`, `uniref90_frequency`, `uniref90_idf`, `uniref90_max_activation`, and `threshold`.
Optional or defaulted fields are `activation_pattern`, `category`, `exemplar_protein_families`, `top_100_uniref_ids`, `top_swissprot_activations`, and `decoder_nearest_neighbors`.
The list endpoint's `description` currently contains the short summary for backward compatibility; detail `summary` and longform `description` are distinct.

## Thumbnails

The endpoint returns `image/png` for `plddt` and `pct-characterized`, with `Cache-Control: public, max-age=31536000, immutable` and `ETag: "{protein_hash}-{thumbnail_type}"`.
The ETag identifies the requested resource and is not a checksum of the PNG bytes.
The generated OpenAPI file incorrectly labels the empty `200` schema as `application/json`, so the script validates the returned PNG bytes.

## Batch lifecycle

`BatchProteinRequest` requires a nonempty `protein_hashes` list and deduplicates it to at most 500 entries.
The raw endpoint reports malformed hashes as per-protein `invalid_hash` errors; the script validates every entry locally and rejects the entire input when any hash is malformed.
Defaults are `topk_features=10`, `include_structure=true`, `include_cluster_info=true`, `include_sequence=true`, and both protein-level and per-residue feature data.
`include_features` may be `false`, `true`, or an object with `protein_level` and/or `per_residue`; an omitted sub-flag defaults to true, so `{}` enables both.

A small synchronous batch returns a `200` ZIP and an asynchronous batch returns a `202` `BatchProteinResponse`, even though the generated OpenAPI response table lists only `200 application/json`.
The job response requires only `status`, one of `pending`, `completed`, `cancelled`, `failed`, or `expired`; `job_id`, `poll_url`, `download_url`, `created_at`, `completed_count`, and `total_count` are optional.
A `202` submission still needs a usable `job_id` to be actionable.
Pending polling uses HTTP 202, a completed job uses HTTP 200 with a time-limited `download_url`, and an expired job uses HTTP 410.

Cancellation is idempotent and returns 204 for pending, completed, or cancelled jobs, and 404 for an unknown job.
Completed output remains available.
Preserve job state, reacquire ephemeral download URLs by polling, and validate the completed ZIP before publication.

## Confidence scaling and schema conflicts

Atlas JSON exposes `ptm`, `mean_plddt`, and `residues_plddt` on a 0 to 1 scale.
Embedded PDB B-factors carry residue-level pLDDT on the same 0 to 1 scale; pTM and mean pLDDT are not B-factor fields.
Multiply by 100 only for conventional presentation, and preserve the original wire scale.

The generated `BatchProteinRequest` schema resolves `include_features` only to the object schema even though its description explicitly supports booleans.
Thumbnails and batch delivery also carry incorrect OpenAPI media and status declarations.
Handle those explicitly as above, and do not invent aliases for documented JSON fields.

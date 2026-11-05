# Biohub API contract coverage

Verified against the public Biohub references on 2026-07-13 and reconciled with the official tutorial notebooks on 2026-07-14:

- [Managed API reference](https://biohub.ai/api-reference)
- [ESM Atlas overview](https://biohub.ai/esm/protein/atlas/api-docs/overview.html)
- [ESM Atlas API reference](https://biohub.ai/esm/protein/atlas/api-docs/api_reference.html)
- [ESM Atlas OpenAPI document](https://biohub.ai/esm/protein/atlas/api-docs/_static/openapi.json)
- [ESM Atlas concepts](https://biohub.ai/esm/protein/atlas/api-docs/concepts.html)
- [ESM Atlas FAQ](https://biohub.ai/esm/protein/atlas/api-docs/faqs.html)
- [ESM Atlas changelog](https://biohub.ai/esm/protein/atlas/api-docs/changelog.html)
- [ESM Atlas Swagger rendering](https://biohub.ai/esm/protein/atlas/api-docs/_static/api.html)
- [ESM Atlas worked examples](https://biohub.ai/esm/protein/atlas/api-docs/examples/index.html)

This document records the complete public endpoint inventory and the plugin surface that uses it. A documented endpoint that is outside this plugin's ESMC, ESMFold2, or Atlas scope is listed explicitly rather than silently treated as implemented.

## Managed API

All managed operations are `POST https://biohub.ai/api/v1/{operation}` with Bearer authentication and JSON request bodies. The public pages document request schemas, but not response schemas, success status tables, or error objects. Response normalization and fold artifact materialization therefore follow the pinned official `Biohub/esm` SDK plus captured contract tests, not an invented public-response schema. A successful `/fold` response must provide atom37 data with finite N, CA, and C coordinates for every biological residue; only an explicit `|` position on a full sequence-length track may use an all-null chain-break row.

The exhaustive request-field matrix is in [`managed-api-field-audit.md`](managed-api-field-audit.md): every nested field, requiredness, nullability, rendered default, bound/enum, plugin disposition, and public-page versus pinned-SDK discrepancy for all nine operations.

| Operation | Published request purpose | Plugin coverage |
| --- | --- | --- |
| `encode` | Encode `Tracks`, including a sequence track that may contain `_` masks | Direct managed request supported. Uses `inputs.sequence`, validates the mask-capable track, and accepts `potential_sequence_of_concern`. |
| `decode` | Decode token inputs for ESMC or ESM3 | Not exposed; ESM3/token decoding is outside the current plugin workflows. |
| `logits` | ESMC/ESM3 logits, embeddings, hidden states, and optional SAE features | ESMC JSON mode supported. Token envelope, output flags, hidden-layer bounds, concern flag, and the five published SAE checkpoint IDs are validated. Binary return mode and ESM3-only tracks are not exposed. |
| `generate` | ESM3 generation over semantic tracks | Not exposed; outside the current ESMC/ESMFold2 scope. |
| `generate_tensor` | ESM3 token-level generation | Not exposed; outside the current ESMC/ESMFold2 scope. |
| `forward_and_sample` | ESM3 forward pass and per-track sampling | Not exposed; outside the current ESMC/ESMFold2 scope. |
| `fold` | Sequence folding with optional MSA and confidence/output controls | Supported for the pinned managed ESMFold2 models. A non-null MSA uses the documented `{sequences, deletions?}` object. |
| `fold_all_atom` | Sequence/MSA folding or structured all-atom input | Supported for either the documented sequence path or `all_atom_input`; mixed biological inputs are rejected locally because the API says `all_atom_input` causes sequence/MSA to be ignored. |
| `inverse_fold` | ESM3 inverse folding from coordinates | Not exposed; outside the current ESMC/ESMFold2 scope. |

The managed validator deliberately requires an explicit supported model even where the service documents a default. That narrows the convenience surface for reproducible provenance without changing the wire contract. It also rejects an MSA for ESMFold2-Fast because the official SDK says that model ignores MSA conditioning; accepting it would misrepresent what was executed.

## ESM Atlas API

Atlas is a public, unauthenticated alpha API rooted at `https://biohub.ai/esm/protein/api/v1alpha1`. Every published operation is represented by the client.

| Method and path | Published contract used by the plugin |
| --- | --- |
| `GET /features` | Returns the 16,384 SAE feature summaries. Each entry requires `feature_index`, `label`, and `description`. |
| `GET /features/{feature_index}` | Returns detailed feature metadata for an index in `0..16383`. |
| `GET /clusters/{protein_hash}` | Returns the representative hash, size, characterization/coverage metrics, and member hashes. |
| `GET /proteins/{protein_hash}/thumbnail/{thumbnail_type}` | Returns a PNG for `plddt` or `pct-characterized`. |
| `GET /proteins/{protein_hash}` | Looks up the MD5-keyed record with feature controls and documented `fold_on_miss` behavior. The plugin opts out of the provider's implicit fold by default; an explicit fold first performs a non-folding lookup and requires the actual provider-returned sequence, validates its Atlas alphabet and MD5 binding, and enforces at most 699 residues before the folding request. `sequence_length` alone is insufficient. The response uses `sequence_length`; nonempty out-of-catalog `feature_indices` reach Atlas so its documented skip behavior applies, while returned in-catalog indices must exactly match caller order. An empty explicit selection is rejected because it is indistinguishable from omitted top-K mode on the wire. Top-K mode cannot return more than the requested count. Sparse COO coordinates must be in bounds and unique. |
| `POST /proteins/batch` | Accepts at most 500 unique hashes and returns either an immediate ZIP or an asynchronous job. Boolean, empty, and partial-object `include_features` forms are preserved. |
| `GET /proteins/batch/jobs/{job_id}` | Returns pending/completed/cancelled/failed/expired state; polling also handles the documented expired response. An omitted/null response `job_id` is bound locally from the requested path. |
| `DELETE /proteins/batch/jobs/{job_id}` | Requests idempotent job cancellation. |
| `GET /similarity-search` | Searches by sequence with top-k, feature, similarity, cluster-characterization, and cluster-info controls. Each hit requires `protein_hash`, `protein_accession`, `sequence_length`, and `similarity_score`. |

Nested Atlas schema failures preserve the complete decoded JSON response before any projected hit or record is validated. This matters for alpha-schema diagnostics: one malformed nested value must not discard the remaining ranked results from the evidence artifact. Malformed or resource-rejected wire bytes remain only in the bounded diagnostic because no complete decoded JSON value exists.

## Fresh public regression

After the fixes, a final fresh unauthenticated GB1 similarity search from the audited source on 2026-07-13 PDT returned HTTP 200 and all 10 requested ranked hits. Every hit carried `sequence_length`; none carried `protein_length`. The first hit remained `ccc9fef4029cc28fe101f059419ca401` at similarity `0.8239336436709238`, length 62, and cluster size 68. The run preserved the complete 439,332-byte decoded response, a normalized 10-hit result, 10 PDB artifacts, and one provider-call provenance record. Evidence SHA-256 values were `1ead41189f9f2cb0e2baeaf7a743609c8670febc93e5334690e9c205a29b3d7a` for the raw response, `0ec17f5c7f3fe2c952a588c23dab45eb91b5494470310d7c8ba979b14b4aec15` for the normalized result, and `3712ef377a45d0a2f9aa9e7d92761205a00b89c87699960b6970656af3a0b402` for provenance. This is execution evidence for the current wire behavior, not a replacement for the alpha API specification.

## Published-reference discrepancies

The plugin keeps these source discrepancies visible instead of silently choosing a different interpretation:

- Atlas OpenAPI permits similarity-search sequences through 2,048 residues, while the worked similarity-search example says 800. The client retains the conservative 800-residue limit.
- Atlas prose documents PNG thumbnails and synchronous ZIP/asynchronous JSON batch responses, while parts of the generated OpenAPI response media/status rendering are incomplete.
- The batch request property's description accepts boolean `include_features` values, while its generated schema resolves only to the object form. The client supports both the explicit boolean contract and optional object sub-flags.
- Atlas conceptual prose describes user-facing pLDDT on a 0-100 scale, while current API examples and live JSON expose normalized `mean_plddt` and `residues_plddt` values in 0-1. The client validates the actual API representation and records the scale.
- Managed `/logits` model tables contain two shortened `300`/`600` spellings, while the endpoint enum uses `300m`/`600m`. The plugin uses the endpoint's exact allowed model IDs.
- Managed fold pages show a scalar `lm_mask_pct` default of zero while describing model-specific defaults (`0.1` for Fast and `0.0` for full). The plugin pins the submitted value in reproducible starters.
- Managed SAE docs default `normalize_features` to true while the exact pinned official SDK requires false for the published 300M SAE. The plugin requires an explicit false value for that model instead of silently changing it.
- Managed MSA field tables omit headers, while the pinned SDK serializes non-empty A3M headers and Biohub's official paired-MSA tutorial requires `key=<taxonomy_id>` header tokens for cross-chain pairing. The plugin validates and preserves headers only on all-atom per-chain MSAs where pairing is meaningful; top-level single-chain managed MSA requests omit them from the wire. Managed all-atom docs separately omit RNA MSA while the SDK emits `msa:null`; that null compatibility sentinel is also removed before the direct wire request.
- Managed all-atom entity IDs are nullable, while the pinned local/Hugging Face SDK path requires iterable IDs. Null IDs are accepted only for managed requests.
- The managed pages omit response/status/error schemas. SDK-derived response fields and live-response tests are labeled accordingly rather than attributed to those pages.

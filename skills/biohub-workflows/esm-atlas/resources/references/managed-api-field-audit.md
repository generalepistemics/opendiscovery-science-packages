# Managed Biohub API field audit

Audited 2026-07-13 against every request field rendered on the nine current [Biohub managed API pages](https://biohub.ai/api-reference) and against the `Biohub/esm` source then pinned by this plugin; reconciled with the three official tutorial notebooks on 2026-07-14.
The plugin now pins `esm==3.4.1.post1`, built from [`Biohub/esm` tag `v3.4.1.post1`](https://github.com/Biohub/esm/tree/43b4548b86762edfa747b07d5f440aad3c33acee); the `FoldingConfig`, `LogitsConfig`, `SAEConfig`, and `ESMProtein` fields this audit relies on appear unchanged there when both source files are compared.
The public pages describe request bodies and a small number of request headers.
They do not publish success-response schemas, error schemas, or status-code tables.
This file therefore does not attribute SDK-derived response fields to the public request reference.

The `Presence / null / default` column transcribes the rendered page:

- `required` means the page marks the property required.
- `optional` means it is not marked required.
- `nullable` appears only where the rendered type explicitly includes `null`.
- `default none` means the page supplies no default. An empty rendered default is written as `""`, even where that conflicts with the declared type.

Plugin dispositions are request-side dispositions:

- **Supported**: accepted by the direct managed client, subject to the stated validation or normalization.
- **Narrowed**: part of the public contract, but deliberately constrained by the plugin for its ESMC/ESMFold2 scope or for deterministic provenance.
- **Not exposed**: audited here, but the endpoint or field is outside the plugin surface. This does not mean the public API lacks the capability.

Common transport behavior is `POST https://biohub.ai/api/v1/{operation}` with a Bearer credential and JSON request body. The plugin pins the origin, sends `Content-Type: application/json`, requests `Accept: application/json`, and allowlists only `encode`, `logits`, `fold`, and `fold_all_atom`.

## `encode`

Source: [`POST /api/v1/encode`](https://biohub.ai/api-reference/encode).

| JSON path | Public type / shape | Presence / null / default | Public bounds or values | Plugin disposition | Pinned-SDK or reference note |
| --- | --- | --- | --- | --- | --- |
| `model` | `string` | required; non-null; default none | `esmc-300m-2024-12`, `esmc-600m-2024-12`, `esmc-6b-2024-12`, `esm3-open-2024-03` | **Narrowed:** exact ESMC ID required; ESM3 rejected | SDK supports ESM3 and ESMC clients. The page does not permit a null/defaulted model. |
| `potential_sequence_of_concern` | `boolean` | optional; non-null; default `false` | none | **Supported** | SDK injects the same field from the protein input when posting. |
| `inputs` | `Tracks` object | required; non-null; default none | none | **Narrowed:** object required; only `sequence` accepted | Public `Tracks` does not mark any individual track required. |
| `inputs.sequence` | `string \| null` | optional; nullable; default none | `_` is the documented mask character | **Narrowed:** required nonempty ESMC sequence; mask-aware alphabet and conservative length checked | SDK sends this track directly. |
| `inputs.secondary_structure` | `string \| null` | optional; nullable; default none | 8-class DSSP string | **Not exposed** | ESM3 SDK request builder supports it; ESMC plugin mode does not. |
| `inputs.sasa` | `array[integer \| number \| null] \| null` | optional; nullable; default none | Page notes null padding and current infinity sentinel `1000` | **Not exposed** | The page renders two unnamed `variant` objects beneath the union; they are renderer artifacts, not JSON keys. SDK sends the numeric/null array. |
| `inputs.function` | `array[array[tuple]] \| null` | optional; nullable; default none | Each annotation is `(InterPro tag, start, end)`; positions are 1-indexed inclusive; InterPro 95.0 | **Not exposed** | SDK converts `FunctionAnnotation` values to tuples. The rendered type does not independently type the three tuple members. |
| `inputs.coordinates` | `array[array[array[number \| null]]] \| null`; documented `N x 37 x 3` | optional; nullable; default none | none | **Not exposed** | SDK converts NaNs to null before submission. The prose calls these N/CA/C coordinates while also declaring 37 atoms. |
| `inputs.plddt` | `array[number] \| null` | optional; nullable; default none | none | **Not exposed** | Present on public `Tracks`, but the pinned SDK encode request builder omits it. |
| `inputs.ptm` | `number \| null` | optional; nullable; default none | none | **Not exposed** | Present on public `Tracks`, but omitted by the pinned SDK encode request builder. |
| `inputs.crmsd` | `number \| null` | optional; nullable; default none | none | **Not exposed** | Described as generated-output metadata; omitted by the pinned SDK encode request builder. |
| `inputs.globularity` | `number \| null` | optional; nullable; default none | none | **Not exposed** | Described as generated-output metadata; omitted by the pinned SDK encode request builder. |
| `inputs.interface` | `array[string] \| null` | optional; nullable; default none | none | **Not exposed** | Present on the page, but omitted by the pinned SDK encode request builder. |
| `inputs.interface_ptm` | `number \| null` | optional; nullable; default none | none | **Not exposed** | Present on the page, but omitted by the pinned SDK encode request builder. |
| `inputs.pae` | `array[array[number]] \| null`; `L x L` | optional; nullable; default none | none | **Not exposed** | Present on the page, but omitted by the pinned SDK encode request builder. |

## `decode`

Source: [`POST /api/v1/decode`](https://biohub.ai/api-reference/decode).
The complete endpoint is **not exposed** by this plugin.

| JSON path | Public type / shape | Presence / null / default | Public bounds or values | Plugin disposition | Pinned-SDK or reference note |
| --- | --- | --- | --- | --- | --- |
| `model` | `string` | required; non-null; default none | `esmc-300m-2024-12`, `esmc-600m-2024-12`, `esmc-6b-2024-12`, `esm3-open-2024-03` | **Not exposed** | SDK supports the listed ESM3/ESMC clients. |
| `potential_sequence_of_concern` | `boolean` | optional; non-null; default `false` | none | **Not exposed** | SDK injects the field during transport. |
| `inputs` | `Tokens` object | required; non-null; default none | none | **Not exposed** | SDK validates an `ESMProteinTensor` before serializing it. |
| `inputs.sequence` | `array[integer] \| null` | optional; nullable; default none | none | **Not exposed** | SDK serializes the sequence tensor. |
| `inputs.coordinates` | `array[array[array[number \| null]]] \| null`; documented `N x 37 x 3` | optional; nullable; default none | none | **Not exposed** | SDK converts NaNs to null. The N/CA/C prose and 37-atom shape are internally imprecise. |
| `inputs.structure` | `array[integer] \| null` | optional; nullable; default none | none | **Not exposed** | SDK serializes structure tokens. |
| `inputs.secondary_structure` | `array[integer] \| null` | optional; nullable; default none | none | **Not exposed** | SDK serializes secondary-structure tokens. |
| `inputs.sasa` | `array[integer \| null] \| null` | optional; nullable; default none | none | **Not exposed** | SDK serializes SASA tokens. |
| `inputs.function` | `array[array[integer]] \| null` | optional; nullable; default none | none | **Not exposed** | SDK serializes function tokens. |
| `inputs.residue_annotation` | `array[array[integer]] \| null` | optional; nullable; default none | none | **Not exposed** | Wire field is singular; the SDK object property is `residue_annotations`. |

## `logits`

Source: [`POST /api/v1/logits`](https://biohub.ai/api-reference/logits).

| JSON path | Public type / shape | Presence / null / default | Public bounds or values | Plugin disposition | Pinned-SDK or reference note |
| --- | --- | --- | --- | --- | --- |
| Header `return-bytes` | `string` | optional; non-null; default `false` | none | **Narrowed:** not configurable; plugin uses JSON mode | SDK can negotiate binary/tensor serialization. |
| Header `accept` | `string \| null` | optional; nullable; default none | none | **Narrowed:** fixed to `application/json` | SDK accepts JSON or its tensor/pickle media types. |
| `model` | `string` | required; non-null; default none | ESMC 300M/600M/6B IDs or `esm3-open-2024-03` | **Narrowed:** exact ESMC ID required; ESM3 rejected | The hidden-layer prose shortens two IDs to `esmc-300-...` and `esmc-600-...`; the endpoint enum contains the canonical `300m`/`600m` IDs used by the plugin. |
| `potential_sequence_of_concern` | `boolean` | optional; non-null; default `false` | none | **Supported** | SDK injects it during transport. |
| `inputs` | `Tokens` object | required; non-null; default none | none | **Narrowed:** only sequence tokens accepted | none |
| `inputs.sequence` | `array[integer] \| null` | optional; nullable; default none | Public page gives no token-ID or envelope bounds | **Narrowed:** required; 3-2048 tokens; IDs `0..32`; BOS `0`, EOS `2`, no interior BOS/EOS | Bounds and special IDs come from the exact pinned ESMC tokenizer rather than the page. |
| `inputs.coordinates` | `array[array[array[number \| null]]] \| null`; documented `N x 37 x 3` | optional; nullable; default none | none | **Not exposed** | ESM3 SDK supports it; ESMC request builder and plugin do not. |
| `inputs.structure` | `array[integer] \| null` | optional; nullable; default none | none | **Not exposed** | ESM3-only in this plugin context. |
| `inputs.secondary_structure` | `array[integer] \| null` | optional; nullable; default none | none | **Not exposed** | ESM3-only in this plugin context. |
| `inputs.sasa` | `array[integer \| null] \| null` | optional; nullable; default none | none | **Not exposed** | ESM3-only in this plugin context. |
| `inputs.function` | `array[array[integer]] \| null` | optional; nullable; default none | none | **Not exposed** | ESM3-only in this plugin context. |
| `inputs.residue_annotation` | `array[array[integer]] \| null` | optional; nullable; default none | none | **Not exposed** | ESM3-only in this plugin context. |
| `logits_config` | `LogitsConfig` object | required; non-null; default none | none | **Supported with ESMC narrowing** | Plugin requires at least one actual output; the public object can otherwise contain all-false defaults. |
| `logits_config.sequence` | `boolean` | optional; non-null; default `false` | none | **Supported** | Returns ESM3/ESMC sequence logits. |
| `logits_config.structure` | `boolean` | optional; non-null; default `false` | Page explicitly says not supported on Forge/Biohub | **Not exposed:** field rejected even when false | SDK type retains it for local use, but managed Forge cannot return it. |
| `logits_config.secondary_structure` | `boolean` | optional; non-null; default `false` | Page explicitly says not supported on Forge/Biohub | **Not exposed:** field rejected even when false | Same local-versus-managed distinction as `structure`. |
| `logits_config.sasa` | `boolean` | optional; non-null; default `false` | Page explicitly says not supported on Forge/Biohub | **Not exposed:** field rejected even when false | Same local-versus-managed distinction as `structure`. |
| `logits_config.function` | `boolean` | optional; non-null; default `false` | Page explicitly says not supported on Forge/Biohub | **Not exposed:** field rejected even when false | Same local-versus-managed distinction as `structure`. |
| `logits_config.residue_annotations` | `boolean` | optional; non-null; default `false` | ESM3 only | **Not exposed** | Config field is plural; input token field is singular. |
| `logits_config.return_embeddings` | `boolean` | optional; non-null; default `false` | none | **Supported** | Per-residue/final hidden-state embeddings. |
| `logits_config.return_mean_embedding` | `boolean` | optional; non-null; default `false` | none | **Supported** | none |
| `logits_config.return_hidden_states` | `boolean` | optional; non-null; default `false` | ESMC and ESM3 except Large | **Supported** | Plugin applies model-specific `ith_hidden_layer` constraints. |
| `logits_config.return_mean_hidden_states` | `boolean` | optional; non-null; default `false` | ESMC and ESM3 except Large | **Supported** | Public shape is `[B, n_layers + 1, D]`. |
| `logits_config.ith_hidden_layer` | `integer` | optional; non-null; default `-1` | `-1` or `0..30` (300M), `0..36` (600M), `0..80` (6B); `-1` unsupported for 6B and ESM3 when hidden states requested | **Supported:** bounds checked; a nonnegative layer requires a hidden-state output | Public prose names several ESM3 variants not present in this endpoint's model enum. |
| `logits_config.sae_config` | `SAEConfig \| null` | optional; nullable; default none | ESMC only | **Supported** | Generic raw JSON mode preserves SAE serialization; the SDK has dedicated base64 tensor decoding. |
| `logits_config.sae_config.models` | `array[string]` | optional; non-null; default none | Five published SAE IDs: one 300M, two 600M, two 6B | **Narrowed:** nonempty, unique, exact IDs, and base-model match required | SDK defaults this list to empty and also has a deprecated singular `model` property that is not part of the public wire schema. |
| `logits_config.sae_config.normalize_features` | `boolean` | optional; non-null; default `true` | none | **Narrowed:** 300M SAE requires explicit `false` | Exact SDK rejects normalized 300M SAE features, despite the public true default. |

## `generate`

Source: [`POST /api/v1/generate`](https://biohub.ai/api-reference/generate).
The complete ESM3 endpoint is **not exposed** by this plugin.

| JSON path | Public type / shape | Presence / null / default | Public bounds or values | Plugin disposition | Pinned-SDK or reference note |
| --- | --- | --- | --- | --- | --- |
| `model` | `string` | required; non-null; default none | `esm3-open-2024-03` | **Not exposed** | SDK ESM3 client supplies its configured model. |
| `potential_sequence_of_concern` | `boolean` | optional; non-null; default `false` | none | **Not exposed** | SDK injects the field during transport. |
| `track` | `string` | required; non-null; default none | Description lists `sequence`, `structure`, `secondary_structure`, `sasa`, `function`; no formal enum is rendered | **Not exposed** | SDK `GenerationConfig.track` defaults to an empty string and does not attach an attrs enum validator. |
| `invalid_ids` | `array[integer]` | optional; non-null; rendered default `""` | none | **Not exposed** | Declared type conflicts with the rendered empty-string default; SDK default is an empty sequence. |
| `schedule` | `string` | optional; non-null; default `cosine` | `cosine`, `linear` | **Not exposed** | SDK enforces this enum. |
| `strategy` | `string` | optional; non-null; default `random` | `random`, `entropy` | **Not exposed** | SDK enforces this enum. |
| `num_steps` | `integer` | optional; non-null; default `20` | `[1, 100]`; must not exceed sequence length | **Not exposed** | SDK clamps a value above input sequence length rather than failing it. |
| `temperature` | `number` | optional; non-null; default `0.5` | `[0, infinity)` | **Not exposed** | **Discrepancy:** pinned `GenerationConfig` defaults to `1.0`, so omission differs between direct-page and SDK construction. |
| `temperature_annealing` | `boolean` | optional; non-null; default `true` | none | **Not exposed** | SDK default is also true. |
| `top_p` | `number` | optional; non-null; default `1` | `(0, 1]` | **Not exposed** | SDK default is 1.0. |
| `condition_on_coordinates_only` | `boolean` | optional; non-null; default `true` | none | **Not exposed** | SDK default is true. |
| `inputs` | `Tracks` object | required; non-null; default none | none | **Not exposed** | SDK serializes an `ESMProtein`. |
| `inputs.sequence` | `string \| null` | optional; nullable; default none | `_` may mark masked positions | **Not exposed** | SDK sends it directly. |
| `inputs.secondary_structure` | `string \| null` | optional; nullable; default none | 8-class DSSP string | **Not exposed** | SDK sends it directly. |
| `inputs.sasa` | `array[integer \| number \| null] \| null` | optional; nullable; default none | Null padding; current infinity sentinel `1000` | **Not exposed** | Two unnamed rendered `variant` children are not JSON properties. |
| `inputs.function` | `array[array[tuple]] \| null` | optional; nullable; default none | `(InterPro tag, 1-indexed inclusive start, end)`; InterPro 95.0 | **Not exposed** | SDK converts function annotations to tuples. |
| `inputs.coordinates` | `array[array[array[number \| null]]] \| null`; documented `N x 37 x 3` | optional; nullable; default none | none | **Not exposed** | SDK converts NaNs to null. |
| `inputs.plddt` | `array[number] \| null` | optional; nullable; default none | none | **Not exposed** | Public `Tracks` permits it, but pinned generate request builder omits it. |
| `inputs.ptm` | `number \| null` | optional; nullable; default none | none | **Not exposed** | Public `Tracks` permits it, but pinned generate request builder omits it. |
| `inputs.crmsd` | `number \| null` | optional; nullable; default none | none | **Not exposed** | Described as generate output metadata; pinned request builder omits it. |
| `inputs.globularity` | `number \| null` | optional; nullable; default none | none | **Not exposed** | Described as generate output metadata; pinned request builder omits it. |
| `inputs.interface` | `array[string] \| null` | optional; nullable; default none | none | **Not exposed** | Public `Tracks` permits it, but pinned request builder omits it. |
| `inputs.interface_ptm` | `number \| null` | optional; nullable; default none | none | **Not exposed** | Public `Tracks` permits it, but pinned request builder omits it. |
| `inputs.pae` | `array[array[number]] \| null`; `L x L` | optional; nullable; default none | none | **Not exposed** | Public `Tracks` permits it, but pinned request builder omits it. |
| `only_compute_backbone_rmsd` | `boolean` | optional; non-null; default `false` | Affects returned cRMSD | **Not exposed** | SDK includes this for decoded-track `generate`, but not for token-level `generate_tensor`, matching the pages. |

## `generate_tensor`

Source: [`POST /api/v1/generate_tensor`](https://biohub.ai/api-reference/generate_tensor).
The complete ESM3 endpoint is **not exposed** by this plugin.

| JSON path | Public type / shape | Presence / null / default | Public bounds or values | Plugin disposition | Pinned-SDK or reference note |
| --- | --- | --- | --- | --- | --- |
| `model` | `string` | required; non-null; default none | `esm3-open-2024-03` | **Not exposed** | SDK ESM3 client supplies its configured model. |
| `potential_sequence_of_concern` | `boolean` | optional; non-null; default `false` | none | **Not exposed** | SDK injects the field during transport. |
| `track` | `string` | required; non-null; default none | Description lists `sequence`, `structure`, `secondary_structure`, `sasa`, `function`; no formal enum is rendered | **Not exposed** | Same `GenerationConfig.track` behavior as `generate`. |
| `invalid_ids` | `array[integer]` | optional; non-null; rendered default `""` | none | **Not exposed** | Declared type conflicts with rendered default; SDK default is an empty sequence. |
| `schedule` | `string` | optional; non-null; default `cosine` | `cosine`, `linear` | **Not exposed** | SDK enforces this enum. |
| `strategy` | `string` | optional; non-null; default `random` | `random`, `entropy` | **Not exposed** | SDK enforces this enum. |
| `num_steps` | `integer` | optional; non-null; default `20` | `[1, 100]`; must not exceed sequence length | **Not exposed** | SDK clamps above-length values before submission. |
| `temperature` | `number` | optional; non-null; default `0.5` | `[0, infinity)` | **Not exposed** | **Discrepancy:** pinned `GenerationConfig` default is `1.0`. |
| `temperature_annealing` | `boolean` | optional; non-null; default `true` | none | **Not exposed** | SDK default is true. |
| `top_p` | `number` | optional; non-null; default `1` | `(0, 1]` | **Not exposed** | SDK default is 1.0. |
| `condition_on_coordinates_only` | `boolean` | optional; non-null; default `true` | none | **Not exposed** | SDK default is true. |
| `inputs` | `Tokens` object | required; non-null; default none | none | **Not exposed** | SDK serializes an `ESMProteinTensor`. |
| `inputs.sequence` | `array[integer] \| null` | optional; nullable; default none | none | **Not exposed** | SDK serializes the sequence tensor. |
| `inputs.coordinates` | `array[array[array[number \| null]]] \| null`; documented `N x 37 x 3` | optional; nullable; default none | none | **Not exposed** | SDK converts NaNs to null. |
| `inputs.structure` | `array[integer] \| null` | optional; nullable; default none | none | **Not exposed** | SDK serializes structure tokens. |
| `inputs.secondary_structure` | `array[integer] \| null` | optional; nullable; default none | none | **Not exposed** | SDK serializes secondary-structure tokens. |
| `inputs.sasa` | `array[integer \| null] \| null` | optional; nullable; default none | none | **Not exposed** | SDK serializes SASA tokens. |
| `inputs.function` | `array[array[integer]] \| null` | optional; nullable; default none | none | **Not exposed** | SDK serializes function tokens. |
| `inputs.residue_annotation` | `array[array[integer]] \| null` | optional; nullable; default none | none | **Not exposed** | SDK object property is plural; wire field is singular. |

## `forward_and_sample`

Source: [`POST /api/v1/forward_and_sample`](https://biohub.ai/api-reference/forward_and_sample). The complete ESM3 endpoint is **not exposed** by this plugin. In the table, `{sequence|structure|secondary_structure|sasa|function}` is documentation shorthand that expands to all five separately named JSON properties; it is not literal wire syntax.

| JSON path | Public type / shape | Presence / null / default | Public bounds or values | Plugin disposition | Pinned-SDK or reference note |
| --- | --- | --- | --- | --- | --- |
| Header `accept` | `string \| null` | optional; nullable; default none | none | **Not exposed** | SDK requests its tensor/pickle media type with JSON fallback. |
| `model` | `string` | required; non-null; default none | `esm3-open-2024-03` | **Not exposed** | SDK ESM3 client supplies its configured model. |
| `potential_sequence_of_concern` | `boolean` | optional; non-null; default `false` | none | **Not exposed** | SDK injects the field during transport. |
| `inputs` | `Tokens` object | required; non-null; default none | none | **Not exposed** | SDK validates and serializes an `ESMProteinTensor`. |
| `inputs.sequence` | `array[integer] \| null` | optional; nullable; default none | none | **Not exposed** | none |
| `inputs.coordinates` | `array[array[array[number \| null]]] \| null`; documented `N x 37 x 3` | optional; nullable; default none | none | **Not exposed** | SDK converts NaNs to null. |
| `inputs.structure` | `array[integer] \| null` | optional; nullable; default none | none | **Not exposed** | none |
| `inputs.secondary_structure` | `array[integer] \| null` | optional; nullable; default none | none | **Not exposed** | none |
| `inputs.sasa` | `array[integer \| null] \| null` | optional; nullable; default none | none | **Not exposed** | none |
| `inputs.function` | `array[array[integer]] \| null` | optional; nullable; default none | none | **Not exposed** | none |
| `inputs.residue_annotation` | `array[array[integer]] \| null` | optional; nullable; default none | none | **Not exposed** | SDK object property is plural; wire field is singular. |
| `sampling_config` | `SamplingConfig` object | required; non-null; default none | none | **Not exposed** | SDK builds this from five optional `SamplingTrackConfig` properties. |
| `sampling_config.sequence` | `PerTrackSamplingConfig \| null` | optional; nullable; default none | none | **Not exposed** | Same child contract as the other four track properties. |
| `sampling_config.structure` | `PerTrackSamplingConfig \| null` | optional; nullable; default none | none | **Not exposed** | Same child contract as the other four track properties. |
| `sampling_config.secondary_structure` | `PerTrackSamplingConfig \| null` | optional; nullable; default none | none | **Not exposed** | Same child contract as the other four track properties. |
| `sampling_config.sasa` | `PerTrackSamplingConfig \| null` | optional; nullable; default none | none | **Not exposed** | Same child contract as the other four track properties. |
| `sampling_config.function` | `PerTrackSamplingConfig \| null` | optional; nullable; default none | none | **Not exposed** | Same child contract as the other four track properties. |
| `sampling_config.{sequence\|structure\|secondary_structure\|sasa\|function}.temperature` | `number` | optional; non-null; default `1` | `[0, infinity)` | **Not exposed** | SDK default is 1.0. |
| `sampling_config.{sequence\|structure\|secondary_structure\|sasa\|function}.top_p` | `number` | optional; non-null; default `1` | `(0, 1]` | **Not exposed** | SDK default is 1.0. |
| `sampling_config.{sequence\|structure\|secondary_structure\|sasa\|function}.only_sample_masked_tokens` | `boolean` | optional; non-null; default `true` | none | **Not exposed** | SDK type defaults true. Its tokenizer-derived helper uses false for secondary structure, SASA, and function because their mask/pad semantics differ. |
| `sampling_config.{sequence\|structure\|secondary_structure\|sasa\|function}.invalid_ids` | `array[integer]` | optional; non-null; rendered default `""` | none | **Not exposed** | Declared type conflicts with rendered default; SDK type defaults to an empty sequence and helper code fills tokenizer-invalid IDs. |
| `sampling_config.{sequence\|structure\|secondary_structure\|sasa\|function}.topk_logprobs` | `integer` | optional; non-null; default `0` | No public range | **Not exposed** | Pinned SDK validation imposes a per-track maximum of 32; that is SDK-derived, not stated on the page. |
| `embedding_config` | `EmbeddingConfig \| null` | optional; nullable; default none | none | **Not exposed** | SDK wire builder always sends an object derived from `SamplingConfig` embedding flags. |
| `embedding_config.sequence` | `boolean` | optional; non-null; default `false` | none | **Not exposed** | Maps from SDK `return_mean_embedding`. |
| `embedding_config.per_residue` | `boolean` | optional; non-null; default `false` | none | **Not exposed** | Maps from SDK `return_per_residue_embeddings`. |

## `fold`

Source: [`POST /api/v1/fold`](https://biohub.ai/api-reference/fold).

| JSON path | Public type / shape | Presence / null / default | Public bounds or values | Plugin disposition | Pinned-SDK or reference note |
| --- | --- | --- | --- | --- | --- |
| `model` | `string \| null` | optional; nullable; field default none; endpoint description says Fast is the default | `esm3-open-2024-03`, `esmfold2-fast-2026-05`, `esmfold2-2026-05`, `null` | **Narrowed:** an exact ESMFold2 managed ID is required; ESM3/null omitted-model routing rejected | Explicit selection records the actual model. |
| `potential_sequence_of_concern` | `boolean` | optional; non-null; default `false` | none | **Supported** | SDK injects the field during transport. |
| `sequence` | `string \| null` | optional; nullable; default none | none | **Narrowed:** required nonempty protein sequence; plugin validates chain separators and alphabet | SDK fold method requires a sequence string. Public nullability is broader than useful ESMFold2 execution. |
| `msa` | `MSA \| null` | optional; nullable; default none | ESMFold2 only | **Supported for the full model; narrowed to one sequence chain; rejected for Fast** | Pinned SDK says Fast ignores MSA conditioning; plugin fails rather than silently misrepresenting it. |
| `msa.sequences` | `array[string]` | required when `msa` is non-null; non-null; default none | none | **Supported:** nonempty equal-width rows; ungapped first row must equal query | Plugin validation is stricter than the page's bare string-array type. |
| `msa.deletions` | `array[array[number]] \| null` | optional; nullable; default none | Shape `(depth, query_length)` | **Supported:** finite, nonnegative matrix matching MSA depth/width | none |
| `msa.headers` `[pinned-SDK compatibility input]` | Not listed publicly | optional SDK field | One string per MSA row | **Normalized:** validated then removed from this single-chain managed request | Cross-chain pairing cannot apply to the top-level single-chain `/fold` input. All-atom per-chain headers are handled separately below. |
| `num_loops` | `integer` | optional; non-null; default `20` | `[0, 20]` | **Supported:** integer/range checked when supplied | SDK default is 20. |
| `num_sampling_steps` | `integer` | optional; non-null; default `100` | `[1, 100]` | **Supported:** integer/range checked when supplied | SDK default is 100. |
| `lm_dropout` | `number` | optional; non-null; default `0.3` | `[0, 1]` | **Supported:** numeric/range checked when supplied | SDK default is 0.3. |
| `lm_mask_pct` | `number` | optional; non-null; rendered default `0` | `[0, 1]`; description says omitted value is `0.1` for Fast and `0.0` for full | **Supported:** numeric/range checked; plugin does not inject a default into generic requests | SDK represents omission as `None` and resolves it model-specifically, matching the prose rather than the scalar rendered default. Reproducible starters submit a value. |
| `msa_max_depth` | `integer \| null` | optional; nullable; default `1024` | `[1, 16384]` when non-null; null disables inference subsampling | **Supported:** null or bounded integer | SDK default is 1024. |
| `msa_column_mask_rate` | `number` | optional; non-null; default `0.1` | `[0, 1]` | **Supported:** numeric/range checked when supplied | SDK default is 0.1. |
| `include_distogram` | `boolean` | optional; non-null; default `false` | ESMFold2 only | **Supported request flag** | Public page does not define the response tensor schema; SDK response handling is the secondary source. |
| `include_pae` | `boolean` | optional; non-null; default `false` | ESMFold2 only | **Supported request flag** | Public page describes PAE inclusion but does not publish its success-response schema. |
| `include_pair_chains_iptm` | `boolean` | optional; non-null; default `false` | ESMFold2 only | **Supported request flag** | Pinned fold SDK sends this flag and reads `pair_chains_iptm`. |
| `include_embeddings` | `boolean` | optional; non-null; default `false` | ESMFold2 only | **Supported request flag** | Pinned SDK maps returned fields to sequence and pair-pooled embeddings; the page does not publish response field names/shapes. |

## `fold_all_atom`

Source: [`POST /api/v1/fold_all_atom`](https://biohub.ai/api-reference/fold_all_atom). The public endpoint offers either the top-level sequence/MSA path or a structured `all_atom_input`. Variant labels such as `ProteinInput` below identify union members inside `all_atom_input.sequences[]`; they are not literal JSON keys.

### Top-level fields

| JSON path | Public type / shape | Presence / null / default | Public bounds or values | Plugin disposition | Pinned-SDK or reference note |
| --- | --- | --- | --- | --- | --- |
| `model` | `string \| null` | optional; nullable; field default none; endpoint description says Fast is the default | `esmfold2-fast-2026-05`, `esmfold2-2026-05`, `null` | **Narrowed:** exact ESMFold2 managed ID required | Explicit selection records the actual model. |
| `potential_sequence_of_concern` | `boolean` | optional; non-null; default `false` | none | **Supported** | SDK injects the field during transport. |
| `sequence` | `string \| null` | optional; nullable; default none | none | **Supported alternative:** required when `all_atom_input` is absent; alphabet/chain separators validated | Pinned SDK convenience method does not expose this documented all-atom sequence path. |
| `msa` | `MSA \| null` | optional; nullable; default none | none | **Supported with full model on a single sequence chain; rejected for Fast** | Applies only to the top-level sequence alternative. |
| `msa.sequences` | `array[string]` | required when `msa` is non-null; non-null; default none | none | **Supported:** equal-width rows and query match validated | none |
| `msa.deletions` | `array[array[number]] \| null` | optional; nullable; default none | Shape `(depth, query_length)` | **Supported:** finite nonnegative matching matrix | none |
| `msa.headers` `[pinned-SDK compatibility input]` | Not listed publicly | optional SDK field | One string per row | **Normalized:** validated then removed from this top-level single-chain alternative | Cross-chain pairing uses the all-atom per-chain form, whose headers are preserved below. |
| `num_loops` | `integer` | optional; non-null; default `20` | `[0, 20]` | **Supported:** integer/range checked | SDK default is 20. |
| `num_sampling_steps` | `integer` | optional; non-null; default `100` | `[1, 100]` | **Supported:** integer/range checked | SDK default is 100. |
| `lm_dropout` | `number` | optional; non-null; default `0.3` | `[0, 1]` | **Supported:** numeric/range checked | SDK default is 0.3. |
| `lm_mask_pct` | `number` | optional; non-null; rendered default `0` | `[0, 1]`; prose says omitted value is model-specific (`0.1` Fast, `0.0` full) | **Supported:** checked when present; no generic default injected | SDK uses `None` and resolves the model-specific value. |
| `msa_max_depth` | `integer \| null` | optional; nullable; default `1024` | `[1, 16384]` when non-null | **Supported** | Null disables inference-time MSA subsampling. |
| `msa_column_mask_rate` | `number` | optional; non-null; default `0.1` | `[0, 1]` | **Supported** | SDK default is 0.1. |
| `include_distogram` | `boolean` | optional; non-null; default `false` | none | **Supported request flag** | Pinned SDK sends it and reads `distogram`; response schema is not public. |
| `include_pae` | `boolean` | optional; non-null; default `false` | none | **Supported request flag** | Response schema is not public. |
| `include_pair_chains_iptm` | `boolean` | optional; non-null; default `false` | none | **Supported request flag** | **Discrepancy:** pinned `_process_fold_all_atom_request` omits this field and its result object has no pair-chain member, although the public page lists it. Direct plugin requests retain it. |
| `all_atom_input` | `FoldAllAtomInput \| null` | optional; nullable; default none | Page says it causes top-level sequence/MSA to be ignored | **Supported alternative; narrowed:** mixed `all_atom_input` and sequence/MSA is rejected instead of silently discarding fields | Pinned convenience SDK supports only this structured path. |
| `include_embeddings` | `boolean` | optional; non-null; default `false` | none | **Supported request flag** | SDK reads sequence and pair-pooled embedding fields; response schema is not public. |

### `all_atom_input.sequences` and entity variants

| JSON path | Public type / shape | Presence / null / default | Public bounds or values | Plugin disposition | Pinned-SDK or reference note |
| --- | --- | --- | --- | --- | --- |
| `all_atom_input.sequences` | `array[ProteinInput \| RNAInput \| DNAInput \| LigandInput]` | required when `all_atom_input` is non-null; non-null; default none | none | **Supported:** must be nonempty | none |
| `all_atom_input.sequences[].ProteinInput.id` | `string \| array[string] \| null` | optional; nullable; default none | none | **Supported managed input:** nonempty unique strings when present | Pinned SDK dataclass types ID as non-null `str \| list[str]`; nullable public IDs are a managed-only compatibility path. |
| `all_atom_input.sequences[].ProteinInput.sequence` | `string` | required; non-null; default none | none | **Supported:** nonempty protein alphabet validated | none |
| `all_atom_input.sequences[].ProteinInput.msa` | `MSA \| null` | optional; nullable; default none | none | **Supported for full model; rejected for Fast** | SDK accepts `MSA` or null. |
| `all_atom_input.sequences[].ProteinInput.msa.sequences` | `array[string]` | required when protein MSA is non-null; non-null; default none | none | **Supported:** equal-width rows and ungapped-query match | none |
| `all_atom_input.sequences[].ProteinInput.msa.deletions` | `array[array[number]] \| null` | optional; nullable; default none | Shape `(depth, query_length)` | **Supported:** finite nonnegative matching matrix | none |
| `all_atom_input.sequences[].ProteinInput.msa.headers` `[pinned-SDK compatibility input]` | Not listed publicly | optional SDK field | One string per row | **Supported from the pinned SDK:** validated and preserved for the full model | Pinned `MSA.state_dict()` serializes it. The official paired-complex tutorial pairs rows across chains by matching `key=<taxonomy_id>` header tokens. |
| `all_atom_input.sequences[].ProteinInput.modifications` | `array[Modification] \| null` | optional; nullable; default none | none | **Supported** | SDK `Modification` also has an optional `smiles` attribute, but the official serializer does not send it and the public wire schema omits it. |
| `all_atom_input.sequences[].ProteinInput.modifications[].position` | `integer` | required per modification; non-null; default none | Zero-indexed position | **Supported:** checked against sequence length | none |
| `all_atom_input.sequences[].ProteinInput.modifications[].ccd` | `string` | required per modification; non-null; default none | CCD code | **Supported:** nonempty string required | none |
| `all_atom_input.sequences[].ProteinInput.type` | `string` | required; non-null; default none | No formal enum rendered | **Narrowed:** must equal `protein` | SDK serializer emits `protein`. |
| `all_atom_input.sequences[].RNAInput.id` | `string \| array[string] \| null` | optional; nullable; default none | none | **Supported managed input:** nonempty unique strings when present | Pinned SDK dataclass types it non-null. |
| `all_atom_input.sequences[].RNAInput.sequence` | `string` | required; non-null; default none | none | **Supported:** RNA alphabet validated | none |
| `all_atom_input.sequences[].RNAInput.msa` `[SDK compatibility input]` | Not listed publicly | SDK serializer emits null when unset | none | **Normalized:** only null accepted for managed input, then removed; non-null rejected | Pinned `RNAInput` includes MSA even though the public RNA variant does not. |
| `all_atom_input.sequences[].RNAInput.modifications` | `array[Modification] \| null` | optional; nullable; default none | none | **Supported** | Same serializer caveat about untransmitted modification `smiles`. |
| `all_atom_input.sequences[].RNAInput.modifications[].position` | `integer` | required per modification; non-null; default none | Zero-indexed position | **Supported:** checked against sequence length | none |
| `all_atom_input.sequences[].RNAInput.modifications[].ccd` | `string` | required per modification; non-null; default none | CCD code | **Supported:** nonempty string required | none |
| `all_atom_input.sequences[].RNAInput.type` | `string` | required; non-null; default none | No formal enum rendered | **Narrowed:** must equal `rna` | SDK serializer emits `rna`. |
| `all_atom_input.sequences[].DNAInput.id` | `string \| array[string] \| null` | optional; nullable; default none | none | **Supported managed input:** nonempty unique strings when present | Pinned SDK dataclass types it non-null. |
| `all_atom_input.sequences[].DNAInput.sequence` | `string` | required; non-null; default none | none | **Supported:** DNA alphabet validated | none |
| `all_atom_input.sequences[].DNAInput.modifications` | `array[Modification] \| null` | optional; nullable; default none | none | **Supported** | Same serializer caveat about untransmitted modification `smiles`. |
| `all_atom_input.sequences[].DNAInput.modifications[].position` | `integer` | required per modification; non-null; default none | Zero-indexed position | **Supported:** checked against sequence length | none |
| `all_atom_input.sequences[].DNAInput.modifications[].ccd` | `string` | required per modification; non-null; default none | CCD code | **Supported:** nonempty string required | none |
| `all_atom_input.sequences[].DNAInput.type` | `string` | required; non-null; default none | No formal enum rendered | **Narrowed:** must equal `dna` | SDK serializer emits `dna`. |
| `all_atom_input.sequences[].LigandInput.id` | `string \| array[string] \| null` | optional; nullable; default none | none | **Supported managed input:** nonempty unique strings when present | Pinned SDK dataclass types it non-null. |
| `all_atom_input.sequences[].LigandInput.smiles` | `string \| null` | optional; nullable; default none | none | **Narrowed:** exactly one nonempty `smiles` or `ccd` representation required | Public page and SDK dataclass permit both properties to be null independently. |
| `all_atom_input.sequences[].LigandInput.ccd` | `array[string] \| null` | optional; nullable; default none | none | **Narrowed:** exactly one nonempty `smiles` or `ccd` representation required | Each CCD entry must be nonempty. |
| `all_atom_input.sequences[].LigandInput.type` | `string` | required; non-null; default none | No formal enum rendered | **Narrowed:** must equal `ligand` | SDK serializer emits `ligand`. |

### Bonds and conditioning

| JSON path | Public type / shape | Presence / null / default | Public bounds or values | Plugin disposition | Pinned-SDK or reference note |
| --- | --- | --- | --- | --- | --- |
| `all_atom_input.covalent_bonds` | `array[CovalentBond] \| null` | optional; nullable; default none | none | **Supported:** if non-null, plugin requires a nonempty list | SDK dataclass uses the same six endpoint fields. |
| `all_atom_input.covalent_bonds[].chain_id1` | `string` | required per bond; non-null; default none | none | **Supported:** must reference an input chain | none |
| `all_atom_input.covalent_bonds[].res_idx1` | `integer` | required per bond; non-null; default none | No public range | **Narrowed:** nonnegative and within known chain length | none |
| `all_atom_input.covalent_bonds[].atom_idx1` | `integer` | required per bond; non-null; default none | No public range | **Narrowed:** nonnegative | Public page does not define atom-index bounds. |
| `all_atom_input.covalent_bonds[].chain_id2` | `string` | required per bond; non-null; default none | none | **Supported:** must reference an input chain | none |
| `all_atom_input.covalent_bonds[].res_idx2` | `integer` | required per bond; non-null; default none | No public range | **Narrowed:** nonnegative and within known chain length | none |
| `all_atom_input.covalent_bonds[].atom_idx2` | `integer` | required per bond; non-null; default none | No public range | **Narrowed:** nonnegative | Public page does not define atom-index bounds. |
| `all_atom_input.pocket` | `PocketConditioning \| null` | optional; nullable; default none | Pocket conditioning on a bound chain | **Supported** | SDK dataclass matches the semantic fields. |
| `all_atom_input.pocket.binder_chain_id` | `string` | required when pocket is non-null; non-null; default none | none | **Supported:** must reference an input chain | none |
| `all_atom_input.pocket.contacts` | rendered `array[array[tuple]]` | required when pocket is non-null; non-null; default none | Description says contacts are `(chain_id, residue_index)` | **Narrowed:** nonempty list of two-item pairs; chain and residue validated | SDK type is `list[tuple[str, int]]`; the rendered nested-array type is imprecise. |
| `all_atom_input.distogram_conditioning` | `array[DistogramConditioning] \| null` | optional; nullable; default none | none | **Supported:** if present, nonempty with unique chain IDs | none |
| `all_atom_input.distogram_conditioning[].chain_id` | `string` | required per item; non-null; default none | none | **Supported:** must reference a sequence-based input chain | none |
| `all_atom_input.distogram_conditioning[].distogram` `[SDK-required, omitted publicly]` | Not rendered; SDK uses an array/NumPy matrix | Not specified publicly; required by SDK object | SDK semantics require a per-chain distance matrix | **Supported SDK field:** finite, nonnegative, exact `L x L` matrix required | Major page/SDK omission: public children list only `chain_id`, while pinned `DistogramConditioning` requires `distogram`. |

## `inverse_fold`

Source: [`POST /api/v1/inverse_fold`](https://biohub.ai/api-reference/inverse_fold).
The complete ESM3 endpoint is **not exposed** by this plugin.

| JSON path | Public type / shape | Presence / null / default | Public bounds or values | Plugin disposition | Pinned-SDK or reference note |
| --- | --- | --- | --- | --- | --- |
| `model` | `string \| null` | optional; nullable; field default none; endpoint description says `esm3-open-2024-03` is the default | `esm3-open-2024-03`, `null` | **Not exposed** | SDK omits the model key when passed `None`, leaving service defaulting. |
| `potential_sequence_of_concern` | `boolean` | optional; non-null; default `false` | none | **Not exposed** | SDK supplies it through the transport call. |
| `coordinates` | `array[array[array[number \| null]]]`; documented `N x 37 x 3` | not marked required; non-null type; rendered default `""` | none | **Not exposed** | Page metadata is internally inconsistent: an empty string is not the declared array type. Pinned SDK requires a coordinate tensor argument and converts NaNs to null. |
| `inverse_folding_config` | `InverseFoldingConfig` object | required; non-null; default none | none | **Not exposed** | SDK requires the config object. |
| `inverse_folding_config.invalid_ids` | `array[integer]` | optional; non-null; rendered default `""` | none | **Not exposed** | Type conflicts with rendered default; SDK default is an empty sequence. |
| `inverse_folding_config.temperature` | `number` | optional; non-null; default `0.1` | `[0, infinity)` | **Not exposed** | SDK default is 0.1 and recommends varying seed rather than increasing temperature, although seed is not a request field on this page. |
| `sequence` | `string \| null` | optional; nullable; default none | Sequence conditioning | **Not exposed** | SDK passes it directly. |

## Cross-source discrepancy register

This register separates public-page facts, pinned-SDK behavior, and plugin policy so future changes can be reviewed without silently redefining one source as the other.

| Area | Public page | Exact pinned SDK | Plugin disposition |
| --- | --- | --- | --- |
| Model requiredness | `encode`, `decode`, `logits`, `generate`, `generate_tensor`, and `forward_and_sample` require a string model. `fold`, `fold_all_atom`, and `inverse_fold` allow null/omission and describe a default. | Client instances normally carry a model; fold/inverse helpers can omit an override. | Directly exposed operations always require an exact model ID for provenance. |
| Encode/generate `Tracks` | Includes confidence and generated-output metadata such as pLDDT, pTM, cRMSD, interface pTM, and PAE. | Encode/generate request builders send only conditioning tracks and omit those metadata fields. | ESMC encode exposes only sequence. |
| Coordinate description | Several pages say N/CA/C coordinates but render `N x 37 x 3`. | SDK treats them as atom37-shaped coordinates and converts NaNs to null. | Exposed folding inputs use the pinned structural SDK rules. |
| Empty collection defaults | `invalid_ids` fields render an empty-string default despite array types. | SDK defaults to empty Python sequences. | Affected ESM3 endpoints are not exposed. |
| Generation temperature | `generate` and `generate_tensor` default to `0.5`. | `GenerationConfig.temperature` defaults to `1.0`. | Endpoints are not exposed; both facts remain recorded. |
| Hidden-layer model names | `/logits` layer table shortens 300M/600M IDs and lists ESM3 variants beyond the endpoint enum. | SDK config uses generic integer layer selection. | Plugin uses endpoint enum IDs and ESMC maxima 30/36/80. |
| 300M SAE normalization | `/logits` defaults `normalize_features` to true and lists a 300M SAE. | SDK rejects true normalization for any 300M SAE. | Plugin requires explicit false for that SAE. |
| MSA headers | Fold pages list only sequences/deletions. | `MSA.state_dict()` serializes non-empty headers, and the official paired-MSA tutorial depends on `key=<taxonomy_id>` tokens. | Plugin preserves validated headers only for all-atom per-chain full-model MSAs; top-level single-chain requests remove them. Fast rejects every MSA. |
| RNA MSA | Public all-atom RNA variant has no MSA property. | `RNAInput` includes MSA; serializer emits `msa:null` when unset. | Plugin accepts only the null compatibility sentinel and strips it. |
| All-atom IDs | Entity IDs are nullable. | Input dataclasses type IDs as non-null strings/lists; local preparation iterates them. | Null IDs are managed-only; local/HF inputs require IDs. |
| All-atom sequence alternative | Page supports top-level sequence/MSA or `all_atom_input`. | Pinned convenience method constructs only `all_atom_input`. | Direct plugin client supports both and rejects mixing them. |
| All-atom pair-chain iPTM | Page includes `include_pair_chains_iptm`. | Pinned all-atom request builder omits it and result type does not retain it. | Direct plugin validation preserves the published request flag. |
| Distogram conditioning body | Public nested table lists only `chain_id`. | `DistogramConditioning` requires both `chain_id` and `distogram`. | Plugin follows SDK semantics and requires a finite nonnegative `L x L` matrix. |
| Modification SMILES | Public modification contains only position and CCD. | SDK `Modification` has optional `smiles`, but serializer drops it. | Plugin follows the actual public/serialized wire shape and rejects the extra property. |
| Ligand representation | Both SMILES and CCD are independently nullable. | SDK dataclass likewise has two nullable properties. | Plugin requires exactly one usable representation to avoid ambiguous or empty input. |
| Pocket contacts | Renderer shows `array[array[tuple]]`; prose says `(chain_id, residue_index)`. | SDK uses `list[tuple[str, int]]`. | Plugin validates a nonempty list of two-item references. |
| `lm_mask_pct` default | Fold pages render `0`, while prose says Fast `0.1` and full `0.0` on omission. | SDK stores `None` and resolves by model. | Generic plugin requests do not inject a value; reproducible starters pin one. |
| Inverse-fold coordinates | Non-null array type is not marked required and renders default `""`. | SDK requires coordinates. | Endpoint is not exposed; ambiguity is preserved rather than guessed. |
| Managed responses | No success schema, error schema, or status table is published on any of the nine pages. | SDK defines response decoders and tensor/structure objects. | Response normalization/materialization is labeled SDK-derived or captured-response-tested, never public-request-schema-derived. |

## Endpoint coverage check

| Official page | Top-level request properties audited | Nested request families audited | Plugin status |
| --- | ---: | --- | --- |
| [`encode`](https://biohub.ai/api-reference/encode) | 3 | All 12 rendered `Tracks` children | ESMC sequence subset exposed |
| [`decode`](https://biohub.ai/api-reference/decode) | 3 | All 7 `Tokens` children | Not exposed |
| [`logits`](https://biohub.ai/api-reference/logits) | 4 plus 2 headers | All 7 `Tokens`, all 12 `LogitsConfig`, and both `SAEConfig` children | ESMC JSON subset exposed |
| [`generate`](https://biohub.ai/api-reference/generate) | 13 | All 12 rendered `Tracks` children | Not exposed |
| [`generate_tensor`](https://biohub.ai/api-reference/generate_tensor) | 12 | All 7 `Tokens` children | Not exposed |
| [`forward_and_sample`](https://biohub.ai/api-reference/forward_and_sample) | 5 plus 1 header | All 7 `Tokens`, five track configs with all 5 repeated children, and both embedding fields | Not exposed |
| [`fold`](https://biohub.ai/api-reference/fold) | 14 | Both public MSA children plus SDK header compatibility | ESMFold2 subset exposed |
| [`fold_all_atom`](https://biohub.ai/api-reference/fold_all_atom) | 15 | MSA; all four entity variants; modifications; bonds; pocket; distogram conditioning; SDK compatibility fields | ESMFold2 exposed |
| [`inverse_fold`](https://biohub.ai/api-reference/inverse_fold) | 5 | Both inverse-fold config children | Not exposed |

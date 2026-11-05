# ESMC managed and SDK contract

Primary sources: [ESMC model page](https://biohub.ai/models/esmc), [managed encode reference](https://biohub.ai/api-reference/encode), [managed logits reference](https://biohub.ai/api-reference/logits), [Biohub/esm](https://github.com/Biohub/esm), and [ESMC-6B model card](https://huggingface.co/biohub/ESMC-6B).

## Managed models

- `esmc-300m-2024-12`
- `esmc-600m-2024-12`
- `esmc-6b-2024-12`

The managed API uses Bearer authentication and JSON requests:

- `POST /api/v1/encode` accepts `model`, `inputs: {sequence}`, and optional boolean `potential_sequence_of_concern`. The sequence is a string; `_` is the documented mask character.
- `POST /api/v1/logits` accepts `model`, tokenized `inputs: {sequence}`, `logits_config`, and optional boolean `potential_sequence_of_concern`.

Both ESMC request schemas require a model. The plugin accepts only the three published ESMC IDs in this surface so provenance records the exact model requested. Use the pinned official SDK to encode raw sequences rather than recreating token IDs.
Never put `ESM_API_KEY` in code, arguments, or files; the example below reads it from the environment. With the plugin installed, pass `token=resolve_esm_api_key().value` instead, after adding `<skill-directory>/resources/scripts` to `sys.path` and importing `resolve_esm_api_key` from `biohub_esm_lib.security`; it reads `ESM_API_KEY` and then the macOS Keychain item that setup saves, which may be the only copy of the key in the desktop app.

```python
import os

from esm.sdk import esmc_client
from esm.sdk.api import ESMProtein, LogitsConfig

client = esmc_client(
    model="esmc-600m-2024-12",
    url="https://biohub.ai",
    token=os.environ["ESM_API_KEY"],
)
protein = ESMProtein(sequence=sequence)
tokens = client.encode(protein)
result = client.logits(
    tokens,
    LogitsConfig(
        sequence=True,
        return_embeddings=True,
        return_hidden_states=False,
        return_mean_embedding=False,
    ),
)
```

For a single substitution, prefer `biohub_esm.py esmc-mutation-score`. Run status-only preflight first, then invoke it directly; a single managed logits request needs no confirmation. Record the exact sequence digest, mutation, model, endpoint, one-request scope, and output artifacts in provenance. Managed requests may incur cost. Report provider-returned credit or token usage when available; otherwise state that the API did not report usage or cost, and never invent an estimate. It uses the pinned SDK tokenizer locally, verifies the executed ESM and Transformers revisions before submission, replaces exactly one residue token with the tokenizer's mask ID, and uses the deterministic managed client for exactly one JSON logits request without implicit retries. The command preserves the actual redacted provider JSON and atomically writes raw output, the derived score, a deterministic `mutation-score.svg` summary, and provenance. The SVG is a visual summary of masked-context model likelihood, not evidence of fitness, stability, activity, binding, or function.

Never put the key in source or a command. `LogitsConfig` supports sequence logits, per-residue/final embeddings, mean embeddings, selected/all hidden states subject to model restrictions, and `SAEConfig`. Structure, secondary structure, SASA, and function logits are not supported on the managed endpoint.

For a complete single-mask landscape, use `biohub_esm.py esmc-landscape`; the PETase card selects `--tutorial petase`. The command verifies the pinned SDK and tokenizer, constructs one locally tokenized masked context per residue, and submits the independent `/logits` requests through a bounded `ThreadPoolExecutor`, matching the official quickstart's managed-concurrency pattern without the SDK batch executor's implicit retries. It pins the Biohub origin, defaults to 16 workers, never retries an indeterminate request, preserves all redacted raw responses, and derives full-vocabulary tutorial entropy plus canonical alternate-minus-wild-type LLRs in tested code.

Generic `--sequence` and `--sequence-file` landscapes are limited to 512 residues because retaining every full-logit response makes memory and raw-artifact size grow quadratically; the 259-residue PETase tutorial remains within that bound.

`SAEConfig` has canonical `models` and optional `normalize_features` (default `true`). The pinned SDK also accepts deprecated singular `model` as a convenience alias, and Biohub's current tutorial still shows that spelling; do not copy the alias into a managed JSON contract or new plugin code. SAE output alone is a valid requested output. Each SAE must match the selected ESMC base model, and the managed reference lists these exact IDs:

- `esmc-300m-2024-12-sae-layer23-k64-codebook65536`
- `esmc-600m-2024-12-sae-layer27-k64-codebook16384`
- `esmc-600m-2024-12-sae-layer27-k64-codebook65536`
- `esmc-6b-2024-12-sae-layer60-k64-codebook16384`
- `esmc-6b-2024-12-sae-layer60-k64-codebook65536`

The public page applies the `normalize_features=true` default generically, but the exact pinned official SDK rejects normalized 300M SAE features. Requests using the 300M SAE must explicitly set `normalize_features=false`; the plugin does not silently change the requested semantics. Generic `managed-post` currently validates the SAE request and preserves the raw provider tensor serialization. Decoded SAE tensor artifacts remain SDK-route work rather than an end-to-end feature of that raw JSON command. For the official ATP-synthase interpretation workflow, use the pinned SDK to decode `sae_outputs["esmc-6b-2024-12-sae-layer60-k64-codebook16384"]`, remove BOS/EOS, and only then rank or map residue activations. Atlas description lookup is valid only for that exact compatible dictionary unless a newer first-party source proves another binding.

The current pinned SDK notes that ESMC-6B managed inference cannot return all hidden layers at once; request one valid `ith_hidden_layer`. Layer 0 is the embedding layer. Check the pinned SDK for the current layer maximum before a layer sweep.

Errors can return a model error object instead of the expected tensor result. Check that path before accessing outputs and retain only redacted diagnostics.

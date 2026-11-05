# ESMFold2 managed and SDK contract

Primary sources: [ESMFold2 model page](https://biohub.ai/models/esmfold2), [managed fold reference](https://biohub.ai/api-reference/fold), [managed all-atom fold reference](https://biohub.ai/api-reference/fold_all_atom), [ESMFold2 model card](https://huggingface.co/biohub/ESMFold2), and [Biohub/esm](https://github.com/Biohub/esm).

## Models

- managed full: `esmfold2-2026-05`
- managed fast: `esmfold2-fast-2026-05`
- open full: `biohub/ESMFold2`
- open fast: `biohub/ESMFold2-Fast`

Use the pinned official `SequenceStructureForgeInferenceClient` or `esmfold2_client` for managed `/fold` and `/fold_all_atom`. Never put `ESM_API_KEY` in code, arguments, or files; the example below reads it from the environment. With the plugin installed, pass `token=resolve_esm_api_key().value` instead, after adding `<skill-directory>/resources/scripts` to `sys.path` and importing `resolve_esm_api_key` from `biohub_esm_lib.security`; it reads `ESM_API_KEY` and then the macOS Keychain item that setup saves, which may be the only copy of the key in the desktop app. The canonical Fast starter uses the sequence `/fold` contract below because it deterministically yields PDB, pLDDT, and requested pAE rather than the all-atom mmCIF route.

Both managed routes are Bearer-authenticated JSON `POST` requests. Their direct wire contracts differ:

- `/api/v1/fold` accepts `model`, a protein `sequence`, optional `msa`, folding settings, output booleans, and optional boolean `potential_sequence_of_concern`.
- `/api/v1/fold_all_atom` accepts either `sequence` with optional `msa`, or `all_atom_input`; do not combine the alternatives. It accepts the same folding/output settings and optional boolean `potential_sequence_of_concern`.
- Managed MSA is an object with `sequences` and optional `deletions`, not a bare sequence list. Each aligned row has one value per alignment column in `deletions` when that matrix is supplied.

The public schemas permit nullable/defaulted models. The plugin requires one exact model ID for reproducibility and rejects an MSA with Fast instead of allowing conditioning to be silently ignored.

```python
import os

from esm.sdk import esmfold2_client
from esm.sdk.api import ESMProteinError, FoldingConfig

sequence = "MTYKLILNGKTLKGETTTEAVDAATAEKVFKQYANDNGVDGEWTYDDATKTFTVTE"
client = esmfold2_client(
    model="esmfold2-fast-2026-05",
    url="https://biohub.ai",
    token=os.environ["ESM_API_KEY"],
    request_timeout=120,
)
result = client.fold(
    sequence=sequence,
    msa=None,
    config=FoldingConfig(
        include_distogram=False,
        include_pae=True,
        include_pair_chains_iptm=False,
        num_sampling_steps=100,
        num_loops=20,
        lm_dropout=0.3,
        lm_mask_pct=0.1,
        msa_max_depth=1024,
        msa_column_mask_rate=0.1,
        include_embeddings=False,
    ),
)
if isinstance(result, ESMProteinError):
    raise RuntimeError(f"managed ESMFold2 failed with code {result.error_code}")
if result.plddt is None or result.pae is None:
    raise RuntimeError("managed ESMFold2 omitted required pLDDT or requested PAE")
pdb_text = result.to_pdb_string()
plddt = result.plddt.detach().cpu()
pae = result.pae.detach().cpu()
```

The convenience `esmfold2_client` has retry behavior for selected provider statuses. The exactly-one-request focused GB1 regression starter therefore records the exact provider, model, endpoint, input digest, request count, inference parameters, and requested artifacts in provenance. Status-only preflight runs first, then the request runs; a single managed fold needs no confirmation. It then uses the pinned `managed-post --endpoint fold` command with no implicit retries and preserves the frozen request through local recovery.

The deterministic `managed-post` CLI preserves the redacted wire response as `raw-response.json` and normalizes the pinned SDK's optional `data` envelope. With `--output-dir`, sequence-only `/fold` responses are serialized from their real `coordinates` array to `prediction.pdb`; `/fold_all_atom` responses are deep-copied and serialized from their real `complex` state to `prediction.cif`. Both conversions use the exact verified pinned `esm` SDK, emit one checksummed `structure_artifact` record, and record that SDK revision in provenance. A malformed response or provider-supplied reserved artifact field publishes no successful result or complete provenance; the checksummed raw diagnostic remains under validated `status: incomplete` provenance. Every artifact `--output-dir` must not already exist. The CLI atomically creates it before a managed provider call, so concurrent generations cannot mix or duplicate provider work. Provenance hashes only endpoint-specific biological inputs; model and inference settings remain under `parameters`. A conversion/schema failure retains the redacted raw response together with validated `status: incomplete` provenance.

Successful fold materialization also emits checksummed `presentation-request.json`, which binds the verified absolute coordinate artifact, requested predicted-confidence view, confidence completeness, and stable `openIntentId`. Presentation consumers use that exact retained ID; they generate one only for legacy artifact sets without this request file.

```bash
<python-3.12-with-pinned-esm> <skill-directory>/resources/scripts/biohub_esm.py managed-recover \
  --endpoint fold_all_atom \
  --input /absolute/path/frozen-request.json \
  --raw-response /absolute/path/raw-response.json \
  [--source-provenance /absolute/path/provenance.json] \
  --output-dir /absolute/path/new-recovery-output
```

`managed-recover` is a zero-provider-call path only for a saved accepted response whose local conversion or materialization failed. Match `--endpoint` to `fold` or `fold_all_atom`, use the exact frozen request and response, include matching incomplete provenance when available, and always use a new nonexistent output directory. Never use recovery to resolve an indeterminate submission.


## Hosted bounds verified 2026-07-01

The helper reads managed and validation request documents through a plugin-level safety envelope before JSON decoding: at most 32 MiB of UTF-8 JSON, 64 nested levels, 1,000,000 decoded nodes, 128 MiB of estimated decoded aggregate storage, and 1 MiB per string. These are local resource-safety ceilings, not provider or model limits. They deliberately accommodate the documented MSA deletion and distogram-conditioning matrices; generic Modal job-control, Atlas hash-list, and fold-config documents retain the smaller 100,000-node and 32 MiB estimated-aggregate control-plane budget.

| Field | Default | Range |
| --- | ---: | ---: |
| `num_loops` | 20 | 0-20 |
| `num_sampling_steps` | 100 | 1-100 |
| `lm_dropout` | 0.3 | 0-1 |
| `lm_mask_pct` | full 0, Fast 0.1 when omitted | 0-1 |
| `msa_max_depth` | 1024 | 1-16,384 or null |
| `msa_column_mask_rate` | 0.1 | 0-1 |

Boolean options include PAE, distogram, embeddings, and `include_pair_chains_iptm` where the endpoint/model returns them. The current API reference documents `include_pair_chains_iptm` on both `/fold` and `/fold_all_atom`; direct managed requests therefore accept it on either route even if an SDK convenience method exposes a narrower signature. For multi-chain `/fold`, current managed responses may return pLDDT on the sequence track with a null/zero entry at each `|` chain break while PAE remains residue-by-residue. Provenance validates both shapes, excludes break placeholders from the pLDDT summary, and requires pair-chain iPTM to be square with one row and column per submitted chain. A successful sequence `/fold` must include finite pLDDT for every actual residue, with only null/zero chain-break placeholders allowed on a documented multi-chain sequence track. Its atom37 structure must include finite N, CA, and C coordinates for every biological residue; other atom positions must be either complete finite triples or all-null missing atoms. A full sequence-length coordinate track may contain an all-null row only at an explicit `|` chain break, while a compact residue-only track contains no placeholder rows. A request with `include_pae=true` must include a fully numeric confidence matrix with no null placeholders. Sequence `/fold` provenance labels pLDDT scope `per-residue` and pAE scope `residue-pair`. `/fold_all_atom` provenance instead labels them `per-token` and `token-pair`; each token is one returned `complex.sequence` entry with its atom span defined by the aligned `complex.token_to_atoms` entry, including protein, nucleic-acid, modified-residue, and ligand tokens. Preserve the raw response and treat either omission as schema drift. Do not send an MSA to Fast: the pinned SDK warns that it will be ignored, and this plugin treats that as a validation error to prevent a false scientific assumption.

The web Fold tool currently limits entry to 700 residues. That is a UI boundary, not a documented universal architectural limit for managed or open ESMFold2.

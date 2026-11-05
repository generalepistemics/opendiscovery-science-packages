"""Pinned model identifiers and public service constants.

Pins were resolved from the public upstreams on 2026-07-01. Callers should
record them in provenance and intentionally update them when validating a new
upstream revision; never silently replace them with ``main``.
"""

from __future__ import annotations

BIOHUB_BASE_URL = "https://biohub.ai"
# The only page that issues API keys, and the quickstart that documents the
# managed client. Surface these verbatim whenever a credential is missing.
BIOHUB_API_KEY_URL = "https://biohub.ai/developer-console/api-keys"
BIOHUB_QUICKSTART_URL = "https://biohub.ai/learn/getting-started"
ATLAS_API_PREFIX = "/esm/protein/api/v1alpha1"
ATLAS_API_VERSION = "v1alpha1"
ATLAS_SCHEMA_VERSION = "0.1.0"

# Python 3.12 is the range this plugin validates the pinned esm SDK on. The
# distribution itself declares ">=3.12", which is stricter than this package's
# own 3.10 floor, so routes that import the SDK check this separately; Atlas
# and Modal-control routes stay usable on 3.10.
ESM_SDK_PYTHON_MIN = (3, 12)
ESM_SDK_PYTHON_EXCLUSIVE_MAX = (3, 13)

# The SDK is pinned to exact PyPI wheels. The payload digest is sha256 over the
# sorted "path,hash" RECORD rows of the importable package (bytecode excluded),
# so an installed copy can be checked without the wheel file. The git revisions
# are the upstream tag commits the wheels correspond to; provenance records them.
ESM_SDK_VERSION = "3.4.1.post1"
ESM_SDK_WHEEL_SHA256 = "f9e62b363519860d27762989871a531cdbd02d69c824cc8c8a1047b16dce3ef6"
ESM_SDK_PAYLOAD_SHA256 = "02e6bbe94ac6b4362fddd56ab622d7be20d151291001392c0dd1d509db50f535"
ESM_GIT_REVISION = "43b4548b86762edfa747b07d5f440aad3c33acee"
TRANSFORMERS_VERSION = "4.57.6"
TRANSFORMERS_WHEEL_SHA256 = "4c9e9de11333ddfe5114bc872c9f370509198acf0b87a832a0ab9458e2bd0550"
TRANSFORMERS_PAYLOAD_SHA256 = "ca8339a7d7a3c5e7616e3e792b0ccfc93c8aa5f1717ba4c09242927bf9cbf3bd"
TRANSFORMERS_GIT_REVISION = "753d61104116eefc8ffc977327b441ee0c8d599f"

# The tutorial notebooks are pinned separately from the SDK: their contract in
# tutorial-use-cases.json was validated at this Biohub/esm commit.
TUTORIAL_SOURCE_REVISION = "ba4d7124864eed323a93bf3cfefcd958f573b75a"

ESMC_MANAGED_MODELS = (
    "esmc-300m-2024-12",
    "esmc-600m-2024-12",
    "esmc-6b-2024-12",
)
ESMC_MANAGED_SAE_MODELS = (
    "esmc-300m-2024-12-sae-layer23-k64-codebook65536",
    "esmc-600m-2024-12-sae-layer27-k64-codebook16384",
    "esmc-600m-2024-12-sae-layer27-k64-codebook65536",
    "esmc-6b-2024-12-sae-layer60-k64-codebook16384",
    "esmc-6b-2024-12-sae-layer60-k64-codebook65536",
)
ESMC_HF_MODELS = (
    "biohub/ESMC-300M",
    "biohub/ESMC-600M",
    "biohub/ESMC-6B",
)
ESMFOLD2_MANAGED_MODELS = (
    "esmfold2-2026-05",
    "esmfold2-fast-2026-05",
)
ESMFOLD2_HF_MODELS = (
    "biohub/ESMFold2",
    "biohub/ESMFold2-Fast",
)

HF_REVISIONS = {
    "biohub/ESMC-300M": "a59b831785f907e96e6a246b1d142bfb76df31ee",
    "biohub/ESMC-600M": "a7e82012c83126b9eedb055fea9fa84b6c02f094",
    "biohub/ESMC-6B": "45b0fa5d7fb06faefbd5e3b89bdcef35d564e79a",
    "biohub/ESMFold2": "1ebf0e3481a5184eb6171d40615c79e384b48796",
    "biohub/ESMFold2-Fast": "b28d8ace5e05e61e5bec1e6820cfd3e221819d12",
}

# The generic Modal control plane relies on the SDK's Function.from_name,
# Function.spawn, FunctionCall.from_id/get/cancel, and exception taxonomy. Pin
# that client surface just like the model/code stacks: a silent SDK upgrade can
# otherwise change whether a remote result is classified as terminal or safe to
# poll again. The companion hard limits keep one durable state file bounded;
# large scientific arrays belong in remote durable storage and are represented
# by artifact metadata in the compact result envelope.
MODAL_SDK_VERSION = "1.5.2"
MODAL_MAX_JOBS = 128
MODAL_INPUT_MAX_BYTES = 16 * 1024 * 1024
MODAL_RESULT_MAX_BYTES = 512 * 1024
MODAL_RESULT_MAX_DEPTH = 32
MODAL_RESULT_MAX_NODES = 50_000
MODAL_JOB_STATE_MAX_BYTES = 72 * 1024 * 1024
MODAL_JOB_STATE_MAX_DEPTH = MODAL_RESULT_MAX_DEPTH + 8
MODAL_JOB_STATE_MAX_NODES = 200_000
MODAL_JOB_STATE_MAX_TEXT_BYTES = MODAL_RESULT_MAX_BYTES * MODAL_MAX_JOBS
MODAL_JOB_STATE_MAX_NUMBER_BYTES = 128
MODAL_CALL_ID_MAX_BYTES = 512

ESMC_MAX_TOKENS = 2048
# Hugging Face tokenizers add BOS and EOS. Without a tokenizer probe, keeping
# two positions free is the safe raw-residue limit.
ESMC_CONSERVATIVE_MAX_RESIDUES = 2046
ATLAS_SEARCH_MAX_RESIDUES = 800
ATLAS_FOLD_MAX_RESIDUES = 699
ATLAS_FEATURE_COUNT = 16_384
ATLAS_BATCH_MAX_UNIQUE_HASHES = 500

HOSTED_FOLD_BOUNDS = {
    "num_loops": (0, 20),
    "num_sampling_steps": (1, 100),
    "lm_dropout": (0.0, 1.0),
    "lm_mask_pct": (0.0, 1.0),
    "msa_max_depth": (1, 16_384),
    "msa_column_mask_rate": (0.0, 1.0),
}

DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_POLL_TIMEOUT_SECONDS = 1800.0

# Keep the shared protein alphabet conservative. Provider-specific additions
# belong in their own allowlists so accepting a tokenizer/service capability
# does not silently broaden ESMFold2 or other protein inputs.
PROTEIN_ALPHABET = frozenset("ACDEFGHIKLMNPQRSTVWYX")
# The pinned ESMC tokenizer and the captured Atlas live probe both accept the
# B/Z ambiguity codes plus the U/O genetically encoded nonstandard residues.
ESMC_PROTEIN_ALPHABET = PROTEIN_ALPHABET | frozenset("BUZO")
ATLAS_PROTEIN_ALPHABET = PROTEIN_ALPHABET | frozenset("BUZO")
DNA_ALPHABET = frozenset("ACGTN")
RNA_ALPHABET = frozenset("ACGUN")

MANAGED_ENDPOINTS = frozenset({"encode", "logits", "fold", "fold_all_atom"})

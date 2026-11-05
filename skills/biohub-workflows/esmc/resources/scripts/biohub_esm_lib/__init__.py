"""Deterministic helpers for the Biohub ESM OpenDiscovery plugin."""

import sys

MINIMUM_PYTHON_VERSION = (3, 10)

# Every entry point reaches the runtime through this package, so the supported
# version floor is enforced here before any submodule loads. The runtime uses
# itertools.pairwise and zip(strict=True), which older interpreters resolve at
# call time rather than import time. One of those call sites is _is_secret_key,
# reached from redact_text, so an unsupported interpreter would fail inside the
# redaction path and print an unredacted traceback.
if sys.version_info < MINIMUM_PYTHON_VERSION:
    sys.stderr.write(
        "biohub-esm requires Python "
        f"{MINIMUM_PYTHON_VERSION[0]}.{MINIMUM_PYTHON_VERSION[1]} or newer. "
        f"This interpreter is {sys.version_info.major}.{sys.version_info.minor}"
        f".{sys.version_info.micro} at {sys.executable}. "
        "Re-run the command with a supported interpreter.\n"
    )
    raise SystemExit(2)

from .atlas import AtlasClient
from .constants import (
    ATLAS_API_PREFIX,
    BIOHUB_BASE_URL,
    ESM_GIT_REVISION,
    ESM_SDK_PAYLOAD_SHA256,
    ESM_SDK_VERSION,
    ESM_SDK_WHEEL_SHA256,
    ESMC_HF_MODELS,
    ESMC_MANAGED_MODELS,
    ESMFOLD2_HF_MODELS,
    ESMFOLD2_MANAGED_MODELS,
    HF_REVISIONS,
    TRANSFORMERS_GIT_REVISION,
    TRANSFORMERS_PAYLOAD_SHA256,
    TRANSFORMERS_VERSION,
    TRANSFORMERS_WHEEL_SHA256,
    TUTORIAL_SOURCE_REVISION,
)
from .errors import APIError, BiohubESMError, SchemaDriftError, ValidationError
from .provenance import build_provenance, validate_provenance, write_json_atomic
from .routing import RouteRequest, RouteResult, route_request

__all__ = [
    "APIError",
    "ATLAS_API_PREFIX",
    "AtlasClient",
    "BIOHUB_BASE_URL",
    "BiohubESMError",
    "ESM_GIT_REVISION",
    "ESM_SDK_PAYLOAD_SHA256",
    "ESM_SDK_VERSION",
    "ESM_SDK_WHEEL_SHA256",
    "ESMC_HF_MODELS",
    "ESMC_MANAGED_MODELS",
    "ESMFOLD2_HF_MODELS",
    "ESMFOLD2_MANAGED_MODELS",
    "HF_REVISIONS",
    "TRANSFORMERS_GIT_REVISION",
    "TRANSFORMERS_PAYLOAD_SHA256",
    "TRANSFORMERS_VERSION",
    "TRANSFORMERS_WHEEL_SHA256",
    "TUTORIAL_SOURCE_REVISION",
    "RouteRequest",
    "RouteResult",
    "SchemaDriftError",
    "ValidationError",
    "build_provenance",
    "route_request",
    "validate_provenance",
    "write_json_atomic",
]

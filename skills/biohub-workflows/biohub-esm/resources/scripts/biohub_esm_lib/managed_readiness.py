"""Offline readiness checks for managed structure response materialization.

This module deliberately has no credential, HTTP, or provider dependencies.  A
caller can run it before constructing a managed client or submitting a paid
request.  The probe is scoped to the two managed structure endpoints because
Atlas reads and managed ESMC calls do not require these serializers.
"""

from __future__ import annotations

import importlib.util
import sys
import warnings
from copy import deepcopy
from functools import lru_cache
from typing import Any, Callable, Literal

from .constants import (
    ESM_GIT_REVISION,
    ESM_SDK_PAYLOAD_SHA256,
    ESM_SDK_PYTHON_EXCLUSIVE_MAX,
    ESM_SDK_PYTHON_MIN,
    ESM_SDK_VERSION,
    TRANSFORMERS_GIT_REVISION,
    TRANSFORMERS_PAYLOAD_SHA256,
    TRANSFORMERS_VERSION,
)
from .errors import ValidationError
from .provenance import DISTRIBUTION_VERIFICATION_METHOD, verify_installed_distribution

ManagedStructureEndpoint = Literal["fold", "fold_all_atom"]

READINESS_SCHEMA_VERSION = "1.1"
READINESS_CAPABILITY = "managed-structure-materialization"
SERIALIZER_SELF_TEST_VERSION = "tiny-offline-v1"
ESM_DISTRIBUTION = "esm"
ESM_MODULE = "esm"
TRANSFORMERS_DISTRIBUTION = "transformers"
DISTRIBUTION_EVIDENCE_KIND = "distribution-build"

_ENDPOINT_FORMATS = {
    "fold": "pdb",
    "fold_all_atom": "mmcif",
}
_ENDPOINT_IMPORTS = {
    "fold": (
        "esm.sdk.api.ESMProtein",
        "esm.utils.misc.maybe_tensor",
    ),
    "fold_all_atom": ("esm.utils.structure.molecular_complex.MolecularComplex",),
}
_FAILURE_REMEDIATIONS = {
    "unsupported-interpreter": "Use the provisioned Python 3.12 serializer runtime.",
    "sdk-unavailable": f"Install esm=={ESM_SDK_VERSION} and transformers=={TRANSFORMERS_VERSION}.",
    "sdk-evidence-unverified": f"Reinstall esm=={ESM_SDK_VERSION} from PyPI.",
    "transformers-evidence-unverified": f"Reinstall transformers=={TRANSFORMERS_VERSION} from PyPI.",
    "sdk-import-failed": (
        f"Reinstall esm=={ESM_SDK_VERSION} with its dependencies (torch>=2.11,<2.12) "
        "in the Python 3.12 environment."
    ),
    "serializer-self-test-failed": "Repair the provisioned offline serializer.",
}

ModuleAvailable = Callable[[str], bool]
DistributionVerifier = Callable[[str], str]
SDKLoader = Callable[[ManagedStructureEndpoint], tuple[Any, ...]]
SerializerSelfTest = Callable[[ManagedStructureEndpoint, tuple[Any, ...]], None]


def _validated_endpoint(endpoint: str) -> ManagedStructureEndpoint:
    if endpoint not in _ENDPOINT_FORMATS:
        raise ValidationError(
            "managed structure materialization readiness requires fold or fold_all_atom"
        )
    return endpoint  # type: ignore[return-value]


def _current_python_version() -> tuple[int, int]:
    return sys.version_info.major, sys.version_info.minor


def _python_requirement() -> str:
    minimum = ".".join(str(value) for value in ESM_SDK_PYTHON_MIN)
    maximum = ".".join(str(value) for value in ESM_SDK_PYTHON_EXCLUSIVE_MAX)
    return f">={minimum},<{maximum}"


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (AttributeError, ImportError, ModuleNotFoundError, ValueError):
        return False


def load_structure_serializer_sdk(endpoint: str) -> tuple[Any, ...]:
    """Load exactly the serializer components exercised by readiness."""

    endpoint = _validated_endpoint(endpoint)
    if endpoint == "fold":
        from esm.sdk.api import ESMProtein
        from esm.utils.misc import maybe_tensor

        return ESMProtein, maybe_tensor

    from esm.utils.structure.molecular_complex import MolecularComplex

    return (MolecularComplex,)


def protein_to_pdb_string(protein: Any) -> str:
    """Serialize an ESMProtein to PDB without the SDK's per-call missing-entity warning."""

    with warnings.catch_warnings():
        # esm 3.4.1 warns on every single-chain export because PDB records carry no entity ID.
        warnings.filterwarnings(
            "ignore", message="Entity ID not found in metadata", category=UserWarning
        )
        return protein.to_pdb_string()


def _require_serialized_atom_record(value: Any, *, format_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"offline {format_name} serializer self-test returned empty output")
    if not any(line.startswith("ATOM") for line in value.splitlines()):
        raise RuntimeError(f"offline {format_name} serializer self-test returned no ATOM record")


def _run_offline_serializer_self_test(
    endpoint: ManagedStructureEndpoint,
    components: tuple[Any, ...],
) -> None:
    """Exercise the endpoint's serializer with one alanine and no file or network I/O."""

    if endpoint == "fold":
        if len(components) != 2:
            raise RuntimeError("offline PDB serializer self-test received invalid components")
        esm_protein, maybe_tensor = components
        coordinates = [
            [
                [0.0, 0.0, 0.0],
                [1.45, 0.0, 0.0],
                [2.0, 1.4, 0.0],
                [1.4, 2.4, 0.0],
            ]
            + [[None, None, None] for _ in range(33)]
        ]
        protein = esm_protein(
            sequence="A",
            coordinates=maybe_tensor(coordinates, convert_none_to_nan=True),
            plddt=maybe_tensor([0.9], convert_none_to_nan=True),
        )
        _require_serialized_atom_record(protein_to_pdb_string(protein), format_name="PDB")
        return

    if len(components) != 1:
        raise RuntimeError("offline mmCIF serializer self-test received invalid components")
    (molecular_complex,) = components
    state = {
        "id": "readiness",
        "sequence": ["ALA"],
        "atom_positions": [
            [0.0, 0.0, 0.0],
            [1.45, 0.0, 0.0],
            [2.0, 1.4, 0.0],
            [1.4, 2.4, 0.0],
        ],
        "atom_elements": ["N", "C", "C", "O"],
        "token_to_atoms": [[0, 4]],
        "chain_id": [0],
        "plddt": [0.9],
        "metadata": {
            "entity_lookup": {0: "ALA"},
            "chain_lookup": {0: "A"},
            "assembly_composition": None,
        },
        "atom_names": ["N", "CA", "C", "O"],
        "atom_hetero": [False, False, False, False],
    }
    serialized = molecular_complex.from_state_dict(state).to_mmcif()
    _require_serialized_atom_record(serialized, format_name="mmCIF")


def _base_report(
    endpoint: ManagedStructureEndpoint,
    python_version: tuple[int, int],
) -> dict[str, Any]:
    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "capability": READINESS_CAPABILITY,
        "endpoint": endpoint,
        "ready": False,
        "status": "blocked",
        "cache_scope": "process",
        "checks": {
            "interpreter": {
                "status": "not-run",
                "current": f"{python_version[0]}.{python_version[1]}",
                "required": _python_requirement(),
            },
            "sdk_availability": {
                "status": "not-run",
                "distribution": ESM_DISTRIBUTION,
                "module": ESM_MODULE,
            },
            "sdk_evidence": {
                "status": "not-run",
                "distribution": ESM_DISTRIBUTION,
                "kind": DISTRIBUTION_EVIDENCE_KIND,
                "verification_method": DISTRIBUTION_VERIFICATION_METHOD,
                "expected_version": ESM_SDK_VERSION,
                "expected_payload_sha256": ESM_SDK_PAYLOAD_SHA256,
                "expected_revision": ESM_GIT_REVISION,
                "verified_revision": None,
            },
            "transformers_evidence": {
                "status": "not-run",
                "distribution": TRANSFORMERS_DISTRIBUTION,
                "kind": DISTRIBUTION_EVIDENCE_KIND,
                "verification_method": DISTRIBUTION_VERIFICATION_METHOD,
                "expected_version": TRANSFORMERS_VERSION,
                "expected_payload_sha256": TRANSFORMERS_PAYLOAD_SHA256,
                "expected_revision": TRANSFORMERS_GIT_REVISION,
                "verified_revision": None,
            },
            "imports": {
                "status": "not-run",
                "required": list(_ENDPOINT_IMPORTS[endpoint]),
            },
            "serializer": {
                "status": "not-run",
                "format": _ENDPOINT_FORMATS[endpoint],
                "self_test": SERIALIZER_SELF_TEST_VERSION,
                "offline": True,
            },
        },
        "failures": [],
    }


def _block(
    report: dict[str, Any],
    *,
    check: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    report["checks"][check]["status"] = "failed"
    report["failures"].append(
        {
            "check": check,
            "code": code,
            "message": message,
        }
    )
    return report


def _probe_managed_structure_materialization_readiness(
    endpoint: ManagedStructureEndpoint,
    *,
    python_version: tuple[int, int],
    module_available: ModuleAvailable = _module_available,
    distribution_verifier: DistributionVerifier = verify_installed_distribution,
    sdk_loader: SDKLoader = load_structure_serializer_sdk,
    serializer_self_test: SerializerSelfTest = _run_offline_serializer_self_test,
) -> dict[str, Any]:
    """Run one deterministic, secret-free readiness probe without network access."""

    report = _base_report(endpoint, python_version)
    checks = report["checks"]

    if not ESM_SDK_PYTHON_MIN <= python_version < ESM_SDK_PYTHON_EXCLUSIVE_MAX:
        return _block(
            report,
            check="interpreter",
            code="unsupported-interpreter",
            message="The pinned Biohub esm serializer requires Python 3.12.",
        )
    checks["interpreter"]["status"] = "passed"

    if not module_available(ESM_MODULE):
        return _block(
            report,
            check="sdk_availability",
            code="sdk-unavailable",
            message="The Biohub esm SDK is not available to the structure serializer.",
        )
    checks["sdk_availability"]["status"] = "passed"

    try:
        verified_revision = distribution_verifier(ESM_DISTRIBUTION)
    except Exception:
        return _block(
            report,
            check="sdk_evidence",
            code="sdk-evidence-unverified",
            message=f"The installed esm build could not be verified as esm=={ESM_SDK_VERSION}.",
        )
    if verified_revision != ESM_GIT_REVISION:
        return _block(
            report,
            check="sdk_evidence",
            code="sdk-evidence-unverified",
            message=f"The installed esm build could not be verified as esm=={ESM_SDK_VERSION}.",
        )
    checks["sdk_evidence"]["status"] = "passed"
    checks["sdk_evidence"]["verified_revision"] = verified_revision

    try:
        verified_transformers_revision = distribution_verifier(TRANSFORMERS_DISTRIBUTION)
    except Exception:
        return _block(
            report,
            check="transformers_evidence",
            code="transformers-evidence-unverified",
            message=(
                "The installed Transformers build could not be verified as "
                f"transformers=={TRANSFORMERS_VERSION}."
            ),
        )
    if verified_transformers_revision != TRANSFORMERS_GIT_REVISION:
        return _block(
            report,
            check="transformers_evidence",
            code="transformers-evidence-unverified",
            message=(
                "The installed Transformers build could not be verified as "
                f"transformers=={TRANSFORMERS_VERSION}."
            ),
        )
    checks["transformers_evidence"]["status"] = "passed"
    checks["transformers_evidence"]["verified_revision"] = verified_transformers_revision

    try:
        components = sdk_loader(endpoint)
    except Exception:
        return _block(
            report,
            check="imports",
            code="sdk-import-failed",
            message="The pinned Biohub esm structure serializer could not be imported.",
        )
    checks["imports"]["status"] = "passed"

    try:
        serializer_self_test(endpoint, components)
    except Exception:
        return _block(
            report,
            check="serializer",
            code="serializer-self-test-failed",
            message="The Biohub esm structure serializer failed its offline self-test.",
        )
    checks["serializer"]["status"] = "passed"

    report["ready"] = True
    report["status"] = "ready"
    return report


@lru_cache(maxsize=2)
def _cached_managed_structure_materialization_readiness(
    endpoint: ManagedStructureEndpoint,
) -> dict[str, Any]:
    return _probe_managed_structure_materialization_readiness(
        endpoint,
        python_version=_current_python_version(),
    )


def managed_structure_materialization_readiness(endpoint: str) -> dict[str, Any]:
    """Return a cached, defensive-copy readiness report for one fold endpoint.

    Setup code that changes the active Python environment in-process should call
    :func:`clear_managed_structure_materialization_readiness_cache` before
    probing again.
    """

    normalized = _validated_endpoint(endpoint)
    return deepcopy(_cached_managed_structure_materialization_readiness(normalized))


def clear_managed_structure_materialization_readiness_cache() -> None:
    """Invalidate process-local serializer readiness after an environment change."""

    _cached_managed_structure_materialization_readiness.cache_clear()


def require_managed_structure_materialization_ready(endpoint: str) -> dict[str, Any]:
    """Return readiness or fail locally before a managed provider submission."""

    report = managed_structure_materialization_readiness(endpoint)
    if report["ready"]:
        return report
    failure = report["failures"][0]
    remediation = _FAILURE_REMEDIATIONS.get(
        failure["code"],
        "Run endpoint-specific preflight for a bounded diagnostic.",
    )
    raise ValidationError(
        f"managed {endpoint} structure materialization is not ready "
        f"({failure['code']}): {remediation}"
    )

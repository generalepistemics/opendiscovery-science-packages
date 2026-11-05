#!/usr/bin/env python3
"""Biohub ESM deterministic helper CLI.

The CLI resolves Biohub credentials from the environment or an existing macOS
Keychain item, and Modal credentials from the environment or an existing
profile. It never accepts credential values as arguments and never prints them.
Modal submissions require the explicit current-turn --confirm-cost execution
token; managed tutorial-scale calls run once access is configured.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import stat
import sys
import tempfile
import time
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from biohub_esm_lib.atlas import (
    AtlasBatchArchive,
    AtlasClient,
    hold_atlas_artifact_identity,
    open_atlas_artifact_snapshot,
    safe_download_endpoint,
)
from biohub_esm_lib.atlas_jobs import (
    AtlasBatchStore,
    _atlas_exception_provider_call,
    _atlas_failure_record,
    _batch_provider_call,
    atlas_batch_sink_preparer,
)
from biohub_esm_lib.cli_parser import build_parser as _build_cli_parser
from biohub_esm_lib.constants import (
    ATLAS_API_PREFIX,
    ATLAS_FOLD_MAX_RESIDUES,
    ATLAS_SEARCH_MAX_RESIDUES,
    BIOHUB_BASE_URL,
    ESM_GIT_REVISION,
    ESM_SDK_PAYLOAD_SHA256,
    ESM_SDK_PYTHON_EXCLUSIVE_MAX,
    ESM_SDK_PYTHON_MIN,
    ESM_SDK_VERSION,
    ESM_SDK_WHEEL_SHA256,
    ESMC_CONSERVATIVE_MAX_RESIDUES,
    ESMC_MANAGED_MODELS,
    HF_REVISIONS,
    MODAL_INPUT_MAX_BYTES,
    MODAL_MAX_JOBS,
    MODAL_SDK_VERSION,
    TRANSFORMERS_GIT_REVISION,
    TRANSFORMERS_PAYLOAD_SHA256,
    TRANSFORMERS_VERSION,
    TRANSFORMERS_WHEEL_SHA256,
    TUTORIAL_SOURCE_REVISION,
)
from biohub_esm_lib.diagnostics import (
    DIAGNOSTIC_ARTIFACT_MAX_BYTES,
    bounded_provider_response_diagnostic,
    redact_provider_json_in_place,
    safe_provider_response_diagnostic,
)
from biohub_esm_lib.errors import APIError, BiohubESMError, SchemaDriftError, ValidationError
from biohub_esm_lib.esmc import (
    derive_single_mask_llr,
    render_mutation_score_svg,
    validate_sequence_logits,
    validate_single_substitution,
)
from biohub_esm_lib.esmc_landscape import (
    CANONICAL_AMINO_ACIDS,
    ESMC_LANDSCAPE_MAX_RESIDUES,
    canonical_token_ids,
    derive_mutation_landscape,
    encode_esmc_sequence,
    mask_esmc_position,
    render_mutation_landscape_csv,
    summarize_reported_usage,
    validate_landscape_sequence,
)
from biohub_esm_lib.esmc_landscape_jobs import ESMCLandscapeStore
from biohub_esm_lib.http import (
    BiohubClient,
    _bind_provider_status,
    _validated_provider_status,
    validate_timeout,
)
from biohub_esm_lib.managed import (
    managed_confidence_metrics,
    managed_structure_quality_warnings,
    materialize_managed_structure,
    normalize_managed_response,
    validate_managed_structure_response,
)
from biohub_esm_lib.managed_readiness import (
    managed_structure_materialization_readiness,
    require_managed_structure_materialization_ready,
)
from biohub_esm_lib.modal_jobs import ModalFunctionAdapter, ModalJobManager, ModalJobStore
from biohub_esm_lib.presentation import (
    build_structure_presentation_request,
    validate_structure_presentation_request,
)
from biohub_esm_lib.provenance import (
    DISTRIBUTION_VERIFICATION_METHOD,
    artifact_record,
    atlas_source_attribution,
    build_provenance,
    canonical_json,
    input_digest,
    materialize_pdb_fields,
    numeric_metric_summary,
    prepare_fresh_output_directory,
    publish_bytes_atomic,
    publish_json_atomic,
    publish_stream_atomic,
    sha256_bytes,
    sha256_file,
    utc_now,
    validate_provenance,
    verify_installed_distribution,
    write_bytes_atomic_noreplace,
    write_json_atomic,
)
from biohub_esm_lib.routing import RouteRequest, route_request
from biohub_esm_lib.security import (
    credential_preflight,
    missing_esm_api_key_message,
    redact,
    register_redaction_secret,
    resolve_esm_api_key,
)
from biohub_esm_lib.starter_examples import load_tutorial_use_cases
from biohub_esm_lib.validation import (
    sequence_md5,
    validate_atlas_fold_sequence,
    validate_atlas_search_sequence,
    validate_batch_hashes,
    validate_esmc_sequence,
    validate_fold_config,
    validate_fold_input,
    validate_managed_esmc_request,
    validate_managed_fold_request,
    validate_md5,
)

# Request/control JSON must remain cheap to decode even when its wire body fits
# inside an endpoint limit. Scientific result arrays belong in bounded durable
# artifacts rather than these request and job-control documents.
CONTROL_JSON_MAX_DEPTH = 64
CONTROL_JSON_MAX_NODES = 100_000
CONTROL_JSON_MAX_AGGREGATE_BYTES = 32 * 1024 * 1024
CONTROL_JSON_MAX_STRING_BYTES = 1024 * 1024
CONTROL_JSON_MAX_NUMBER_CHARACTERS = 128
CONTROL_JSON_ESTIMATED_NODE_BYTES = 128
CONTROL_JSON_MAX_WIRE_BYTES = 32 * 1024 * 1024
SCIENTIFIC_JSON_MAX_NODES = 1_000_000
SCIENTIFIC_JSON_MAX_AGGREGATE_BYTES = 128 * 1024 * 1024
ATLAS_PROVENANCE_MAX_BYTES = 32 * 1024 * 1024


def _validate_control_json_wire_budget(
    encoded: bytes,
    *,
    field: str,
    max_nodes: int | None = None,
    max_aggregate_bytes: int | None = None,
) -> None:
    """Bound decoded-tree expansion before ``json.loads`` allocates the tree."""

    node_limit = CONTROL_JSON_MAX_NODES if max_nodes is None else max_nodes
    aggregate_limit = (
        CONTROL_JSON_MAX_AGGREGATE_BYTES if max_aggregate_bytes is None else max_aggregate_bytes
    )
    nodes = 0
    depth = 0
    aggregate_bytes = 0
    in_string = False
    escaped = False
    string_bytes = 0
    index = 0

    def add_node(payload_bytes: int = 0) -> None:
        nonlocal nodes, aggregate_bytes
        nodes += 1
        if nodes > node_limit:
            raise ValidationError(f"{field} exceeds the {node_limit}-node decoded-tree limit")
        aggregate_bytes += CONTROL_JSON_ESTIMATED_NODE_BYTES + payload_bytes
        if aggregate_bytes > aggregate_limit:
            raise ValidationError(
                f"{field} exceeds the {aggregate_limit}-byte estimated decoded aggregate limit"
            )

    while index < len(encoded):
        byte = encoded[index]
        if in_string:
            if escaped:
                escaped = False
                string_bytes += 1
            elif byte == 0x5C:
                escaped = True
                string_bytes += 1
            elif byte == 0x22:
                in_string = False
                add_node(string_bytes)
                index += 1
                continue
            else:
                string_bytes += 1
            if string_bytes > CONTROL_JSON_MAX_STRING_BYTES:
                raise ValidationError(
                    f"{field} contains a string exceeding the "
                    f"{CONTROL_JSON_MAX_STRING_BYTES}-byte limit"
                )
            index += 1
            continue

        if byte == 0x22:
            in_string = True
            string_bytes = 0
            index += 1
            continue
        if byte in (0x7B, 0x5B):
            depth += 1
            if depth > CONTROL_JSON_MAX_DEPTH:
                raise ValidationError(
                    f"{field} exceeds the {CONTROL_JSON_MAX_DEPTH}-level nesting depth"
                )
            add_node()
            index += 1
            continue
        if byte in (0x7D, 0x5D):
            depth = max(0, depth - 1)
            index += 1
            continue
        if byte in b"-0123456789":
            start = index
            index += 1
            while index < len(encoded) and encoded[index] in b"+-.0123456789Ee":
                index += 1
            token_length = index - start
            if token_length > CONTROL_JSON_MAX_NUMBER_CHARACTERS:
                raise ValidationError(
                    f"{field} contains a numeric token exceeding the "
                    f"{CONTROL_JSON_MAX_NUMBER_CHARACTERS}-character limit"
                )
            add_node(token_length)
            continue

        matched_literal = False
        for literal in (b"true", b"false", b"null"):
            if encoded.startswith(literal, index):
                add_node(len(literal))
                index += len(literal)
                matched_literal = True
                break
        if not matched_literal:
            index += 1


def load_bounded_json(
    path: str,
    *,
    max_bytes: int,
    field: str,
    max_nodes: int | None = None,
    max_aggregate_bytes: int | None = None,
) -> Any:
    """Load one request document within explicit wire and decoded-tree budgets."""

    try:
        if path == "-":
            stream = getattr(sys.stdin, "buffer", sys.stdin)
            encoded = stream.read(max_bytes + 1)
        else:
            with Path(path).open("rb") as handle:
                encoded = handle.read(max_bytes + 1)
    except (OSError, MemoryError) as exc:
        raise ValidationError(f"could not read {field}") from exc
    if isinstance(encoded, str):
        try:
            encoded = encoded.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValidationError(f"{field} must be valid bounded JSON") from exc
    if len(encoded) > max_bytes:
        raise ValidationError(f"{field} exceeds the {max_bytes}-byte limit")
    _validate_control_json_wire_budget(
        encoded,
        field=field,
        max_nodes=max_nodes,
        max_aggregate_bytes=max_aggregate_bytes,
    )

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    def bounded_int(value: str) -> int:
        if len(value) > CONTROL_JSON_MAX_NUMBER_CHARACTERS:
            raise ValueError("JSON integer token exceeds the numeric safety bound")
        return int(value)

    def finite_float(value: str) -> float:
        if len(value) > CONTROL_JSON_MAX_NUMBER_CHARACTERS:
            raise ValueError("JSON float token exceeds the numeric safety bound")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("non-finite JSON number")
        mantissa = value.lower().split("e", 1)[0]
        if result == 0.0 and any(character in "123456789" for character in mantissa):
            raise ValueError("JSON number underflows the finite float range")
        return result

    try:
        return json.loads(
            encoded,
            parse_constant=reject_constant,
            parse_float=finite_float,
            parse_int=bounded_int,
        )
    except ValidationError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        OverflowError,
        RecursionError,
        MemoryError,
        ValueError,
    ) as exc:
        raise ValidationError(f"{field} must be valid bounded JSON") from exc


def load_bounded_sequence(path: str, *, max_residues: int) -> str:
    """Read one FASTA without allocating an unbounded header or sequence."""

    # Leave room for a descriptive FASTA header, wrapping, and CRLF without
    # allowing a sequence database to be materialized before residue validation.
    max_bytes = 16 * 1024 + 8 * max_residues
    try:
        with Path(path).open("rb") as handle:
            encoded = handle.read(max_bytes + 1)
    except (OSError, MemoryError) as exc:
        raise ValidationError("could not read sequence file") from exc
    if len(encoded) > max_bytes:
        raise ValidationError(
            f"sequence file exceeds the {max_bytes}-byte limit for "
            f"a {max_residues}-residue sequence"
        )
    try:
        return encoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("sequence file must contain valid UTF-8") from exc


def emit(value: Any) -> None:
    print(
        json.dumps(
            redact(value),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    )


def _bounded_provider_diagnostic_bytes(raw: Any) -> bytes:
    """Encode one redacted diagnostic envelope within the shared 64 KiB bound."""

    payload = {
        "schema_version": "1.0",
        "status": "rejected-provider-response",
        "diagnostic": bounded_provider_response_diagnostic(raw),
    }
    encoded = canonical_json(payload) + b"\n"
    if len(encoded) >= DIAGNOSTIC_ARTIFACT_MAX_BYTES:
        payload["diagnostic"] = {
            "representation": "diagnostic-safety-fallback",
            "truncated": True,
            "truncation_reasons": ["artifact-byte-limit"],
        }
        encoded = canonical_json(payload) + b"\n"
    if len(encoded) >= DIAGNOSTIC_ARTIFACT_MAX_BYTES:
        raise ValidationError("schema-drift diagnostic exceeded its 64 KiB safety bound")
    return encoded


def _write_bounded_provider_diagnostic(path: Path, raw: Any) -> None:
    """Persist one redacted diagnostic envelope within the shared 64 KiB bound."""

    encoded = _bounded_provider_diagnostic_bytes(raw)
    write_bytes_atomic_noreplace(path, encoded)


def _persist_schema_drift(args: argparse.Namespace, exc: SchemaDriftError) -> None:
    """Retain a redacted diagnostic artifact without echoing the payload to stderr."""

    if exc.diagnostic_path:
        return
    output_dir_value = getattr(args, "output_dir", None)
    output_value = getattr(args, "output", None)
    if exc.raw is None or (not output_dir_value and not output_value):
        return
    if output_dir_value:
        output_dir = Path(output_dir_value).resolve()
        prefix = "schema-drift-diagnostic"
    else:
        output_path = Path(output_value).resolve()
        output_dir = output_path.parent
        prefix = f"{output_path.name}.schema-drift-diagnostic"
    path = output_dir / f"{prefix}.json"
    _write_bounded_provider_diagnostic(path, exc.raw)
    exc.diagnostic_path = str(path)


def _save_atlas_artifact_provenance(
    artifact_path: Path,
    *,
    media_type: str,
    endpoint_path: str,
    inputs: Any,
    parameters: dict[str, Any],
    started_at: str,
    base_url: str = BIOHUB_BASE_URL,
    provider_calls: list[dict[str, Any]] | None = None,
    input_sha256: str | None = None,
    replace_existing: bool = True,
    expected_artifact_identity: tuple[int, int] | None = None,
    expected_artifact_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provenance_path = artifact_path.with_name(f"{artifact_path.name}.provenance.json")
    with open_atlas_artifact_snapshot(
        artifact_path,
        media_type=media_type,
        expected_identity=expected_artifact_identity,
    ) as artifact_snapshot:
        if expected_artifact_record is not None:
            expected_size = expected_artifact_record.get("size_bytes")
            expected_sha256 = expected_artifact_record.get("sha256")
            if (
                isinstance(expected_size, bool)
                or not isinstance(expected_size, int)
                or expected_size < 0
                or not isinstance(expected_sha256, str)
                or len(expected_sha256) != 64
                or any(character not in "0123456789abcdef" for character in expected_sha256)
            ):
                raise ValidationError("validated Atlas artifact record is malformed")
            if (
                artifact_snapshot.record["size_bytes"] != expected_size
                or artifact_snapshot.record["sha256"] != expected_sha256
            ):
                raise ValidationError("Atlas artifact content changed after validated download")
        provenance = build_provenance(
            route="atlas-api",
            endpoint=f"{base_url.rstrip('/')}{ATLAS_API_PREFIX}{endpoint_path}",
            model_id=None,
            model_revision=None,
            inputs=inputs,
            input_sha256=input_sha256,
            parameters=parameters,
            seed=None,
            started_at=started_at,
            artifacts=[artifact_snapshot.record],
            provider_calls=provider_calls,
            source_attribution=atlas_source_attribution(),
        )
        with publish_json_atomic(
            provenance_path,
            provenance,
            replace=replace_existing,
        ) as provenance_publication:
            with open_atlas_artifact_snapshot(
                provenance_path,
                media_type="application/json",
                expected_identity=provenance_publication.identity,
            ) as provenance_snapshot:
                artifact_snapshot.validate_path_identity()
                provenance_snapshot.validate_path_identity()
                return {
                    "artifact": artifact_snapshot.record,
                    "artifact_identity": artifact_snapshot.identity,
                    "provenance": str(provenance_path),
                    "provenance_artifact": provenance_snapshot.record,
                    "provenance_identity": provenance_snapshot.identity,
                }


def _atlas_endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{ATLAS_API_PREFIX}{path}"


def _safe_download_endpoint(url: str) -> str:
    return safe_download_endpoint(url)


def _atlas_output_claim_path(destination: Path) -> Path:
    return destination.with_name(f".{destination.name}.biohub-esm-materialization.lock")


@contextmanager
def _atlas_output_claim(destination: Path, *, deadline: float | None = None) -> Iterator[None]:
    """Serialize cooperating materializers that target the same resolved output."""

    if deadline is not None and (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(deadline)
    ):
        raise ValidationError("Atlas output claim deadline must be finite")
    lock_path = _atlas_output_claim_path(destination)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise ValidationError("Atlas output claim path is not a safe regular file") from exc
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValidationError("Atlas output claim path is not a safe regular file")
    with os.fdopen(descriptor, "a+b") as handle:
        if deadline is None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        else:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise APIError(
                        status=None,
                        kind="timeout",
                        message="Atlas output claim timed out",
                    )
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(min(0.01, remaining))
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _atlas_output_claim_if_present(
    destination: Path | None, *, deadline: float | None = None
) -> Iterator[None]:
    if destination is None:
        yield
        return
    with _atlas_output_claim(destination, deadline=deadline):
        yield


def _reserve_atlas_batch_partial(destination: Path) -> tuple[Path, tuple[int, int]] | None:
    """Reserve a new partial name; existing partials must already be state-bound."""

    partial = destination.with_suffix(destination.suffix + ".partial")
    if partial.exists() or partial.is_symlink():
        return None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(partial, flags, 0o600)
    except FileExistsError:
        raise ValidationError(
            "refusing to adopt an Atlas batch partial that appeared after proof validation"
        ) from None
    try:
        info = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    return partial, (info.st_dev, info.st_ino)


def _state_bound_atlas_partial_marker(
    state: dict[str, Any], destination: Path
) -> dict[str, Any] | None:
    response = state.get("last_response")
    marker = response.get("artifact_materialization") if isinstance(response, dict) else None
    partial = destination.with_suffix(destination.suffix + ".partial")
    if not (
        state.get("status") == "completed"
        and isinstance(state.get("job_id"), str)
        and isinstance(marker, dict)
        and marker.get("status") in {"pending", "failed", "completed"}
        and marker.get("destination_path") == str(destination)
        and marker.get("partial_path") == str(partial)
        and (
            marker.get("status") == "pending"
            or marker.get("partial_reserved") is True
            or marker.get("partial_output") is True
            or (marker.get("status") == "failed" and marker.get("output_present") is True)
            or (marker.get("status") == "completed" and marker.get("partial_residue") is True)
        )
    ):
        return None
    device = marker.get("partial_device")
    inode = marker.get("partial_inode")
    if (
        isinstance(device, bool)
        or not isinstance(device, int)
        or device < 0
        or isinstance(inode, bool)
        or not isinstance(inode, int)
        or inode < 0
    ):
        return None
    try:
        info = partial.stat(follow_symlinks=False)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != (device, inode):
        return None
    return dict(marker)


def _state_bound_atlas_artifact_identity(
    state: dict[str, Any], destination: Path
) -> tuple[int, int] | None:
    marker = _state_bound_atlas_partial_marker(state, destination)
    if marker is None:
        return None
    return marker["partial_device"], marker["partial_inode"]


def _atlas_marker_identity(marker: Any, prefix: str) -> tuple[int, int] | None:
    if not isinstance(marker, dict):
        return None
    device = marker.get(f"{prefix}_device")
    inode = marker.get(f"{prefix}_inode")
    if (
        isinstance(device, bool)
        or not isinstance(device, int)
        or device < 0
        or isinstance(inode, bool)
        or not isinstance(inode, int)
        or inode < 0
    ):
        return None
    return device, inode


def _decode_atlas_provenance_snapshot(encoded: bytes | None) -> dict[str, Any]:
    if encoded is None:
        raise ValidationError("Atlas provenance snapshot is unavailable")
    _validate_control_json_wire_budget(encoded, field="Atlas artifact provenance")

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    def finite_float(value: str) -> float:
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("non-finite JSON number")
        return result

    try:
        provenance = json.loads(
            encoded,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        OverflowError,
        RecursionError,
        MemoryError,
        ValueError,
    ) as exc:
        raise ValidationError("Atlas artifact provenance must be valid bounded JSON") from exc
    if not isinstance(provenance, dict):
        raise ValidationError("Atlas artifact provenance must be an object")
    return provenance


@contextmanager
def _atlas_artifact_pair_snapshot(
    artifact_path: Path,
    provenance_path: Path,
    *,
    media_type: str,
    expected_artifact_identity: tuple[int, int] | None = None,
    expected_provenance_identity: tuple[int, int] | None = None,
) -> Iterator[dict[str, Any]]:
    with open_atlas_artifact_snapshot(
        artifact_path,
        media_type=media_type,
        expected_identity=expected_artifact_identity,
    ) as artifact_snapshot:
        with open_atlas_artifact_snapshot(
            provenance_path,
            media_type="application/json",
            expected_identity=expected_provenance_identity,
            capture_max_bytes=ATLAS_PROVENANCE_MAX_BYTES,
        ) as provenance_snapshot:
            provenance = _decode_atlas_provenance_snapshot(provenance_snapshot.captured)
            artifact_snapshot.validate_path_identity()
            provenance_snapshot.validate_path_identity()
            yield {
                "artifact": artifact_snapshot.record,
                "artifact_identity": artifact_snapshot.identity,
                "provenance_artifact": provenance_snapshot.record,
                "provenance_identity": provenance_snapshot.identity,
                "provenance": provenance,
            }
            artifact_snapshot.validate_path_identity()
            provenance_snapshot.validate_path_identity()


def _atlas_published_residue_identity(partial: Path, destination: Path) -> tuple[int, int] | None:
    try:
        partial_info = partial.stat(follow_symlinks=False)
        destination_info = destination.stat(follow_symlinks=False)
    except OSError:
        return None
    partial_identity = (partial_info.st_dev, partial_info.st_ino)
    if (
        not stat.S_ISREG(partial_info.st_mode)
        or not stat.S_ISREG(destination_info.st_mode)
        or partial_identity != (destination_info.st_dev, destination_info.st_ino)
    ):
        return None
    return partial_identity


def _atlas_partial_is_published_residue(partial: Path, destination: Path) -> bool:
    return _atlas_published_residue_identity(partial, destination) is not None


def _atlas_partial_size(
    partial: Path,
    *,
    expected_identity: tuple[int, int] | None = None,
) -> int | None:
    try:
        info = partial.stat(follow_symlinks=False)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or (
        expected_identity is not None and (info.st_dev, info.st_ino) != expected_identity
    ):
        return None
    return info.st_size


def _bind_atlas_published_residue(marker: dict[str, Any], partial: Path, destination: Path) -> None:
    identity = _atlas_published_residue_identity(partial, destination)
    if identity is not None:
        marker["partial_residue"] = True
        marker["partial_device"] = identity[0]
        marker["partial_inode"] = identity[1]


def _validate_atlas_batch_output(store: AtlasBatchStore, output: str | None) -> None:
    if output is None:
        return
    destination = Path(output).resolve()
    controls = (store.path, store.provenance_path, store.lock_path)
    claim_path = _atlas_output_claim_path(destination)
    candidates = (
        destination,
        destination.with_name(f"{destination.name}.provenance.json"),
        destination.with_suffix(destination.suffix + ".partial"),
    )
    if claim_path in controls or any(candidate in controls for candidate in candidates):
        raise ValidationError("Atlas batch output must not alias state control files")
    if claim_path.exists() and any(
        control.exists() and os.path.samefile(claim_path, control) for control in controls
    ):
        raise ValidationError("Atlas output claim must not alias state control files")
    existing = tuple(
        candidate for candidate in candidates if candidate.exists() or candidate.is_symlink()
    )
    if not existing:
        return
    if not store.path.exists():
        raise ValidationError(
            "refusing to overwrite an existing Atlas batch output without durable state"
        )
    for candidate in existing:
        for control in controls:
            if control.exists() and candidate.exists() and os.path.samefile(candidate, control):
                raise ValidationError("Atlas batch output must not alias state control files")

    state = store.load()
    destination_exists = destination in existing
    provenance_path = candidates[1]
    provenance_exists = provenance_path in existing
    partial_path = candidates[2]
    partial_exists = partial_path in existing

    verified: dict[str, Any] | None = None
    if destination_exists or provenance_exists:
        job_id = state.get("job_id")
        if isinstance(job_id, str):
            verified = _verified_atlas_batch_materialization(
                state,
                destination,
                job_id=job_id,
                endpoint=_atlas_endpoint(
                    BIOHUB_BASE_URL,
                    f"/proteins/batch/jobs/{job_id}",
                ),
            )
        elif job_id is None:
            request = state.get("request")
            if isinstance(request, dict):
                input_sha256 = request.get("input_sha256")
                parameters = request.get("parameters")
                if isinstance(input_sha256, str) and isinstance(parameters, dict):
                    verified = _verified_synchronous_atlas_batch_materialization(
                        state,
                        destination,
                        endpoint=state["endpoint"],
                        input_sha256=input_sha256,
                        parameters=parameters,
                    )
                    if verified is None:
                        verified = _verified_completed_atlas_batch_artifacts(state, destination)
        if verified is None:
            raise ValidationError(
                "refusing to overwrite an Atlas batch output that is not bound by "
                "matching artifact provenance"
            )

    if partial_exists:
        published_residue = (
            verified is not None
            and destination_exists
            and provenance_exists
            and not partial_path.is_symlink()
            and _atlas_partial_is_published_residue(partial_path, destination)
        )
        exact_partial_resume = published_residue or (
            _state_bound_atlas_partial_marker(state, destination) is not None
            and not partial_path.is_symlink()
            and not destination_exists
            and not provenance_exists
        )
        if not exact_partial_resume:
            raise ValidationError(
                "refusing to resume an Atlas batch partial output that is not bound "
                "to the exact durable materialization state"
            )


def _validate_atlas_batch_topk(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise ValidationError("topk_features must be an integer between 1 and 100")


def _record_atlas_batch_call_failure(
    store: AtlasBatchStore,
    client: Any,
    *,
    endpoint: str,
    operation: str,
    exc: BiohubESMError,
    partial_marker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = store.record_provider_call(
        provider_call=_atlas_exception_provider_call(
            client,
            endpoint=endpoint,
            operation=operation,
            exc=exc,
        ),
        response=_atlas_failure_record(exc),
    )
    if partial_marker is not None:
        state["last_response"]["artifact_materialization"] = partial_marker
        state = store.save(state)
    _persist_atlas_batch_provenance(store, state)
    return state


def _atlas_batch_materialization_paths(destination: Path) -> tuple[Path, Path, Path]:
    destination = destination.resolve()
    provenance_path = destination.with_name(f"{destination.name}.provenance.json")
    partial_path = destination.with_suffix(destination.suffix + ".partial")
    return destination, provenance_path, partial_path


def _atlas_artifact_path(record: dict[str, Any]) -> Path | None:
    value = record.get("path")
    if not isinstance(value, str) or not value:
        return None
    try:
        return Path(value).resolve()
    except OSError:
        return None


def _atlas_artifact_matches(
    record: dict[str, Any], expected: dict[str, Any], expected_path: Path
) -> bool:
    return (
        _atlas_artifact_path(record) == expected_path
        and record.get("size_bytes") == expected["size_bytes"]
        and record.get("sha256") == expected["sha256"]
        and record.get("media_type") == expected["media_type"]
    )


@contextmanager
def _atlas_verified_artifact_pair(
    destination: Path, verified: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    destination, provenance_path, _ = _atlas_batch_materialization_paths(destination)
    artifact_identity = verified.get("artifact_identity")
    provenance_identity = verified.get("provenance_identity")
    with _atlas_artifact_pair_snapshot(
        destination,
        provenance_path,
        media_type="application/zip",
        expected_artifact_identity=artifact_identity,
        expected_provenance_identity=provenance_identity,
    ) as current:
        if not _atlas_artifact_matches(verified["artifact"], current["artifact"], destination):
            raise ValidationError("Atlas artifact changed before durable acceptance")
        if not _atlas_artifact_matches(
            verified["provenance_artifact"],
            current["provenance_artifact"],
            provenance_path,
        ):
            raise ValidationError("Atlas artifact provenance changed before durable acceptance")
        yield current


@contextmanager
def _atlas_retained_partial_acceptance(
    destination: Path, artifact_identity: tuple[int, int]
) -> Iterator[None]:
    _, _, partial_path = _atlas_batch_materialization_paths(destination)
    if not (partial_path.exists() or partial_path.is_symlink()):
        yield
        return
    with hold_atlas_artifact_identity(
        partial_path,
        expected_identity=artifact_identity,
    ):
        yield


def _bind_atlas_evidence_identities(marker: dict[str, Any], evidence: dict[str, Any]) -> None:
    artifact_identity = evidence["artifact_identity"]
    provenance_identity = evidence["provenance_identity"]
    marker.update(
        {
            "artifact_device": artifact_identity[0],
            "artifact_inode": artifact_identity[1],
            "provenance_device": provenance_identity[0],
            "provenance_inode": provenance_identity[1],
        }
    )


def _without_atlas_materialization_artifacts(
    artifacts: list[dict[str, Any]], destination: Path, provenance_path: Path
) -> list[dict[str, Any]]:
    controlled = {destination, provenance_path}
    return [record for record in artifacts if _atlas_artifact_path(record) not in controlled]


def _verified_atlas_batch_materialization(
    state: dict[str, Any],
    destination: Path,
    *,
    job_id: str,
    endpoint: str,
) -> dict[str, Any] | None:
    """Verify a completed zip and its independent provenance before adoption.

    This is the recovery boundary for a process that ended after the artifact
    provenance was made durable but before the batch state captured it.
    """

    destination, provenance_path, _ = _atlas_batch_materialization_paths(destination)
    if not destination.is_file() or not provenance_path.is_file():
        return None
    expected_artifact_identity = _state_bound_atlas_artifact_identity(state, destination)
    marker = state.get("last_response", {}).get("artifact_materialization")
    marker_artifact_identity = _atlas_marker_identity(marker, "artifact")
    marker_provenance_identity = _atlas_marker_identity(marker, "provenance")
    if (
        expected_artifact_identity is not None
        and marker_artifact_identity is not None
        and marker_artifact_identity != expected_artifact_identity
    ):
        return None
    expected_artifact_identity = expected_artifact_identity or marker_artifact_identity
    durable_checksum_binding = (
        expected_artifact_identity is None
        and isinstance(marker, dict)
        and marker.get("status") == "completed"
        and marker.get("destination_path") == str(destination)
        and isinstance(marker.get("artifact_sha256"), str)
        and isinstance(marker.get("provenance_sha256"), str)
    )
    if expected_artifact_identity is None and not durable_checksum_binding:
        return None
    try:
        with _atlas_artifact_pair_snapshot(
            destination,
            provenance_path,
            media_type="application/zip",
            expected_artifact_identity=expected_artifact_identity,
            expected_provenance_identity=marker_provenance_identity,
        ) as verified:
            artifact = verified["artifact"]
            provenance_artifact = verified["provenance_artifact"]
            provenance = verified["provenance"]
            validate_provenance(provenance)
            if (
                provenance.get("execution_route") != "atlas-api"
                or provenance.get("endpoint") != endpoint
                or provenance.get("input_sha256") != input_digest({"job_id": job_id})
            ):
                return None
            provenance_records = provenance.get("artifacts", [])
            if not any(
                isinstance(record, dict) and _atlas_artifact_matches(record, artifact, destination)
                for record in provenance_records
            ):
                return None
            download_calls = [
                call
                for call in provenance.get("provider_calls", [])
                if isinstance(call, dict) and call.get("operation") == "download"
            ]
            if not download_calls:
                return None
            try:
                safe_download_endpoint(download_calls[-1]["endpoint"])
            except (KeyError, TypeError, ValidationError):
                return None

            expected_by_path = {destination: artifact, provenance_path: provenance_artifact}
            state_records = [
                record
                for record in state.get("artifacts", [])
                if isinstance(record, dict) and _atlas_artifact_path(record) in expected_by_path
            ]
            if durable_checksum_binding and (
                len(state_records) != 2
                or marker["artifact_sha256"] != artifact["sha256"]
                or marker["provenance_sha256"] != provenance_artifact["sha256"]
            ):
                return None
            if any(
                not _atlas_artifact_matches(record, expected_by_path[path], path)
                for record in state_records
                if (path := _atlas_artifact_path(record)) in expected_by_path
            ):
                return None
            result = {
                **verified,
                "download_call": download_calls[-1],
            }
    except (OSError, BiohubESMError, ValueError):
        return None
    return result


def _verified_synchronous_atlas_batch_materialization(
    state: dict[str, Any],
    destination: Path,
    *,
    endpoint: str,
    input_sha256: str,
    parameters: dict[str, Any],
) -> dict[str, Any] | None:
    """Verify sync output made durable before its submission state was reconciled."""

    destination, provenance_path, _ = _atlas_batch_materialization_paths(destination)
    calls = state.get("provider_calls")
    unresolved_call = calls[-1] if isinstance(calls, list) and calls else None
    if (
        not isinstance(unresolved_call, dict)
        or unresolved_call.get("operation") != "submit"
        or not isinstance(unresolved_call.get("started_at"), str)
        or state.get("status") not in {"submitting", "submission-indeterminate"}
        or state.get("job_id") is not None
        or state.get("endpoint") != endpoint
        or state.get("request", {}).get("input_sha256") != input_sha256
        or state.get("request", {}).get("parameters") != redact(parameters)
        or not destination.is_file()
        or not provenance_path.is_file()
    ):
        return None
    try:
        with _atlas_artifact_pair_snapshot(
            destination,
            provenance_path,
            media_type="application/zip",
        ) as verified:
            artifact = verified["artifact"]
            provenance = verified["provenance"]
            validate_provenance(provenance)
            if (
                provenance.get("execution_route") != "atlas-api"
                or provenance.get("endpoint") != endpoint
                or provenance.get("input_sha256") != input_sha256
                or provenance.get("started_at") != unresolved_call["started_at"]
                or provenance.get("parameters") != redact(parameters)
            ):
                return None
            if not any(
                isinstance(record, dict) and _atlas_artifact_matches(record, artifact, destination)
                for record in provenance.get("artifacts", [])
            ):
                return None
            submit_calls = [
                call
                for call in provenance.get("provider_calls", [])
                if isinstance(call, dict)
                and call.get("operation") == "submit"
                and call.get("endpoint") == endpoint
                and call.get("http_status") == 200
            ]
            if not submit_calls:
                return None
            result = {**verified, "submit_call": submit_calls[-1]}
    except (OSError, BiohubESMError, ValueError):
        return None
    return result


def _verified_completed_atlas_batch_artifacts(
    state: dict[str, Any], destination: Path
) -> dict[str, Any] | None:
    """Verify an already-reconciled synchronous artifact pair from durable checksums."""

    destination, provenance_path, _ = _atlas_batch_materialization_paths(destination)
    if (
        state.get("status") != "completed"
        or state.get("job_id") is not None
        or not destination.is_file()
        or not provenance_path.is_file()
    ):
        return None
    marker = state.get("last_response", {}).get("artifact_materialization")
    try:
        with _atlas_artifact_pair_snapshot(
            destination,
            provenance_path,
            media_type="application/zip",
            expected_artifact_identity=_atlas_marker_identity(marker, "artifact"),
            expected_provenance_identity=_atlas_marker_identity(marker, "provenance"),
        ) as verified:
            artifact = verified["artifact"]
            provenance_artifact = verified["provenance_artifact"]
            expected_by_path = {destination: artifact, provenance_path: provenance_artifact}
            matching = [
                record
                for record in state.get("artifacts", [])
                if isinstance(record, dict) and _atlas_artifact_path(record) in expected_by_path
            ]
            if len(matching) != 2:
                return None
            if any(
                not _atlas_artifact_matches(record, expected_by_path[path], path)
                for record in matching
                if (path := _atlas_artifact_path(record)) in expected_by_path
            ):
                return None
            result = verified
    except (OSError, BiohubESMError, ValueError):
        return None
    return result


def _atlas_materialization_is_current(
    state: dict[str, Any], destination: Path, verified: dict[str, Any]
) -> bool:
    destination, provenance_path, _ = _atlas_batch_materialization_paths(destination)
    try:
        with (
            _atlas_verified_artifact_pair(destination, verified) as current,
            _atlas_retained_partial_acceptance(
                destination,
                current["artifact_identity"],
            ),
        ):
            marker = state.get("last_response", {}).get("artifact_materialization")
            if not isinstance(marker, dict) or marker.get("status") != "completed":
                return False
            if (
                marker.get("destination_path") != str(destination)
                or marker.get("artifact_sha256") != current["artifact"]["sha256"]
                or marker.get("provenance_sha256") != current["provenance_artifact"]["sha256"]
            ):
                return False
            marker_artifact_identity = _atlas_marker_identity(marker, "artifact")
            marker_provenance_identity = _atlas_marker_identity(marker, "provenance")
            if (
                marker_artifact_identity is not None
                and marker_artifact_identity != current["artifact_identity"]
            ) or (
                marker_provenance_identity is not None
                and marker_provenance_identity != current["provenance_identity"]
            ):
                return False
            matching = [
                record
                for record in state.get("artifacts", [])
                if isinstance(record, dict)
                and _atlas_artifact_path(record) in {destination, provenance_path}
            ]
            if len(matching) != 2:
                return False
            for record in matching:
                path = _atlas_artifact_path(record)
                expected = (
                    current["artifact"] if path == destination else current["provenance_artifact"]
                )
                if path is None or not _atlas_artifact_matches(record, expected, path):
                    return False
    except (OSError, BiohubESMError, ValueError):
        return False
    return True


def _reconcile_atlas_batch_materialization(
    store: AtlasBatchStore,
    state: dict[str, Any],
    destination: Path,
    verified: dict[str, Any],
) -> dict[str, Any]:
    destination, provenance_path, partial_path = _atlas_batch_materialization_paths(destination)
    with (
        _atlas_verified_artifact_pair(destination, verified) as current,
        _atlas_retained_partial_acceptance(
            destination,
            current["artifact_identity"],
        ),
    ):
        state["artifacts"] = _without_atlas_materialization_artifacts(
            state["artifacts"], destination, provenance_path
        )
        state["artifacts"].extend([current["artifact"], current["provenance_artifact"]])
        response = dict(state["last_response"])
        marker = {
            "status": "completed",
            "destination_path": str(destination),
            "partial_path": str(partial_path),
            "partial_output": False,
            "artifact_sha256": current["artifact"]["sha256"],
            "provenance_sha256": current["provenance_artifact"]["sha256"],
            "recovered_from_artifact_provenance": True,
        }
        _bind_atlas_evidence_identities(marker, current)
        _bind_atlas_published_residue(marker, partial_path, destination)
        response["artifact_materialization"] = marker
        state["last_response"] = response
        verified_download_call = verified.get("download_call")
        if isinstance(verified_download_call, dict):
            download_call = dict(verified_download_call)
            already_recorded = any(
                call.get("operation") == "download"
                and call.get("endpoint") == download_call.get("endpoint")
                and call.get("http_status") == download_call.get("http_status")
                for call in state["provider_calls"]
            )
            if not already_recorded:
                download_call["recovered_from_artifact_provenance"] = True
                state["provider_calls"].append(download_call)
        state["updated_at"] = utc_now()
        return store.save(state)


def _begin_atlas_batch_materialization(
    store: AtlasBatchStore,
    state: dict[str, Any],
    destination: Path,
    partial_identity: tuple[int, int],
) -> dict[str, Any]:
    destination, provenance_path, partial_path = _atlas_batch_materialization_paths(destination)
    if state.get("status") != "completed" or state.get("job_id") is None:
        raise ValidationError("Atlas batch output can only materialize a completed async job")
    state["artifacts"] = _without_atlas_materialization_artifacts(
        state["artifacts"], destination, provenance_path
    )
    response = dict(state["last_response"])
    partial_size = _atlas_partial_size(
        partial_path,
        expected_identity=partial_identity,
    )
    response["artifact_materialization"] = {
        "status": "pending",
        "destination_path": str(destination),
        "partial_path": str(partial_path),
        "partial_device": partial_identity[0],
        "partial_inode": partial_identity[1],
        "partial_reserved": partial_size is not None,
        "partial_output": partial_size is not None and partial_size > 0,
        "output_present": destination.is_file(),
    }
    state["last_response"] = response
    state["updated_at"] = utc_now()
    return store.save(state)


def _fail_atlas_batch_materialization(
    store: AtlasBatchStore,
    state: dict[str, Any],
    destination: Path,
    *,
    reason: str,
    provider_call: dict[str, Any] | None = None,
) -> dict[str, Any]:
    destination, provenance_path, partial_path = _atlas_batch_materialization_paths(destination)
    state["artifacts"] = _without_atlas_materialization_artifacts(
        state["artifacts"], destination, provenance_path
    )
    response = dict(state["last_response"])
    previous_marker = response.get("artifact_materialization")
    partial_identity = _atlas_marker_identity(previous_marker, "partial")
    partial_size = (
        None
        if partial_identity is None
        else _atlas_partial_size(
            partial_path,
            expected_identity=partial_identity,
        )
    )
    marker = {
        "status": "failed",
        "destination_path": str(destination),
        "partial_path": str(partial_path),
        "partial_reserved": partial_size is not None,
        "partial_output": (
            partial_size is not None
            and partial_size > 0
            and not _atlas_partial_is_published_residue(partial_path, destination)
        ),
        "output_present": destination.is_file(),
        "error": redact(reason),
    }
    if isinstance(previous_marker, dict):
        for key in ("partial_device", "partial_inode"):
            value = previous_marker.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                marker[key] = value
    response["artifact_materialization"] = marker
    state["last_response"] = response
    if provider_call is not None:
        state["provider_calls"].append(redact(provider_call))
    state["updated_at"] = utc_now()
    return store.save(state)


def _retry_synchronous_artifact_materialization(
    store: AtlasBatchStore,
    state: dict[str, Any],
    *,
    endpoint: str,
    input_sha256: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Re-arm an exact submit whose confirmed synchronous output was not durable."""

    response = state.get("last_response")
    materialization = (
        response.get("artifact_materialization") if isinstance(response, dict) else None
    )
    if (
        state.get("status") != "completed"
        or state.get("job_id") is not None
        or not isinstance(response, dict)
        or response.get("delivery") != "synchronous"
        or not isinstance(materialization, dict)
        or materialization.get("status") not in {"pending", "failed"}
        or state.get("artifacts")
    ):
        raise ValidationError("Atlas batch state is not an incomplete synchronous delivery")
    if state["request"]["input_sha256"] != input_sha256 or state["request"]["parameters"] != redact(
        parameters
    ):
        raise ValidationError(
            "retry request does not match the incomplete synchronous Atlas batch submission"
        )

    started_at = utc_now()
    state["status"] = "submitting"
    state["endpoint"] = endpoint
    state["updated_at"] = started_at
    state["last_http_status"] = None
    state["last_response"] = {
        "status": "submitting",
        "retry": True,
        "reason": "synchronous-artifact-materialization",
    }
    state["provider_calls"].append(
        {
            "endpoint": endpoint,
            "operation": "submit",
            "http_status": None,
            "started_at": started_at,
            "outcome": "in-flight",
            "retry_after_artifact_materialization": redact(materialization),
        }
    )
    return store.save(state)


def _persist_atlas_batch_provenance(
    store: AtlasBatchStore, state: dict[str, Any]
) -> dict[str, Any]:
    state_artifact = artifact_record(store.path, media_type="application/json")
    provenance = build_provenance(
        route="atlas-api",
        endpoint=state["endpoint"],
        model_id=None,
        model_revision=None,
        inputs={"job_id": state["job_id"], "status": state["status"]},
        input_sha256=state["request"]["input_sha256"],
        parameters=state["request"]["parameters"],
        seed=None,
        started_at=state["submitted_at"],
        artifacts=[state_artifact, *state["artifacts"]],
        provider_calls=state["provider_calls"],
        finished_at=state["updated_at"],
        source_attribution=atlas_source_attribution(),
    )
    if "provider_call_history" in state:
        provenance["provider_call_history"] = redact(state["provider_call_history"])
        validate_provenance(provenance)
    write_json_atomic(store.provenance_path, provenance)
    return {
        "state": str(store.path),
        "state_artifact": state_artifact,
        "provenance": str(store.provenance_path),
        "job": state,
    }


def _load_or_adopt_atlas_batch(
    args: argparse.Namespace,
    *,
    store: AtlasBatchStore | None = None,
) -> tuple[AtlasBatchStore, str | None, dict[str, Any]]:
    store = store or AtlasBatchStore(Path(args.state).resolve())
    if store.path.is_file():
        state = store.load()
        _persist_atlas_batch_provenance(store, state)
        if state["job_id"] is None and state["status"] == "completed":
            if getattr(args, "job_id", None) is not None:
                raise ValidationError("--job-id does not match the durable Atlas batch state")
            return store, None, state
        job_id = store.resolve_job_id(getattr(args, "job_id", None), state=state)
        return store, job_id, state
    requested = getattr(args, "job_id", None)
    if not requested:
        raise ValidationError(
            "Atlas batch state is missing; provide --job-id once to adopt an existing job"
        )
    endpoint = _atlas_endpoint(args.base_url, f"/proteins/batch/jobs/{requested}")
    state = store.adopt(job_id=requested, endpoint=endpoint)
    _persist_atlas_batch_provenance(store, state)
    return store, requested, state


def _strip_embedded_pdb(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key == "pdb" and isinstance(item, str):
                result["pdb_summary"] = {
                    "embedded": True,
                    "size_bytes": len(item.encode("utf-8")),
                    "sha256": sha256_bytes(item.encode("utf-8")),
                    "note": "pass --output-dir to preserve the structure artifact",
                }
            else:
                result[key] = _strip_embedded_pdb(item)
        return result
    if isinstance(value, list):
        return [_strip_embedded_pdb(item) for item in value]
    return value


def _save_atlas_result(
    result: dict[str, Any],
    *,
    raw_result: dict[str, Any] | None = None,
    output_dir: Path,
    operation: str,
    endpoint_path: str,
    inputs: Any,
    parameters: dict[str, Any],
    started_at: str,
    base_url: str = BIOHUB_BASE_URL,
    provider_calls: list[dict[str, Any]] | None = None,
    output_dir_prepared: bool = False,
    publication_stack: ExitStack | None = None,
    artifact_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scientific_raw = dict(result if raw_result is None else raw_result)
    redact_provider_json_in_place(scientific_raw)
    redact_provider_json_in_place(result)
    if output_dir_prepared:
        if not output_dir.is_dir():
            raise ValidationError("prepared Atlas output directory is missing")
    else:
        prepare_fresh_output_directory(output_dir)
    with ExitStack() as owned_publications:
        publications = publication_stack or owned_publications
        artifacts = artifact_records if artifact_records is not None else []
        if artifacts:
            raise ValidationError("Atlas artifact publication state must start empty")

        def publish_pdb(path: Path, value: bytes, media_type: str) -> dict[str, Any]:
            publication = publications.enter_context(
                publish_bytes_atomic(
                    path,
                    value,
                    replace=False,
                    media_type=media_type,
                )
            )
            record = dict(publication.record)
            artifacts.append(record)
            return record

        raw_path = output_dir / "raw-response.json"
        raw_publication = publications.enter_context(
            publish_json_atomic(raw_path, scientific_raw, replace=False)
        )
        artifacts.append(dict(raw_publication.record))
        normalized, _pdb_artifacts = materialize_pdb_fields(
            result,
            output_dir,
            prefix=operation,
            artifact_publisher=publish_pdb,
        )
        result_path = output_dir / "result.json"
        result_publication = publications.enter_context(
            publish_json_atomic(result_path, normalized, replace=False)
        )
        artifacts.append(dict(result_publication.record))
        confidence: dict[str, Any] = {}
        if operation == "search":
            hits = [hit for hit in result.get("similar_proteins", []) if isinstance(hit, dict)]
            confidence["similarity_scores"] = [
                hit.get("similarity_score") for hit in hits if "similarity_score" in hit
            ]
            for field in ("mean_plddt", "ptm"):
                values = [hit[field] for hit in hits if hit.get(field) is not None]
                if values:
                    confidence[f"hit_{field}"] = values
            residue_confidence = [
                {
                    "protein_hash": hit.get("protein_hash"),
                    **numeric_metric_summary(hit["residues_plddt"]),
                }
                for hit in hits
                if isinstance(hit.get("residues_plddt"), list)
            ]
            if residue_confidence:
                confidence["hit_residues_plddt"] = residue_confidence
        else:
            for key in ("mean_plddt", "ptm", "cluster_pct_characterized"):
                if key in result:
                    confidence[key] = result[key]
            if isinstance(result.get("residues_plddt"), list):
                confidence["residues_plddt"] = numeric_metric_summary(result["residues_plddt"])
        scaled_confidence = {
            field
            for field in (
                "hit_mean_plddt",
                "hit_ptm",
                "hit_residues_plddt",
                "mean_plddt",
                "ptm",
                "residues_plddt",
            )
            if field in confidence
        }
        if scaled_confidence:
            confidence["metric_metadata"] = {
                field: {"scale": "0-1"} for field in sorted(scaled_confidence)
            }
        provenance = build_provenance(
            route="atlas-api",
            endpoint=f"{base_url.rstrip('/')}{ATLAS_API_PREFIX}{endpoint_path}",
            model_id=None,
            model_revision=None,
            inputs=inputs,
            parameters=parameters,
            seed=None,
            started_at=started_at,
            artifacts=artifacts,
            confidence_metrics=confidence,
            provider_calls=provider_calls,
            source_attribution=atlas_source_attribution(),
        )
        provenance_path = output_dir / "provenance.json"
        provenance_publication = publications.enter_context(
            publish_json_atomic(provenance_path, provenance, replace=False)
        )
        return {
            "result": normalized,
            "artifacts": [*artifacts, dict(provenance_publication.record)],
            "provenance": str(provenance_path),
        }


def _persist_atlas_incomplete(
    exc: BiohubESMError,
    *,
    output_dir: Path,
    endpoint_path: str,
    inputs: Any,
    parameters: dict[str, Any],
    started_at: str,
    provider_calls: list[dict[str, Any]],
    base_url: str,
    output_dir_prepared: bool = False,
    publication_stack: ExitStack | None = None,
    existing_artifacts: list[dict[str, Any]] | None = None,
) -> None:
    """Bind a failed public Atlas request to bounded diagnostics and provenance."""

    if output_dir_prepared:
        if not output_dir.is_dir():
            raise ValidationError("prepared Atlas output directory is missing")
    else:
        prepare_fresh_output_directory(output_dir)
    with ExitStack() as owned_publications:
        publications = publication_stack or owned_publications
        artifacts = [dict(record) for record in (existing_artifacts or [])]
        raw_response_path = next(
            (
                output_dir / "raw-response.json"
                for record in artifacts
                if record.get("path") == str(output_dir / "raw-response.json")
            ),
            None,
        )
        if isinstance(exc, SchemaDriftError) and exc.raw is not None:
            # Provider JSON was already bounded and validated by decode_json. Redact
            # containers in place so preserving a large alpha response does not
            # duplicate the entire tree. Decoder failures carry bytes instead and
            # remain only in the bounded diagnostic below.
            redacted_raw = (
                redact_provider_json_in_place(exc.raw)
                if isinstance(exc.raw, (dict, list))
                else redact(exc.raw)
            )
            if raw_response_path is None and not isinstance(redacted_raw, (bytes, bytearray)):
                raw_response_path = output_dir / "raw-response.json"
                raw_publication = publications.enter_context(
                    publish_json_atomic(raw_response_path, redacted_raw, replace=False)
                )
                artifacts.append(dict(raw_publication.record))
            diagnostic_path = output_dir / "schema-drift-diagnostic.json"
            artifacts.append(
                _persist_managed_schema_drift_raw(
                    diagnostic_path,
                    exc.raw,
                    publications=publications,
                )
            )
            exc.diagnostic_path = str(diagnostic_path)
        provenance = build_provenance(
            route="atlas-api",
            endpoint=_atlas_endpoint(base_url, endpoint_path),
            model_id=None,
            model_revision=None,
            inputs=inputs,
            parameters=parameters,
            seed=None,
            started_at=started_at,
            artifacts=artifacts,
            provider_calls=provider_calls,
            source_attribution=atlas_source_attribution(),
        )
        provenance["status"] = "incomplete"
        failure = _atlas_failure_record(exc)
        provider_status = (
            _validated_provider_status(provider_calls[-1].get("http_status"))
            if provider_calls
            else None
        )
        if provider_status is not None and failure.get("provider_status") is None:
            failure["provider_status"] = provider_status
        if raw_response_path is not None:
            failure["raw_response_path"] = str(raw_response_path)
        provenance["failure"] = failure
        validate_provenance(provenance)
        publications.enter_context(
            publish_json_atomic(output_dir / "provenance.json", provenance, replace=False)
        )


def _persist_atlas_artifact_incomplete(
    exc: BiohubESMError,
    *,
    artifact_path: Path,
    endpoint_path: str,
    inputs: Any,
    parameters: dict[str, Any],
    started_at: str,
    provider_calls: list[dict[str, Any]],
    base_url: str,
) -> None:
    """Persist failed binary Atlas call evidence without fabricating an artifact."""

    with ExitStack() as publications:
        artifacts: list[dict[str, Any]] = []
        if isinstance(exc, SchemaDriftError) and exc.raw is not None:
            diagnostic_path = artifact_path.with_name(
                f"{artifact_path.name}.schema-drift-diagnostic.json"
            )
            artifacts.append(
                _persist_managed_schema_drift_raw(
                    diagnostic_path,
                    exc.raw,
                    publications=publications,
                )
            )
            exc.diagnostic_path = str(diagnostic_path)
        provenance = build_provenance(
            route="atlas-api",
            endpoint=_atlas_endpoint(base_url, endpoint_path),
            model_id=None,
            model_revision=None,
            inputs=inputs,
            parameters=parameters,
            seed=None,
            started_at=started_at,
            artifacts=artifacts,
            provider_calls=provider_calls,
            source_attribution=atlas_source_attribution(),
        )
        provenance["status"] = "incomplete"
        failure = _atlas_failure_record(exc)
        provider_status = (
            _validated_provider_status(provider_calls[-1].get("http_status"))
            if provider_calls
            else None
        )
        if provider_status is not None and failure.get("provider_status") is None:
            failure["provider_status"] = provider_status
        provenance["failure"] = failure
        validate_provenance(provenance)
        publications.enter_context(
            publish_json_atomic(
                artifact_path.with_name(f"{artifact_path.name}.provenance.json"),
                provenance,
                replace=False,
            )
        )


def _run_atlas_json_command(
    args: argparse.Namespace,
    *,
    operation: str,
    endpoint_path: str,
    inputs: Any,
    parameters: dict[str, Any],
    invocation: Callable[[AtlasClient], dict[str, Any]],
    strip_embedded_pdb: bool,
) -> None:
    started = utc_now()
    client = AtlasClient(base_url=args.base_url, timeout=args.timeout)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else None
    if output_dir is not None:
        prepare_fresh_output_directory(output_dir)
    try:
        result = invocation(client)
    except BiohubESMError as exc:
        provider_calls = list(client.provider_calls)
        if output_dir is not None:
            if provider_calls:
                _persist_atlas_incomplete(
                    exc,
                    output_dir=output_dir,
                    endpoint_path=endpoint_path,
                    inputs=inputs,
                    parameters=parameters,
                    started_at=started,
                    provider_calls=provider_calls,
                    base_url=args.base_url,
                    output_dir_prepared=True,
                )
            else:
                output_dir.rmdir()
        raise
    raw_result = getattr(client, "last_raw_response", None)
    if not isinstance(raw_result, dict):
        raw_result = result
    redact_provider_json_in_place(result)
    if output_dir is None:
        emit(_strip_embedded_pdb(result) if strip_embedded_pdb else result)
        return
    partial_artifacts: list[dict[str, Any]] = []
    with ExitStack() as publications:
        try:
            saved = _save_atlas_result(
                result,
                raw_result=raw_result,
                output_dir=output_dir,
                operation=operation,
                endpoint_path=endpoint_path,
                inputs=inputs,
                parameters=parameters,
                started_at=started,
                base_url=args.base_url,
                provider_calls=list(client.provider_calls),
                output_dir_prepared=True,
                publication_stack=publications,
                artifact_records=partial_artifacts,
            )
        except BiohubESMError as exc:
            _persist_atlas_incomplete(
                exc,
                output_dir=output_dir,
                endpoint_path=endpoint_path,
                inputs=inputs,
                parameters=parameters,
                started_at=started,
                provider_calls=list(client.provider_calls),
                base_url=args.base_url,
                output_dir_prepared=True,
                publication_stack=publications,
                existing_artifacts=partial_artifacts,
            )
            raise
    emit(saved)


def esm_sdk_runtime_status() -> dict[str, object]:
    """Report whether this interpreter can install the pinned esm SDK.

    The package floor is 3.10, which is correct for Atlas, routing, and the Modal
    control plane. The pinned esm distribution is stricter: ``esm==3.4.1.post1``
    requires Python 3.12 or newer and is validated here on 3.12 only, so
    reporting only credential status would let preflight look healthy on an
    interpreter where the SDK cannot be installed or has not been validated.
    """

    current = (sys.version_info.major, sys.version_info.minor)
    supported = ESM_SDK_PYTHON_MIN <= current < ESM_SDK_PYTHON_EXCLUSIVE_MAX
    required = f"{ESM_SDK_PYTHON_MIN[0]}.{ESM_SDK_PYTHON_MIN[1]}"
    status: dict[str, object] = {
        "status": "supported" if supported else "unsupported",
        "interpreter": f"{current[0]}.{current[1]}",
        "required": f">={required},<"
        f"{ESM_SDK_PYTHON_EXCLUSIVE_MAX[0]}.{ESM_SDK_PYTHON_EXCLUSIVE_MAX[1]}",
        "affects": (
            "managed ESMC mutation scoring, esmc-landscape, and ESMFold2 response serialization"
        ),
    }
    if not supported:
        status["remedy"] = (
            f"Create the environment with python{required} explicitly; "
            "Atlas and Modal-control routes still work on this interpreter."
        )
    return status


def command_preflight(args: argparse.Namespace) -> None:
    report = credential_preflight()
    report["esm_sdk_runtime"] = esm_sdk_runtime_status()
    endpoint = getattr(args, "endpoint", None)
    if endpoint in {"fold", "fold_all_atom"}:
        report["managed_structure_materialization"] = managed_structure_materialization_readiness(
            endpoint
        )
    emit(report)


def command_pins(_: argparse.Namespace) -> None:
    emit(
        {
            "esm_version": ESM_SDK_VERSION,
            "esm_wheel_sha256": ESM_SDK_WHEEL_SHA256,
            "esm_payload_sha256": ESM_SDK_PAYLOAD_SHA256,
            "esm_git_revision": ESM_GIT_REVISION,
            "transformers_version": TRANSFORMERS_VERSION,
            "transformers_wheel_sha256": TRANSFORMERS_WHEEL_SHA256,
            "transformers_payload_sha256": TRANSFORMERS_PAYLOAD_SHA256,
            "transformers_git_revision": TRANSFORMERS_GIT_REVISION,
            "tutorial_source_revision": TUTORIAL_SOURCE_REVISION,
            "hugging_face_revisions": HF_REVISIONS,
            "modal_sdk_version": MODAL_SDK_VERSION,
        }
    )


def command_verify_install(_: argparse.Namespace) -> None:
    esm_revision = verify_installed_distribution("esm")
    transformers_revision = verify_installed_distribution("transformers")
    emit(
        {
            "verification_method": DISTRIBUTION_VERIFICATION_METHOD,
            "esm_version": ESM_SDK_VERSION,
            "esm_payload_sha256": ESM_SDK_PAYLOAD_SHA256,
            "esm_git_revision": esm_revision,
            "transformers_version": TRANSFORMERS_VERSION,
            "transformers_payload_sha256": TRANSFORMERS_PAYLOAD_SHA256,
            "transformers_git_revision": transformers_revision,
        }
    )


def command_route(args: argparse.Namespace) -> None:
    request = RouteRequest(
        task=args.task,
        item_count=args.item_count,
        long_running=args.long_running,
        bulk_dataset=args.bulk_dataset,
        private=args.private,
        offline=args.offline,
        data_residency=args.data_residency,
        custom_model=args.custom_model,
        fine_tune=args.fine_tune,
        sustained_workload=args.sustained_workload,
        has_msa=args.has_msa,
        accuracy_priority=args.accuracy_priority,
        owns_gpu=args.owns_gpu,
    )
    emit(route_request(request).as_dict())


def command_validate_sequence(args: argparse.Namespace) -> None:
    maximum_residues = {
        "esmc": ESMC_CONSERVATIVE_MAX_RESIDUES,
        "atlas-search": ATLAS_SEARCH_MAX_RESIDUES,
        "atlas-fold": ATLAS_FOLD_MAX_RESIDUES,
    }.get(args.target, ATLAS_FOLD_MAX_RESIDUES)
    value = (
        load_bounded_sequence(args.sequence_file, max_residues=maximum_residues)
        if args.sequence_file
        else args.sequence
    )
    if value is None:
        raise ValidationError("provide --sequence or --sequence-file")
    if args.target == "esmc":
        normalized = validate_esmc_sequence(value)
        md5_provider = "esmc"
    elif args.target == "atlas-search":
        normalized = validate_atlas_search_sequence(value)
        md5_provider = "atlas"
    else:
        normalized = validate_atlas_fold_sequence(value)
        md5_provider = "atlas"
    emit(
        {
            "valid": True,
            "target": args.target,
            "residues": len(normalized),
            "input_sha256": input_digest(normalized),
            "md5": sequence_md5(normalized, provider=md5_provider),
        }
    )


def command_validate_fold(args: argparse.Namespace) -> None:
    payload = load_bounded_json(
        args.input,
        max_bytes=CONTROL_JSON_MAX_WIRE_BYTES,
        field="fold input",
        max_nodes=SCIENTIFIC_JSON_MAX_NODES,
        max_aggregate_bytes=SCIENTIFIC_JSON_MAX_AGGREGATE_BYTES,
    )
    if not isinstance(payload, dict):
        raise ValidationError("fold input JSON must be an object")
    normalized = validate_fold_input(
        payload,
        model=args.model,
        require_msa=args.require_msa,
        require_msa_insertions_removed=args.require_msa_insertions_removed,
        require_paired_msa_keys=args.require_paired_msa_keys,
        msa_max_depth=args.msa_max_depth,
    )
    config: dict[str, Any] = {}
    if args.config:
        raw_config = load_bounded_json(
            args.config,
            max_bytes=CONTROL_JSON_MAX_WIRE_BYTES,
            field="fold config",
        )
        if not isinstance(raw_config, dict):
            raise ValidationError("fold config JSON must be an object")
        config = validate_fold_config(
            raw_config,
            model=args.model,
            endpoint=args.endpoint,
        )
    emit(
        {
            "valid": True,
            "model": args.model,
            "entity_count": len(normalized["sequences"]),
            "config": config,
            "msa_validation": {
                "required": args.require_msa,
                "insertions_removed_required": args.require_msa_insertions_removed,
                "paired_taxonomy_keys_required": args.require_paired_msa_keys,
                "maximum_depth": args.msa_max_depth,
            },
            "input_sha256": input_digest(normalized),
        }
    )


MANAGED_INPUT_PARAMETER_FIELDS = {
    "input",
    "inputs",
    "all_atom_input",
    "protein",
    "protein_tensor",
    "sequence",
    "sequences",
    "msa",
}


def _managed_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key in MANAGED_INPUT_PARAMETER_FIELDS
        and not (key == "sequence" and isinstance(value, bool))
    }


def _managed_parameters(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in MANAGED_INPUT_PARAMETER_FIELDS
        or (key == "sequence" and isinstance(value, bool))
    }


def _build_managed_provenance(
    *,
    endpoint: str,
    payload: dict[str, Any],
    started_at: str,
    artifacts: list[dict[str, Any]],
    confidence_metrics: dict[str, Any],
    esm_git_revision: str | None,
    provider_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    model_id = str(payload.get("model")) if payload.get("model") else None
    return build_provenance(
        route="biohub",
        endpoint=f"{BIOHUB_BASE_URL}/api/v1/{endpoint}",
        model_id=model_id,
        model_revision=model_id,
        inputs=_managed_inputs(payload),
        parameters=_managed_parameters(payload),
        seed=(
            payload.get("seed")
            if isinstance(payload.get("seed"), int) and not isinstance(payload.get("seed"), bool)
            else None
        ),
        started_at=started_at,
        artifacts=artifacts,
        confidence_metrics=confidence_metrics,
        provider_calls=provider_calls,
        esm_git_revision=esm_git_revision,
    )


def _validate_managed_payload(endpoint: str, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError("managed request input must be a JSON object")
    if endpoint in {"encode", "logits"}:
        return validate_managed_esmc_request(endpoint, payload)
    if endpoint in {"fold", "fold_all_atom"}:
        return validate_managed_fold_request(endpoint, payload)
    raise ValidationError(f"unsupported managed endpoint: {endpoint}")


def _publish_managed_finalization(
    *,
    endpoint: str,
    payload: dict[str, Any],
    safe_result: dict[str, Any],
    output_dir: Path,
    started_at: str,
    provider_calls: list[dict[str, Any]],
    publications: ExitStack,
    artifacts: list[dict[str, Any]],
    provenance_path: Path,
    provenance_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Materialize one saved response without performing provider I/O."""

    esm_revision: str | None = None
    confidence_metrics: dict[str, Any] = {}
    presentation_summary: dict[str, Any] | None = None

    def publish_structure(path: Path, value: bytes, media_type: str) -> dict[str, Any]:
        publication = publications.enter_context(
            publish_bytes_atomic(
                path,
                value,
                replace=False,
                media_type=media_type,
            )
        )
        record = dict(publication.record)
        artifacts.append(record)
        return record

    try:
        managed_result = normalize_managed_response(safe_result)
        if "presentation_request" in managed_result:
            raise SchemaDriftError(
                "managed response contains reserved presentation_request",
                raw=managed_result,
            )
        confidence_metrics = managed_confidence_metrics(
            managed_result,
            endpoint=endpoint,
            request=payload,
        )
        validate_managed_structure_response(endpoint, managed_result, payload)
        quality_warnings = managed_structure_quality_warnings(
            endpoint,
            managed_result,
            payload,
        )
        normalized: Any = _strip_embedded_pdb(managed_result)
        if endpoint in {"fold", "fold_all_atom"}:
            normalized, structure_artifacts, esm_revision = materialize_managed_structure(
                endpoint,
                managed_result,
                payload,
                output_dir,
                artifact_publisher=publish_structure,
            )
            if len(structure_artifacts) != 1:
                raise ValidationError(
                    "managed structure materialization must produce exactly one coordinate artifact"
                )
            if quality_warnings:
                normalized["quality_warnings"] = quality_warnings
            presentation = build_structure_presentation_request(
                structure_artifacts[0],
                confidence_metrics,
            )
            presentation_path = output_dir / "presentation-request.json"
            presentation_publication = publications.enter_context(
                publish_json_atomic(
                    presentation_path,
                    presentation,
                    replace=False,
                    media_type="application/json",
                )
            )
            presentation_record = dict(presentation_publication.record)
            artifacts.append(presentation_record)
            normalized["presentation_request"] = presentation_record
            presentation_summary = {
                "status": presentation["status"],
                "openIntentId": presentation["openIntentId"],
                "request": str(presentation_path),
            }

        result_path = output_dir / "result.json"
        result_publication = publications.enter_context(
            publish_json_atomic(
                result_path,
                normalized,
                replace=False,
                media_type="application/json",
            )
        )
        artifacts.append(dict(result_publication.record))
    except BiohubESMError as exc:
        if isinstance(exc, SchemaDriftError) and exc.raw is not None:
            exc.diagnostic_path = str(output_dir / "raw-response.json")
        incomplete = _build_managed_provenance(
            endpoint=endpoint,
            payload=payload,
            started_at=started_at,
            artifacts=artifacts,
            confidence_metrics=confidence_metrics,
            esm_git_revision=esm_revision,
            provider_calls=provider_calls,
        )
        incomplete["status"] = "incomplete"
        failure = {
            "kind": exc.__class__.__name__,
            "message": str(exc),
        }
        provider_status = (
            _validated_provider_status(provider_calls[-1].get("http_status"))
            if provider_calls
            else None
        )
        if provider_status is not None:
            failure["provider_status"] = provider_status
        if isinstance(exc, SchemaDriftError) and exc.diagnostic_path:
            failure["diagnostic_path"] = exc.diagnostic_path
        incomplete["failure"] = redact(failure)
        if provenance_extra:
            incomplete.update(redact(provenance_extra))
        validate_provenance(incomplete)
        publications.enter_context(
            publish_json_atomic(
                provenance_path,
                incomplete,
                replace=False,
                media_type="application/json",
            )
        )
        raise

    provenance = _build_managed_provenance(
        endpoint=endpoint,
        payload=payload,
        started_at=started_at,
        artifacts=artifacts,
        confidence_metrics=confidence_metrics,
        esm_git_revision=esm_revision,
        provider_calls=provider_calls,
    )
    if provenance_extra:
        provenance.update(redact(provenance_extra))
    validate_provenance(provenance)
    provenance_publication = publications.enter_context(
        publish_json_atomic(
            provenance_path,
            provenance,
            replace=False,
            media_type="application/json",
        )
    )
    response = {
        "result": normalized,
        "artifacts": [*artifacts, dict(provenance_publication.record)],
        "provenance": str(provenance_path),
    }
    if presentation_summary is not None:
        response["presentation"] = presentation_summary
    if normalized.get("quality_warnings"):
        response["quality_warnings"] = normalized["quality_warnings"]
    return response


def _load_recovery_source_provenance(
    source_path: Path | None,
    *,
    payload: dict[str, Any],
    endpoint: str,
    source_raw_sha256: str,
    source_raw_size_bytes: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if source_path is None:
        return (
            [
                {
                    "endpoint": f"{BIOHUB_BASE_URL}/api/v1/{endpoint}",
                    "operation": endpoint,
                    "outcome": "reused-saved-response",
                    "recovery_network_calls": 0,
                }
            ],
            None,
        )
    source = load_bounded_json(
        str(source_path),
        max_bytes=ATLAS_PROVENANCE_MAX_BYTES,
        field="managed source provenance",
    )
    if not isinstance(source, dict):
        raise ValidationError("managed source provenance must be a JSON object")
    validate_provenance(source)
    if source["input_sha256"] != input_digest(_managed_inputs(payload)):
        raise ValidationError("managed source provenance does not match the recovery request")
    expected_endpoint = f"{BIOHUB_BASE_URL}/api/v1/{endpoint}"
    if source["endpoint"] != expected_endpoint:
        raise ValidationError("managed source provenance endpoint does not match recovery")
    expected_model = str(payload.get("model")) if payload.get("model") else None
    expected_seed = (
        payload.get("seed")
        if isinstance(payload.get("seed"), int) and not isinstance(payload.get("seed"), bool)
        else None
    )
    if (
        source["model_id"] != expected_model
        or source["model_revision"] != expected_model
        or source["parameters"] != _managed_parameters(payload)
        or source["seed"] != expected_seed
    ):
        raise ValidationError("managed source provenance parameters do not match recovery")
    raw_records = [
        record for record in source["artifacts"] if Path(record["path"]).name == "raw-response.json"
    ]
    if len(raw_records) != 1:
        raise ValidationError("managed source provenance must identify one raw response artifact")
    raw_record = raw_records[0]
    if (
        raw_record["sha256"] != source_raw_sha256
        or raw_record["size_bytes"] != source_raw_size_bytes
    ):
        raise ValidationError("managed raw response does not match its source provenance")
    return list(source["provider_calls"]), {
        "path": str(source_path),
        "sha256": sha256_file(source_path),
    }


def _validate_existing_recovery_artifacts(
    output_dir: Path,
    provenance: dict[str, Any],
    *,
    endpoint: str,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for record in provenance["artifacts"]:
        path = Path(record["path"])
        if not path.is_absolute() or path.parent != output_dir:
            raise ValidationError("recovery provenance contains an artifact outside its output")
        if path.name in records:
            raise ValidationError("recovery provenance repeats an artifact name")
        observed = artifact_record(path, media_type=record["media_type"])
        if observed["size_bytes"] != record["size_bytes"] or observed["sha256"] != record["sha256"]:
            raise ValidationError("completed recovery artifact no longer matches provenance")
        records[path.name] = record
    required = {
        "raw-response.json",
        "result.json",
        "presentation-request.json",
        "prediction.cif" if endpoint == "fold_all_atom" else "prediction.pdb",
    }
    if not required.issubset(records):
        raise ValidationError("completed recovery is missing required artifacts")
    return records


def _existing_recovery_response(
    output_dir: Path,
    *,
    endpoint: str,
    request_sha256: str,
    source_raw_sha256: str,
    source_provenance: dict[str, Any] | None,
) -> dict[str, Any] | None:
    provenance_path = output_dir / "recovery-provenance.json"
    if not provenance_path.exists():
        return None
    provenance = load_bounded_json(
        str(provenance_path),
        max_bytes=ATLAS_PROVENANCE_MAX_BYTES,
        field="managed recovery provenance",
    )
    if not isinstance(provenance, dict):
        raise ValidationError("managed recovery provenance must be a JSON object")
    validate_provenance(provenance)
    if provenance.get("status") == "incomplete":
        raise ValidationError(
            "existing recovery is incomplete; preserve it and choose a new output directory"
        )
    recovery = provenance.get("recovery")
    expected_recovery = {
        "schema_version": "1.0",
        "offline": True,
        "network_calls": 0,
        "endpoint": endpoint,
        "request_sha256": request_sha256,
        "source_raw_sha256": source_raw_sha256,
        "source_provenance": source_provenance,
    }
    if recovery != expected_recovery:
        raise ValidationError("existing recovery does not match the supplied source artifacts")
    records = _validate_existing_recovery_artifacts(
        output_dir,
        provenance,
        endpoint=endpoint,
    )
    result = load_bounded_json(
        str(output_dir / "result.json"),
        max_bytes=CONTROL_JSON_MAX_WIRE_BYTES,
        field="managed recovered result",
        max_nodes=SCIENTIFIC_JSON_MAX_NODES,
        max_aggregate_bytes=SCIENTIFIC_JSON_MAX_AGGREGATE_BYTES,
    )
    presentation = load_bounded_json(
        str(output_dir / "presentation-request.json"),
        max_bytes=CONTROL_JSON_MAX_WIRE_BYTES,
        field="managed presentation request",
    )
    if not isinstance(result, dict) or not isinstance(presentation, dict):
        raise ValidationError("completed recovery result or presentation is malformed")
    validate_structure_presentation_request(presentation)
    if result.get("presentation_request") != records["presentation-request.json"]:
        raise ValidationError("completed recovery result lost its presentation artifact binding")
    structure = result.get("structure_artifact")
    if not isinstance(structure, dict):
        raise ValidationError("completed recovery result lost its structure artifact binding")
    structure_name = "prediction.cif" if endpoint == "fold_all_atom" else "prediction.pdb"
    if structure != records[structure_name]:
        raise ValidationError("completed recovery result lost its structure artifact binding")
    presentation_artifact = presentation["artifact"]
    identity_fields = ("path", "media_type", "size_bytes", "sha256")
    if any(presentation_artifact[field] != structure.get(field) for field in identity_fields):
        raise ValidationError("completed recovery presentation no longer binds the structure")
    provenance_record = artifact_record(provenance_path, media_type="application/json")
    response = {
        "result": result,
        "artifacts": [*provenance["artifacts"], provenance_record],
        "provenance": str(provenance_path),
        "presentation": {
            "status": presentation["status"],
            "openIntentId": presentation["openIntentId"],
            "request": str(output_dir / "presentation-request.json"),
        },
        "reused": True,
    }
    if result.get("quality_warnings"):
        response["quality_warnings"] = result["quality_warnings"]
    return response


def command_managed_post(args: argparse.Namespace) -> None:
    # Managed requests at tutorial scale run without a consent gate. The flag the agent
    # always passed was ceremony, not a safeguard. Modal spawn keeps its gate.
    payload = load_bounded_json(
        args.input,
        max_bytes=CONTROL_JSON_MAX_WIRE_BYTES,
        field="managed request input",
        max_nodes=SCIENTIFIC_JSON_MAX_NODES,
        max_aggregate_bytes=SCIENTIFIC_JSON_MAX_AGGREGATE_BYTES,
    )
    payload = _validate_managed_payload(args.endpoint, payload)
    requested_output_dir = getattr(args, "output_dir", None)
    if requested_output_dir and args.endpoint in {"fold", "fold_all_atom"}:
        require_managed_structure_materialization_ready(args.endpoint)
    credential = resolve_esm_api_key()
    register_redaction_secret(credential.value)
    client = BiohubClient(
        token=credential.value or "",
        base_url=BIOHUB_BASE_URL,
        timeout=args.timeout,
        credential_source=credential.source,
    )
    output_dir = Path(requested_output_dir).resolve() if requested_output_dir else None
    provider_calls: list[dict[str, Any]] = []
    started = utc_now()
    if output_dir is None:
        result = _tracked_biohub_post(client, args.endpoint, payload, provider_calls)
        managed_result = normalize_managed_response(result)
        managed_confidence_metrics(
            managed_result,
            endpoint=args.endpoint,
            request=payload,
        )
        validate_managed_structure_response(args.endpoint, managed_result, payload)
        emit(_strip_embedded_pdb(managed_result))
        return

    prepare_fresh_output_directory(output_dir)
    raw_path = output_dir / "raw-response.json"
    provenance_path = output_dir / "provenance.json"
    artifacts: list[dict[str, Any]] = []
    try:
        result = _tracked_biohub_post(client, args.endpoint, payload, provider_calls)
    except ValidationError:
        try:
            output_dir.rmdir()
        except OSError:
            pass
        raise
    except (APIError, SchemaDriftError) as exc:
        with ExitStack() as publications:
            if isinstance(exc, SchemaDriftError) and exc.raw is not None:
                artifacts.append(
                    _persist_managed_schema_drift_raw(
                        raw_path,
                        exc.raw,
                        publications=publications,
                    )
                )
                exc.diagnostic_path = str(raw_path)
            incomplete = _build_managed_provenance(
                endpoint=args.endpoint,
                payload=payload,
                started_at=started,
                artifacts=artifacts,
                confidence_metrics={},
                esm_git_revision=None,
                provider_calls=provider_calls,
            )
            incomplete["status"] = "incomplete"
            failure = {
                "kind": getattr(exc, "kind", exc.__class__.__name__),
                "message": str(exc),
            }
            if isinstance(exc, APIError):
                failure.update(
                    {
                        "status": exc.status,
                        "retry_after": exc.retry_after,
                        "partial": exc.partial,
                        "response_body_partial": exc.response_body_partial,
                        "operation_indeterminate": exc.operation_indeterminate,
                    }
                )
            provider_status = _validated_provider_status(getattr(exc, "provider_status", None))
            if provider_status is None and provider_calls:
                provider_status = _validated_provider_status(provider_calls[-1].get("http_status"))
            if provider_status is not None:
                failure["provider_status"] = provider_status
            if isinstance(exc, SchemaDriftError) and exc.diagnostic_path:
                failure["diagnostic_path"] = exc.diagnostic_path
            incomplete["failure"] = redact(failure)
            validate_provenance(incomplete)
            publications.enter_context(
                publish_json_atomic(provenance_path, incomplete, replace=False)
            )
        raise

    safe_result = redact(result)
    with ExitStack() as publications:
        raw_publication = publications.enter_context(
            publish_json_atomic(
                raw_path,
                safe_result,
                replace=False,
                media_type="application/json",
            )
        )
        artifacts = [dict(raw_publication.record)]
        response = _publish_managed_finalization(
            endpoint=args.endpoint,
            payload=payload,
            safe_result=safe_result,
            output_dir=output_dir,
            started_at=started,
            provider_calls=provider_calls,
            publications=publications,
            artifacts=artifacts,
            provenance_path=provenance_path,
        )
    emit(response)


def command_managed_recover(args: argparse.Namespace) -> None:
    """Finalize a preserved managed fold response without credentials or HTTP."""

    payload = load_bounded_json(
        args.input,
        max_bytes=CONTROL_JSON_MAX_WIRE_BYTES,
        field="managed recovery request input",
        max_nodes=SCIENTIFIC_JSON_MAX_NODES,
        max_aggregate_bytes=SCIENTIFIC_JSON_MAX_AGGREGATE_BYTES,
    )
    payload = _validate_managed_payload(args.endpoint, payload)
    if args.endpoint not in {"fold", "fold_all_atom"}:
        raise ValidationError("managed recovery supports only structure endpoints")

    def resolve_source_file(value: str, field: str) -> Path:
        try:
            path = Path(value).resolve(strict=True)
        except OSError as exc:
            raise ValidationError(f"could not read {field}") from exc
        if not path.is_file():
            raise ValidationError(f"{field} must be a regular file")
        return path

    source_raw_path = resolve_source_file(args.raw_response, "managed raw response")
    source_raw = load_bounded_json(
        str(source_raw_path),
        max_bytes=CONTROL_JSON_MAX_WIRE_BYTES,
        field="managed raw response",
        max_nodes=SCIENTIFIC_JSON_MAX_NODES,
        max_aggregate_bytes=SCIENTIFIC_JSON_MAX_AGGREGATE_BYTES,
    )
    if not isinstance(source_raw, dict):
        raise ValidationError("managed raw response must be a JSON object")
    safe_result = redact(source_raw)
    source_raw_sha256 = sha256_file(source_raw_path)
    request_sha256 = input_digest(payload)

    source_provenance_path: Path | None
    if args.source_provenance:
        source_provenance_path = resolve_source_file(
            args.source_provenance,
            "managed source provenance",
        )
    else:
        adjacent = source_raw_path.parent / "provenance.json"
        source_provenance_path = (
            resolve_source_file(str(adjacent), "managed source provenance")
            if adjacent.is_file()
            else None
        )
    provider_calls, source_provenance = _load_recovery_source_provenance(
        source_provenance_path,
        payload=payload,
        endpoint=args.endpoint,
        source_raw_sha256=source_raw_sha256,
        source_raw_size_bytes=source_raw_path.stat().st_size,
    )

    output_dir = Path(args.output_dir).resolve()
    if output_dir == source_raw_path.parent:
        raise ValidationError("managed recovery output must not overwrite the source run")
    if output_dir.exists():
        existing = _existing_recovery_response(
            output_dir,
            endpoint=args.endpoint,
            request_sha256=request_sha256,
            source_raw_sha256=source_raw_sha256,
            source_provenance=source_provenance,
        )
        if existing is None:
            raise ValidationError(
                "managed recovery output already exists without a completed matching recovery"
            )
        emit(existing)
        return

    # Runtime readiness is wired here and in managed-post before publication or
    # credential access. This command itself never resolves credentials or
    # constructs a provider client.
    require_managed_structure_materialization_ready(args.endpoint)
    prepare_fresh_output_directory(output_dir)
    started = utc_now()
    provenance_path = output_dir / "recovery-provenance.json"
    recovery = {
        "recovery": {
            "schema_version": "1.0",
            "offline": True,
            "network_calls": 0,
            "endpoint": args.endpoint,
            "request_sha256": request_sha256,
            "source_raw_sha256": source_raw_sha256,
            "source_provenance": source_provenance,
        }
    }
    with ExitStack() as publications:
        raw_publication = publications.enter_context(
            publish_json_atomic(
                output_dir / "raw-response.json",
                safe_result,
                replace=False,
                media_type="application/json",
            )
        )
        response = _publish_managed_finalization(
            endpoint=args.endpoint,
            payload=payload,
            safe_result=safe_result,
            output_dir=output_dir,
            started_at=started,
            provider_calls=provider_calls,
            publications=publications,
            artifacts=[dict(raw_publication.record)],
            provenance_path=provenance_path,
            provenance_extra=recovery,
        )
    response["reused"] = False
    emit(response)


def _load_esmc_tokenizer():
    from esm.tokenization import get_esmc_model_tokenizers

    return get_esmc_model_tokenizers()


def _resolve_bundled_petase_sequence() -> str:
    path = SCRIPT_DIR.parent / "examples" / "tutorial-use-cases.json"
    contract = load_tutorial_use_cases(path)
    use_cases = contract.get("use_cases")
    if not isinstance(use_cases, list):
        raise ValidationError("bundled tutorial contract has no use cases")
    matches = [
        item
        for item in use_cases
        if isinstance(item, dict) and item.get("id") == "esmc-mutation-landscape"
    ]
    if len(matches) != 1:
        raise ValidationError("bundled PETase tutorial contract is missing or ambiguous")
    use_case = matches[0]
    target = use_case.get("target")
    route = use_case.get("route")
    if not isinstance(target, dict) or not isinstance(route, dict):
        raise ValidationError("bundled PETase tutorial target or route is malformed")
    sequence_record = target.get("sequence")
    if not isinstance(sequence_record, dict):
        raise ValidationError("bundled PETase tutorial sequence is malformed")
    literal = sequence_record.get("literal")
    expected_length = sequence_record.get("length")
    expected_sha256 = sequence_record.get("sha256")
    if not isinstance(literal, str):
        raise ValidationError("bundled PETase tutorial sequence literal is missing")
    sequence = validate_landscape_sequence(literal)
    if (
        isinstance(expected_length, bool)
        or not isinstance(expected_length, int)
        or expected_length != len(sequence)
        or expected_sha256 != input_digest(sequence)
    ):
        raise ValidationError("bundled PETase tutorial sequence digest or length drifted")
    if (
        route.get("execution_route") != "biohub"
        or route.get("model_id") != "esmc-600m-2024-12"
        or route.get("masked_context_count") != len(sequence)
    ):
        raise ValidationError("bundled PETase tutorial managed execution contract drifted")
    return sequence


def _load_esmc_landscape_sequence(args: argparse.Namespace) -> str:
    if getattr(args, "tutorial", None) == "petase":
        return _resolve_bundled_petase_sequence()
    sequence_file = getattr(args, "sequence_file", None)
    raw_sequence = (
        load_bounded_sequence(
            sequence_file,
            max_residues=ESMC_LANDSCAPE_MAX_RESIDUES,
        )
        if sequence_file
        else getattr(args, "sequence", None)
    )
    if raw_sequence is None:
        raise ValidationError("provide --sequence, --sequence-file, or --tutorial petase")
    return validate_landscape_sequence(raw_sequence)


def _esmc_logits_config() -> dict[str, Any]:
    return {
        "sequence": True,
        "return_embeddings": False,
        "return_mean_embedding": False,
        "return_mean_hidden_states": False,
        "return_hidden_states": False,
        "ith_hidden_layer": -1,
        "sae_config": None,
    }


def _tracked_biohub_post(
    client: BiohubClient,
    endpoint: str,
    payload: dict[str, Any],
    provider_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    started_at = utc_now()
    try:
        result = client.post(endpoint, payload)
    except BiohubESMError as exc:
        finished_at = utc_now()
        status = getattr(exc, "status", None)
        if status is None:
            status = _validated_provider_status(getattr(exc, "provider_status", None))
        if status is None:
            status = _validated_provider_status(getattr(client, "last_http_status", None))
        _bind_provider_status(exc, status)
        error_kind = getattr(exc, "kind", exc.__class__.__name__)
        indeterminate = isinstance(exc, APIError) and exc.operation_indeterminate
        record: dict[str, Any] = {
            "endpoint": f"{BIOHUB_BASE_URL}/api/v1/{endpoint}",
            "method": "POST",
            "operation": endpoint,
            "started_at": started_at,
            "finished_at": finished_at,
            "outcome": "indeterminate" if indeterminate else "error",
            "error_kind": error_kind,
        }
        if isinstance(exc, APIError):
            record["partial"] = exc.partial
            record["response_body_partial"] = exc.response_body_partial
            record["operation_indeterminate"] = exc.operation_indeterminate
        if isinstance(status, int) and not isinstance(status, bool):
            record["http_status"] = status
        retry_after = getattr(exc, "retry_after", None)
        if retry_after is not None:
            record["retry_after"] = retry_after
        provider_calls.append(record)
        raise
    provider_calls.append(
        {
            "endpoint": f"{BIOHUB_BASE_URL}/api/v1/{endpoint}",
            "method": "POST",
            "operation": endpoint,
            "http_status": 200,
            "started_at": started_at,
            "finished_at": utc_now(),
            "outcome": "success",
        }
    )
    return result


def _persist_managed_raw_response(
    path: Path,
    response: dict[str, Any],
    *,
    publications: ExitStack | None = None,
) -> dict[str, Any]:
    def persist(value: Any) -> dict[str, Any]:
        if publications is None:
            write_json_atomic(path, value)
            return artifact_record(path, media_type="application/json")
        publication = publications.enter_context(publish_json_atomic(path, value, replace=False))
        return dict(publication.record)

    try:
        return persist(response)
    except ValidationError:
        return persist(
            {
                "schema_version": "1.0",
                "status": "rejected-provider-response",
                "redacted_response": safe_provider_response_diagnostic(response),
                "diagnostic": {
                    key: value
                    for key, value in bounded_provider_response_diagnostic(response).items()
                    if key != "projection"
                },
            },
        )


def _persist_managed_schema_drift_raw(
    path: Path,
    raw: Any,
    *,
    publications: ExitStack | None = None,
) -> dict[str, Any]:
    """Persist a redacted diagnostic whose complete artifact stays below 64 KiB."""

    encoded = _bounded_provider_diagnostic_bytes(raw)
    if publications is None:
        write_bytes_atomic_noreplace(path, encoded)
        return artifact_record(path, media_type="application/json")
    publication = publications.enter_context(
        publish_bytes_atomic(
            path,
            encoded,
            replace=False,
            media_type="application/json",
        )
    )
    return dict(publication.record)


def command_esmc_mutation_score(args: argparse.Namespace) -> None:
    raw_sequence = (
        load_bounded_sequence(
            args.sequence_file,
            max_residues=ESMC_CONSERVATIVE_MAX_RESIDUES,
        )
        if args.sequence_file
        else args.sequence
    )
    if raw_sequence is None:
        raise ValidationError("provide --sequence or --sequence-file")
    sequence = validate_esmc_sequence(raw_sequence)
    mutation = validate_single_substitution(sequence, args.mutation)
    if args.model not in ESMC_MANAGED_MODELS:
        raise ValidationError("mutation scoring requires an exact managed ESMC model ID")
    credential = resolve_esm_api_key()
    token = credential.value
    if not token:
        raise APIError(
            status=None,
            kind="missing-credentials",
            message=missing_esm_api_key_message(credential.source),
        )
    register_redaction_secret(token)

    esm_revision = verify_installed_distribution("esm")
    transformers_revision = verify_installed_distribution("transformers")
    tokenizer = _load_esmc_tokenizer()
    token_ids = {
        "wild_type": tokenizer.convert_tokens_to_ids(mutation["wild_type"]),
        "alternate": tokenizer.convert_tokens_to_ids(mutation["alternate"]),
        "mask": tokenizer.mask_token_id,
        "bos": tokenizer.cls_token_id,
        "eos": tokenizer.eos_token_id,
    }
    for label, token_id in token_ids.items():
        if isinstance(token_id, bool) or not isinstance(token_id, int) or token_id < 0:
            raise ValidationError(f"pinned ESMC tokenizer returned an invalid {label} token id")
    encoded_tokens = [token_ids["bos"]]
    for residue in sequence:
        token_id = tokenizer.convert_tokens_to_ids(residue)
        if isinstance(token_id, bool) or not isinstance(token_id, int) or token_id < 0:
            raise ValidationError(
                f"pinned ESMC tokenizer returned an invalid token id for residue {residue}"
            )
        encoded_tokens.append(token_id)
    encoded_tokens.append(token_ids["eos"])
    if len(encoded_tokens) != len(sequence) + 2:
        raise ValidationError("pinned ESMC tokenizer must add exactly one BOS and one EOS token")
    logits_index = mutation["logits_index_zero_based"]
    if encoded_tokens[logits_index] != token_ids["wild_type"]:
        raise ValidationError("pinned ESMC tokenizer does not preserve the wild-type residue")
    masked_tokens = list(encoded_tokens)
    masked_tokens[logits_index] = token_ids["mask"]
    changed = [
        index
        for index, pair in enumerate(zip(encoded_tokens, masked_tokens, strict=True))
        if pair[0] != pair[1]
    ]
    if changed != [logits_index]:
        raise ValidationError("mutation scoring must replace exactly one encoded residue")

    client = BiohubClient(
        token=token,
        base_url=BIOHUB_BASE_URL,
        timeout=args.timeout,
    )
    output_dir = prepare_fresh_output_directory(Path(args.output_dir).resolve())
    raw_path = output_dir / "raw-response.json"
    score_path = output_dir / "mutation-score.json"
    score_card_path = output_dir / "mutation-score.svg"
    provenance_path = output_dir / "provenance.json"
    artifacts: list[dict[str, Any]] = []
    provider_calls: list[dict[str, Any]] = []
    started = utc_now()
    logits_config = {
        "sequence": True,
        "return_embeddings": False,
        "return_mean_embedding": False,
        "return_mean_hidden_states": False,
        "return_hidden_states": False,
        "ith_hidden_layer": -1,
        "sae_config": None,
    }
    payload = {
        "model": args.model,
        "inputs": {"sequence": masked_tokens},
        "logits_config": logits_config,
        "potential_sequence_of_concern": False,
    }
    parameters = {
        "mutation": mutation["label"],
        "masking": "exactly one residue replaced by the pinned tokenizer mask token",
        "logits_config": logits_config,
        "potential_sequence_of_concern": False,
        "normalization": "natural-log log_softmax over the full returned vocabulary",
        "numbering": "one-based residues with one BOS token",
        "managed_request_count": 1,
        "implicit_retries": False,
    }

    raw_response: dict[str, Any] | None = None
    raw_artifact: dict[str, Any] | None = None
    raw_publication_attempted = False
    with ExitStack() as publications:
        try:
            raw_response = redact(_tracked_biohub_post(client, "logits", payload, provider_calls))
            # Publish and retain the exact provider response before interpreting it.
            # The explicit attempted flag distinguishes an owned publication from a
            # path created by a concurrent writer if no-replace publication fails.
            raw_publication_attempted = True
            raw_artifact = _persist_managed_raw_response(
                raw_path,
                raw_response,
                publications=publications,
            )
            artifacts.append(raw_artifact)
            managed_result = normalize_managed_response(raw_response)
            logits_container = managed_result.get("logits")
            if not isinstance(logits_container, dict):
                raise SchemaDriftError(
                    "managed ESMC response is missing sequence logits",
                    raw=raw_response,
                )
            sequence_logits = validate_sequence_logits(
                logits_container.get("sequence"),
                expected_positions=len(sequence) + 2,
                minimum_width=max(token_ids.values()) + 1,
            )
            score = derive_single_mask_llr(
                sequence_logits,
                mutation,
                wild_type_token_id=token_ids["wild_type"],
                alternate_token_id=token_ids["alternate"],
                mask_token_id=token_ids["mask"],
            )
            score.update(
                {
                    "sequence": {
                        "sha256": input_digest(sequence),
                        "length": len(sequence),
                        "numbering": "one-based on the normalized input sequence",
                    },
                    "model": {
                        "id": args.model,
                        "revision": args.model,
                        "revision_kind": "versioned-managed-model-id",
                    },
                    "sdk_revisions": {
                        "esm": esm_revision,
                        "transformers": transformers_revision,
                    },
                    "raw_response_artifact": raw_artifact,
                }
            )
            score_publication = publications.enter_context(
                publish_json_atomic(score_path, score, replace=False)
            )
            artifacts.append(dict(score_publication.record))
            score_card_publication = publications.enter_context(
                publish_bytes_atomic(
                    score_card_path,
                    render_mutation_score_svg(score),
                    replace=False,
                    media_type="image/svg+xml",
                )
            )
            artifacts.append(dict(score_card_publication.record))
        except BiohubESMError as exc:
            if raw_artifact is None and not raw_publication_attempted:
                if raw_response is not None:
                    raw_publication_attempted = True
                    raw_artifact = _persist_managed_raw_response(
                        raw_path,
                        raw_response,
                        publications=publications,
                    )
                elif isinstance(exc, SchemaDriftError) and exc.raw is not None:
                    raw_publication_attempted = True
                    raw_artifact = _persist_managed_schema_drift_raw(
                        raw_path,
                        exc.raw,
                        publications=publications,
                    )
                if raw_artifact is not None:
                    artifacts.append(raw_artifact)
            if isinstance(exc, SchemaDriftError) and raw_artifact is not None:
                owned_diagnostic_path = raw_artifact.get("path")
                if isinstance(owned_diagnostic_path, str):
                    exc.diagnostic_path = owned_diagnostic_path
            incomplete = build_provenance(
                route="biohub",
                endpoint=f"{BIOHUB_BASE_URL}/api/v1/logits",
                model_id=args.model,
                model_revision=args.model,
                inputs=sequence,
                input_sha256=input_digest(sequence),
                parameters=parameters,
                seed=None,
                started_at=started,
                artifacts=artifacts,
                provider_calls=provider_calls,
                esm_git_revision=esm_revision,
                transformers_git_revision=transformers_revision,
            )
            incomplete["status"] = "incomplete"
            failure = {
                "kind": getattr(exc, "kind", exc.__class__.__name__),
                "message": str(exc),
            }
            if isinstance(exc, APIError):
                failure.update(
                    {
                        "status": exc.status,
                        "retry_after": exc.retry_after,
                        "partial": exc.partial,
                        "response_body_partial": exc.response_body_partial,
                        "operation_indeterminate": exc.operation_indeterminate,
                    }
                )
            provider_status = _validated_provider_status(getattr(exc, "provider_status", None))
            if provider_status is None and provider_calls:
                provider_status = _validated_provider_status(provider_calls[-1].get("http_status"))
            if provider_status is not None:
                failure["provider_status"] = provider_status
            if isinstance(exc, SchemaDriftError) and exc.diagnostic_path:
                failure["diagnostic_path"] = exc.diagnostic_path
            incomplete["failure"] = redact(failure)
            validate_provenance(incomplete)
            publications.enter_context(
                publish_json_atomic(provenance_path, incomplete, replace=False)
            )
            raise

        provenance = build_provenance(
            route="biohub",
            endpoint=f"{BIOHUB_BASE_URL}/api/v1/logits",
            model_id=args.model,
            model_revision=args.model,
            inputs=sequence,
            input_sha256=input_digest(sequence),
            parameters=parameters,
            seed=None,
            started_at=started,
            artifacts=artifacts,
            provider_calls=provider_calls,
            esm_git_revision=esm_revision,
            transformers_git_revision=transformers_revision,
        )
        provenance_publication = publications.enter_context(
            publish_json_atomic(provenance_path, provenance, replace=False)
        )
        response = {
            "result": score,
            "artifacts": [*artifacts, dict(provenance_publication.record)],
            "provenance": str(provenance_path),
        }
    emit(response)


def command_esmc_landscape(args: argparse.Namespace) -> None:
    if args.model not in ESMC_MANAGED_MODELS:
        raise ValidationError("mutation landscapes require an exact managed ESMC model ID")
    if getattr(args, "tutorial", None) == "petase" and args.model != "esmc-600m-2024-12":
        raise ValidationError("the PETase tutorial requires model esmc-600m-2024-12")
    sequence = _load_esmc_landscape_sequence(args)
    if (
        isinstance(args.max_workers, bool)
        or not isinstance(args.max_workers, int)
        or not 1 <= args.max_workers <= 32
    ):
        raise ValidationError("ESMC landscape --max-workers must be between 1 and 32")
    timeout = validate_timeout(args.timeout, "Biohub request timeout")

    esm_revision = verify_installed_distribution("esm")
    transformers_revision = verify_installed_distribution("transformers")
    tokenizer = _load_esmc_tokenizer()
    tokenization = encode_esmc_sequence(tokenizer, sequence)
    canonical_ids = canonical_token_ids(tokenizer)
    minimum_width = (
        max(
            *canonical_ids.values(),
            tokenization["mask_token_id"],
        )
        + 1
    )
    logits_config = _esmc_logits_config()

    payloads: dict[int, dict[str, Any]] = {}
    request_sha256_by_position: dict[int, str] = {}
    for position_one_based in range(1, len(sequence) + 1):
        masked_tokens = mask_esmc_position(
            tokenization["tokens"],
            position_one_based=position_one_based,
            mask_token_id=tokenization["mask_token_id"],
        )
        payload = {
            "model": args.model,
            "inputs": {"sequence": masked_tokens},
            "logits_config": logits_config,
            "potential_sequence_of_concern": False,
        }
        payloads[position_one_based] = payload
        request_sha256_by_position[position_one_based] = sha256_bytes(canonical_json(payload))
    binding = {
        "endpoint": f"{BIOHUB_BASE_URL}/api/v1/logits",
        "model": args.model,
        "sequence": sequence,
        "sequence_sha256": input_digest(sequence),
        "sequence_length": len(sequence),
        "input_source": (
            "bundled-official-petase-tutorial"
            if getattr(args, "tutorial", None) == "petase"
            else "user-supplied-sequence"
        ),
        "esm_git_revision": esm_revision,
        "transformers_git_revision": transformers_revision,
        "tokenizer": {
            "bos_token_id": tokenization["bos_token_id"],
            "eos_token_id": tokenization["eos_token_id"],
            "mask_token_id": tokenization["mask_token_id"],
            "canonical_token_ids": canonical_ids,
        },
        "logits_config": logits_config,
        "potential_sequence_of_concern": False,
        "request_sha256_by_position": {
            str(position): digest for position, digest in request_sha256_by_position.items()
        },
    }

    output_path = Path(args.output_dir).resolve()
    resume = bool(getattr(args, "resume", False))
    if resume:
        if not output_path.is_dir():
            raise ValidationError("ESMC landscape --resume requires an existing output directory")
        output_dir = output_path
        store = ESMCLandscapeStore.resume(
            output_dir,
            binding=binding,
            request_sha256_by_position=request_sha256_by_position,
        )
    else:
        output_dir = prepare_fresh_output_directory(output_path)
        store = ESMCLandscapeStore.create(
            output_dir,
            binding=binding,
            request_sha256_by_position=request_sha256_by_position,
        )
    raw_path = output_dir / "raw-responses.json"
    landscape_path = output_dir / "mutation-landscape.json"
    csv_path = output_dir / "mutation-landscape.csv"
    provenance_path = output_dir / "provenance.json"
    started = store.state["started_at"]
    parameters = {
        "analysis": "one masked context per residue",
        "input_source": (
            "bundled-official-petase-tutorial"
            if getattr(args, "tutorial", None) == "petase"
            else "user-supplied-sequence"
        ),
        "managed_request_count": len(sequence),
        "max_workers": min(args.max_workers, len(sequence)),
        "concurrency": (
            "bounded ThreadPoolExecutor with one host-pinned managed logits call per context"
        ),
        "backend_batching": "Biohub-managed",
        "implicit_retries": False,
        "resume_policy": (
            "explicit --resume reuses only exact-request-bound completed checkpoints; "
            "indeterminate submissions are never replayed"
        ),
        "masking": "one pinned-tokenizer mask at each one-based residue position",
        "bos_offset": 1,
        "logits_config": logits_config,
        "entropy": "full returned vocabulary, log base 2",
        "canonical_llr": "alternate logit minus wild-type logit",
        "negative_substitution_fraction_denominator": 19,
        "potential_sequence_of_concern": False,
    }

    runnable_positions = store.runnable_positions()
    token = ""
    if runnable_positions:
        credential = resolve_esm_api_key()
        token = credential.value
        if not token:
            store.close()
            raise APIError(
                status=None,
                kind="missing-credentials",
                message=missing_esm_api_key_message(credential.source),
            )
        register_redaction_secret(token)

    def invoke(position_one_based: int) -> dict[str, Any]:
        calls: list[dict[str, Any]] = []
        try:
            client = BiohubClient(
                token=token,
                base_url=BIOHUB_BASE_URL,
                timeout=timeout,
            )
            response = redact(
                _tracked_biohub_post(client, "logits", payloads[position_one_based], calls)
            )
            if not isinstance(response, dict):
                raise SchemaDriftError(
                    "managed ESMC response must remain a JSON object after redaction"
                )
            error: Exception | None = None
        # Preserve every completed context when any worker fails.
        except Exception as exc:  # noqa: BLE001
            response = None
            error = exc
        for call in calls:
            call["position_one_based"] = position_one_based
        return {
            "position_one_based": position_one_based,
            "wild_type": sequence[position_one_based - 1],
            "response": response,
            "provider_calls": calls,
            "error": error,
        }

    errors: dict[int, Exception] = {}
    position_iterator = iter(runnable_positions)
    max_workers = min(args.max_workers, len(sequence))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: dict[Future[dict[str, Any]], int] = {}

        def submit_next() -> bool:
            try:
                position = next(position_iterator)
            except StopIteration:
                return False
            store.mark_submitting(position)
            futures[executor.submit(invoke, position)] = position
            return True

        for _ in range(min(max_workers, len(runnable_positions))):
            submit_next()
        stop_scheduling = False
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                position = futures.pop(future)
                try:
                    outcome = future.result()
                except Exception as exc:  # noqa: BLE001
                    outcome = {
                        "position_one_based": position,
                        "wild_type": sequence[position - 1],
                        "response": None,
                        "provider_calls": [],
                        "error": exc,
                    }
                error = outcome["error"]
                if error is None:
                    response = outcome["response"]
                    if not isinstance(response, dict):
                        error = SchemaDriftError(
                            "managed ESMC response must remain a JSON object after redaction"
                        )
                if error is None:
                    store.record_success(
                        position,
                        wild_type=outcome["wild_type"],
                        response=response,
                        provider_calls=outcome["provider_calls"],
                    )
                else:
                    assert isinstance(error, Exception)
                    store.record_failure(
                        position,
                        error=error,
                        provider_calls=outcome["provider_calls"],
                    )
                    errors[position] = error
                    stop_scheduling = True
            while not stop_scheduling and len(futures) < max_workers and submit_next():
                pass

    outcomes = store.completed_outcomes()
    primary_failure_position = min(errors) if errors else None
    primary_failure = errors[primary_failure_position] if primary_failure_position else None
    provider_calls = store.provider_calls()
    if primary_failure_position is not None:
        primary_calls = [
            call
            for call in provider_calls
            if call.get("position_one_based") == primary_failure_position
        ]
        provider_calls = [
            call
            for call in provider_calls
            if call.get("position_one_based") != primary_failure_position
        ] + primary_calls
    completed = outcomes
    failed_positions = store.positions_with_status(
        "submission-rejected", "submission-indeterminate"
    )
    pending_positions = store.positions_with_status("pending", "submitting")
    raw_bundle = {
        "schema_version": "1.0",
        "analysis": "single-mask-canonical-mutation-landscape",
        "expected_context_count": len(sequence),
        "completed_context_count": len(completed),
        "failed_positions_one_based": failed_positions,
        "pending_positions_one_based": pending_positions,
        "resume_count": store.state["resume_count"],
        "responses": [
            {
                "position_one_based": item["position_one_based"],
                "wild_type": item["wild_type"],
                "response": item["response"],
            }
            for item in completed
        ],
    }
    artifacts: list[dict[str, Any]] = []

    def incomplete_provenance(exc: Exception) -> dict[str, Any]:
        incomplete = build_provenance(
            route="biohub",
            endpoint=f"{BIOHUB_BASE_URL}/api/v1/logits",
            model_id=args.model,
            model_revision=args.model,
            inputs=sequence,
            input_sha256=input_digest(sequence),
            parameters=parameters,
            seed=None,
            started_at=started,
            artifacts=artifacts,
            provider_calls=provider_calls,
            esm_git_revision=esm_revision,
            transformers_git_revision=transformers_revision,
        )
        incomplete["status"] = "incomplete"
        failure: dict[str, Any] = {
            "kind": getattr(exc, "kind", exc.__class__.__name__),
            "message": str(exc),
        }
        if isinstance(exc, APIError):
            failure.update(
                {
                    "status": exc.status,
                    "retry_after": exc.retry_after,
                    "partial": exc.partial,
                    "response_body_partial": exc.response_body_partial,
                    "operation_indeterminate": exc.operation_indeterminate,
                }
            )
        provider_status = _validated_provider_status(getattr(exc, "provider_status", None))
        if provider_status is None and provider_calls:
            provider_status = _validated_provider_status(provider_calls[-1].get("http_status"))
        if provider_status is not None:
            failure["provider_status"] = provider_status
        incomplete["failure"] = redact(failure)
        validate_provenance(incomplete)
        return incomplete

    with ExitStack() as publications:
        raw_publication = publications.enter_context(
            publish_json_atomic(raw_path, raw_bundle, replace=True)
        )
        raw_artifact = dict(raw_publication.record)
        artifacts.append(raw_artifact)

        if primary_failure is not None:
            exc = primary_failure
            publications.enter_context(
                publish_json_atomic(
                    provenance_path,
                    incomplete_provenance(exc),
                    replace=True,
                )
            )
            raise exc

        try:
            masked_rows: list[list[float]] = []
            responses: list[dict[str, Any]] = []
            for item in outcomes:
                response = item["response"]
                if not isinstance(response, dict):
                    raise SchemaDriftError("managed ESMC landscape response is missing")
                responses.append(response)
                managed_result = normalize_managed_response(response)
                logits_container = managed_result.get("logits")
                if not isinstance(logits_container, dict):
                    raise SchemaDriftError(
                        "managed ESMC response is missing sequence logits",
                        raw=response,
                    )
                sequence_logits = validate_sequence_logits(
                    logits_container.get("sequence"),
                    expected_positions=len(sequence) + 2,
                    minimum_width=minimum_width,
                )
                masked_rows.append(sequence_logits[item["position_one_based"]])
            landscape = derive_mutation_landscape(
                sequence,
                masked_rows,
                canonical_ids=canonical_ids,
                mask_token_id=tokenization["mask_token_id"],
            )
            usage = summarize_reported_usage(responses)
            landscape.update(
                {
                    "sequence": {
                        "sha256": input_digest(sequence),
                        "length": len(sequence),
                        "numbering": "one-based on the normalized input sequence",
                    },
                    "model": {
                        "id": args.model,
                        "revision": args.model,
                        "revision_kind": "versioned-managed-model-id",
                    },
                    "tokenizer": {
                        "esm_git_revision": esm_revision,
                        "transformers_git_revision": transformers_revision,
                        "bos_token_id": tokenization["bos_token_id"],
                        "eos_token_id": tokenization["eos_token_id"],
                        "mask_token_id": tokenization["mask_token_id"],
                        "canonical_token_ids": {
                            residue: canonical_ids[residue] for residue in CANONICAL_AMINO_ACIDS
                        },
                    },
                    "execution": parameters,
                    "usage": usage,
                    "raw_response_artifact": raw_artifact,
                }
            )
            landscape_publication = publications.enter_context(
                publish_json_atomic(landscape_path, landscape, replace=True)
            )
            artifacts.append(dict(landscape_publication.record))
            csv_publication = publications.enter_context(
                publish_bytes_atomic(
                    csv_path,
                    render_mutation_landscape_csv(landscape),
                    replace=True,
                    media_type="text/csv",
                )
            )
            artifacts.append(dict(csv_publication.record))
        except BiohubESMError as exc:
            publications.enter_context(
                publish_json_atomic(
                    provenance_path,
                    incomplete_provenance(exc),
                    replace=True,
                )
            )
            raise

        provenance = build_provenance(
            route="biohub",
            endpoint=f"{BIOHUB_BASE_URL}/api/v1/logits",
            model_id=args.model,
            model_revision=args.model,
            inputs=sequence,
            input_sha256=input_digest(sequence),
            parameters=parameters,
            seed=None,
            started_at=started,
            artifacts=artifacts,
            provider_calls=provider_calls,
            esm_git_revision=esm_revision,
            transformers_git_revision=transformers_revision,
        )
        provenance_publication = publications.enter_context(
            publish_json_atomic(provenance_path, provenance, replace=True)
        )
        response = {
            "result": {
                "analysis": landscape["analysis"],
                "sequence": landscape["sequence"],
                "model": landscape["model"],
                "usage": landscape["usage"],
                "summary": landscape["summary"],
                "interpretation": landscape["interpretation"],
                "detailed_result_artifact": dict(landscape_publication.record),
            },
            "artifacts": [*artifacts, dict(provenance_publication.record)],
            "provenance": str(provenance_path),
        }
        store.mark_finalized()
    store.close()
    emit(response)


def command_atlas_search(args: argparse.Namespace) -> None:
    sequence = validate_atlas_search_sequence(args.sequence)
    params = {
        "topk_results": args.topk_results,
        "topk_features": args.topk_features,
        "min_similarity": args.min_similarity,
        "cluster_pct_characterized_max": args.cluster_pct_characterized_max,
        "include_cluster_info": args.include_cluster_info,
    }
    _run_atlas_json_command(
        args,
        operation="search",
        endpoint_path="/similarity-search",
        inputs=sequence,
        parameters=params,
        invocation=lambda client: client.search(
            sequence,
            topk_results=args.topk_results,
            topk_features=args.topk_features,
            min_similarity=args.min_similarity,
            cluster_pct_characterized_max=args.cluster_pct_characterized_max,
            include_cluster_info=args.include_cluster_info,
        ),
        strip_embedded_pdb=True,
    )


def command_atlas_protein(args: argparse.Namespace) -> None:
    protein_hash = validate_md5(args.protein_hash)
    params = {
        "topk_features": args.topk_features,
        "fold_on_miss": args.fold_on_miss,
        "normalize_features": not args.raw_features,
        "feature_indices": args.feature_index,
    }
    _run_atlas_json_command(
        args,
        operation="protein",
        endpoint_path=f"/proteins/{protein_hash}",
        inputs={"protein_hash": protein_hash},
        parameters=params,
        invocation=lambda client: client.protein(
            protein_hash,
            topk_features=args.topk_features,
            fold_on_miss=args.fold_on_miss,
            normalize_features=not args.raw_features,
            feature_indices=args.feature_index,
        ),
        strip_embedded_pdb=True,
    )


def command_atlas_cluster(args: argparse.Namespace) -> None:
    protein_hash = validate_md5(args.protein_hash)
    _run_atlas_json_command(
        args,
        operation="cluster",
        endpoint_path=f"/clusters/{protein_hash}",
        inputs={"protein_hash": protein_hash},
        parameters={"topk_features": args.topk_features},
        invocation=lambda client: client.cluster(
            protein_hash,
            topk_features=args.topk_features,
        ),
        strip_embedded_pdb=True,
    )


def command_atlas_features(args: argparse.Namespace) -> None:
    _run_atlas_json_command(
        args,
        operation="features",
        endpoint_path="/features",
        inputs={"catalog": "ESM Atlas 16,384 SAE features"},
        parameters={},
        invocation=lambda client: client.features(),
        strip_embedded_pdb=False,
    )


def command_atlas_feature(args: argparse.Namespace) -> None:
    _run_atlas_json_command(
        args,
        operation=f"feature-{args.feature_index}",
        endpoint_path=f"/features/{args.feature_index}",
        inputs={"feature_index": args.feature_index},
        parameters={},
        invocation=lambda client: client.feature(args.feature_index),
        strip_embedded_pdb=False,
    )


def command_atlas_thumbnail(args: argparse.Namespace) -> None:
    started = utc_now()
    protein_hash = validate_md5(args.protein_hash)
    endpoint_path = f"/proteins/{protein_hash}/thumbnail/{args.thumbnail_type}"
    destination = Path(args.output).resolve()
    provenance_path = destination.with_name(f"{destination.name}.provenance.json")
    diagnostic_path = destination.with_name(f"{destination.name}.schema-drift-diagnostic.json")
    if any(
        path.exists() or path.is_symlink()
        for path in (destination, provenance_path, diagnostic_path)
    ):
        raise ValidationError("Atlas thumbnail output and sidecars must not already exist")
    client = AtlasClient(base_url=args.base_url, timeout=args.timeout)
    try:
        response = client.thumbnail(protein_hash, args.thumbnail_type)
    except BiohubESMError as exc:
        provider_calls = list(client.provider_calls)
        if provider_calls:
            _persist_atlas_artifact_incomplete(
                exc,
                artifact_path=destination,
                endpoint_path=endpoint_path,
                inputs={"protein_hash": protein_hash},
                parameters={"thumbnail_type": args.thumbnail_type},
                started_at=started,
                provider_calls=provider_calls,
                base_url=args.base_url,
            )
        raise
    with publish_bytes_atomic(
        destination,
        response.body,
        replace=False,
        media_type="image/png",
    ) as artifact_publication:
        evidence = _save_atlas_artifact_provenance(
            destination,
            media_type="image/png",
            endpoint_path=endpoint_path,
            inputs={"protein_hash": protein_hash},
            parameters={"thumbnail_type": args.thumbnail_type},
            started_at=started,
            base_url=args.base_url,
            provider_calls=list(client.provider_calls),
            replace_existing=False,
            expected_artifact_identity=artifact_publication.identity,
        )
    emit(
        {
            key: value
            for key, value in evidence.items()
            if key not in {"artifact_identity", "provenance_identity"}
        }
    )


def command_atlas_batch_submit(args: argparse.Namespace) -> None:
    invoked_at = utc_now()
    raw_hashes = load_bounded_json(
        args.hashes,
        max_bytes=CONTROL_JSON_MAX_WIRE_BYTES,
        field="Atlas batch hashes",
    )
    if not isinstance(raw_hashes, list):
        raise ValidationError("batch hashes file must contain a JSON list")
    hashes = validate_batch_hashes(raw_hashes)
    parameters = {
        "topk_features": args.topk_features,
        "include_structure": not args.no_structure,
        "include_cluster_info": not args.no_cluster_info,
        "include_sequence": not args.no_sequence,
        "include_features": {
            "protein_level": not args.no_features,
            "per_residue": not args.no_features and not args.no_per_residue_features,
        },
    }
    request_sha256 = input_digest(hashes)
    store = AtlasBatchStore(Path(args.state).resolve())
    _validate_atlas_batch_topk(args.topk_features)
    _validate_atlas_batch_output(store, args.output)
    client = AtlasClient(base_url=args.base_url, timeout=args.timeout)
    submit_endpoint = _atlas_endpoint(args.base_url, "/proteins/batch")
    with (
        _atlas_output_claim(Path(args.output).resolve()),
        store.operation_lock(),
        atlas_batch_sink_preparer(
            client,
            temporary_file=tempfile.TemporaryFile,
        ) as prepare_synchronous_sink,
    ):
        _validate_atlas_batch_output(store, args.output)
        if store.path.exists():
            current = store.load()
            recovered = _verified_synchronous_atlas_batch_materialization(
                current,
                Path(args.output).resolve(),
                endpoint=submit_endpoint,
                input_sha256=request_sha256,
                parameters=parameters,
            )
            if recovered is not None:
                path = Path(args.output).resolve()
                try:
                    with _atlas_verified_artifact_pair(path, recovered) as accepted:
                        marker = {
                            "status": "completed",
                            "partial_output": False,
                            "destination_path": str(path),
                            "artifact_sha256": accepted["artifact"]["sha256"],
                            "provenance_sha256": accepted["provenance_artifact"]["sha256"],
                            "recovered_from_artifact_provenance": True,
                        }
                        _bind_atlas_evidence_identities(marker, accepted)
                        state = store.recover_synchronous_submission(
                            endpoint=submit_endpoint,
                            input_sha256=request_sha256,
                            parameters=parameters,
                            response={
                                "status": "completed",
                                "delivery": "synchronous",
                                "artifact_materialization": marker,
                            },
                            artifacts=[
                                accepted["artifact"],
                                accepted["provenance_artifact"],
                            ],
                        )
                except BaseException as exc:
                    current_after_failure = store.load()
                    if (
                        current_after_failure.get("status") == "completed"
                        and current_after_failure.get("job_id") is None
                    ):
                        state = _fail_atlas_batch_materialization(
                            store,
                            current_after_failure,
                            path,
                            reason=(
                                "Recovered Atlas artifact acceptance ended with "
                                f"{type(exc).__name__}"
                            ),
                        )
                        _persist_atlas_batch_provenance(store, state)
                    raise
                emit({"http_status": 200, **_persist_atlas_batch_provenance(store, state)})
                return
            if current["status"] == "submission-rejected":
                synchronous_sink = prepare_synchronous_sink()
                _persist_atlas_batch_provenance(store, current)
                state = store.retry_rejected_submission(
                    endpoint=submit_endpoint,
                    input_sha256=request_sha256,
                    parameters=parameters,
                    invoked_at=invoked_at,
                )
            elif (
                current["status"] == "completed"
                and current["job_id"] is None
                and current["last_response"].get("delivery") == "synchronous"
                and isinstance(current["last_response"].get("artifact_materialization"), dict)
                and current["last_response"]["artifact_materialization"].get("status")
                in {"pending", "failed"}
            ):
                _persist_atlas_batch_provenance(store, current)
                if current["request"]["input_sha256"] != request_sha256 or current["request"][
                    "parameters"
                ] != redact(parameters):
                    raise ValidationError(
                        "retry request does not match the completed synchronous "
                        "Atlas batch submission"
                    )
                raise ValidationError(
                    "Atlas already accepted this synchronous batch submission; "
                    "its output could not be materialized, so automatic "
                    "resubmission is unsafe and requires manual reconciliation"
                )
            else:
                _persist_atlas_batch_provenance(store, current)
                raise ValidationError("refusing to overwrite an existing Atlas batch state")
        else:
            synchronous_sink = prepare_synchronous_sink()
            state = store.begin_submission(
                submitted_at=invoked_at,
                endpoint=submit_endpoint,
                input_sha256=request_sha256,
                parameters=parameters,
            )
        attempt_started_at = state["provider_calls"][-1]["started_at"]
        try:
            if synchronous_sink is None:
                status, result, _ = client.submit_batch(hashes, **parameters)
            else:
                status, result, _ = client.submit_batch(
                    hashes,
                    synchronous_sink=synchronous_sink,
                    **parameters,
                )
        except BaseException as exc:
            try:
                provider_call = _atlas_exception_provider_call(
                    client,
                    endpoint=submit_endpoint,
                    operation="submit",
                    exc=exc,
                )
                failure = (
                    _atlas_failure_record(exc)
                    if isinstance(exc, BiohubESMError)
                    else {
                        "kind": type(exc).__name__,
                        "message": "Atlas submit ended before durable reconciliation",
                    }
                )
                observed_status = _validated_provider_status(provider_call.get("http_status"))
                if isinstance(exc, APIError):
                    _bind_provider_status(exc, observed_status)
                    # Submit response bytes are held only in an anonymous spool;
                    # no partial artifact survives this command boundary.
                    exc.partial = False
                    provider_call["partial"] = False
                    failure = _atlas_failure_record(exc)
                state = store.reconcile_submission_failure(
                    observed_status=observed_status,
                    endpoint=submit_endpoint,
                    destination_path=str(Path(args.output).resolve()),
                    error_name=type(exc).__name__,
                    failure=failure,
                    provider_call=provider_call,
                )
                _persist_atlas_batch_provenance(store, state)
            except BaseException:
                pass
            raise

        provider_call = _batch_provider_call(
            endpoint=submit_endpoint, operation="submit", http_status=status
        )
        if status == 200:
            path = Path(args.output).resolve()
            try:
                if isinstance(result, AtlasBatchArchive):
                    publication = publish_stream_atomic(
                        path,
                        result.handle,
                        expected_size=result.size_bytes,
                        expected_sha256=result.sha256,
                        replace=False,
                        media_type="application/zip",
                    )
                else:
                    publication = publish_bytes_atomic(
                        path,
                        result,
                        replace=False,
                        media_type="application/zip",
                    )
                with publication as artifact_publication:
                    artifact_evidence = _save_atlas_artifact_provenance(
                        path,
                        media_type="application/zip",
                        endpoint_path="/proteins/batch",
                        inputs={"protein_hashes": hashes},
                        parameters=parameters,
                        started_at=attempt_started_at,
                        base_url=args.base_url,
                        provider_calls=[provider_call],
                        input_sha256=request_sha256,
                        replace_existing=False,
                        expected_artifact_identity=artifact_publication.identity,
                    )
                    with _atlas_verified_artifact_pair(path, artifact_evidence) as accepted:
                        marker = {
                            "status": "completed",
                            "partial_output": False,
                            "destination_path": str(path),
                            "artifact_sha256": accepted["artifact"]["sha256"],
                            "provenance_sha256": accepted["provenance_artifact"]["sha256"],
                        }
                        _bind_atlas_evidence_identities(marker, accepted)
                        state = store.reconcile_submission(
                            job_id=None,
                            status="completed",
                            endpoint=submit_endpoint,
                            http_status=status,
                            response={
                                "status": "completed",
                                "delivery": "synchronous",
                                "artifact_materialization": marker,
                            },
                            artifacts=[
                                accepted["artifact"],
                                accepted["provenance_artifact"],
                            ],
                        )
                        evidence = _persist_atlas_batch_provenance(store, state)
            except BaseException as exc:
                try:
                    current_after_failure = state
                    if (
                        current_after_failure.get("status") == "completed"
                        and current_after_failure.get("job_id") is None
                    ):
                        state = _fail_atlas_batch_materialization(
                            store,
                            current_after_failure,
                            path,
                            reason=(
                                "Local Atlas batch artifact acceptance ended with "
                                f"{type(exc).__name__}"
                            ),
                        )
                    else:
                        state = store.reconcile_submission(
                            job_id=None,
                            status="completed",
                            endpoint=submit_endpoint,
                            http_status=status,
                            response={
                                "status": "completed",
                                "delivery": "synchronous",
                                "artifact_materialization": {
                                    "status": "failed",
                                    "partial_output": path.exists(),
                                    "error": (
                                        "local artifact materialization ended with "
                                        f"{type(exc).__name__}"
                                    ),
                                },
                            },
                        )
                    _persist_atlas_batch_provenance(store, state)
                except BaseException:
                    pass
                raise
            finally:
                if isinstance(result, AtlasBatchArchive):
                    result.close()
        else:
            job_id = result["job_id"]
            state = store.reconcile_submission(
                job_id=job_id,
                status=result["status"],
                endpoint=_atlas_endpoint(args.base_url, f"/proteins/batch/jobs/{job_id}"),
                http_status=status,
                response=result,
            )
            evidence = _persist_atlas_batch_provenance(store, state)
    emit({"http_status": status, **evidence})


def command_atlas_batch_status(args: argparse.Namespace) -> None:
    store = AtlasBatchStore(Path(args.state).resolve())
    with store.operation_lock():
        store, job_id, current = _load_or_adopt_atlas_batch(args, store=store)
        if job_id is None:
            emit(
                {
                    "http_status": current["last_http_status"],
                    **_persist_atlas_batch_provenance(store, current),
                }
            )
            return
    client = AtlasClient(base_url=args.base_url, timeout=args.timeout)
    status, _, evidence = _atlas_batch_status_call(
        args,
        store,
        job_id,
        client,
    )
    emit({"http_status": status, **evidence})


def command_atlas_batch_cancel(args: argparse.Namespace) -> None:
    store = AtlasBatchStore(Path(args.state).resolve())
    with store.operation_lock():
        store, job_id, current = _load_or_adopt_atlas_batch(args, store=store)
        retry_delay = store.cancellation_retry_delay(current)
        if current["status"] in {"completed", "failed", "expired", "cancelled"}:
            evidence = {
                "cancel": "no-op-terminal-state",
                **_persist_atlas_batch_provenance(store, current),
            }
        elif current["status"] == "cancellation-requested" and retry_delay is None:
            evidence = {
                "cancel": "already-requested",
                **_persist_atlas_batch_provenance(store, current),
            }
        elif current["status"] == "cancellation-requested" and retry_delay > 0:
            _persist_atlas_batch_provenance(store, current)
            raise APIError(
                status=429,
                kind="rate-limit",
                message="Atlas cancellation retry is not yet permitted; honor Retry-After",
                retry_after=retry_delay,
            )
        else:
            if job_id is None:  # pragma: no cover - guarded by state validation
                raise ValidationError("Atlas batch state has no resumable job_id")
            client = AtlasClient(base_url=args.base_url, timeout=args.timeout)
            state = store.begin_cancellation(
                provider_call=_batch_provider_call(
                    endpoint=_atlas_endpoint(args.base_url, f"/proteins/batch/jobs/{job_id}"),
                    operation="cancel",
                    http_status=None,
                )
            )
            _persist_atlas_batch_provenance(store, state)
            try:
                client.cancel_batch(job_id)
            except BaseException as exc:
                try:
                    call = _atlas_exception_provider_call(
                        client,
                        endpoint=_atlas_endpoint(args.base_url, f"/proteins/batch/jobs/{job_id}"),
                        operation="cancel",
                        exc=exc,
                    )
                    accepted = call.get("http_status") == 204
                    state = store.reconcile_cancellation(
                        http_status=call.get("http_status"),
                        accepted=accepted,
                        provider_call=call,
                    )
                    _persist_atlas_batch_provenance(store, state)
                except BaseException:
                    pass
                raise
            state = store.reconcile_cancellation(http_status=204, accepted=True)
            evidence = _persist_atlas_batch_provenance(store, state)
    emit(evidence)


def _atlas_batch_status_call(
    args: argparse.Namespace,
    store: AtlasBatchStore,
    job_id: str,
    client: AtlasClient,
    *,
    deadline: float | None = None,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    endpoint = _atlas_endpoint(args.base_url, f"/proteins/batch/jobs/{job_id}")
    with store.operation_lock(deadline=deadline):
        prior_state = store.load()
        output = getattr(args, "output", None)
        destination = Path(output).resolve() if output else None
        existing_response = prior_state.get("last_response")
        existing_marker = (
            existing_response.get("artifact_materialization")
            if isinstance(existing_response, dict)
            else None
        )
        if destination is None and isinstance(existing_marker, dict):
            marker_destination = existing_marker.get("destination_path")
            if isinstance(marker_destination, str) and marker_destination:
                destination = Path(marker_destination).resolve()
        prior_partial_marker = (
            _state_bound_atlas_partial_marker(prior_state, destination)
            if destination is not None
            else None
        )
        remaining = None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise APIError(
                    status=None,
                    kind="timeout",
                    message="Atlas batch polling timed out; durable state is preserved",
                )
        original_timeout = getattr(client, "timeout", None)
        timeout_changed = (
            remaining is not None
            and not isinstance(original_timeout, bool)
            and isinstance(original_timeout, (int, float))
        )
        if timeout_changed:
            client.timeout = min(float(original_timeout), remaining)
        try:
            try:
                if (
                    deadline is not None
                    and getattr(client, "_supports_absolute_deadline", False) is True
                ):
                    http_status, result = client.batch_status(job_id, deadline=deadline)
                else:
                    http_status, result = client.batch_status(job_id)
            except BiohubESMError as exc:
                _record_atlas_batch_call_failure(
                    store,
                    client,
                    endpoint=endpoint,
                    operation="status",
                    exc=exc,
                    partial_marker=prior_partial_marker,
                )
                raise
        finally:
            if timeout_changed:
                client.timeout = original_timeout
        deadline_expired_after_response = deadline is not None and deadline - time.monotonic() <= 0
        state_response = dict(result)
        if prior_partial_marker is not None:
            state_response["artifact_materialization"] = prior_partial_marker
        state = store.update(
            response=state_response,
            http_status=http_status,
            provider_call=_batch_provider_call(
                endpoint=endpoint,
                operation="status",
                http_status=http_status,
            ),
        )
        evidence = _persist_atlas_batch_provenance(store, state)
        if deadline_expired_after_response:
            exc = APIError(
                status=None,
                kind="timeout",
                message=(
                    "Atlas batch polling timed out after provider response; "
                    "durable state is preserved"
                ),
                operation_indeterminate=False,
            )
            raise _bind_provider_status(exc, _validated_provider_status(http_status))
    return http_status, result, evidence


def _recover_or_fail_atlas_batch_materialization(
    store: AtlasBatchStore,
    destination: Path,
    *,
    job_id: str,
    endpoint: str,
    reason: str,
) -> dict[str, Any] | None:
    """Resolve a concurrent materialization before recording unavailability.

    The caller must hold the batch operation lock. A second waiter may have
    completed the artifact and provenance sidecar after this waiter released
    the status-call lock, so the current durable state is authoritative here.
    """

    state = store.load()
    verified = _verified_atlas_batch_materialization(
        state,
        destination,
        job_id=job_id,
        endpoint=endpoint,
    )
    if verified is not None:
        if not _atlas_materialization_is_current(state, destination, verified):
            state = _reconcile_atlas_batch_materialization(store, state, destination, verified)
        return _persist_atlas_batch_provenance(store, state)
    state = _fail_atlas_batch_materialization(
        store,
        state,
        destination,
        reason=reason,
    )
    _persist_atlas_batch_provenance(store, state)
    return None


def _materialize_atlas_batch_output(
    args: argparse.Namespace,
    *,
    store: AtlasBatchStore,
    state: dict[str, Any],
    client: AtlasClient,
    result: dict[str, Any],
    job_id: str,
    destination: Path,
    status_endpoint: str,
    download_url: str,
    download_endpoint: str,
    started_at: str,
    status_http_status: int,
    deadline: float,
) -> dict[str, Any]:
    if deadline - time.monotonic() <= 0:
        raise APIError(
            status=None,
            kind="timeout",
            message=(
                "Atlas batch polling timed out before output download; durable state is preserved"
            ),
        )

    reservation = _reserve_atlas_batch_partial(destination)
    if reservation is not None:
        partial_identity = reservation[1]
    else:
        marker = _state_bound_atlas_partial_marker(state, destination)
        if marker is None:
            raise ValidationError(
                "refusing to adopt an Atlas batch partial without exact durable identity"
            )
        partial_identity = (marker["partial_device"], marker["partial_inode"])
    state = _begin_atlas_batch_materialization(store, state, destination, partial_identity)
    _persist_atlas_batch_provenance(store, state)
    download: dict[str, Any] | None = None
    download_started = False
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise APIError(
                status=None,
                kind="timeout",
                message=(
                    "Atlas batch polling timed out before output download; "
                    "durable state is preserved"
                ),
            )
        original_timeout = getattr(client, "timeout", None)
        timeout_changed = not isinstance(original_timeout, bool) and isinstance(
            original_timeout, (int, float)
        )
        if timeout_changed:
            client.timeout = min(float(original_timeout), remaining)
        download_started = True
        try:
            download = client.download(
                download_url,
                destination,
                deadline=deadline,
                expected_partial_identity=partial_identity,
            )
        finally:
            if timeout_changed:
                client.timeout = original_timeout
        transport_attempts = download.get(
            "transport_attempts",
            [
                {
                    "http_status": download["http_status"],
                    "range_start": None,
                    "outcome": "completed",
                }
            ],
        )
        status_call = {
            "endpoint": status_endpoint,
            "operation": "status",
            "http_status": status_http_status,
        }
        download_call = {
            "endpoint": download_endpoint,
            "operation": "download",
            "http_status": download["http_status"],
            "transport_attempts": transport_attempts,
            "resume_recovery": download.get("resume_recovery"),
        }
        artifact_evidence = _save_atlas_artifact_provenance(
            destination,
            media_type="application/zip",
            endpoint_path=f"/proteins/batch/jobs/{job_id}",
            inputs={"job_id": job_id},
            parameters={
                "poll_interval": args.poll_interval,
                "poll_timeout": args.poll_timeout,
                "resumed": download["resumed"],
                "transport_attempts": transport_attempts,
                "resume_recovery": download.get("resume_recovery"),
            },
            started_at=started_at,
            base_url=args.base_url,
            provider_calls=[status_call, download_call],
            replace_existing=False,
            expected_artifact_identity=partial_identity,
            expected_artifact_record=download,
        )
        with (
            _atlas_verified_artifact_pair(destination, artifact_evidence) as accepted,
            _atlas_retained_partial_acceptance(
                destination,
                accepted["artifact_identity"],
            ),
        ):
            response = dict(result)
            response["download"] = download
            marker = {
                "status": "completed",
                "destination_path": str(destination),
                "partial_path": str(destination.with_suffix(destination.suffix + ".partial")),
                "partial_output": False,
                "artifact_sha256": accepted["artifact"]["sha256"],
                "provenance_sha256": accepted["provenance_artifact"]["sha256"],
            }
            _bind_atlas_evidence_identities(marker, accepted)
            _bind_atlas_published_residue(
                marker,
                destination.with_suffix(destination.suffix + ".partial"),
                destination,
            )
            response["artifact_materialization"] = marker
            state_download_call = _batch_provider_call(
                endpoint=download_endpoint,
                operation="download",
                http_status=download["http_status"],
            )
            state_download_call["transport_attempts"] = transport_attempts
            state_download_call["resume_recovery"] = download.get("resume_recovery")
            state = store.update(
                response=response,
                http_status=download["http_status"],
                provider_call=state_download_call,
                artifacts=[
                    accepted["artifact"],
                    accepted["provenance_artifact"],
                ],
            )
    except BaseException as exc:
        try:
            state = store.load()
            verified = _verified_atlas_batch_materialization(
                state,
                destination,
                job_id=job_id,
                endpoint=status_endpoint,
            )
            if verified is not None:
                state = _reconcile_atlas_batch_materialization(store, state, destination, verified)
            else:
                if not download_started:
                    reason = f"Atlas batch download did not start: {type(exc).__name__}"
                    provider_call = None
                elif download is None:
                    reason = f"Atlas batch download ended with {type(exc).__name__}"
                    provider_call = _atlas_exception_provider_call(
                        None,
                        endpoint=download_endpoint,
                        operation="download",
                        exc=exc,
                    )
                    provider_call.setdefault("partial", bool(getattr(exc, "partial", False)))
                    provider_call.setdefault(
                        "response_body_partial",
                        bool(getattr(exc, "response_body_partial", False)),
                    )
                    transport_attempts = getattr(exc, "transport_attempts", None)
                    if isinstance(transport_attempts, list):
                        provider_call["transport_attempts"] = transport_attempts
                        provider_call["resume_recovery"] = getattr(
                            exc,
                            "resume_recovery",
                            None,
                        )
                else:
                    reason = (
                        "Local Atlas batch artifact materialization ended with "
                        f"{type(exc).__name__}"
                    )
                    provider_call = _batch_provider_call(
                        endpoint=download_endpoint,
                        operation="download",
                        http_status=download.get("http_status"),
                    )
                    provider_call["transport_attempts"] = download.get("transport_attempts", [])
                    provider_call["resume_recovery"] = download.get("resume_recovery")
                state = _fail_atlas_batch_materialization(
                    store,
                    state,
                    destination,
                    reason=reason,
                    provider_call=provider_call,
                )
            _persist_atlas_batch_provenance(store, state)
        except BaseException:
            pass
        raise
    return _persist_atlas_batch_provenance(store, state)


def command_atlas_batch_wait(args: argparse.Namespace) -> None:
    started = utc_now()
    if (
        not math.isfinite(args.poll_interval)
        or not math.isfinite(args.poll_timeout)
        or args.poll_interval <= 0
        or args.poll_timeout <= 0
    ):
        raise ValidationError("poll interval and timeout must be finite and positive")
    deadline = time.monotonic() + args.poll_timeout
    store = AtlasBatchStore(Path(args.state).resolve())
    destination = Path(args.output).resolve() if args.output else None
    _validate_atlas_batch_output(store, args.output)
    with (
        _atlas_output_claim_if_present(destination, deadline=deadline),
        store.operation_lock(deadline=deadline),
    ):
        _validate_atlas_batch_output(store, args.output)
        store, job_id, current = _load_or_adopt_atlas_batch(args, store=store)
        if job_id is None:
            emit(_persist_atlas_batch_provenance(store, current))
            return
        status_endpoint = _atlas_endpoint(args.base_url, f"/proteins/batch/jobs/{job_id}")
        if current["status"] == "completed" and destination is not None:
            verified = _verified_atlas_batch_materialization(
                current,
                destination,
                job_id=job_id,
                endpoint=status_endpoint,
            )
            if verified is not None:
                if not _atlas_materialization_is_current(current, destination, verified):
                    current = _reconcile_atlas_batch_materialization(
                        store, current, destination, verified
                    )
                emit(_persist_atlas_batch_provenance(store, current))
                return
        if current["status"] in {"completed", "cancelled", "failed", "expired"} and (
            current["status"] != "completed" or destination is None
        ):
            emit(_persist_atlas_batch_provenance(store, current))
            return
    client = AtlasClient(base_url=args.base_url, timeout=args.timeout)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise APIError(
                status=None,
                kind="timeout",
                message="Atlas batch polling timed out; durable state is preserved",
            )
        http_status, result, evidence = _atlas_batch_status_call(
            args, store, job_id, client, deadline=deadline
        )
        state = evidence["job"]
        if state["status"] in {"completed", "cancelled", "failed", "expired"}:
            needs_matching_completed_response = (
                state["status"] == "completed"
                and destination is not None
                and result.get("status") == "pending"
            )
            if not needs_matching_completed_response:
                break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise APIError(
                status=None,
                kind="timeout",
                message="Atlas batch polling timed out; durable state is preserved",
            )
        time.sleep(min(args.poll_interval, remaining))

    if state["status"] != "completed" or destination is None:
        emit(evidence)
        return
    observed_terminal = result.get("status")
    if observed_terminal in {"expired", "failed", "cancelled"}:
        with (
            _atlas_output_claim(destination, deadline=deadline),
            store.operation_lock(deadline=deadline),
        ):
            _validate_atlas_batch_output(store, args.output)
            recovered_evidence = _recover_or_fail_atlas_batch_materialization(
                store,
                destination,
                job_id=job_id,
                endpoint=status_endpoint,
                reason=(
                    "provider reports Atlas batch "
                    f"{observed_terminal} before durable output was materialized"
                ),
            )
        if recovered_evidence is not None:
            emit(recovered_evidence)
            return
        raise APIError(
            status=http_status,
            kind=("provider" if observed_terminal == "failed" else observed_terminal),
            message=(
                "completed Atlas batch output is not materialized and the provider now "
                f"reports the job as {observed_terminal}"
            ),
        )
    download_url = result.get("download_url")
    if not isinstance(download_url, str):
        with (
            _atlas_output_claim(destination, deadline=deadline),
            store.operation_lock(deadline=deadline),
        ):
            _validate_atlas_batch_output(store, args.output)
            recovered_evidence = _recover_or_fail_atlas_batch_materialization(
                store,
                destination,
                job_id=job_id,
                endpoint=status_endpoint,
                reason="provider no longer supplies the completed Atlas batch download",
            )
        if recovered_evidence is not None:
            emit(recovered_evidence)
            return
        raise APIError(
            status=http_status,
            kind="expired",
            message=(
                "completed Atlas batch output is not materialized and its download is unavailable"
            ),
        )

    download_endpoint = _safe_download_endpoint(download_url)
    with (
        _atlas_output_claim(destination, deadline=deadline),
        store.operation_lock(deadline=deadline),
    ):
        _validate_atlas_batch_output(store, args.output)
        state = store.load()
        verified = _verified_atlas_batch_materialization(
            state,
            destination,
            job_id=job_id,
            endpoint=status_endpoint,
        )
        if verified is not None:
            if not _atlas_materialization_is_current(state, destination, verified):
                state = _reconcile_atlas_batch_materialization(store, state, destination, verified)
            evidence = _persist_atlas_batch_provenance(store, state)
        else:
            evidence = _materialize_atlas_batch_output(
                args,
                store=store,
                state=state,
                client=client,
                result=result,
                job_id=job_id,
                destination=destination,
                status_endpoint=status_endpoint,
                download_url=download_url,
                download_endpoint=download_endpoint,
                started_at=started,
                status_http_status=http_status,
                deadline=deadline,
            )
    emit(evidence)


def _modal_manager(args: argparse.Namespace) -> ModalJobManager:
    adapter = ModalFunctionAdapter(
        app_name=args.app_name,
        function_name=args.function_name,
        function_version=args.function_version,
        workspace_name=args.workspace_name,
        environment_name=args.environment_name,
    )
    return ModalJobManager(adapter, ModalJobStore(Path(args.state).resolve()))


def command_modal_spawn(args: argparse.Namespace) -> None:
    if args.max_jobs < 1 or args.max_jobs > MODAL_MAX_JOBS:
        raise ValidationError(f"Modal --max-jobs must be between 1 and {MODAL_MAX_JOBS}")
    payloads = load_bounded_json(
        args.input,
        max_bytes=MODAL_INPUT_MAX_BYTES,
        field="Modal input",
    )
    if not isinstance(payloads, list) or any(not isinstance(item, dict) for item in payloads):
        raise ValidationError("Modal input must be a JSON list of objects")
    if not payloads:
        raise ValidationError("at least one Modal payload is required")
    if not args.confirm_cost:
        raise ValidationError("Modal ESM submission is missing its internal execution token")
    if len(payloads) > args.max_jobs:
        raise ValidationError("Modal payload count exceeds the configured --max-jobs")
    emit(_modal_manager(args).spawn(payloads, kind=args.kind))


def command_modal_gather(args: argparse.Namespace) -> None:
    emit(_modal_manager(args).gather(timeout_per_call=args.timeout_per_call))


def command_modal_cancel(args: argparse.Namespace) -> None:
    emit(_modal_manager(args).cancel())


def build_parser() -> argparse.ArgumentParser:
    return _build_cli_parser(sys.modules[__name__], description=__doc__)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
        return 0
    except SchemaDriftError as exc:
        _persist_schema_drift(args, exc)
        print(
            json.dumps(
                redact({"error": exc.as_dict()}),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            ),
            file=sys.stderr,
        )
        return 2
    except BiohubESMError as exc:
        error = (
            exc.as_dict()
            if hasattr(exc, "as_dict")
            else {"kind": exc.__class__.__name__, "message": str(exc)}
        )
        print(
            json.dumps(redact({"error": error}), indent=2, sort_keys=True, allow_nan=False),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {"error": {"kind": exc.__class__.__name__, "message": redact(str(exc))}},
                indent=2,
                allow_nan=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

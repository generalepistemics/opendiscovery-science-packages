"""Public ESM Atlas v1alpha1 client with schema-drift checks."""

from __future__ import annotations

import binascii
import hashlib
import io
import math
import os
import re
import stat
import struct
import tempfile
import time
import zipfile
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterator
from urllib.parse import urlencode, urlsplit

from .constants import (
    ATLAS_API_PREFIX,
    ATLAS_FEATURE_COUNT,
    ATLAS_FOLD_MAX_RESIDUES,
    BIOHUB_BASE_URL,
    DEFAULT_POLL_TIMEOUT_SECONDS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
)
from .errors import APIError, BiohubESMError, SchemaDriftError, ValidationError
from .http import (
    HTTPResponse,
    Transport,
    UrllibTransport,
    _bind_provider_status,
    _open_status_bound_stream_destination,
    _open_stream_destination,
    _status_bound_stream_handle,
    _status_bound_stream_size,
    _sync_stream_destination,
    _validated_provider_status,
    _write_stream_destination,
    decode_json,
    encode_json_body,
    raise_for_status,
    validate_content_range,
    validate_timeout,
)
from .provenance import promote_file_noreplace, utc_now
from .validation import (
    normalize_sequence,
    sequence_md5,
    validate_atlas_fold_sequence,
    validate_atlas_search_sequence,
    validate_batch_hashes,
    validate_feature_index,
    validate_md5,
)

_DOWNLOAD_ATTEMPT_OUTCOMES = {
    "completed",
    "failed",
    "invalid-archive",
    "invalid-content-range",
    "invalid-full-archive",
    "invalid-full-response",
    "invalid-resumed-archive",
    "range-not-satisfiable",
    "publication-failed",
}
_DOWNLOAD_RECOVERY_REASONS = {
    "invalid-content-range",
    "invalid-resumed-archive",
    "range-not-satisfiable",
}
JOB_ID_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
DOWNLOAD_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    re.IGNORECASE,
)
AWS_REGION_RE = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)+-\d+$")
PNG_MAX_CHUNKS = 65_536
PNG_MAX_DIMENSION = 8_192
PNG_MAX_PIXELS = 16 * 1024 * 1024
PNG_MAX_IDAT_COMPRESSED_BYTES = 64 * 1024 * 1024
PNG_MAX_DECOMPRESSED_BYTES = 128 * 1024 * 1024
PNG_INFLATE_CHUNK_BYTES = 64 * 1024
ZIP_MAX_MEMBERS = 4_096
ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
ZIP_MAX_TOTAL_COMPRESSED_BYTES = 1024 * 1024 * 1024
ZIP_MAX_CENTRAL_DIRECTORY_BYTES = 16 * 1024 * 1024
ZIP_MAX_VALIDATION_READ_BYTES = ZIP_MAX_CENTRAL_DIRECTORY_BYTES + 128 * 1024
ZIP_MAX_EXPANSION_RATIO = 1_000
ZIP_ALLOWED_COMPRESSION_METHODS = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
ATLAS_BATCH_ARCHIVE_MAX_BYTES = ZIP_MAX_TOTAL_COMPRESSED_BYTES + 64 * 1024 * 1024


@dataclass(frozen=True)
class AtlasBatchArchive:
    """Owned anonymous archive returned by a synchronous Atlas submission."""

    handle: BinaryIO
    size_bytes: int
    sha256: str

    def close(self) -> None:
        self.handle.close()

    def __enter__(self) -> "AtlasBatchArchive":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


@dataclass
class OpenAtlasArtifactSnapshot:
    path: Path
    handle: BinaryIO
    record: dict[str, Any]
    identity: tuple[int, int]
    fingerprint: tuple[int, int, int, int, int, int]
    captured: bytes | None

    def validate_path_identity(self) -> None:
        retained_before = os.fstat(self.handle.fileno())
        try:
            path_before = self.path.stat(follow_symlinks=False)
        except OSError as exc:
            raise ValidationError("Atlas artifact identity changed after publication") from exc
        if (
            not stat.S_ISREG(retained_before.st_mode)
            or not stat.S_ISREG(path_before.st_mode)
            or (retained_before.st_dev, retained_before.st_ino) != self.identity
            or (path_before.st_dev, path_before.st_ino) != self.identity
        ):
            raise ValidationError("Atlas artifact identity changed after publication")
        if (
            _atlas_file_fingerprint(retained_before) != self.fingerprint
            or _atlas_file_fingerprint(path_before) != self.fingerprint
        ):
            raise ValidationError("Atlas artifact content changed after publication")
        expected_size = self.record.get("size_bytes")
        if isinstance(expected_size, bool) or not isinstance(expected_size, int):
            raise ValidationError("Atlas artifact content changed after publication")
        digest, _ = _atlas_descriptor_snapshot_exact(
            self.handle.fileno(),
            expected_size=expected_size,
            capture=False,
            changed_message="Atlas artifact content changed after publication",
        )
        retained_after = os.fstat(self.handle.fileno())
        try:
            path_after = self.path.stat(follow_symlinks=False)
        except OSError as exc:
            raise ValidationError("Atlas artifact identity changed after publication") from exc
        terminal_digest, _ = _atlas_descriptor_snapshot_exact(
            self.handle.fileno(),
            expected_size=expected_size,
            capture=False,
            changed_message="Atlas artifact content changed after publication",
        )
        terminal_retained = os.fstat(self.handle.fileno())
        try:
            terminal_path = self.path.stat(follow_symlinks=False)
        except OSError as exc:
            raise ValidationError("Atlas artifact identity changed after publication") from exc
        if (
            digest != self.record.get("sha256")
            or terminal_digest != self.record.get("sha256")
            or self.record.get("size_bytes") != retained_after.st_size
            or _atlas_file_fingerprint(retained_after) != self.fingerprint
            or _atlas_file_fingerprint(path_after) != self.fingerprint
            or _atlas_file_fingerprint(terminal_path) != self.fingerprint
            or _atlas_file_fingerprint(terminal_retained) != self.fingerprint
        ):
            raise ValidationError("Atlas artifact content changed after publication")


def _atlas_file_fingerprint(
    info: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _atlas_descriptor_snapshot_exact(
    descriptor: int,
    *,
    expected_size: int,
    capture: bool,
    changed_message: str,
) -> tuple[str, bytes | None]:
    """Hash exactly one preflight size and reject one bounded extra byte."""

    digest = hashlib.sha256()
    captured = bytearray() if capture else None
    offset = 0
    try:
        while offset < expected_size:
            chunk = os.pread(descriptor, min(1024 * 1024, expected_size - offset), offset)
            if not chunk:
                raise ValidationError(changed_message)
            digest.update(chunk)
            if captured is not None:
                captured.extend(chunk)
            offset += len(chunk)
        if os.pread(descriptor, 1, expected_size):
            raise ValidationError(changed_message)
    except OSError as exc:
        raise ValidationError(changed_message) from exc
    return digest.hexdigest(), bytes(captured) if captured is not None else None


@contextmanager
def hold_atlas_artifact_identity(
    path: Path, *, expected_identity: tuple[int, int]
) -> Iterator[tuple[int, int]]:
    """Keep one regular artifact inode live while a paired state update commits."""

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValidationError("Atlas retained artifact is not a safe regular file") from exc
    try:
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino)
        if not stat.S_ISREG(info.st_mode) or identity != expected_identity:
            raise ValidationError("Atlas retained artifact identity changed")
        yield identity
        retained = os.fstat(descriptor)
        current = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(retained.st_mode)
            or (retained.st_dev, retained.st_ino) != identity
            or not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != identity
        ):
            raise ValidationError("Atlas retained artifact identity changed")
    finally:
        os.close(descriptor)


@contextmanager
def open_atlas_artifact_snapshot(
    path: Path,
    *,
    media_type: str | None = None,
    expected_identity: tuple[int, int] | None = None,
    capture_max_bytes: int | None = None,
) -> Iterator[OpenAtlasArtifactSnapshot]:
    """Hold the hashed Atlas artifact descriptor through final pathname checks."""

    if expected_identity is not None and (
        not isinstance(expected_identity, tuple)
        or len(expected_identity) != 2
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 0
            for item in expected_identity
        )
    ):
        raise ValidationError("expected Atlas artifact identity is invalid")
    if capture_max_bytes is not None and (
        isinstance(capture_max_bytes, bool)
        or not isinstance(capture_max_bytes, int)
        or capture_max_bytes < 0
    ):
        raise ValidationError("Atlas artifact capture limit is invalid")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValidationError("Atlas artifact is not a safe regular file") from exc

    try:
        handle = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    with handle:
        try:
            before = os.fstat(handle.fileno())
            identity = (before.st_dev, before.st_ino)
            if not stat.S_ISREG(before.st_mode):
                raise ValidationError("Atlas artifact must be a regular file")
            if expected_identity is not None and identity != expected_identity:
                raise ValidationError("Atlas artifact identity changed after publication")
            if capture_max_bytes is not None and before.st_size > capture_max_bytes:
                raise ValidationError("Atlas artifact exceeds its bounded capture limit")
            digest, captured = _atlas_descriptor_snapshot_exact(
                handle.fileno(),
                expected_size=before.st_size,
                capture=capture_max_bytes is not None,
                changed_message="Atlas artifact changed while metadata was computed",
            )
            after = os.fstat(handle.fileno())
        except BaseException:
            raise

        before_fingerprint = _atlas_file_fingerprint(before)
        after_fingerprint = _atlas_file_fingerprint(after)
        if before_fingerprint != after_fingerprint:
            raise ValidationError("Atlas artifact changed while metadata was computed")

        record: dict[str, Any] = {
            "path": str(path),
            "size_bytes": after.st_size,
            "sha256": digest,
        }
        if media_type is not None:
            record["media_type"] = media_type
        snapshot = OpenAtlasArtifactSnapshot(
            path=path,
            handle=handle,
            record=record,
            identity=identity,
            fingerprint=after_fingerprint,
            captured=captured,
        )
        snapshot.validate_path_identity()
        try:
            yield snapshot
        except BaseException:
            raise
        else:
            snapshot.validate_path_identity()


def atlas_artifact_snapshot(
    path: Path,
    *,
    media_type: str | None = None,
    expected_identity: tuple[int, int] | None = None,
    capture_max_bytes: int | None = None,
    descriptor_validator: Callable[[BinaryIO], None] | None = None,
) -> tuple[dict[str, Any], tuple[int, int], bytes | None]:
    with open_atlas_artifact_snapshot(
        path,
        media_type=media_type,
        expected_identity=expected_identity,
        capture_max_bytes=capture_max_bytes,
    ) as snapshot:
        if descriptor_validator is not None:
            descriptor_validator(snapshot.handle)
        return snapshot.record, snapshot.identity, snapshot.captured


def validate_job_id(job_id: str) -> str:
    if not isinstance(job_id, str) or not JOB_ID_RE.fullmatch(job_id):
        raise ValidationError(
            "job_id must be 1-128 path-safe characters beginning and ending alphanumeric"
        )
    return job_id


def _is_aws_s3_download_host(hostname: str) -> bool:
    """Accept only AWS-owned public S3 endpoint hostname shapes.

    Atlas documents async batch results as S3 downloads.  Restricting the
    provider-supplied URL to AWS-owned S3 DNS names avoids both direct-IP SSRF
    and DNS-rebinding/TOCTOU problems from attacker-controlled hostnames.
    """

    labels = hostname.lower().split(".")
    if len(labels) < 3 or labels[-2:] != ["amazonaws", "com"]:
        return False

    endpoint_labels = labels[:-2]
    for index, service_label in enumerate(endpoint_labels):
        tail = endpoint_labels[index:]
        if tail == ["s3"]:
            return True
        if len(tail) == 2 and tail[0] == "s3" and AWS_REGION_RE.fullmatch(tail[1]):
            return True
        if len(tail) == 3 and tail[:2] == ["s3", "dualstack"] and AWS_REGION_RE.fullmatch(tail[2]):
            return True
        if tail in (["s3-accelerate"], ["s3-accelerate", "dualstack"]):
            return True
        if (
            len(tail) == 1
            and service_label.startswith("s3-")
            and AWS_REGION_RE.fullmatch(service_label.removeprefix("s3-"))
        ):
            return True
    return False


def safe_download_endpoint(url: str) -> str:
    """Validate an ephemeral Atlas download URL and omit its signed query."""

    if not isinstance(url, str) or any(ord(character) < 32 for character in url):
        raise ValidationError("download URL must be a valid HTTPS URL")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ValidationError("download URL must be a valid HTTPS URL") from exc
    hostname = parts.hostname
    if (
        parts.scheme != "https"
        or hostname is None
        or not DOWNLOAD_HOST_RE.fullmatch(hostname)
        or not _is_aws_s3_download_host(hostname)
        or parts.username is not None
        or parts.password is not None
        or (port is not None and port != 443)
        or not parts.path.startswith("/")
        or parts.fragment
    ):
        raise ValidationError(
            "download URL requires HTTPS on a public AWS S3 endpoint, no userinfo/fragment, "
            "and port 443"
        )
    return f"https://{hostname.lower()}{parts.path}"


def _require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaDriftError(f"Atlas {context} response must be a JSON object", raw=value)
    return value


def _require_keys(value: dict[str, Any], context: str, keys: set[str]) -> None:
    missing = sorted(keys - set(value))
    if missing:
        raise SchemaDriftError(
            f"Atlas {context} response is missing: {', '.join(missing)}", raw=value
        )


def _require_string(value: Any, context: str, *, nonempty: bool = False) -> None:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        qualifier = "a non-empty" if nonempty else "a"
        raise SchemaDriftError(f"Atlas {context} must be {qualifier} string", raw=value)


def _require_integer(
    value: Any,
    context: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> None:
    invalid = isinstance(value, bool) or not isinstance(value, int)
    if minimum is not None and not invalid:
        invalid = value < minimum
    if maximum is not None and not invalid:
        invalid = value > maximum
    if invalid:
        bounds = ""
        if minimum is not None and maximum is not None:
            bounds = f" between {minimum} and {maximum}"
        elif minimum is not None:
            bounds = f" greater than or equal to {minimum}"
        elif maximum is not None:
            bounds = f" less than or equal to {maximum}"
        raise SchemaDriftError(f"Atlas {context} must be an integer{bounds}", raw=value)


def _preserve_full_json_response(method: Any) -> Any:
    """Attach the complete decoded provider object to nested schema failures."""

    @wraps(method)
    def wrapped(self: "AtlasClient", *args: Any, **kwargs: Any) -> Any:
        try:
            return method(self, *args, **kwargs)
        except SchemaDriftError as exc:
            if self.last_raw_response is not None:
                exc.raw = self.last_raw_response
            raise

    return wrapped


def _require_response_md5(value: Any, context: str, *, allow_none: bool = False) -> None:
    if allow_none and value is None:
        return
    if (
        not isinstance(value, str)
        or value != value.lower()
        or not re.fullmatch(r"[0-9a-f]{32}", value)
    ):
        suffix = " or null" if allow_none else ""
        raise SchemaDriftError(f"Atlas {context} must be a lowercase MD5 string{suffix}", raw=value)


def require_returned_cluster_representative(*records: Any) -> str:
    """Return a provider-supplied representative hash without inferring one from a hit."""

    representative: str | None = None
    representative_count = 0
    diagnostic_hashes: list[str] = []
    diagnostic_hash_set: set[str] = set()
    diagnostic_truncated = False
    disagree = False
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise SchemaDriftError(
                f"Atlas cluster source record {index} must be an object",
                raw=record,
            )
        if "cluster_rep_protein_hash" not in record or record["cluster_rep_protein_hash"] is None:
            continue
        candidate = record["cluster_rep_protein_hash"]
        _require_response_md5(
            candidate,
            f"cluster source record {index} cluster_rep_protein_hash",
        )
        representative_count += 1
        if representative is None:
            representative = candidate
        elif candidate != representative:
            disagree = True
        if candidate not in diagnostic_hash_set:
            if len(diagnostic_hashes) < 16:
                diagnostic_hashes.append(candidate)
                diagnostic_hash_set.add(candidate)
            else:
                diagnostic_truncated = True
    if disagree:
        raise SchemaDriftError(
            "Atlas cluster source records disagree on cluster_rep_protein_hash",
            raw={
                "representative_count": representative_count,
                "validated_representative_hashes": diagnostic_hashes,
                "truncated": diagnostic_truncated,
            },
        )
    if representative is not None:
        return representative
    raise APIError(
        status=None,
        kind="partial-result",
        message=(
            "Atlas returned no cluster representative; preserve the search/protein artifacts "
            "and do not infer a representative from an ordinary hit hash"
        ),
        partial=True,
    )


def _require_finite_number(value: Any, context: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SchemaDriftError(f"Atlas {context} must be a finite number", raw=value)


def _require_bounded_number(value: Any, context: str, low: float, high: float) -> None:
    _require_finite_number(value, context)
    if not low <= value <= high:
        raise SchemaDriftError(f"Atlas {context} must be between {low:g} and {high:g}", raw=value)


def _validate_optional_structure_fields(value: dict[str, Any], context: str) -> None:
    """Validate known scientific fields without rejecting additive alpha fields."""

    if "pdb_artifact" in value:
        raise SchemaDriftError(
            f"Atlas {context} contains reserved local pdb_artifact metadata",
            raw=value,
        )

    for field in ("mean_plddt", "ptm"):
        metric = value.get(field)
        if metric is not None:
            _require_bounded_number(metric, f"{context} {field}", 0.0, 1.0)

    residue_confidence = value.get("residues_plddt")
    if residue_confidence is not None:
        if not isinstance(residue_confidence, list):
            raise SchemaDriftError(f"Atlas {context} residues_plddt must be a list", raw=value)
        for index, metric in enumerate(residue_confidence):
            _require_bounded_number(
                metric,
                f"{context} residues_plddt entry {index}",
                0.0,
                1.0,
            )

    characterized = value.get("cluster_pct_characterized")
    if characterized is not None:
        _require_bounded_number(
            characterized,
            f"{context} cluster_pct_characterized",
            0.0,
            100.0,
        )

    pdb = value.get("pdb")
    if pdb is not None and not isinstance(pdb, str):
        raise SchemaDriftError(f"Atlas {context} pdb must be a string or null", raw=value)

    representative = value.get("cluster_rep_protein_hash")
    if representative is not None:
        _require_response_md5(
            representative,
            f"{context} cluster_rep_protein_hash",
        )


def _validate_optional_strings(
    value: dict[str, Any], fields: tuple[str, ...], context: str
) -> None:
    for field in fields:
        item = value.get(field)
        if item is not None:
            _require_string(item, f"{context} {field}")


def _validate_sae_feature_response(
    value: Any,
    context: str,
    *,
    sequence_length: int | None = None,
) -> None:
    feature = _require_object(value, context)
    _require_keys(
        feature,
        context,
        {"feature_index", "label", "description", "value"},
    )
    try:
        validate_feature_index(feature["feature_index"])
    except ValidationError as exc:
        raise SchemaDriftError(f"Atlas {context} feature_index is invalid", raw=feature) from exc
    _require_string(feature["label"], f"{context} label")
    _require_string(feature["description"], f"{context} description")
    _require_finite_number(feature["value"], f"{context} value")
    regions = feature.get("residue_regions", [])
    if not isinstance(regions, list):
        raise SchemaDriftError(f"Atlas {context} residue_regions must be a list", raw=feature)
    for index, item in enumerate(regions):
        region_context = f"{context} residue_regions entry {index}"
        region = _require_object(item, region_context)
        _require_keys(
            region,
            region_context,
            {"start", "end", "peak_residue", "mean_activation"},
        )
        for field in ("start", "end", "peak_residue"):
            _require_integer(
                region[field],
                f"{region_context} {field}",
                minimum=0,
                maximum=sequence_length - 1 if sequence_length is not None else None,
            )
        start = region["start"]
        end = region["end"]
        peak_residue = region["peak_residue"]
        if start > end:
            raise SchemaDriftError(
                f"Atlas {region_context} start must be less than or equal to end",
                raw=region,
            )
        if not start <= peak_residue <= end:
            raise SchemaDriftError(
                f"Atlas {region_context} peak_residue must fall within start and end",
                raw=region,
            )
        _require_finite_number(
            region["mean_activation"],
            f"{region_context} mean_activation",
        )


def _bind_protein_feature_response(
    features: list[Any],
    *,
    requested_indices: list[int] | None,
    topk_features: int,
    raw: dict[str, Any],
    sequence_length: int | None,
) -> None:
    """Bind returned SAE features to the protein lookup selection mode."""

    returned_indices: list[int] = []
    for position, feature in enumerate(features):
        _validate_sae_feature_response(
            feature,
            f"protein sae_features entry {position}",
            sequence_length=sequence_length,
        )
        returned_indices.append(feature["feature_index"])

    if requested_indices is None:
        if len(features) > topk_features:
            raise SchemaDriftError(
                "Atlas protein sae_features returned more entries than requested by topk_features",
                raw=raw,
            )
        if len(set(returned_indices)) != len(returned_indices):
            raise SchemaDriftError(
                "Atlas protein sae_features feature_index values must be unique in top-K mode",
                raw=raw,
            )
        return

    expected_indices = [index for index in requested_indices if 0 <= index < ATLAS_FEATURE_COUNT]
    if returned_indices != expected_indices:
        raise SchemaDriftError(
            "Atlas protein sae_features must exactly match requested in-catalog "
            "feature_indices in caller order",
            raw=raw,
        )


def _validate_sparse_activations(
    value: Any,
    context: str,
    *,
    sequence_length: int | None = None,
) -> None:
    sparse = _require_object(value, context)
    _require_keys(sparse, context, {"indices", "values", "shape"})
    indices = sparse["indices"]
    values = sparse["values"]
    shape = sparse["shape"]
    if not isinstance(indices, list) or not all(isinstance(axis, list) for axis in indices):
        raise SchemaDriftError(f"Atlas {context} indices must be a list of lists", raw=sparse)
    if not isinstance(values, list):
        raise SchemaDriftError(f"Atlas {context} values must be a list", raw=sparse)
    if not isinstance(shape, list):
        raise SchemaDriftError(f"Atlas {context} shape must be a list", raw=sparse)
    for index, item in enumerate(shape):
        _require_integer(item, f"{context} shape entry {index}", minimum=0)
    if len(indices) != len(shape):
        raise SchemaDriftError(
            f"Atlas {context} COO index-axis count must match shape rank",
            raw=sparse,
        )
    if sequence_length is not None and (not shape or shape[0] != sequence_length):
        raise SchemaDriftError(
            f"Atlas {context} residue-axis shape must match the protein sequence length",
            raw=sparse,
        )
    for axis_index, (axis, extent) in enumerate(zip(indices, shape, strict=True)):
        for position, item in enumerate(axis):
            _require_integer(
                item,
                f"{context} indices axis {axis_index} entry {position}",
                minimum=0,
            )
            if item >= extent:
                raise SchemaDriftError(
                    f"Atlas {context} COO coordinate exceeds shape on axis {axis_index}",
                    raw=sparse,
                )
        if len(axis) != len(values):
            raise SchemaDriftError(
                f"Atlas {context} COO index and value lengths must match",
                raw=sparse,
            )
    for index, item in enumerate(values):
        _require_finite_number(item, f"{context} values entry {index}")
    coordinates: set[tuple[int, ...]] = set()
    for position in range(len(values)):
        coordinate = tuple(axis[position] for axis in indices)
        if coordinate in coordinates:
            raise SchemaDriftError(
                f"Atlas {context} COO coordinates must be unique",
                raw=sparse,
            )
        coordinates.add(coordinate)


def _validate_protein_response(
    raw: Any,
    *,
    digest: str,
    requested_indices: list[int] | None,
    topk_features: int,
) -> dict[str, Any]:
    wire_result = _require_object(raw, "protein")
    result = dict(wire_result)
    _require_keys(result, "protein", {"protein_hash"})
    if result["protein_hash"] != digest:
        raise SchemaDriftError("Atlas protein response hash does not match the request", raw=result)
    sequence_length = _bind_atlas_protein_sequence(result, digest)
    representative = result.get("cluster_rep_protein_hash")
    if representative is not None:
        _require_response_md5(
            representative,
            "protein cluster_rep_protein_hash",
        )
    _validate_optional_structure_fields(result, "protein response")
    _validate_optional_strings(
        result,
        ("header", "source", "accession"),
        "protein response",
    )
    features = result.get("sae_features", [])
    if not isinstance(features, list):
        raise SchemaDriftError("Atlas protein sae_features must be a list", raw=result)
    _bind_protein_feature_response(
        features,
        requested_indices=requested_indices,
        topk_features=topk_features,
        raw=result,
        sequence_length=sequence_length,
    )
    for field in ("protein_activations", "per_residue_activations"):
        activations = result.get(field)
        if activations is not None:
            _validate_sparse_activations(
                activations,
                f"protein {field}",
                sequence_length=sequence_length if field == "per_residue_activations" else None,
            )
    folded_on_demand = result.get("folded_on_demand")
    if folded_on_demand is not None and not isinstance(folded_on_demand, bool):
        raise SchemaDriftError(
            "Atlas protein folded_on_demand must be boolean",
            raw=result,
        )
    return result


def _validate_search_feature_summary(value: Any, context: str) -> None:
    feature = _require_object(value, context)
    _require_keys(
        feature,
        context,
        {
            "feature_index",
            "occurrence_count",
            "min_activation",
            "max_activation",
            "mean_activation",
        },
    )
    try:
        validate_feature_index(feature["feature_index"])
    except ValidationError as exc:
        raise SchemaDriftError(f"Atlas {context} feature_index is invalid", raw=feature) from exc
    _require_integer(feature["occurrence_count"], f"{context} occurrence_count", minimum=0)
    for field in ("min_activation", "max_activation", "mean_activation"):
        _require_finite_number(feature[field], f"{context} {field}")
    if not (feature["min_activation"] <= feature["mean_activation"] <= feature["max_activation"]):
        raise SchemaDriftError(
            f"Atlas {context} activation summary is inconsistent",
            raw=feature,
        )


def _bind_atlas_protein_sequence(result: dict[str, Any], digest: str) -> int | None:
    """Normalize and bind optional protein metadata to the requested MD5."""

    sequence = result.get("sequence")
    normalized_sequence: str | None = None
    if sequence is not None:
        if not isinstance(sequence, str):
            raise SchemaDriftError(
                "Atlas protein response sequence must be a string when present",
                raw=result,
            )
        try:
            normalized_sequence = normalize_sequence(sequence)
            recomputed_hash = sequence_md5(normalized_sequence, provider="atlas")
        except ValidationError as exc:
            raise SchemaDriftError(
                "Atlas protein response sequence contains unsupported protein symbols",
                raw=result,
            ) from exc
        if recomputed_hash != digest:
            raise SchemaDriftError(
                "Atlas protein response sequence MD5 does not match the requested hash",
                raw=result,
            )
        result["sequence"] = normalized_sequence

    sequence_length = result.get("sequence_length")
    if sequence_length is not None:
        try:
            _require_integer(
                sequence_length,
                "protein response sequence_length",
                minimum=1,
            )
        except SchemaDriftError as exc:
            raise SchemaDriftError(
                "Atlas protein response sequence_length must be a positive integer",
                raw=result,
            ) from exc
        if normalized_sequence is not None and sequence_length != len(normalized_sequence):
            raise SchemaDriftError(
                "Atlas protein response sequence_length does not match sequence length",
                raw=result,
            )

    residue_confidence = result.get("residues_plddt")
    expected_length = (
        len(normalized_sequence) if normalized_sequence is not None else sequence_length
    )
    if (
        expected_length is not None
        and isinstance(residue_confidence, list)
        and len(residue_confidence) != expected_length
    ):
        raise SchemaDriftError(
            "Atlas protein response residues_plddt length does not match sequence length",
            raw=result,
        )
    return expected_length


def _validate_fold_on_miss_preflight(result: dict[str, Any], *, digest: str) -> None:
    """Require the stored sequence itself before requesting an on-demand fold."""

    sequence = result.get("sequence")
    if not isinstance(sequence, str):
        raise ValidationError(
            "Atlas fold-on-miss requires a non-folding lookup that returns the actual sequence"
        )
    try:
        normalized = validate_atlas_fold_sequence(sequence)
    except ValidationError as exc:
        raise ValidationError(
            "Atlas fold-on-miss requires an actual Atlas protein sequence containing at most "
            f"{ATLAS_FOLD_MAX_RESIDUES} residues"
        ) from exc
    if sequence_md5(normalized, provider="atlas") != digest:
        raise ValidationError(
            "Atlas fold-on-miss preflight sequence does not match the requested protein hash"
        )


def _integer_in_range(name: str, value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValidationError(f"{name} must be an integer between {low} and {high}")
    return value


def _boolean(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{name} must be boolean")
    return value


def _validate_deadline(deadline: float | None, context: str) -> float | None:
    if deadline is None:
        return None
    if (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(deadline)
    ):
        raise ValidationError(f"{context} deadline must be finite")
    return float(deadline)


def _require_deadline(
    deadline: float | None,
    message: str,
    *,
    partial: bool = False,
) -> None:
    if deadline is not None and deadline - time.monotonic() <= 0:
        raise APIError(
            status=None,
            kind="timeout",
            message=message,
            partial=partial,
        )


def _open_atlas_partial(
    path: Path, *, expected_identity: tuple[int, int] | None = None
) -> tuple[tuple[int, int], int]:
    """Open-or-create a regular partial without following a raced symlink."""

    path.parent.mkdir(parents=True, exist_ok=True)
    safe_open_flags = os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0
    if hasattr(os, "O_NONBLOCK"):
        safe_open_flags |= os.O_NONBLOCK
    while True:
        try:
            descriptor = os.open(path, os.O_WRONLY | safe_open_flags)
        except FileNotFoundError:
            if expected_identity is not None:
                raise ValidationError("Atlas batch partial identity changed") from None
            try:
                descriptor = os.open(
                    path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | safe_open_flags,
                    0o600,
                )
            except FileExistsError:
                continue
            except OSError as exc:
                raise ValidationError("Atlas batch partial is not a safe regular file") from exc
        except OSError as exc:
            raise ValidationError("Atlas batch partial is not a safe regular file") from exc
        break
    try:
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino)
        if not stat.S_ISREG(info.st_mode):
            raise ValidationError("Atlas batch partial must be a regular file")
        if expected_identity is not None and identity != expected_identity:
            raise ValidationError("Atlas batch partial identity changed")
        return identity, info.st_size
    finally:
        os.close(descriptor)


def _require_atlas_partial_identity(path: Path, expected: tuple[int, int]) -> int:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise ValidationError("Atlas batch partial identity is unavailable") from exc
    if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != expected:
        raise ValidationError("Atlas batch partial identity changed")
    return info.st_size


def _truncate_atlas_partial(path: Path, expected: tuple[int, int]) -> None:
    """Reset a definitively invalid response without unlinking its reserved inode."""

    handle, observed_identity = _open_stream_destination(
        path,
        append=False,
        expected_identity=expected,
    )
    handle.close()
    if observed_identity != expected:  # pragma: no cover - defensive
        raise ValidationError("Atlas batch partial identity changed")


def _zip_read_exact_range(
    source: bytes | BinaryIO,
    offset: int,
    length: int,
    context: str,
) -> bytes:
    if offset < 0 or length < 0:
        raise SchemaDriftError(f"{context} zip metadata offsets are invalid")
    if isinstance(source, bytes):
        result = source[offset : offset + length]
    else:
        try:
            descriptor = source.fileno()
            chunks = bytearray()
            while len(chunks) < length:
                chunk = os.pread(
                    descriptor,
                    length - len(chunks),
                    offset + len(chunks),
                )
                if not chunk:
                    break
                chunks.extend(chunk)
            result = bytes(chunks)
        except (AttributeError, OSError, ValueError) as exc:
            raise ValidationError(
                f"{context} zip metadata could not be read from local storage"
            ) from exc
    if len(result) != length:
        raise SchemaDriftError(f"{context} zip metadata is truncated")
    return result


class _FixedZipDescriptorView:
    """Seekable fixed-size view with immutable ZIP allocation metadata."""

    def __init__(
        self,
        descriptor: int,
        size: int,
        overlays: tuple[tuple[int, bytes], ...],
    ) -> None:
        self._descriptor = descriptor
        self._size = size
        self._overlays = overlays
        self._position = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            position = offset
        elif whence == os.SEEK_CUR:
            position = self._position + offset
        elif whence == os.SEEK_END:
            position = self._size + offset
        else:
            raise ValueError("invalid ZIP view seek mode")
        if position < 0:
            raise ValueError("negative ZIP view seek position")
        self._position = position
        return position

    def read(self, size: int = -1) -> bytes:
        if self._position >= self._size:
            return b""
        if size is None or size < 0:
            size = self._size - self._position
        else:
            size = min(size, self._size - self._position)
        if size > ZIP_MAX_VALIDATION_READ_BYTES:
            raise SchemaDriftError("ZIP validation requested an oversized in-memory read")
        start = self._position
        data = bytearray()
        try:
            while len(data) < size:
                chunk = os.pread(
                    self._descriptor,
                    size - len(data),
                    start + len(data),
                )
                if not chunk:
                    break
                data.extend(chunk)
        except OSError as exc:
            raise ValidationError(
                "ZIP source could not be read from local storage during validation"
            ) from exc
        end = start + len(data)
        for overlay_offset, overlay in self._overlays:
            overlay_end = overlay_offset + len(overlay)
            overlap_start = max(start, overlay_offset)
            overlap_end = min(end, overlay_end)
            if overlap_start < overlap_end:
                data[overlap_start - start : overlap_end - start] = overlay[
                    overlap_start - overlay_offset : overlap_end - overlay_offset
                ]
        self._position = end
        return bytes(data)


def _preflight_zip_central_directory(
    source: bytes | BinaryIO,
    archive_size: int,
    context: str,
) -> tuple[tuple[int, bytes], ...]:
    """Bound central-directory allocation before zipfile materializes entries."""

    eocd_size = 22
    max_comment_size = 65_535
    if archive_size < eocd_size:
        raise SchemaDriftError(f"{context} is not a valid zip archive")
    tail_size = min(archive_size, eocd_size + max_comment_size)
    tail_offset = archive_size - tail_size
    tail = _zip_read_exact_range(source, tail_offset, tail_size, context)
    search_end = len(tail)
    eocd_index = -1
    eocd_fields: tuple[int, ...] | None = None
    while search_end > 0:
        candidate = tail.rfind(b"PK\x05\x06", 0, search_end)
        if candidate < 0:
            break
        if candidate + eocd_size <= len(tail):
            fields = struct.unpack_from("<4s4H2LH", tail, candidate)
            comment_size = fields[-1]
            if candidate + eocd_size + comment_size == len(tail):
                eocd_index = candidate
                eocd_fields = fields[1:]
                break
        search_end = candidate
    if eocd_fields is None:
        raise SchemaDriftError(f"{context} is not a valid zip archive (missing end record)")

    (
        disk_number,
        directory_disk,
        entries_on_disk,
        entry_count,
        directory_size,
        directory_offset,
        _comment_size,
    ) = eocd_fields
    eocd_offset = tail_offset + eocd_index
    directory_end_limit = eocd_offset
    metadata_overlays: list[tuple[int, bytes]] = [(tail_offset, tail)]
    uses_zip64 = (
        entries_on_disk == 0xFFFF
        or entry_count == 0xFFFF
        or directory_size == 0xFFFFFFFF
        or directory_offset == 0xFFFFFFFF
    )
    if uses_zip64:
        locator_offset = eocd_offset - 20
        locator = _zip_read_exact_range(source, locator_offset, 20, context)
        metadata_overlays.append((locator_offset, locator))
        signature, zip64_disk, zip64_offset, total_disks = struct.unpack("<4sLQL", locator)
        if signature != b"PK\x06\x07" or zip64_disk != 0 or total_disks != 1:
            raise SchemaDriftError(f"{context} zip64 locator is invalid")
        zip64_record = _zip_read_exact_range(source, zip64_offset, 56, context)
        metadata_overlays.append((zip64_offset, zip64_record))
        (
            zip64_signature,
            zip64_record_size,
            _version_made,
            _version_needed,
            disk_number,
            directory_disk,
            entries_on_disk,
            entry_count,
            directory_size,
            directory_offset,
        ) = struct.unpack("<4sQ2H2L4Q", zip64_record)
        if (
            zip64_signature != b"PK\x06\x06"
            or zip64_record_size < 44
            or zip64_offset + 12 + zip64_record_size > locator_offset
        ):
            raise SchemaDriftError(f"{context} zip64 end record is invalid")
        directory_end_limit = zip64_offset
    if disk_number != 0 or directory_disk != 0 or entries_on_disk != entry_count:
        raise SchemaDriftError(f"{context} multi-disk zip archives are unsupported")
    if entry_count > ZIP_MAX_MEMBERS:
        raise SchemaDriftError(f"{context} exceeds the zip member-count limit")
    if directory_size > ZIP_MAX_CENTRAL_DIRECTORY_BYTES:
        raise SchemaDriftError(f"{context} exceeds the central-directory byte limit")
    if (
        directory_offset > archive_size
        or directory_size > archive_size - directory_offset
        or directory_offset + directory_size > directory_end_limit
        or directory_size > directory_end_limit
    ):
        raise SchemaDriftError(f"{context} zip central-directory bounds are invalid")

    directory_start = directory_end_limit - directory_size
    directory = _zip_read_exact_range(source, directory_start, directory_size, context)
    metadata_overlays.append((directory_start, directory))
    scan_offset = 0
    scan_end = len(directory)
    scanned_entries = 0
    while scan_offset < scan_end:
        if scan_end - scan_offset < 46:
            raise SchemaDriftError(f"{context} zip central-directory record is truncated")
        header = directory[scan_offset : scan_offset + 46]
        fields = struct.unpack("<4s6H3L5H2L", header)
        if fields[0] != b"PK\x01\x02":
            raise SchemaDriftError(f"{context} zip central-directory record is invalid")
        filename_size, extra_size, comment_size = fields[10:13]
        disk_start = fields[13]
        record_size = 46 + filename_size + extra_size + comment_size
        if disk_start != 0 or record_size > scan_end - scan_offset:
            raise SchemaDriftError(f"{context} zip central-directory record is invalid")
        scanned_entries += 1
        if scanned_entries > ZIP_MAX_MEMBERS:
            raise SchemaDriftError(f"{context} exceeds the zip member-count limit")
        scan_offset += record_size
    if scan_offset != scan_end:
        raise SchemaDriftError(f"{context} zip central-directory record is truncated")
    if scanned_entries != entry_count:
        raise SchemaDriftError(f"{context} zip entry count does not match the central directory")
    return tuple(metadata_overlays)


def _validate_zip_snapshot(
    source: bytes | BinaryIO,
    archive_size: int,
    context: str,
) -> str | None:
    if archive_size > ATLAS_BATCH_ARCHIVE_MAX_BYTES:
        raise SchemaDriftError(f"{context} exceeds the total archive byte limit")
    metadata_source: bytes | BinaryIO = source
    metadata_overlays = _preflight_zip_central_directory(
        metadata_source,
        archive_size,
        context,
    )
    if isinstance(source, bytes):
        zip_source: io.BytesIO | _FixedZipDescriptorView = io.BytesIO(source)
    else:
        zip_source = _FixedZipDescriptorView(
            source.fileno(),
            archive_size,
            metadata_overlays,
        )
    with zipfile.ZipFile(zip_source) as archive:
        members = archive.infolist()
        if not members or not any(not member.is_dir() for member in members):
            raise SchemaDriftError(f"{context} zip archive has no file members")
        if len(members) > ZIP_MAX_MEMBERS:
            raise SchemaDriftError(f"{context} exceeds the zip member-count limit")
        total_uncompressed = 0
        total_compressed = 0
        member_names: set[str] = set()
        for member in members:
            if member.filename in member_names:
                raise SchemaDriftError(f"{context} contains a duplicate zip member name")
            member_names.add(member.filename)
            if member.flag_bits & 0x1:
                raise SchemaDriftError(f"{context} contains an encrypted zip member")
            if member.compress_type not in ZIP_ALLOWED_COMPRESSION_METHODS:
                raise SchemaDriftError(f"{context} contains an unsupported zip compression method")
            if member.file_size > ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES:
                raise SchemaDriftError(f"{context} exceeds the per-member uncompressed zip limit")
            if member.file_size and member.compress_size == 0:
                raise SchemaDriftError(f"{context} exceeds the zip expansion-ratio limit")
            if (
                member.compress_size
                and member.file_size > member.compress_size * ZIP_MAX_EXPANSION_RATIO
            ):
                raise SchemaDriftError(f"{context} exceeds the zip expansion-ratio limit")
            total_uncompressed += member.file_size
            total_compressed += member.compress_size
            if total_uncompressed > ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise SchemaDriftError(f"{context} exceeds the aggregate uncompressed zip limit")
            if total_compressed > ZIP_MAX_TOTAL_COMPRESSED_BYTES:
                raise SchemaDriftError(f"{context} exceeds the aggregate compressed zip limit")
        return archive.testzip()


def _validate_zip(value: bytes | Path | BinaryIO, context: str) -> None:
    try:
        if isinstance(value, bytes):
            bad_member = _validate_zip_snapshot(value, len(value), context)
        else:
            close_handle = isinstance(value, Path)
            if close_handle:
                flags = os.O_RDONLY
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                if hasattr(os, "O_NONBLOCK"):
                    flags |= os.O_NONBLOCK
                descriptor = os.open(value, flags)
                try:
                    handle: BinaryIO = os.fdopen(descriptor, "rb")
                except BaseException:
                    os.close(descriptor)
                    raise
            else:
                handle = value
            try:
                before = os.fstat(handle.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise SchemaDriftError(f"{context} must be a regular file")
                archive_size = before.st_size
                if archive_size > ATLAS_BATCH_ARCHIVE_MAX_BYTES:
                    raise SchemaDriftError(f"{context} exceeds the total archive byte limit")
                validation_error: BaseException | None = None
                try:
                    bad_member = _validate_zip_snapshot(handle, archive_size, context)
                except BaseException as exc:
                    validation_error = exc
                after = os.fstat(handle.fileno())
                if _atlas_file_fingerprint(before) != _atlas_file_fingerprint(after):
                    raise SchemaDriftError(f"{context} changed during validation") from (
                        validation_error
                    )
                if validation_error is not None:
                    raise validation_error
            finally:
                if close_handle:
                    handle.close()
    except SchemaDriftError:
        raise
    except ValidationError:
        raise
    except MemoryError as exc:
        raise ValidationError("Atlas zip validation exhausted bounded local memory") from exc
    except OSError as exc:
        raise ValidationError(
            f"{context} could not be read from local storage during zip validation"
        ) from exc
    except (
        RuntimeError,
        NotImplementedError,
        UnicodeError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        zlib.error,
    ) as exc:
        raise SchemaDriftError(f"{context} is not a valid zip archive") from exc
    if bad_member is not None:
        raise SchemaDriftError(f"{context} has a corrupt zip member")


def _annotate_download_failure(
    error: BaseException,
    attempts: list[dict[str, Any]],
    resume_recovery: str | None,
) -> None:
    """Attach strict, capability-free transport context to a failed download."""

    safe_attempts: list[dict[str, Any]] = []
    for attempt in attempts:
        http_status = attempt.get("http_status")
        if (
            isinstance(http_status, bool)
            or not isinstance(http_status, int)
            or not 100 <= http_status <= 599
        ):
            http_status = None
        range_start = attempt.get("range_start")
        if isinstance(range_start, bool) or not isinstance(range_start, int) or range_start < 0:
            range_start = None
        outcome = attempt.get("outcome")
        if outcome not in _DOWNLOAD_ATTEMPT_OUTCOMES:
            outcome = "failed"
        safe_attempts.append(
            {
                "http_status": http_status,
                "range_start": range_start,
                "outcome": outcome,
            }
        )
    error.transport_attempts = safe_attempts
    error.resume_recovery = (
        resume_recovery if resume_recovery in _DOWNLOAD_RECOVERY_REASONS else None
    )


def _png_scanline_lengths(
    width: int,
    height: int,
    *,
    bit_depth: int,
    color_type: int,
    interlace: int,
) -> list[int]:
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    lengths: list[int] = []

    def append_pass(pass_width: int, pass_height: int) -> None:
        if pass_width <= 0 or pass_height <= 0:
            return
        row_length = 1 + (pass_width * channels * bit_depth + 7) // 8
        lengths.extend([row_length] * pass_height)

    if interlace == 0:
        append_pass(width, height)
        return lengths
    for x_start, y_start, x_step, y_step in (
        (0, 0, 8, 8),
        (4, 0, 8, 8),
        (0, 4, 4, 8),
        (2, 0, 4, 4),
        (0, 2, 2, 4),
        (1, 0, 2, 2),
        (0, 1, 1, 2),
    ):
        pass_width = 0 if width <= x_start else (width - x_start + x_step - 1) // x_step
        pass_height = 0 if height <= y_start else (height - y_start + y_step - 1) // y_step
        append_pass(pass_width, pass_height)
    return lengths


def _validate_png(value: bytes, context: str) -> None:
    diagnostic = {"size_bytes": len(value), "prefix_hex": value[:16].hex()}
    if not value.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SchemaDriftError(f"{context} is not a PNG", raw=diagnostic)
    offset = 8
    chunk_count = 0
    first_kind: bytes | None = None
    last_kind: bytes | None = None
    bit_depth: int | None = None
    color_type: int | None = None
    interlace: int | None = None
    scanline_lengths: list[int] = []
    expected_inflated_size = 0
    scanline_index = 0
    scanline_offset = 0
    inflated_size = 0
    idat_compressed_size = 0
    idat_started = False
    idat_ended = False
    plte_seen = False
    decompressor: Any | None = None
    view = memoryview(value)

    def consume_inflated(data: bytes) -> None:
        nonlocal inflated_size, scanline_index, scanline_offset
        position = 0
        while position < len(data):
            if scanline_index >= len(scanline_lengths):
                raise SchemaDriftError(
                    f"{context} PNG decompressed data exceeds its IHDR dimensions",
                    raw=diagnostic,
                )
            scanline_length = scanline_lengths[scanline_index]
            if scanline_offset == 0 and data[position] > 4:
                raise SchemaDriftError(
                    f"{context} PNG contains an invalid scanline filter",
                    raw=diagnostic,
                )
            consumed = min(scanline_length - scanline_offset, len(data) - position)
            position += consumed
            scanline_offset += consumed
            inflated_size += consumed
            if inflated_size > PNG_MAX_DECOMPRESSED_BYTES:
                raise SchemaDriftError(
                    f"{context} PNG exceeds the decompressed-byte limit",
                    raw=diagnostic,
                )
            if scanline_offset == scanline_length:
                scanline_index += 1
                scanline_offset = 0

    def consume_idat(payload: memoryview) -> None:
        if decompressor is None:  # pragma: no cover - guarded by first-chunk validation
            raise SchemaDriftError(f"{context} PNG IHDR is invalid", raw=diagnostic)
        pending: bytes | memoryview = payload
        while pending:
            remaining = expected_inflated_size - inflated_size
            output_limit = min(PNG_INFLATE_CHUNK_BYTES, remaining + 1)
            try:
                inflated = decompressor.decompress(pending, max_length=max(1, output_limit))
            except zlib.error as exc:
                raise SchemaDriftError(
                    f"{context} PNG IDAT stream is invalid",
                    raw=diagnostic,
                ) from exc
            consume_inflated(inflated)
            next_pending = decompressor.unconsumed_tail
            if decompressor.unused_data:
                raise SchemaDriftError(
                    f"{context} PNG IDAT stream has trailing data",
                    raw=diagnostic,
                )
            if not next_pending:
                break
            if len(next_pending) == len(pending) and not inflated:
                raise SchemaDriftError(
                    f"{context} PNG IDAT stream made no progress",
                    raw=diagnostic,
                )
            pending = next_pending

    while offset < len(value):
        if len(value) - offset < 12:
            raise SchemaDriftError(f"{context} PNG is truncated", raw=diagnostic)
        chunk_count += 1
        if chunk_count > PNG_MAX_CHUNKS:
            raise SchemaDriftError(f"{context} PNG exceeds the chunk-count limit", raw=diagnostic)
        length = struct.unpack(">I", value[offset : offset + 4])[0]
        payload_start = offset + 8
        payload_end = payload_start + length
        chunk_end = payload_end + 4
        if chunk_end > len(value):
            raise SchemaDriftError(f"{context} PNG is truncated", raw=diagnostic)
        kind = value[offset + 4 : offset + 8]
        if any(not (65 <= byte <= 90 or 97 <= byte <= 122) for byte in kind):
            raise SchemaDriftError(f"{context} PNG chunk type is invalid", raw=diagnostic)
        if kind[2] & 0x20:
            raise SchemaDriftError(f"{context} PNG reserved chunk bit is invalid", raw=diagnostic)
        expected_crc = struct.unpack(">I", value[payload_end:chunk_end])[0]
        observed_crc = binascii.crc32(kind)
        observed_crc = binascii.crc32(view[payload_start:payload_end], observed_crc) & 0xFFFFFFFF
        if observed_crc != expected_crc:
            raise SchemaDriftError(f"{context} PNG checksum is invalid", raw=diagnostic)
        if first_kind is None:
            first_kind = kind
            if kind != b"IHDR" or length != 13:
                raise SchemaDriftError(f"{context} PNG IHDR is invalid", raw=diagnostic)
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", view[payload_start:payload_end]
            )
            legal_depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if (
                width <= 0
                or height <= 0
                or width > PNG_MAX_DIMENSION
                or height > PNG_MAX_DIMENSION
                or width * height > PNG_MAX_PIXELS
                or color_type not in legal_depths
                or bit_depth not in legal_depths[color_type]
                or compression != 0
                or filtering != 0
                or interlace not in {0, 1}
            ):
                raise SchemaDriftError(f"{context} PNG IHDR is invalid", raw=diagnostic)
            scanline_lengths.extend(
                _png_scanline_lengths(
                    width,
                    height,
                    bit_depth=bit_depth,
                    color_type=color_type,
                    interlace=interlace,
                )
            )
            expected_inflated_size = sum(scanline_lengths)
            if expected_inflated_size > PNG_MAX_DECOMPRESSED_BYTES:
                raise SchemaDriftError(
                    f"{context} PNG exceeds the decompressed-byte limit",
                    raw=diagnostic,
                )
            decompressor = zlib.decompressobj()
        elif kind == b"IHDR":
            raise SchemaDriftError(f"{context} PNG contains duplicate IHDR", raw=diagnostic)
        if kind == b"PLTE":
            if plte_seen:
                raise SchemaDriftError(f"{context} PNG contains duplicate PLTE", raw=diagnostic)
            if idat_started:
                raise SchemaDriftError(
                    f"{context} PNG PLTE must precede IDAT",
                    raw=diagnostic,
                )
            if color_type in {0, 4}:
                raise SchemaDriftError(
                    f"{context} PNG PLTE is prohibited for grayscale color types",
                    raw=diagnostic,
                )
            palette_entries, remainder = divmod(length, 3)
            if remainder or not 1 <= palette_entries <= 256:
                raise SchemaDriftError(f"{context} PNG PLTE size is invalid", raw=diagnostic)
            if color_type == 3 and bit_depth is not None and palette_entries > 1 << bit_depth:
                raise SchemaDriftError(
                    f"{context} PNG PLTE has too many entries for indexed bit depth",
                    raw=diagnostic,
                )
            plte_seen = True
        if kind == b"IDAT":
            if color_type == 3 and not plte_seen:
                raise SchemaDriftError(
                    f"{context} indexed-color PNG requires PLTE before IDAT",
                    raw=diagnostic,
                )
            if idat_ended:
                raise SchemaDriftError(
                    f"{context} PNG IDAT chunks are not consecutive",
                    raw=diagnostic,
                )
            idat_started = True
            idat_compressed_size += length
            if idat_compressed_size > PNG_MAX_IDAT_COMPRESSED_BYTES:
                raise SchemaDriftError(
                    f"{context} PNG exceeds the compressed IDAT byte limit",
                    raw=diagnostic,
                )
            consume_idat(view[payload_start:payload_end])
        else:
            if idat_started and kind != b"IEND":
                idat_ended = True
            if kind not in {b"IHDR", b"PLTE", b"IEND"} and not kind[0] & 0x20:
                raise SchemaDriftError(
                    f"{context} PNG contains an unknown critical chunk",
                    raw=diagnostic,
                )
        last_kind = kind
        offset = chunk_end
        if kind == b"IEND":
            if length != 0:
                raise SchemaDriftError(f"{context} PNG structure is invalid", raw=diagnostic)
            break
    if (
        offset != len(value)
        or first_kind != b"IHDR"
        or last_kind != b"IEND"
        or bit_depth is None
        or color_type is None
        or interlace is None
        or (color_type == 3 and not plte_seen)
        or not idat_started
        or idat_compressed_size == 0
        or decompressor is None
        or not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
        or scanline_index != len(scanline_lengths)
        or scanline_offset != 0
    ):
        raise SchemaDriftError(f"{context} PNG structure is invalid", raw=diagnostic)


class AtlasClient:
    _supports_absolute_deadline = True

    def __init__(
        self,
        *,
        base_url: str = BIOHUB_BASE_URL,
        transport: Transport | None = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if self.base_url != BIOHUB_BASE_URL:
            raise ValidationError(
                "Atlas biological inputs can only be sent to the canonical Biohub host"
            )
        self.transport = transport or UrllibTransport()
        self._supports_synchronous_sink = isinstance(self.transport, UrllibTransport)
        self.timeout = validate_timeout(timeout, "Atlas request timeout")
        self.provider_calls: list[dict[str, Any]] = []
        self.last_raw_response: Any = None

    def _url(self, path: str, query: dict[str, Any] | None = None) -> str:
        url = f"{self.base_url}{ATLAS_API_PREFIX}{path}"
        if query:
            values: list[tuple[str, str]] = []
            for key, item in query.items():
                if item is None:
                    continue
                if isinstance(item, bool):
                    values.append((key, "true" if item else "false"))
                elif isinstance(item, list):
                    values.extend((key, str(element)) for element in item)
                else:
                    values.append((key, str(item)))
            url += "?" + urlencode(values)
        return url

    def _json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        call_parameters: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        expected: set[int] | None = None,
        deadline: float | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        self.last_raw_response = None
        deadline = _validate_deadline(deadline, "Atlas request")
        if expected is None:
            expected = {200}
        body = None if payload is None else encode_json_body(payload)
        headers = {"accept": "application/json"}
        if body is not None:
            headers["content-type"] = "application/json"
        request_timeout = self.timeout
        if deadline is not None:
            remaining = deadline - time.monotonic()
            _require_deadline(
                deadline,
                "Atlas request deadline expired before provider request",
            )
            request_timeout = min(request_timeout, remaining)
        request_arguments = {
            "headers": headers,
            "body": body,
            "timeout": request_timeout,
        }
        if deadline is not None and isinstance(self.transport, UrllibTransport):
            request_arguments["deadline"] = deadline
        started_at = utc_now()
        endpoint = self._url(path)
        response: HTTPResponse | None = None
        try:
            response = self.transport.request(
                method,
                self._url(path, query),
                **request_arguments,
            )
            _require_deadline(
                deadline,
                "Atlas request deadline expired after provider response",
                partial=bool(response.body),
            )
            raise_for_status(response, expected=expected)
            result = None if response.status == 204 or not response.body else decode_json(response)
            self.last_raw_response = result
        except BiohubESMError as exc:
            http_status = exc.status if isinstance(exc, APIError) else None
            if http_status is None:
                http_status = _validated_provider_status(getattr(exc, "provider_status", None))
            if http_status is None and response is not None:
                http_status = _validated_provider_status(response.status)
            _bind_provider_status(exc, http_status)
            if isinstance(exc, APIError):
                # JSON responses have no durable artifact until the command
                # publishes one. In-memory response bytes are not `partial`.
                exc.partial = False
            error_kind = getattr(exc, "kind", exc.__class__.__name__)
            indeterminate = isinstance(exc, APIError) and exc.operation_indeterminate
            call: dict[str, Any] = {
                "endpoint": endpoint,
                "method": method,
                "operation": path,
                "started_at": started_at,
                "finished_at": utc_now(),
                "outcome": "indeterminate" if indeterminate else "error",
                "error_kind": error_kind,
            }
            if isinstance(exc, APIError):
                call["partial"] = exc.partial
                call["response_body_partial"] = exc.response_body_partial
                call["operation_indeterminate"] = exc.operation_indeterminate
                if exc.retry_after is not None:
                    call["retry_after"] = exc.retry_after
            if http_status is not None:
                call["http_status"] = http_status
            if call_parameters is not None:
                call["parameters"] = dict(call_parameters)
            self.provider_calls.append(call)
            raise
        call = {
            "endpoint": endpoint,
            "method": method,
            "operation": path,
            "http_status": response.status,
            "started_at": started_at,
            "finished_at": utc_now(),
            "outcome": "success",
        }
        if call_parameters is not None:
            call["parameters"] = dict(call_parameters)
        self.provider_calls.append(call)
        return response.status, result, response.headers

    @_preserve_full_json_response
    def search(
        self,
        sequence: str,
        *,
        topk_results: int = 10,
        topk_features: int = 20,
        min_similarity: float = 0.5,
        cluster_pct_characterized_max: int | None = None,
        include_cluster_info: bool = False,
    ) -> dict[str, Any]:
        normalized = validate_atlas_search_sequence(sequence)
        _integer_in_range("topk_results", topk_results, 1, 100)
        _integer_in_range("topk_features", topk_features, 1, 100)
        if (
            isinstance(min_similarity, bool)
            or not isinstance(min_similarity, (int, float))
            or not math.isfinite(min_similarity)
            or not 0 <= min_similarity <= 1
        ):
            raise ValidationError("Atlas min_similarity must be between 0 and 1")
        if cluster_pct_characterized_max is not None:
            _integer_in_range(
                "cluster_pct_characterized_max",
                cluster_pct_characterized_max,
                0,
                100,
            )
        _boolean("include_cluster_info", include_cluster_info)
        _, raw, _ = self._json(
            "GET",
            "/similarity-search",
            query={
                "sequence": normalized,
                "topk_results": topk_results,
                "topk_features": topk_features,
                "min_similarity": min_similarity,
                "cluster_pct_characterized_max": cluster_pct_characterized_max,
                "include_cluster_info": include_cluster_info,
            },
        )
        result = _require_object(raw, "similarity-search")
        _require_keys(result, "similarity-search", {"query_sequence", "similar_proteins"})
        if result["query_sequence"] != normalized:
            raise SchemaDriftError(
                "Atlas similarity-search query_sequence does not match the request",
                raw=result,
            )
        hits = result["similar_proteins"]
        if not isinstance(hits, list):
            raise SchemaDriftError(
                "Atlas similarity-search similar_proteins must be a list", raw=result
            )
        if len(hits) > topk_results:
            raise SchemaDriftError(
                "Atlas similarity-search returned more hits than requested by topk_results",
                raw=result,
            )
        if "protein_hash" in result:
            query_hash = result["protein_hash"]
            _require_response_md5(
                query_hash,
                "similarity-search protein_hash",
                allow_none=True,
            )
            if query_hash is not None and query_hash != sequence_md5(
                normalized,
                provider="atlas",
            ):
                raise SchemaDriftError(
                    "Atlas similarity-search protein_hash does not match the query sequence",
                    raw=result,
                )
        seen_hashes: set[str] = set()
        previous_similarity: float | int | None = None
        for index, hit in enumerate(hits):
            if not isinstance(hit, dict):
                raise SchemaDriftError(
                    f"Atlas similarity-search hit {index} must be an object", raw=result
                )
            _require_keys(
                hit,
                f"similarity-search hit {index}",
                {
                    "protein_hash",
                    "protein_accession",
                    "sequence_length",
                    "similarity_score",
                },
            )
            protein_hash = hit["protein_hash"]
            _require_response_md5(protein_hash, f"similarity-search hit {index} hash")
            if protein_hash in seen_hashes:
                raise SchemaDriftError(
                    "Atlas similarity-search protein_hash values must be unique",
                    raw=result,
                )
            seen_hashes.add(protein_hash)

            accession = hit["protein_accession"]
            if not isinstance(accession, str) or not accession.strip():
                raise SchemaDriftError(
                    f"Atlas similarity-search hit {index} protein_accession must be non-empty",
                    raw=result,
                )
            sequence_length = hit["sequence_length"]
            try:
                _require_integer(
                    sequence_length,
                    f"similarity-search hit {index} sequence_length",
                    minimum=1,
                )
            except SchemaDriftError as exc:
                raise SchemaDriftError(
                    f"Atlas similarity-search hit {index} sequence_length must be a positive integer",
                    raw=result,
                ) from exc

            similarity = hit["similarity_score"]
            _require_bounded_number(
                similarity,
                f"similarity-search hit {index} similarity_score",
                0.0,
                1.0,
            )
            if similarity < min_similarity:
                raise SchemaDriftError(
                    "Atlas similarity-search returned a hit below min_similarity",
                    raw=result,
                )
            if previous_similarity is not None and similarity > previous_similarity:
                raise SchemaDriftError(
                    "Atlas similarity-search hits must be ordered by nonincreasing similarity",
                    raw=result,
                )
            previous_similarity = similarity
            _validate_optional_structure_fields(hit, f"similarity-search hit {index}")
            cluster_size = hit.get("cluster_size")
            if cluster_size is not None:
                _require_integer(
                    cluster_size,
                    f"similarity-search hit {index} cluster_size",
                    minimum=0,
                )
            protein_name = hit.get("protein_name")
            if protein_name is not None:
                _require_string(
                    protein_name,
                    f"similarity-search hit {index} protein_name",
                )
            residue_confidence = hit.get("residues_plddt")
            if isinstance(residue_confidence, list) and len(residue_confidence) != sequence_length:
                raise SchemaDriftError(
                    f"Atlas similarity-search hit {index} residues_plddt length "
                    "does not match sequence_length",
                    raw=result,
                )
        shared_features = result.get("top_features_across_results", [])
        if not isinstance(shared_features, list):
            raise SchemaDriftError(
                "Atlas similarity-search top_features_across_results must be a list",
                raw=result,
            )
        if len(shared_features) > topk_features:
            raise SchemaDriftError(
                "Atlas similarity-search returned more feature summaries than requested "
                "by topk_features",
                raw=result,
            )
        shared_feature_indices: set[int] = set()
        for index, feature in enumerate(shared_features):
            _validate_search_feature_summary(
                feature,
                f"similarity-search top_features_across_results entry {index}",
            )
            feature_index = feature["feature_index"]
            if feature_index in shared_feature_indices:
                raise SchemaDriftError(
                    "Atlas similarity-search feature summary indices must be unique",
                    raw=result,
                )
            shared_feature_indices.add(feature_index)
        restricted_count = result.get("restricted_count", 0)
        _require_integer(
            restricted_count,
            "similarity-search restricted_count",
            minimum=0,
        )
        return result

    @_preserve_full_json_response
    def protein(
        self,
        protein_hash: str,
        *,
        topk_features: int = 10,
        fold_on_miss: bool = False,
        normalize_features: bool = True,
        feature_indices: list[int] | None = None,
    ) -> dict[str, Any]:
        digest = validate_md5(protein_hash)
        _boolean("fold_on_miss", fold_on_miss)
        _integer_in_range("topk_features", topk_features, 1, 100)
        _boolean("normalize_features", normalize_features)
        indices = None
        if feature_indices is not None:
            if not feature_indices:
                raise ValidationError("feature_indices must contain at least one entry")
            if len(feature_indices) > 100:
                raise ValidationError("feature_indices is capped at 100 entries")
            if any(
                isinstance(index, bool) or not isinstance(index, int) for index in feature_indices
            ):
                raise ValidationError("feature_indices entries must be integers")
            # Atlas explicitly skips indices outside the catalog. Preserve the
            # caller's order and values instead of narrowing that wire contract.
            indices = list(feature_indices)
        query = {
            "topk_features": topk_features,
            "fold_on_miss": False,
            "normalize_features": normalize_features,
            "feature_indices": indices,
        }
        _, raw, _ = self._json(
            "GET",
            f"/proteins/{digest}",
            query=query,
            call_parameters=query,
        )
        result = _validate_protein_response(
            raw,
            digest=digest,
            requested_indices=indices,
            topk_features=topk_features,
        )
        if not fold_on_miss or (isinstance(result.get("pdb"), str) and result["pdb"].strip()):
            return result

        _validate_fold_on_miss_preflight(result, digest=digest)
        query["fold_on_miss"] = True
        _, raw, _ = self._json(
            "GET",
            f"/proteins/{digest}",
            query=query,
            call_parameters=query,
        )
        folded_result = _validate_protein_response(
            raw,
            digest=digest,
            requested_indices=indices,
            topk_features=topk_features,
        )
        if not isinstance(folded_result.get("pdb"), str) or not folded_result["pdb"].strip():
            raise SchemaDriftError(
                "Atlas fold-on-miss response is missing the requested structure",
                raw=folded_result,
            )
        return folded_result

    @_preserve_full_json_response
    def cluster(self, protein_hash: str, *, topk_features: int = 10) -> dict[str, Any]:
        digest = validate_md5(protein_hash)
        _integer_in_range("topk_features", topk_features, 1, 100)
        _, raw, _ = self._json("GET", f"/clusters/{digest}", query={"topk_features": topk_features})
        result = _require_object(raw, "cluster")
        _require_keys(
            result,
            "cluster",
            {
                "protein_hash",
                "cluster_size",
                "cluster_pct_characterized",
                "cluster_mean_domain_coverage",
                "member_protein_hashes",
            },
        )
        if result["protein_hash"] != digest:
            raise SchemaDriftError(
                "Atlas cluster response hash does not match the request", raw=result
            )
        cluster_size = result["cluster_size"]
        if isinstance(cluster_size, bool) or not isinstance(cluster_size, int) or cluster_size < 0:
            raise SchemaDriftError("Atlas cluster_size must be a nonnegative integer", raw=result)
        if not isinstance(result["member_protein_hashes"], list):
            raise SchemaDriftError("Atlas cluster member_protein_hashes must be a list", raw=result)
        member_hashes = result["member_protein_hashes"]
        if any(
            not isinstance(member, str)
            or member != member.lower()
            or not re.fullmatch(r"[0-9a-f]{32}", member)
            for member in member_hashes
        ):
            raise SchemaDriftError("Atlas cluster member hashes are invalid", raw=result)
        if len(set(member_hashes)) != len(member_hashes):
            raise SchemaDriftError("Atlas cluster member hashes must be unique", raw=result)
        if len(member_hashes) > cluster_size:
            raise SchemaDriftError(
                "Atlas cluster returned more member hashes than cluster_size",
                raw=result,
            )
        _require_integer(
            result["cluster_pct_characterized"],
            "cluster cluster_pct_characterized",
            minimum=0,
            maximum=100,
        )
        _require_finite_number(
            result["cluster_mean_domain_coverage"],
            "cluster cluster_mean_domain_coverage",
        )
        _validate_optional_structure_fields(result, "cluster response")
        _validate_optional_strings(
            result,
            ("protein_name", "source", "accession"),
            "cluster response",
        )
        domains = result.get("cluster_top_pfam_domains")
        if domains is not None:
            if not isinstance(domains, dict):
                raise SchemaDriftError(
                    "Atlas cluster_top_pfam_domains must be an object or null",
                    raw=result,
                )
            for accession, value in domains.items():
                _require_string(accession, "cluster Pfam accession", nonempty=True)
                domain = _require_object(value, f"cluster Pfam {accession}")
                _require_keys(domain, f"cluster Pfam {accession}", {"count", "name"})
                _require_integer(
                    domain["count"],
                    f"cluster Pfam {accession} count",
                    minimum=0,
                )
                _require_string(domain["name"], f"cluster Pfam {accession} name")
        features = result.get("cluster_representative_features", [])
        if not isinstance(features, list):
            raise SchemaDriftError(
                "Atlas cluster_representative_features must be a list",
                raw=result,
            )
        if len(features) > topk_features:
            raise SchemaDriftError(
                "Atlas cluster returned more representative features than requested "
                "by topk_features",
                raw=result,
            )
        feature_indices: set[int] = set()
        for index, feature in enumerate(features):
            _validate_sae_feature_response(
                feature,
                f"cluster representative feature entry {index}",
            )
            feature_index = feature["feature_index"]
            if feature_index in feature_indices:
                raise SchemaDriftError(
                    "Atlas cluster representative feature indices must be unique",
                    raw=result,
                )
            feature_indices.add(feature_index)
        taxonomy = result.get("cluster_taxonomy_info")
        if taxonomy is not None:
            taxonomy = _require_object(taxonomy, "cluster taxonomy")
            _require_keys(taxonomy, "cluster taxonomy", {"rank", "name"})
            _require_string(taxonomy["rank"], "cluster taxonomy rank")
            _require_string(taxonomy["name"], "cluster taxonomy name")
        top_phyla = result.get("top_phyla")
        if top_phyla is not None:
            if not isinstance(top_phyla, dict):
                raise SchemaDriftError(
                    "Atlas cluster top_phyla must be an object or null", raw=result
                )
            for name, count in top_phyla.items():
                _require_string(name, "cluster top_phyla name", nonempty=True)
                _require_integer(count, f"cluster top_phyla {name} count", minimum=0)
        return result

    @_preserve_full_json_response
    def features(self) -> dict[str, Any]:
        _, raw, _ = self._json("GET", "/features")
        result = _require_object(raw, "features")
        _require_keys(result, "features", {"data"})
        entries = result["data"]
        if not isinstance(entries, list):
            raise SchemaDriftError("Atlas features data must be a list", raw=result)
        if len(entries) != ATLAS_FEATURE_COUNT:
            raise SchemaDriftError(
                "Atlas features data must contain the documented 16,384 entries",
                raw=result,
            )
        seen_indices: set[int] = set()
        for position, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise SchemaDriftError(
                    f"Atlas features entry {position} must be an object", raw=result
                )
            _require_keys(
                entry,
                f"features entry {position}",
                {"feature_index", "label", "description"},
            )
            try:
                validate_feature_index(entry["feature_index"])
            except ValidationError as exc:
                raise SchemaDriftError(
                    f"Atlas features entry {position} has an invalid feature_index", raw=result
                ) from exc
            if entry["feature_index"] in seen_indices:
                raise SchemaDriftError(
                    "Atlas features data contains a duplicate feature_index",
                    raw=result,
                )
            seen_indices.add(entry["feature_index"])
            for field in ("label", "description"):
                if not isinstance(entry[field], str):
                    raise SchemaDriftError(
                        f"Atlas features entry {position} {field} must be a string",
                        raw=result,
                    )
        if seen_indices != set(range(ATLAS_FEATURE_COUNT)):
            raise SchemaDriftError(
                "Atlas features data does not cover feature indices 0 through 16,383",
                raw=result,
            )
        return result

    @_preserve_full_json_response
    def feature(self, feature_index: int) -> dict[str, Any]:
        index = validate_feature_index(feature_index)
        _, raw, _ = self._json("GET", f"/features/{index}")
        result = _require_object(raw, "feature")
        _require_keys(
            result,
            "feature",
            {
                "feature_index",
                "label",
                "summary",
                "description",
                "uniref90_frequency",
                "uniref90_idf",
                "uniref90_max_activation",
                "threshold",
            },
        )
        if (
            isinstance(result["feature_index"], bool)
            or not isinstance(result["feature_index"], int)
            or result["feature_index"] != index
        ):
            raise SchemaDriftError(
                "Atlas feature response index does not match the request", raw=result
            )
        for field in ("label", "summary", "description"):
            _require_string(result[field], f"feature {field}")
        _require_integer(
            result["uniref90_frequency"],
            "feature uniref90_frequency",
            minimum=0,
        )
        for field in ("uniref90_idf", "uniref90_max_activation", "threshold"):
            _require_finite_number(result[field], f"feature {field}")
        _validate_optional_strings(
            result,
            ("activation_pattern", "category", "exemplar_protein_families"),
            "feature",
        )
        for field, id_field in (
            ("top_100_uniref_ids", "uniref_id"),
            ("top_swissprot_activations", "uniprot_id"),
        ):
            entries = result.get(field, [])
            if not isinstance(entries, list):
                raise SchemaDriftError(f"Atlas feature {field} must be a list", raw=result)
            for position, item in enumerate(entries):
                item_context = f"feature {field} entry {position}"
                item = _require_object(item, item_context)
                _require_keys(item, item_context, {id_field, "activation"})
                _require_string(item[id_field], f"{item_context} {id_field}")
                _require_finite_number(item["activation"], f"{item_context} activation")
        neighbors = result.get("decoder_nearest_neighbors", [])
        if not isinstance(neighbors, list):
            raise SchemaDriftError(
                "Atlas feature decoder_nearest_neighbors must be a list",
                raw=result,
            )
        for position, neighbor in enumerate(neighbors):
            try:
                validate_feature_index(neighbor)
            except ValidationError as exc:
                raise SchemaDriftError(
                    f"Atlas feature decoder neighbor {position} is invalid",
                    raw=result,
                ) from exc
        return result

    def thumbnail(self, protein_hash: str, thumbnail_type: str) -> HTTPResponse:
        digest = validate_md5(protein_hash)
        if thumbnail_type not in {"pct-characterized", "plddt"}:
            raise ValidationError("thumbnail_type must be pct-characterized or plddt")
        path = f"/proteins/{digest}/thumbnail/{thumbnail_type}"
        endpoint = self._url(path)
        started_at = utc_now()
        response: HTTPResponse | None = None
        try:
            response = self.transport.request(
                "GET",
                endpoint,
                headers={"accept": "image/png"},
                timeout=self.timeout,
            )
            raise_for_status(response, expected={200})
        except BiohubESMError as exc:
            http_status = exc.status if isinstance(exc, APIError) else None
            if http_status is None:
                http_status = _validated_provider_status(getattr(exc, "provider_status", None))
            if http_status is None and response is not None:
                http_status = _validated_provider_status(response.status)
            _bind_provider_status(exc, http_status)
            if isinstance(exc, APIError):
                # Thumbnail bytes are still in memory; no artifact has been
                # published at this layer.
                exc.partial = False
            error_kind = getattr(exc, "kind", exc.__class__.__name__)
            indeterminate = isinstance(exc, APIError) and exc.operation_indeterminate
            call: dict[str, Any] = {
                "endpoint": endpoint,
                "method": "GET",
                "operation": path,
                "started_at": started_at,
                "finished_at": utc_now(),
                "outcome": "indeterminate" if indeterminate else "error",
                "error_kind": error_kind,
            }
            if isinstance(exc, APIError):
                call["partial"] = exc.partial
                call["response_body_partial"] = exc.response_body_partial
                call["operation_indeterminate"] = exc.operation_indeterminate
                if exc.retry_after is not None:
                    call["retry_after"] = exc.retry_after
            if http_status is not None:
                call["http_status"] = http_status
            self.provider_calls.append(call)
            raise
        self.provider_calls.append(
            {
                "endpoint": endpoint,
                "method": "GET",
                "operation": path,
                "http_status": response.status,
                "started_at": started_at,
                "finished_at": utc_now(),
                "outcome": "success",
            }
        )
        content_type = next(
            (value for key, value in response.headers.items() if key.lower() == "content-type"),
            None,
        )
        if (
            content_type is not None
            and content_type.split(";", 1)[0].strip().lower() != "image/png"
        ):
            raise SchemaDriftError(
                "Atlas thumbnail response Content-Type must be image/png",
                raw={"content_type": content_type},
            )
        _validate_png(response.body, "Atlas thumbnail response")
        return response

    @_preserve_full_json_response
    def submit_batch(
        self,
        protein_hashes: list[str],
        *,
        topk_features: int = 10,
        include_structure: bool = True,
        include_cluster_info: bool = True,
        include_sequence: bool = True,
        include_features: bool | dict[str, bool] | None = None,
        synchronous_sink: BinaryIO | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        self.last_raw_response = None
        hashes = validate_batch_hashes(protein_hashes)
        _integer_in_range("topk_features", topk_features, 1, 100)
        _boolean("include_structure", include_structure)
        _boolean("include_cluster_info", include_cluster_info)
        _boolean("include_sequence", include_sequence)
        if include_features is None:
            feature_options: bool | dict[str, bool] = {
                "protein_level": True,
                "per_residue": True,
            }
        elif isinstance(include_features, bool):
            feature_options = include_features
        elif isinstance(include_features, dict):
            unknown = set(include_features) - {"protein_level", "per_residue"}
            if unknown or any(not isinstance(value, bool) for value in include_features.values()):
                raise ValidationError(
                    "include_features accepts only boolean protein_level and per_residue fields"
                )
            # Both keys are optional and default true in Atlas. Preserve a
            # partial object exactly so the provider applies its own defaults.
            feature_options = dict(include_features)
        else:
            raise ValidationError("include_features must be boolean or an object")
        payload = {
            "protein_hashes": hashes,
            "topk_features": topk_features,
            "include_structure": include_structure,
            "include_cluster_info": include_cluster_info,
            "include_sequence": include_sequence,
            "include_features": feature_options,
        }
        endpoint = self._url("/proteins/batch")
        if synchronous_sink is not None and not self._supports_synchronous_sink:
            raise ValidationError("synchronous_sink requires the built-in streaming transport")
        archive_sink = synchronous_sink
        owns_archive_sink = False
        if isinstance(self.transport, UrllibTransport) and archive_sink is None:
            try:
                archive_sink = tempfile.TemporaryFile(mode="w+b")
            except OSError as exc:
                raise ValidationError(
                    "Atlas synchronous response spool could not be created"
                ) from exc
            owns_archive_sink = True
        started_at = utc_now()
        response: HTTPResponse | None = None
        try:
            request_headers = {
                "accept": "application/json, application/zip",
                "content-type": "application/json",
            }
            request_body = encode_json_body(payload)
            if isinstance(self.transport, UrllibTransport):
                if archive_sink is None:  # pragma: no cover - preflight invariant
                    raise ValidationError("Atlas synchronous response spool is unavailable")
                response = self.transport.request_stream_status_to(
                    "POST",
                    endpoint,
                    archive_sink,
                    stream_status=200,
                    max_stream_bytes=ATLAS_BATCH_ARCHIVE_MAX_BYTES,
                    headers=request_headers,
                    body=request_body,
                    timeout=self.timeout,
                )
            else:
                response = self.transport.request(
                    "POST",
                    endpoint,
                    headers=request_headers,
                    body=request_body,
                    timeout=self.timeout,
                )
            status = response.status
            if status == 200:
                if archive_sink is None:
                    _validate_zip(response.body, "Atlas synchronous batch response")
                    raw: Any = response.body
                else:
                    before = os.fstat(archive_sink.fileno())
                    _validate_zip(archive_sink, "Atlas synchronous batch response")
                    digest, _ = _atlas_descriptor_snapshot_exact(
                        archive_sink.fileno(),
                        expected_size=before.st_size,
                        capture=False,
                        changed_message=(
                            "Atlas synchronous batch response changed during validation"
                        ),
                    )
                    after = os.fstat(archive_sink.fileno())
                    if _atlas_file_fingerprint(before) != _atlas_file_fingerprint(after):
                        raise ValidationError(
                            "Atlas synchronous batch response changed during validation"
                        )
                    archive_sink.seek(0)
                    raw = AtlasBatchArchive(
                        handle=archive_sink,
                        size_bytes=after.st_size,
                        sha256=digest,
                    )
                    archive_sink = None
            else:
                raise_for_status(response, expected={202})
                raw = decode_json(response)
                self.last_raw_response = raw
                result = _require_object(raw, "batch submit")
                _require_keys(result, "batch submit", {"status", "job_id"})
                try:
                    validate_job_id(result["job_id"])
                except ValidationError as exc:
                    raise SchemaDriftError(
                        "Atlas batch submit job_id is invalid", raw=result
                    ) from exc
                if result["status"] != "pending":
                    raise SchemaDriftError("Atlas batch submit status must be pending", raw=result)
        except BiohubESMError as exc:
            http_status = exc.status if isinstance(exc, APIError) else None
            if http_status is None:
                http_status = _validated_provider_status(getattr(exc, "provider_status", None))
            if http_status is None and response is not None:
                http_status = _validated_provider_status(response.status)
            _bind_provider_status(exc, http_status)
            if isinstance(exc, APIError) and owns_archive_sink:
                # The built-in synchronous spool is anonymous and is closed in
                # this frame, so its bytes are not a retained partial artifact.
                exc.partial = False
            indeterminate = isinstance(exc, APIError) and exc.operation_indeterminate
            call: dict[str, Any] = {
                "endpoint": endpoint,
                "method": "POST",
                "operation": "/proteins/batch",
                "started_at": started_at,
                "finished_at": utc_now(),
                "outcome": "indeterminate" if indeterminate else "error",
                "error_kind": getattr(exc, "kind", exc.__class__.__name__),
            }
            if http_status is not None:
                call["http_status"] = http_status
            if isinstance(exc, APIError):
                call["partial"] = exc.partial
                call["response_body_partial"] = exc.response_body_partial
                call["operation_indeterminate"] = exc.operation_indeterminate
                if exc.retry_after is not None:
                    call["retry_after"] = exc.retry_after
            self.provider_calls.append(call)
            raise
        finally:
            if archive_sink is not None and owns_archive_sink:
                try:
                    archive_sink.close()
                except (OSError, ValueError):
                    # This owned spool is either unused for a validated 202
                    # response or already secondary to an active failure. Its
                    # close error must not erase provider acceptance/certainty.
                    pass
        self.provider_calls.append(
            {
                "endpoint": endpoint,
                "method": "POST",
                "operation": "/proteins/batch",
                "http_status": response.status,
                "started_at": started_at,
                "finished_at": utc_now(),
                "outcome": "success",
            }
        )
        return status, raw, response.headers

    @_preserve_full_json_response
    def batch_status(
        self,
        job_id: str,
        *,
        deadline: float | None = None,
    ) -> tuple[int, dict[str, Any]]:
        job_id = validate_job_id(job_id)
        status, raw, _ = self._json(
            "GET",
            f"/proteins/batch/jobs/{job_id}",
            expected={200, 202, 410},
            deadline=deadline,
        )
        if status == 410:
            if raw is not None and not isinstance(raw, dict):
                raise SchemaDriftError("Atlas expired batch response must be an object", raw=raw)
            expired = dict(raw) if isinstance(raw, dict) else {}
            if expired.get("job_id") is not None:
                returned_job_id = expired["job_id"]
                try:
                    validate_job_id(returned_job_id)
                except ValidationError as exc:
                    raise SchemaDriftError(
                        "Atlas expired batch job_id is invalid", raw=expired
                    ) from exc
                if returned_job_id != job_id:
                    raise SchemaDriftError(
                        "Atlas expired batch returned a different job_id", raw=expired
                    )
            expired.update({"status": "expired", "job_id": job_id})
            return status, expired
        result = _require_object(raw, "batch status")
        _require_keys(result, "batch status", {"status"})
        returned_job_id = result.get("job_id")
        if returned_job_id is not None:
            if not isinstance(returned_job_id, str) or not JOB_ID_RE.fullmatch(returned_job_id):
                raise SchemaDriftError("Atlas batch status job_id is invalid", raw=result)
            if returned_job_id != job_id:
                raise SchemaDriftError("Atlas batch status returned a different job_id", raw=result)
        # BatchProteinResponse makes job_id nullable/optional. The request path
        # is authoritative when the response omits it, so bind that known ID in
        # the normalized result while retaining the original in last_raw_response.
        result = dict(result)
        result["job_id"] = job_id
        if result["status"] not in {"pending", "completed", "cancelled", "failed", "expired"}:
            raise SchemaDriftError(
                f"Atlas batch status is unknown: {result['status']!r}", raw=result
            )
        if status == 202 and result["status"] != "pending":
            raise SchemaDriftError(
                "Atlas HTTP 202 batch status must be pending",
                raw=result,
            )
        if status == 200 and result["status"] == "pending":
            raise SchemaDriftError(
                "Atlas pending batch status must use HTTP 202",
                raw=result,
            )
        for field in ("completed_count", "total_count"):
            value = result.get(field)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise SchemaDriftError(
                    f"Atlas batch status {field} must be a nonnegative integer",
                    raw=result,
                )
        if (
            isinstance(result.get("completed_count"), int)
            and isinstance(result.get("total_count"), int)
            and result["completed_count"] > result["total_count"]
        ):
            raise SchemaDriftError("Atlas batch completed_count exceeds total_count", raw=result)
        download_url = result.get("download_url")
        if result["status"] == "completed" and download_url is None:
            raise SchemaDriftError(
                "Atlas completed batch is missing a valid HTTPS download_url", raw=result
            )
        if download_url is not None:
            try:
                safe_download_endpoint(download_url)
            except ValidationError as exc:
                raise SchemaDriftError("Atlas batch download_url is invalid", raw=result) from exc
        for field in ("poll_url", "created_at"):
            value = result.get(field)
            if value is not None and not isinstance(value, str):
                raise SchemaDriftError(
                    f"Atlas batch status {field} must be a string or null",
                    raw=result,
                )
        return status, result

    def cancel_batch(self, job_id: str) -> None:
        job_id = validate_job_id(job_id)
        self._json("DELETE", f"/proteins/batch/jobs/{job_id}", expected={204})

    def wait_for_batch(
        self,
        job_id: str,
        *,
        poll_interval: float = 5.0,
        timeout: float = DEFAULT_POLL_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        poll_interval = validate_timeout(poll_interval, "Atlas batch poll interval")
        timeout = validate_timeout(timeout, "Atlas batch poll timeout")
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise APIError(status=None, kind="timeout", message="Atlas batch polling timed out")
            _, result = self.batch_status(job_id, deadline=deadline)
            if result["status"] != "pending":
                return result
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise APIError(status=None, kind="timeout", message="Atlas batch polling timed out")
            time.sleep(min(poll_interval, remaining))

    def download(
        self,
        url: str,
        destination: Path,
        *,
        resume: bool = True,
        deadline: float | None = None,
        expected_partial_identity: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        deadline = _validate_deadline(deadline, "Atlas download")
        attempts: list[dict[str, Any]] = []
        failure_context: dict[str, str | None] = {"resume_recovery": None}
        observed_partial_identity = [expected_partial_identity]
        try:
            return self._download(
                url,
                destination,
                resume=resume,
                deadline=deadline,
                attempts=attempts,
                failure_context=failure_context,
                expected_partial_identity=expected_partial_identity,
                observed_partial_identity=observed_partial_identity,
            )
        except BaseException as error:
            partial = destination.with_suffix(destination.suffix + ".partial")
            partial_output_present = False
            identity = observed_partial_identity[0]
            if identity is not None:
                try:
                    partial_output_present = _require_atlas_partial_identity(partial, identity) > 0
                except ValidationError:
                    pass
            error.partial = partial_output_present
            if attempts:
                _annotate_download_failure(
                    error,
                    attempts,
                    failure_context["resume_recovery"],
                )
            raise

    def _download(
        self,
        url: str,
        destination: Path,
        *,
        resume: bool,
        deadline: float | None,
        attempts: list[dict[str, Any]],
        failure_context: dict[str, str | None],
        expected_partial_identity: tuple[int, int] | None,
        observed_partial_identity: list[tuple[int, int] | None],
    ) -> dict[str, Any]:
        safe_download_endpoint(url)
        if destination.exists() or destination.is_symlink():
            raise ValidationError(f"refusing to overwrite an existing artifact: {destination}")
        partial = destination.with_suffix(destination.suffix + ".partial")
        partial_identity, partial_size = _open_atlas_partial(
            partial,
            expected_identity=expected_partial_identity,
        )
        observed_partial_identity[0] = partial_identity
        headers: dict[str, str] = {}
        resume_recovery: str | None = None
        validated_download_record: dict[str, Any] | None = None
        offset = partial_size if resume else 0
        if offset:
            try:
                _validate_zip(partial, "Atlas completed partial batch download")
            except SchemaDriftError:
                headers["range"] = f"bytes={offset}-"
            else:
                # A syntactically complete partial is not bound to this job or
                # signed URL. Replace it with a fresh full response rather than
                # publishing potentially stale bytes.
                offset = 0

        def partial_output_present() -> bool:
            try:
                return _require_atlas_partial_identity(partial, partial_identity) > 0
            except ValidationError:
                return False

        def fetch(request_headers: dict[str, str], expected_offset: int) -> HTTPResponse:
            request_timeout = self.timeout
            if deadline is not None:
                remaining = deadline - time.monotonic()
                _require_deadline(
                    deadline,
                    "Atlas batch download deadline expired before provider request",
                    partial=partial_output_present(),
                )
                request_timeout = min(request_timeout, remaining)
            attempt = {
                "http_status": None,
                "range_start": expected_offset if "range" in request_headers else None,
                "outcome": "failed",
            }
            attempts.append(attempt)
            response: HTTPResponse | None = None
            try:
                stream_to = getattr(self.transport, "stream_to", None)
                if callable(stream_to):
                    stream_arguments = {
                        "headers": request_headers,
                        "timeout": request_timeout,
                        "append_on_partial": bool(expected_offset),
                        "expected_offset": expected_offset,
                    }
                    if isinstance(self.transport, UrllibTransport):
                        stream_arguments["max_total_bytes"] = ATLAS_BATCH_ARCHIVE_MAX_BYTES
                        stream_arguments["expected_destination_identity"] = partial_identity
                        if deadline is not None:
                            stream_arguments["deadline"] = deadline
                    response = stream_to("GET", url, partial, **stream_arguments)
                    attempt["http_status"] = _validated_provider_status(response.status)
                    archive_size = _require_atlas_partial_identity(partial, partial_identity)
                    if archive_size > ATLAS_BATCH_ARCHIVE_MAX_BYTES:
                        raise SchemaDriftError(
                            "Atlas batch download exceeds the total archive byte limit",
                            raw={
                                "representation": "atlas-batch-archive-byte-limit",
                                "limit_bytes": ATLAS_BATCH_ARCHIVE_MAX_BYTES,
                                "received_size_bytes": archive_size,
                                "truncated": True,
                            },
                        )
                else:
                    request_arguments = {
                        "headers": request_headers,
                        "timeout": request_timeout,
                    }
                    if deadline is not None and isinstance(self.transport, UrllibTransport):
                        request_arguments["deadline"] = deadline
                    response = self.transport.request("GET", url, **request_arguments)
                    attempt["http_status"] = _validated_provider_status(response.status)
                _require_deadline(
                    deadline,
                    "Atlas batch download deadline expired after provider response",
                    partial=partial_output_present(),
                )
                raise_for_status(response, expected={200, 206})
                if not callable(stream_to):
                    provider_status = _validated_provider_status(response.status)
                    mode = "ab" if expected_offset and response.status == 206 else "wb"
                    retained_size = expected_offset if mode == "ab" else 0
                    observed_size = retained_size + len(response.body)
                    if observed_size > ATLAS_BATCH_ARCHIVE_MAX_BYTES:
                        raise SchemaDriftError(
                            "Atlas batch download exceeds the total archive byte limit",
                            raw={
                                "representation": "atlas-batch-archive-byte-limit",
                                "limit_bytes": ATLAS_BATCH_ARCHIVE_MAX_BYTES,
                                "resume_offset_bytes": retained_size,
                                "received_size_bytes": observed_size,
                                "truncated": True,
                            },
                        )
                    handle, observed_identity = _open_status_bound_stream_destination(
                        partial,
                        append=mode == "ab",
                        expected_identity=partial_identity,
                        provider_status=provider_status,
                    )
                    if observed_identity != partial_identity:  # pragma: no cover - defensive
                        raise ValidationError("Atlas batch partial identity changed")
                    with _status_bound_stream_handle(
                        handle,
                        partial,
                        provider_status=provider_status,
                        expected_identity=partial_identity,
                    ):
                        base_size = _status_bound_stream_size(
                            handle,
                            provider_status=provider_status,
                            partial=partial_output_present(),
                        )
                        if mode == "ab" and base_size != expected_offset:
                            raise ValidationError(
                                "Atlas batch partial size changed before resumed writing"
                            )
                        _write_stream_destination(
                            handle,
                            response.body,
                            provider_status=provider_status,
                            partial=base_size > 0,
                        )
                        _sync_stream_destination(
                            handle,
                            provider_status=provider_status,
                            partial=base_size + len(response.body) > 0,
                        )
                        final_size = base_size + len(response.body)
                    if response.status == 206:
                        validate_content_range(
                            response.headers,
                            expected_offset,
                            final_size=final_size,
                        )
            except BaseException as error:
                response_status = (
                    _validated_provider_status(response.status) if response is not None else None
                )
                if response_status is None:
                    response_status = _validated_provider_status(
                        getattr(error, "provider_status", None)
                    )
                if isinstance(error, BiohubESMError):
                    _bind_provider_status(error, response_status)
                error_status = getattr(error, "status", None)
                if error_status is None:
                    error_status = getattr(error, "provider_status", None)
                if error_status is None:
                    error_status = response_status
                if (
                    isinstance(error_status, int)
                    and not isinstance(error_status, bool)
                    and 100 <= error_status <= 599
                ):
                    attempt["http_status"] = error_status
                attempt["outcome"] = "failed"
                raise
            return response

        def recover_with_full_get(reason: str) -> HTTPResponse:
            nonlocal offset, resume_recovery, validated_download_record

            resume_recovery = reason
            failure_context["resume_recovery"] = reason
            offset = 0
            attempt_count = len(attempts)
            try:
                full_response = fetch({}, 0)
            except SchemaDriftError:
                if len(attempts) == attempt_count:
                    attempts.append(
                        {
                            "http_status": None,
                            "range_start": None,
                            "outcome": "invalid-full-response",
                        }
                    )
                else:
                    attempts[-1]["outcome"] = "invalid-full-response"
                _truncate_atlas_partial(partial, partial_identity)
                raise
            try:
                _require_atlas_partial_identity(partial, partial_identity)
                validated_download_record, _, _ = atlas_artifact_snapshot(
                    partial,
                    expected_identity=partial_identity,
                    descriptor_validator=lambda handle: _validate_zip(
                        handle,
                        "Atlas batch download after full retry",
                    ),
                )
            except SchemaDriftError:
                attempts[-1]["outcome"] = "invalid-full-archive"
                _truncate_atlas_partial(partial, partial_identity)
                raise
            attempts[-1]["outcome"] = "completed"
            return full_response

        recovered_with_full_get = False
        attempt_count = len(attempts)
        try:
            response = fetch(headers, offset)
        except APIError as exc:
            if not offset or exc.status != 416:
                raise
            if len(attempts) == attempt_count:
                attempts.append(
                    {
                        "http_status": exc.status,
                        "range_start": offset,
                        "outcome": "range-not-satisfiable",
                    }
                )
            else:
                attempts[-1]["outcome"] = "range-not-satisfiable"
            response = recover_with_full_get("range-not-satisfiable")
            recovered_with_full_get = True
        except SchemaDriftError:
            if not offset:
                attempts[-1]["outcome"] = "invalid-full-response"
                _truncate_atlas_partial(partial, partial_identity)
                raise
            if len(attempts) == attempt_count:
                attempts.append(
                    {
                        "http_status": None,
                        "range_start": offset,
                        "outcome": "invalid-content-range",
                    }
                )
            else:
                attempts[-1]["outcome"] = "invalid-content-range"
            response = recover_with_full_get("invalid-content-range")
            recovered_with_full_get = True
        if not recovered_with_full_get:
            try:
                _require_atlas_partial_identity(partial, partial_identity)
                validated_download_record, _, _ = atlas_artifact_snapshot(
                    partial,
                    expected_identity=partial_identity,
                    descriptor_validator=lambda handle: _validate_zip(
                        handle,
                        "Atlas batch download",
                    ),
                )
            except SchemaDriftError:
                attempts[-1]["outcome"] = "invalid-archive"
                if not offset or response.status != 206:
                    _truncate_atlas_partial(partial, partial_identity)
                    raise
                attempts[-1]["outcome"] = "invalid-resumed-archive"
                response = recover_with_full_get("invalid-resumed-archive")
            else:
                attempts[-1]["outcome"] = "completed"
        try:
            _require_deadline(
                deadline,
                "Atlas batch download deadline expired before artifact promotion",
                partial=partial_output_present(),
            )
        except APIError as exc:
            _bind_provider_status(exc, _validated_provider_status(response.status))
            raise
        if validated_download_record is None:  # pragma: no cover - defensive
            attempts[-1]["outcome"] = "publication-failed"
            raise ValidationError("Atlas downloaded bytes were not validated for publication")
        try:
            promote_file_noreplace(
                partial,
                destination,
                expected_source_identity=partial_identity,
            )
            with open_atlas_artifact_snapshot(
                destination,
                expected_identity=partial_identity,
            ) as published_snapshot:
                _validate_zip(
                    published_snapshot.handle,
                    "Atlas published batch download",
                )
                if (
                    published_snapshot.record["size_bytes"]
                    != validated_download_record["size_bytes"]
                    or published_snapshot.record["sha256"] != validated_download_record["sha256"]
                ):
                    raise ValidationError(
                        "Atlas published batch download differs from validated downloaded bytes"
                    )
                published_snapshot.validate_path_identity()
                artifact = dict(published_snapshot.record)
        except (SchemaDriftError, ValidationError):
            attempts[-1]["outcome"] = "publication-failed"
            raise
        result = {
            **artifact,
            "resumed": bool(offset and response.status == 206),
            "http_status": response.status,
            "transport_attempts": attempts,
        }
        if resume_recovery is not None:
            result["resume_recovery"] = resume_recovery
        return result

"""Artifact integrity and provenance sidecars."""

from __future__ import annotations

import base64
import csv
import ctypes
import errno
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import math
import os
import re
import secrets
import stat
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable

from .constants import (
    ATLAS_API_VERSION,
    ATLAS_SCHEMA_VERSION,
    ESM_GIT_REVISION,
    ESM_SDK_PAYLOAD_SHA256,
    ESM_SDK_VERSION,
    ESMC_MANAGED_MODELS,
    ESMFOLD2_MANAGED_MODELS,
    HF_REVISIONS,
    TRANSFORMERS_GIT_REVISION,
    TRANSFORMERS_PAYLOAD_SHA256,
    TRANSFORMERS_VERSION,
)
from .errors import SchemaDriftError, ValidationError
from .security import redact

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ALL_HF_REVISIONS = dict(HF_REVISIONS)
MANAGED_MODEL_IDS = {*ESMC_MANAGED_MODELS, *ESMFOLD2_MANAGED_MODELS}
BASE_EXECUTION_ROUTES = {"atlas-api", "atlas-s3", "biohub", "modal", "self-hosted"}
HTTP_METHODS = {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}
MATERIALIZED_PDB_MAX_ARTIFACTS = 128
MATERIALIZED_PDB_MAX_TOTAL_BYTES = 64 * 1024 * 1024


def atlas_source_attribution() -> dict[str, str]:
    return {
        "name": "ESM Atlas",
        "source_url": "https://biohub.ai/esm/protein/atlas/api-docs/overview.html",
        "license": "CC-BY-4.0",
        "api_version": ATLAS_API_VERSION,
        "schema_version": ATLAS_SCHEMA_VERSION,
    }


def numeric_metric_summary(value: Any) -> Any:
    if isinstance(value, (bool, int, float)):
        return value
    if not isinstance(value, list):
        return {"sha256": input_digest(value)}

    shape: list[int] = []
    cursor: Any = value
    while isinstance(cursor, list):
        shape.append(len(cursor))
        cursor = cursor[0] if cursor else None

    count = 0
    mean: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    stack = [iter((value,))]
    while stack:
        iterator = stack[-1]
        try:
            item = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        if isinstance(item, list):
            stack.append(iter(item))
        elif not isinstance(item, bool) and isinstance(item, (int, float)) and math.isfinite(item):
            number = float(item)
            next_count = count + 1
            if mean is None:
                mean = number
            else:
                delta = number - mean
                if math.isfinite(delta):
                    mean += delta / next_count
                else:
                    mean = mean * (count / next_count) + number / next_count
                if not math.isfinite(mean):
                    raise ValidationError("numeric metric mean is not finite")
            count = next_count
            minimum = number if minimum is None else min(minimum, number)
            maximum = number if maximum is None else max(maximum, number)

    summary: dict[str, Any] = {"shape": shape, "sha256": input_digest(value)}
    if count:
        summary.update(
            {
                "min": minimum,
                "max": maximum,
                "mean": mean,
            }
        )
    return summary


def _utc_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"provenance {field} must be a UTC timestamp")
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError(f"provenance {field} must be a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValidationError(f"provenance {field} must be a UTC timestamp")
    return parsed


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json_chunks(value: Any) -> Iterator[bytes]:
    encoder = json.JSONEncoder(
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    try:
        for chunk in encoder.iterencode(value):
            yield chunk.encode("utf-8")
    except (TypeError, ValueError, RecursionError, MemoryError) as exc:
        raise ValidationError(
            "value must be interoperable JSON without non-finite numbers"
        ) from exc


def canonical_json(value: Any) -> bytes:
    try:
        return b"".join(_canonical_json_chunks(value))
    except MemoryError as exc:
        raise ValidationError("canonical JSON exceeds available memory") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def input_digest(value: Any) -> str:
    if isinstance(value, bytes):
        return sha256_bytes(value)
    if isinstance(value, str):
        return sha256_bytes(value.encode("utf-8"))
    digest = hashlib.sha256()
    for chunk in _canonical_json_chunks(value):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_fresh_output_directory(path: Path) -> Path:
    """Atomically claim a nonexistent directory for exactly one generation."""

    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ValidationError(
            "output directory must not already exist; choose a fresh path"
        ) from None
    return path


def _atomic_rename_noreplace(
    temporary_name: str,
    destination_name: str,
    *,
    parent_descriptor: int,
    display_path: Path,
) -> bool:
    """Atomically consume a held-directory temp without replacing, when supported."""

    try:
        libc = ctypes.CDLL(None, use_errno=True)
    except OSError:
        return False

    unsupported = {
        errno.ENOSYS,
        errno.EINVAL,
        errno.EOPNOTSUPP,
        getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
    }

    try:
        renameat2 = libc.renameat2
    except AttributeError:
        renameat2 = None
    if renameat2 is not None:
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            parent_descriptor,
            os.fsencode(temporary_name),
            parent_descriptor,
            os.fsencode(destination_name),
            1,
        )
        if result == 0:
            return True
        error_number = ctypes.get_errno()
        if error_number == errno.EEXIST:
            raise ValidationError(f"refusing to overwrite an existing artifact: {display_path}")
        if error_number not in unsupported:
            raise OSError(error_number, os.strerror(error_number), str(display_path))

    # macOS exposes a descriptor-relative equivalent through renameatx_np.
    try:
        renameatx_np = libc.renameatx_np
    except AttributeError:
        return False
    renameatx_np.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameatx_np.restype = ctypes.c_int
    result = renameatx_np(
        parent_descriptor,
        os.fsencode(temporary_name),
        parent_descriptor,
        os.fsencode(destination_name),
        0x00000004,
    )
    if result == 0:
        return True
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise ValidationError(f"refusing to overwrite an existing artifact: {display_path}")
    if error_number in unsupported:
        return False
    raise OSError(error_number, os.strerror(error_number), str(display_path))


def _regular_file_fingerprint(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _sha256_descriptor_exact(descriptor: int, expected_size: int) -> str:
    """Hash one expected-size publication with at most one extra probe byte."""

    digest = hashlib.sha256()
    offset = 0
    while offset < expected_size:
        chunk = os.pread(descriptor, min(1024 * 1024, expected_size - offset), offset)
        if not chunk:
            raise ValidationError("published artifact content or identity changed")
        digest.update(chunk)
        offset += len(chunk)
    if os.pread(descriptor, 1, expected_size):
        raise ValidationError("published artifact content or identity changed")
    return digest.hexdigest()


def _published_file_info(path: Path) -> os.stat_result:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise ValidationError("published artifact is unavailable after atomic write") from exc
    if not stat.S_ISREG(info.st_mode):
        raise ValidationError("published artifact is not the expected regular file")
    return info


def _published_file_info_in_held_parent(
    destination_name: str,
    parent_descriptor: int,
) -> os.stat_result:
    try:
        info = os.stat(
            destination_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise ValidationError("published artifact is unavailable after atomic write") from exc
    if not stat.S_ISREG(info.st_mode):
        raise ValidationError("published artifact is not the expected regular file")
    return info


@contextmanager
def _held_parent_directory(
    path: Path,
    *,
    expected_identity: tuple[int, int] | None = None,
) -> Iterator[tuple[int, tuple[int, int]]]:
    """Retain the publication directory identity across rename and durability."""

    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path.parent, flags)
    except OSError as exc:
        raise ValidationError("atomic artifact parent directory could not be synchronized") from exc
    try:
        retained = os.fstat(descriptor)
        published = path.parent.stat(follow_symlinks=False)
    except OSError as exc:
        os.close(descriptor)
        raise ValidationError("atomic artifact parent directory could not be synchronized") from exc
    identity = (retained.st_dev, retained.st_ino)
    if expected_identity is not None and (
        not isinstance(expected_identity, tuple)
        or len(expected_identity) != 2
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 0
            for item in expected_identity
        )
    ):
        os.close(descriptor)
        raise ValidationError("expected artifact parent identity is invalid")
    if (
        not stat.S_ISDIR(retained.st_mode)
        or not stat.S_ISDIR(published.st_mode)
        or (published.st_dev, published.st_ino) != identity
        or (expected_identity is not None and identity != expected_identity)
    ):
        os.close(descriptor)
        raise ValidationError("atomic artifact parent directory could not be synchronized")
    try:
        yield descriptor, identity
    finally:
        os.close(descriptor)


def _fsync_parent_directory(
    path: Path,
    descriptor: int,
    expected_identity: tuple[int, int],
) -> None:
    """Synchronize the retained directory before reporting a lexical rebind failure."""

    try:
        retained = os.fstat(descriptor)
    except OSError as exc:
        raise ValidationError("atomic artifact parent directory could not be synchronized") from exc
    if (
        not stat.S_ISDIR(retained.st_mode)
        or (retained.st_dev, retained.st_ino) != expected_identity
    ):
        raise ValidationError("atomic artifact parent directory could not be synchronized")
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise ValidationError("atomic artifact parent directory could not be synchronized") from exc
    try:
        published = path.parent.stat(follow_symlinks=False)
    except OSError as exc:
        raise ValidationError("atomic artifact parent directory could not be synchronized") from exc
    if (
        not stat.S_ISDIR(published.st_mode)
        or (published.st_dev, published.st_ino) != expected_identity
    ):
        raise ValidationError("atomic artifact parent directory could not be synchronized")


def _sync_parent_after_failure(
    path: Path,
    descriptor: int,
    expected_identity: tuple[int, int],
    original_error: BaseException,
) -> None:
    """Best-effort durability without discarding the first publication failure."""

    try:
        _fsync_parent_directory(path, descriptor, expected_identity)
    except BaseException:
        raise ValidationError(
            "atomic artifact failure could not be synchronized"
        ) from original_error


def _content_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    """Identity fields that remain stable when a directory entry is renamed."""

    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
    )


def _replace_if_unchanged_in_held_parent(
    *,
    temporary_name: str,
    destination_name: str,
    path: Path,
    parent_descriptor: int,
    expected_fingerprint: tuple[int, int, int, int, int, int],
    expected_sha256: str,
) -> None:
    """Publish without overwriting a destination that changed concurrently."""

    if (
        not isinstance(expected_fingerprint, tuple)
        or len(expected_fingerprint) != 6
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 0
            for item in expected_fingerprint
        )
        or SHA256_RE.fullmatch(expected_sha256) is None
    ):
        raise ValidationError("expected artifact snapshot is invalid")

    try:
        parent_info = os.fstat(parent_descriptor)
    except OSError as exc:
        raise ValidationError("atomic artifact parent directory could not be synchronized") from exc
    if not stat.S_ISDIR(parent_info.st_mode):
        raise ValidationError("atomic artifact parent directory could not be synchronized")
    parent_identity = (parent_info.st_dev, parent_info.st_ino)

    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        destination_descriptor = os.open(
            destination_name,
            flags,
            dir_fd=parent_descriptor,
        )
    except OSError as exc:
        raise ValidationError("artifact changed before conditional publication") from exc
    try:
        before = os.fstat(destination_descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or _regular_file_fingerprint(before) != expected_fingerprint
            or _sha256_descriptor_exact(destination_descriptor, expected_fingerprint[3])
            != expected_sha256
            or _regular_file_fingerprint(os.fstat(destination_descriptor)) != expected_fingerprint
        ):
            raise ValidationError("artifact changed before conditional publication")

        backup_name = f".{destination_name}.previous.{secrets.token_hex(16)}"
        moved = _atomic_rename_noreplace(
            destination_name,
            backup_name,
            parent_descriptor=parent_descriptor,
            display_path=path,
        )
        if not moved:
            raise ValidationError("atomic conditional publication is unavailable")

        try:
            displaced = os.stat(
                backup_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            retained = os.fstat(destination_descriptor)
            displaced_digest = _sha256_descriptor_exact(
                destination_descriptor,
                expected_fingerprint[3],
            )
            expected_content_identity = expected_fingerprint[:5]
            if (
                _content_identity(displaced) != expected_content_identity
                or _content_identity(retained) != expected_content_identity
                or displaced_digest != expected_sha256
            ):
                raise ValidationError("artifact changed during conditional publication")

            published = _atomic_rename_noreplace(
                temporary_name,
                destination_name,
                parent_descriptor=parent_descriptor,
                display_path=path,
            )
            if not published:
                raise ValidationError("atomic conditional publication is unavailable")
        except BaseException as exc:
            # The first no-replace rename consumed the canonical entry. Restore
            # the displaced file on every later failure, but never overwrite a
            # writer that has already claimed the canonical name. If restoration
            # itself cannot proceed, the displaced file remains as a named
            # residue instead of being deleted or silently lost.
            restoration_error: BaseException | None = None
            try:
                restored = _atomic_rename_noreplace(
                    backup_name,
                    destination_name,
                    parent_descriptor=parent_descriptor,
                    display_path=path,
                )
            except BaseException as restore_exc:
                restored = False
                restoration_error = restore_exc
            try:
                _fsync_parent_directory(path, parent_descriptor, parent_identity)
            except BaseException as sync_exc:
                raise ValidationError(
                    "conditional publication recovery could not be synchronized"
                ) from sync_exc
            if restoration_error is not None or not restored:
                raise ValidationError(
                    "conditional publication failed; displaced artifact was preserved as a residue"
                ) from exc
            if not isinstance(exc, (OSError, ValidationError)):
                raise
            raise ValidationError("artifact changed during conditional publication") from exc
    finally:
        os.close(destination_descriptor)


def _publish_temporary_file_in_held_parent(
    temporary: str,
    path: Path,
    *,
    parent_descriptor: int,
    replace: bool,
    source_descriptor: int,
    expected_size: int,
    expected_sha256: str,
    expected_existing_fingerprint: tuple[int, int, int, int, int, int] | None = None,
    expected_existing_sha256: str | None = None,
) -> tuple[int, int]:
    source_info = os.fstat(source_descriptor)
    if (
        not stat.S_ISREG(source_info.st_mode)
        or source_info.st_size != expected_size
        or _sha256_descriptor_exact(source_descriptor, expected_size) != expected_sha256
    ):
        raise ValidationError("atomic artifact source is not a regular file")
    expected_identity = (source_info.st_dev, source_info.st_ino)
    temporary_path = Path(temporary)
    temporary_name = temporary_path.name
    destination_name = path.name
    try:
        named_source_info = os.stat(
            temporary_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise ValidationError("atomic artifact source changed before publication") from exc
    if (
        not stat.S_ISREG(named_source_info.st_mode)
        or (named_source_info.st_dev, named_source_info.st_ino) != expected_identity
    ):
        raise ValidationError("atomic artifact source changed before publication")
    if (expected_existing_fingerprint is None) != (expected_existing_sha256 is None):
        raise ValidationError("conditional publication snapshot is incomplete")
    if expected_existing_fingerprint is not None:
        if not replace:
            raise ValidationError("conditional publication requires replace mode")
        _replace_if_unchanged_in_held_parent(
            temporary_name=temporary_name,
            destination_name=destination_name,
            path=path,
            parent_descriptor=parent_descriptor,
            expected_fingerprint=expected_existing_fingerprint,
            expected_sha256=expected_existing_sha256,
        )
    elif replace:
        os.replace(
            temporary_name,
            destination_name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
    elif not _atomic_rename_noreplace(
        temporary_name,
        destination_name,
        parent_descriptor=parent_descriptor,
        display_path=path,
    ):
        try:
            os.link(
                temporary_name,
                destination_name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            raise ValidationError(f"refusing to overwrite an existing artifact: {path}") from None
        # The hardlink fallback cannot safely compare-and-unlink the source pathname.
        # Retain it as a benign residue rather than risk deleting a raced replacement.
    retained_info = os.fstat(source_descriptor)
    published_info = _published_file_info_in_held_parent(
        destination_name,
        parent_descriptor,
    )
    if (
        not stat.S_ISREG(retained_info.st_mode)
        or (retained_info.st_dev, retained_info.st_ino) != expected_identity
        or (published_info.st_dev, published_info.st_ino) != expected_identity
    ):
        # Never unlink an unexpected publication: another writer may have replaced
        # the pathname after our atomic operation. Fail closed and preserve it.
        raise ValidationError("atomic artifact source changed during publication")
    retained_fingerprint = _regular_file_fingerprint(retained_info)
    if _regular_file_fingerprint(published_info) != retained_fingerprint:
        raise ValidationError("atomic artifact source changed during publication")
    try:
        retained_digest = _sha256_descriptor_exact(source_descriptor, expected_size)
        final_retained = os.fstat(source_descriptor)
        final_published = _published_file_info_in_held_parent(
            destination_name,
            parent_descriptor,
        )
        terminal_digest = _sha256_descriptor_exact(source_descriptor, expected_size)
        terminal_retained = os.fstat(source_descriptor)
        terminal_published = _published_file_info_in_held_parent(
            destination_name,
            parent_descriptor,
        )
    except OSError as exc:
        raise ValidationError("atomic artifact source changed during publication") from exc
    if (
        retained_digest != expected_sha256
        or terminal_digest != expected_sha256
        or final_retained.st_size != expected_size
        or _regular_file_fingerprint(final_retained) != retained_fingerprint
        or _regular_file_fingerprint(final_published) != retained_fingerprint
        or _regular_file_fingerprint(terminal_retained) != retained_fingerprint
        or _regular_file_fingerprint(terminal_published) != retained_fingerprint
    ):
        raise ValidationError("atomic artifact source changed during publication")
    return expected_identity


def _publish_temporary_file(
    temporary: str,
    path: Path,
    *,
    replace: bool,
    source_descriptor: int,
    expected_size: int,
    expected_sha256: str,
    expected_existing_fingerprint: tuple[int, int, int, int, int, int] | None = None,
    expected_existing_sha256: str | None = None,
) -> tuple[int, int]:
    with _held_parent_directory(path) as (parent_descriptor, parent_identity):
        try:
            identity = _publish_temporary_file_in_held_parent(
                temporary,
                path,
                parent_descriptor=parent_descriptor,
                replace=replace,
                source_descriptor=source_descriptor,
                expected_size=expected_size,
                expected_sha256=expected_sha256,
                expected_existing_fingerprint=expected_existing_fingerprint,
                expected_existing_sha256=expected_existing_sha256,
            )
        except BaseException as exc:
            _sync_parent_after_failure(
                path,
                parent_descriptor,
                parent_identity,
                exc,
            )
            raise
        _fsync_parent_directory(path, parent_descriptor, parent_identity)
        return identity


class OpenArtifactPublication:
    """Descriptor-bound artifact publication held through provenance acceptance."""

    def __init__(
        self,
        *,
        path: Path,
        handle: BinaryIO,
        identity: tuple[int, int],
        expected_size: int,
        expected_sha256: str,
        media_type: str | None,
    ) -> None:
        self.path = path
        self.handle = handle
        self.identity = identity
        info = os.fstat(handle.fileno())
        self.fingerprint = _regular_file_fingerprint(info)
        self.record: dict[str, Any] = {
            "path": str(path),
            "size_bytes": expected_size,
            "sha256": expected_sha256,
        }
        if media_type is not None:
            self.record["media_type"] = media_type

    def validate(self) -> None:
        try:
            retained_before = os.fstat(self.handle.fileno())
            path_before = _published_file_info(self.path)
        except OSError as exc:
            raise ValidationError("published artifact identity is ambiguous") from exc
        if (
            _regular_file_fingerprint(retained_before) != self.fingerprint
            or _regular_file_fingerprint(path_before) != self.fingerprint
            or retained_before.st_size != self.record["size_bytes"]
        ):
            raise ValidationError("published artifact content or identity changed")
        try:
            retained_digest = _sha256_descriptor_exact(
                self.handle.fileno(),
                self.record["size_bytes"],
            )
            retained_after = os.fstat(self.handle.fileno())
            path_after = _published_file_info(self.path)
        except OSError as exc:
            raise ValidationError("published artifact identity is ambiguous") from exc
        if (
            _regular_file_fingerprint(retained_after) != self.fingerprint
            or _regular_file_fingerprint(path_after) != self.fingerprint
            or retained_digest != self.record["sha256"]
            or retained_after.st_size != self.record["size_bytes"]
        ):
            raise ValidationError("published artifact content or identity changed")
        try:
            terminal_digest = _sha256_descriptor_exact(
                self.handle.fileno(),
                self.record["size_bytes"],
            )
            terminal_retained = os.fstat(self.handle.fileno())
            terminal_path = _published_file_info(self.path)
        except OSError as exc:
            raise ValidationError("published artifact identity is ambiguous") from exc
        if (
            terminal_digest != self.record["sha256"]
            or _regular_file_fingerprint(terminal_retained) != self.fingerprint
            or _regular_file_fingerprint(terminal_path) != self.fingerprint
            or terminal_retained.st_size != self.record["size_bytes"]
        ):
            raise ValidationError("published artifact content or identity changed")


def _open_temporary_file_in_held_parent(
    destination_name: str,
    parent_descriptor: int,
) -> tuple[int, str]:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    for _ in range(128):
        temporary_name = f".{destination_name}.{secrets.token_hex(16)}"
        try:
            descriptor = os.open(
                temporary_name,
                flags,
                0o600,
                dir_fd=parent_descriptor,
            )
        except FileExistsError:
            continue
        except OSError as exc:
            raise ValidationError("atomic artifact temporary file could not be created") from exc
        return descriptor, temporary_name
    raise ValidationError("atomic artifact temporary file could not be created")


def _validate_published_source_in_held_parent(
    *,
    source_descriptor: int,
    destination_name: str,
    parent_descriptor: int,
    expected_fingerprint: tuple[int, int, int, int, int, int],
    expected_size: int,
    expected_sha256: str,
) -> None:
    for _ in range(2):
        retained_before = os.fstat(source_descriptor)
        published_before = _published_file_info_in_held_parent(
            destination_name,
            parent_descriptor,
        )
        digest = _sha256_descriptor_exact(source_descriptor, expected_size)
        retained_after = os.fstat(source_descriptor)
        published_after = _published_file_info_in_held_parent(
            destination_name,
            parent_descriptor,
        )
        if (
            _regular_file_fingerprint(retained_before) != expected_fingerprint
            or _regular_file_fingerprint(published_before) != expected_fingerprint
            or digest != expected_sha256
            or _regular_file_fingerprint(retained_after) != expected_fingerprint
            or _regular_file_fingerprint(published_after) != expected_fingerprint
        ):
            raise ValidationError("published artifact content or identity changed")


def _write_chunks_atomic_if_unchanged(
    path: Path,
    chunks: Iterable[bytes],
    *,
    expected_fingerprint: tuple[int, int, int, int, int, int],
    expected_sha256: str,
    expected_parent_identity: tuple[int, int],
) -> tuple[int, int]:
    """Publish prevalidated chunks entirely through the expected parent dirfd."""

    if (
        not isinstance(expected_parent_identity, tuple)
        or len(expected_parent_identity) != 2
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 0
            for item in expected_parent_identity
        )
    ):
        raise ValidationError("expected artifact parent identity is invalid")
    with _held_parent_directory(
        path,
        expected_identity=expected_parent_identity,
    ) as (parent_descriptor, parent_identity):
        descriptor, temporary_name = _open_temporary_file_in_held_parent(
            path.name,
            parent_descriptor,
        )
        try:
            handle = os.fdopen(descriptor, "w+b")
        except BaseException as exc:
            os.close(descriptor)
            _sync_parent_after_failure(
                path,
                parent_descriptor,
                parent_identity,
                exc,
            )
            raise
        directory_sync_attempted = False
        directory_sync_completed = False
        try:
            with handle:
                digest = hashlib.sha256()
                size = 0
                for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise ValidationError("atomic artifact chunks must be bytes")
                    handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
                identity = _publish_temporary_file_in_held_parent(
                    temporary_name,
                    path,
                    parent_descriptor=parent_descriptor,
                    replace=True,
                    source_descriptor=handle.fileno(),
                    expected_size=size,
                    expected_sha256=digest.hexdigest(),
                    expected_existing_fingerprint=expected_fingerprint,
                    expected_existing_sha256=expected_sha256,
                )
                published_fingerprint = _regular_file_fingerprint(os.fstat(handle.fileno()))
                published_sha256 = digest.hexdigest()
                directory_sync_attempted = True
                _fsync_parent_directory(path, parent_descriptor, parent_identity)
                directory_sync_completed = True
                _validate_published_source_in_held_parent(
                    source_descriptor=handle.fileno(),
                    destination_name=path.name,
                    parent_descriptor=parent_descriptor,
                    expected_fingerprint=published_fingerprint,
                    expected_size=size,
                    expected_sha256=published_sha256,
                )
        except BaseException as exc:
            if not directory_sync_attempted or directory_sync_completed:
                _sync_parent_after_failure(
                    path,
                    parent_descriptor,
                    parent_identity,
                    exc,
                )
            raise
        return identity


@contextmanager
def publish_json_atomic(
    path: Path,
    value: Any,
    *,
    replace: bool = True,
    media_type: str | None = "application/json",
) -> Iterator[OpenArtifactPublication]:
    encoder = json.JSONEncoder(
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )
    # Finish the exact pretty-printed serialization before creating a named
    # publication temp. A compact validation pass is insufficient because the
    # indented encoder can reach a recursion failure at a shallower JSON depth.
    # SpooledTemporaryFile rolls large values to an anonymous temporary file, so
    # an encoder failure cannot leave a path that would require a TOCTOU-prone
    # cleanup decision.
    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as serialized:
        try:
            for chunk in encoder.iterencode(value):
                serialized.write(chunk.encode("utf-8"))
            serialized.write(b"\n")
        except (TypeError, ValueError, RecursionError, MemoryError) as exc:
            raise ValidationError(
                "JSON artifact contains a non-serializable or non-finite value"
            ) from exc
        serialized.seek(0)

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(fd, "w+b") as handle:
            digest = hashlib.sha256()
            size = 0
            while chunk := serialized.read(1024 * 1024):
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            handle.flush()
            os.fsync(handle.fileno())
            identity = _publish_temporary_file(
                temporary,
                path,
                replace=replace,
                source_descriptor=handle.fileno(),
                expected_size=size,
                expected_sha256=digest.hexdigest(),
            )
            publication = OpenArtifactPublication(
                path=path,
                handle=handle,
                identity=identity,
                expected_size=size,
                expected_sha256=digest.hexdigest(),
                media_type=media_type,
            )
            publication.validate()
            try:
                yield publication
            except BaseException:
                publication.validate()
                raise
            else:
                publication.validate()


def _write_json_atomic(path: Path, value: Any, *, replace: bool) -> tuple[int, int]:
    with publish_json_atomic(path, value, replace=replace) as publication:
        return publication.identity


def write_json_atomic(path: Path, value: Any) -> tuple[int, int]:
    return _write_json_atomic(path, value, replace=True)


def write_json_atomic_noreplace(path: Path, value: Any) -> tuple[int, int]:
    """Atomically publish JSON only if no filesystem entry already exists."""

    return _write_json_atomic(path, value, replace=False)


def write_json_atomic_if_unchanged(
    path: Path,
    value: Any,
    *,
    expected_fingerprint: tuple[int, int, int, int, int, int],
    expected_sha256: str,
    expected_parent_identity: tuple[int, int],
) -> tuple[int, int]:
    """Replace one JSON artifact only if its exact prior snapshot is still current."""

    encoder = json.JSONEncoder(
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )
    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as serialized:
        try:
            for chunk in encoder.iterencode(value):
                serialized.write(chunk.encode("utf-8"))
            serialized.write(b"\n")
        except (TypeError, ValueError, RecursionError, MemoryError) as exc:
            raise ValidationError(
                "JSON artifact contains a non-serializable or non-finite value"
            ) from exc
        serialized.seek(0)
        return _write_chunks_atomic_if_unchanged(
            path,
            iter(lambda: serialized.read(1024 * 1024), b""),
            expected_fingerprint=expected_fingerprint,
            expected_sha256=expected_sha256,
            expected_parent_identity=expected_parent_identity,
        )


@contextmanager
def publish_bytes_atomic(
    path: Path,
    value: bytes,
    *,
    replace: bool = True,
    media_type: str | None = None,
) -> Iterator[OpenArtifactPublication]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w+b") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
        expected_sha256 = sha256_bytes(value)
        identity = _publish_temporary_file(
            temporary,
            path,
            replace=replace,
            source_descriptor=handle.fileno(),
            expected_size=len(value),
            expected_sha256=expected_sha256,
        )
        publication = OpenArtifactPublication(
            path=path,
            handle=handle,
            identity=identity,
            expected_size=len(value),
            expected_sha256=expected_sha256,
            media_type=media_type,
        )
        publication.validate()
        try:
            yield publication
        except BaseException:
            publication.validate()
            raise
        else:
            publication.validate()


@contextmanager
def publish_stream_atomic(
    path: Path,
    source: BinaryIO,
    *,
    expected_size: int,
    expected_sha256: str,
    replace: bool = True,
    media_type: str | None = None,
) -> Iterator[OpenArtifactPublication]:
    """Copy a descriptor-bound stream into the atomic publication machinery."""

    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size < 0
        or not isinstance(expected_sha256, str)
        or not SHA256_RE.fullmatch(expected_sha256)
    ):
        raise ValidationError("expected artifact stream binding is invalid")
    try:
        source_before = os.fstat(source.fileno())
        source.seek(0)
    except (AttributeError, OSError, ValueError) as exc:
        raise ValidationError("artifact stream is unavailable") from exc
    if not stat.S_ISREG(source_before.st_mode) or source_before.st_size != expected_size:
        raise ValidationError("artifact stream must be a regular file")
    source_fingerprint = _regular_file_fingerprint(source_before)
    try:
        validated_digest = _sha256_descriptor_exact(source.fileno(), expected_size)
        source_validated = os.fstat(source.fileno())
    except OSError as exc:
        raise ValidationError("artifact stream changed before publication") from exc
    if (
        validated_digest != expected_sha256
        or _regular_file_fingerprint(source_validated) != source_fingerprint
    ):
        raise ValidationError("artifact stream changed before publication")

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w+b") as handle:
        digest = hashlib.sha256()
        size = 0
        while True:
            try:
                chunk = source.read(1024 * 1024)
            except (OSError, ValueError) as exc:
                raise ValidationError("artifact stream read failed") from exc
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise ValidationError("artifact stream must yield bytes")
            if handle.write(chunk) != len(chunk):
                raise ValidationError("artifact publication write was incomplete")
            digest.update(chunk)
            size += len(chunk)
        try:
            source_after = os.fstat(source.fileno())
            source_digest = _sha256_descriptor_exact(source.fileno(), source_before.st_size)
            source_terminal = os.fstat(source.fileno())
        except OSError as exc:
            raise ValidationError("artifact stream changed during publication") from exc
        if (
            _regular_file_fingerprint(source_after) != source_fingerprint
            or _regular_file_fingerprint(source_terminal) != source_fingerprint
            or size != expected_size
            or digest.hexdigest() != expected_sha256
            or source_digest != digest.hexdigest()
        ):
            raise ValidationError("artifact stream changed during publication")
        handle.flush()
        os.fsync(handle.fileno())
        identity = _publish_temporary_file(
            temporary,
            path,
            replace=replace,
            source_descriptor=handle.fileno(),
            expected_size=size,
            expected_sha256=expected_sha256,
        )
        publication = OpenArtifactPublication(
            path=path,
            handle=handle,
            identity=identity,
            expected_size=size,
            expected_sha256=expected_sha256,
            media_type=media_type,
        )
        publication.validate()
        try:
            yield publication
        except BaseException:
            publication.validate()
            raise
        else:
            publication.validate()


def _write_bytes_atomic(path: Path, value: bytes, *, replace: bool) -> tuple[int, int]:
    with publish_bytes_atomic(path, value, replace=replace) as publication:
        return publication.identity


def write_bytes_atomic(path: Path, value: bytes) -> tuple[int, int]:
    return _write_bytes_atomic(path, value, replace=True)


def write_bytes_atomic_noreplace(path: Path, value: bytes) -> tuple[int, int]:
    """Atomically publish bytes only if no filesystem entry already exists."""

    return _write_bytes_atomic(path, value, replace=False)


def write_bytes_atomic_if_unchanged(
    path: Path,
    value: bytes,
    *,
    expected_fingerprint: tuple[int, int, int, int, int, int],
    expected_sha256: str,
    expected_parent_identity: tuple[int, int],
) -> tuple[int, int]:
    """Replace bytes only if the exact prior artifact snapshot is still current."""

    return _write_chunks_atomic_if_unchanged(
        path,
        (value,),
        expected_fingerprint=expected_fingerprint,
        expected_sha256=expected_sha256,
        expected_parent_identity=expected_parent_identity,
    )


def promote_file_noreplace(
    source: Path,
    destination: Path,
    *,
    expected_source_identity: tuple[int, int] | None = None,
) -> None:
    """Publish one same-filesystem regular file without replacing a destination."""

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        source_descriptor = os.open(source, flags)
    except OSError as exc:
        raise ValidationError("artifact source is unavailable for promotion") from exc
    try:
        source_stat = os.fstat(source_descriptor)
        if not stat.S_ISREG(source_stat.st_mode):
            raise ValidationError("artifact source must be a regular file")
        if expected_source_identity is not None and (
            not isinstance(expected_source_identity, tuple)
            or len(expected_source_identity) != 2
            or any(
                isinstance(item, bool) or not isinstance(item, int) or item < 0
                for item in expected_source_identity
            )
        ):
            raise ValidationError("expected artifact source identity is invalid")
        source_identity = (source_stat.st_dev, source_stat.st_ino)
        if expected_source_identity is not None and source_identity != expected_source_identity:
            raise ValidationError("artifact source identity changed before promotion")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, destination, follow_symlinks=False)
        except FileExistsError:
            raise ValidationError(
                f"refusing to overwrite an existing artifact: {destination}"
            ) from None
        published_stat = destination.stat(follow_symlinks=False)
        retained_stat = os.fstat(source_descriptor)
        if (
            not stat.S_ISREG(retained_stat.st_mode)
            or (retained_stat.st_dev, retained_stat.st_ino) != source_identity
            or not stat.S_ISREG(published_stat.st_mode)
            or (published_stat.st_dev, published_stat.st_ino) != source_identity
        ):
            raise ValidationError("artifact source changed during promotion")
    finally:
        os.close(source_descriptor)
    # There is no portable atomic compare-and-unlink by pathname. Keep the
    # source path as a benign hardlink residue rather than risk deleting a
    # foreign replacement that raced in after publication.


def artifact_record(path: Path, *, media_type: str | None = None) -> dict[str, Any]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValidationError("artifact is not a safe regular file") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValidationError("artifact is not a safe regular file")
        digest = _sha256_descriptor_exact(descriptor, before.st_size)
        after = os.fstat(descriptor)
        current = _published_file_info(path)
        terminal_digest = _sha256_descriptor_exact(descriptor, before.st_size)
        terminal = os.fstat(descriptor)
        terminal_path = _published_file_info(path)
    except OSError as exc:
        raise ValidationError("artifact changed while its record was computed") from exc
    finally:
        os.close(descriptor)
    fingerprint = _regular_file_fingerprint(before)
    if (
        _regular_file_fingerprint(after) != fingerprint
        or _regular_file_fingerprint(current) != fingerprint
        or _regular_file_fingerprint(terminal) != fingerprint
        or _regular_file_fingerprint(terminal_path) != fingerprint
        or terminal_digest != digest
    ):
        raise ValidationError("artifact changed while its record was computed")
    result: dict[str, Any] = {
        "path": str(path),
        "size_bytes": terminal.st_size,
        "sha256": terminal_digest,
    }
    if media_type:
        result["media_type"] = media_type
    return result


@dataclass(frozen=True)
class PinnedDistribution:
    """An exact PyPI wheel whose installed payload must match before provenance cites it."""

    version: str
    package: str
    payload_sha256: str
    source_revision: str


DISTRIBUTION_VERIFICATION_METHOD = "pinned-wheel-payload-sha256"
PINNED_DISTRIBUTIONS: dict[str, PinnedDistribution] = {
    "esm": PinnedDistribution(
        version=ESM_SDK_VERSION,
        package="esm",
        payload_sha256=ESM_SDK_PAYLOAD_SHA256,
        source_revision=ESM_GIT_REVISION,
    ),
    "transformers": PinnedDistribution(
        version=TRANSFORMERS_VERSION,
        package="transformers",
        payload_sha256=TRANSFORMERS_PAYLOAD_SHA256,
        source_revision=TRANSFORMERS_GIT_REVISION,
    ),
}


def record_payload_entries(record_text: str, package: str) -> list[tuple[str, str]]:
    """Return the sorted, hashed RECORD rows of one importable package.

    Bytecode is excluded because installers may add or omit it. Every remaining
    row must carry a sha256 hash, since an unhashed row cannot be re-verified.
    """

    entries = []
    for row in csv.reader(record_text.splitlines()):
        if not row:
            continue
        path = row[0]
        parts = path.split("/")
        if parts[0] != package or "__pycache__" in parts or path.endswith(".pyc"):
            continue
        file_hash = row[1] if len(row) > 1 else ""
        if not file_hash.startswith("sha256="):
            raise ValidationError(f"{package} RECORD has an unhashed payload entry: {path}")
        entries.append((path, file_hash))
    return sorted(entries)


def record_payload_sha256(entries: Iterable[tuple[str, str]]) -> str:
    """Digest sorted ``path,hash`` rows; the same value comes from a wheel or an install."""

    return sha256_bytes("".join(f"{path},{file_hash}\n" for path, file_hash in entries).encode())


def _record_file_hash(path: Path) -> str:
    digest = bytes.fromhex(sha256_file(path))
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _is_recorded_source_bytecode(path: Path, location: Path, recorded: set[str]) -> bool:
    if path.suffix != ".pyc" or path.parent.name != "__pycache__":
        return False
    try:
        source = Path(importlib.util.source_from_cache(str(path))).relative_to(location)
    except (NotImplementedError, ValueError):
        return False
    return source.as_posix() in recorded


def _reject_unlisted_package_files(
    distribution_name: str, location: Path, package: str, record_text: str
) -> None:
    """Reject package-tree entries RECORD does not list, other than bytecode of recorded sources.

    An unlisted ``__init__.py``, extension module, or symlinked directory can
    shadow a verified module at import time without changing any recorded file.
    """

    recorded = {row[0] for row in csv.reader(record_text.splitlines()) if row}

    def raise_walk_error(error: OSError) -> None:
        raise error

    try:
        for directory, dirnames, filenames in os.walk(location / package, onerror=raise_walk_error):
            base = Path(directory)
            for name in dirnames:
                if (base / name).is_symlink():
                    relative = (base / name).relative_to(location).as_posix()
                    raise ValidationError(
                        f"{distribution_name} has a symlinked directory its RECORD does not "
                        f"list: {relative}"
                    )
            for name in filenames:
                path = base / name
                relative = path.relative_to(location).as_posix()
                if relative in recorded or _is_recorded_source_bytecode(path, location, recorded):
                    continue
                raise ValidationError(
                    f"{distribution_name} has a file its RECORD does not list: {relative}"
                )
    except OSError as exc:
        raise ValidationError(
            f"{distribution_name} package tree cannot be listed: {exc.filename or exc}"
        ) from exc


def verify_installed_distribution(distribution_name: str) -> str:
    """Verify an installed pinned wheel and return the source revision it was built from.

    The install must be files on disk with exactly one metadata directory, the
    exact pinned version, and not a VCS checkout or local source tree. Its RECORD
    must carry the pinned payload, every listed file must still match on disk,
    no unlisted file may sit in the package tree, and it must be the copy Python
    imports. Bytecode caches for recorded sources are trusted.
    """

    pin = PINNED_DISTRIBUTIONS.get(distribution_name)
    if pin is None:
        raise ValidationError(f"{distribution_name} is not a pinned distribution")
    try:
        distribution = metadata.distribution(distribution_name)
    except metadata.PackageNotFoundError as exc:
        raise ValidationError(f"{distribution_name} is not installed") from exc
    location = distribution.locate_file("")
    if not isinstance(location, Path):
        raise ValidationError(
            f"{distribution_name} must be installed as files on disk; it resolves to {location}"
        )
    installed = list(metadata.distributions(name=distribution_name, path=[str(location)]))
    if len(installed) > 1:
        raise ValidationError(
            f"{distribution_name} has {len(installed)} installed metadata directories at "
            f"{location}; keep only {distribution_name}=={pin.version}"
        )
    if distribution.version != pin.version:
        raise ValidationError(
            f"{distribution_name} {distribution.version} is installed at {location}; "
            f"the verified pin is {distribution_name}=={pin.version}"
        )
    try:
        direct_url = json.loads(distribution.read_text("direct_url.json") or "null")
    except ValueError as exc:
        raise ValidationError(f"{distribution_name} has an unreadable direct_url.json") from exc
    if direct_url is not None and (
        not isinstance(direct_url, dict)
        or "vcs_info" in direct_url
        or "dir_info" in direct_url
        or "archive_info" not in direct_url
    ):
        raise ValidationError(
            f"{distribution_name} is not an index or wheel-file install: its direct_url.json "
            "records a VCS checkout, a source tree, or a URL without archive_info"
        )
    try:
        record_text = distribution.read_text("RECORD")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{distribution_name} has an unreadable RECORD") from exc
    if not record_text:
        raise ValidationError(f"{distribution_name} has no installed RECORD")
    entries = record_payload_entries(record_text, pin.package)
    if record_payload_sha256(entries) != pin.payload_sha256:
        raise ValidationError(
            f"{distribution_name} installed payload does not match the pinned wheel"
        )
    for path, file_hash in entries:
        try:
            actual = _record_file_hash(location / path)
        except OSError as exc:
            raise ValidationError(
                f"{distribution_name} installed file is missing or unreadable: {path}"
            ) from exc
        if actual != file_hash:
            raise ValidationError(f"{distribution_name} installed file was modified: {path}")
    _reject_unlisted_package_files(distribution_name, location, pin.package, record_text)
    try:
        spec = importlib.util.find_spec(pin.package)
    except (ImportError, ValueError) as exc:
        raise ValidationError(f"{pin.package} cannot be located for import") from exc
    expected_origin = (location / pin.package / "__init__.py").resolve()
    if spec is None or spec.origin is None or Path(spec.origin).resolve() != expected_origin:
        raise ValidationError(
            f"{pin.package} imports from a different location than the verified distribution"
        )
    return pin.source_revision


def build_provenance(
    *,
    route: str,
    endpoint: str,
    model_id: str | None,
    model_revision: str | None,
    inputs: Any,
    parameters: dict[str, Any],
    seed: int | None,
    started_at: str,
    artifacts: list[dict[str, Any]],
    confidence_metrics: dict[str, Any] | None = None,
    provider_calls: list[dict[str, Any]] | None = None,
    finished_at: str | None = None,
    esm_git_revision: str | None = None,
    transformers_git_revision: str | None = None,
    input_sha256: str | None = None,
    source_attribution: dict[str, str] | None = None,
) -> dict[str, Any]:
    resolved_revision = model_revision
    revision_kind = "not-applicable"
    if model_id in ALL_HF_REVISIONS and resolved_revision is None:
        resolved_revision = ALL_HF_REVISIONS[model_id]
    if model_id in ALL_HF_REVISIONS:
        if resolved_revision != ALL_HF_REVISIONS[model_id]:
            raise ValidationError("Hugging Face model revision does not match the validated pin")
        revision_kind = "hugging-face-commit"
    elif model_id in MANAGED_MODEL_IDS and "biohub" in route.split("+"):
        resolved_revision = model_id
        revision_kind = "versioned-managed-model-id"
    elif model_id is not None and "biohub" in route.split("+"):
        raise ValidationError("Biohub provenance requires a supported managed model ID")
    elif model_id is not None:
        revision_kind = "explicit"
    result = {
        "schema_version": "1.0",
        "execution_route": route,
        "endpoint": endpoint,
        "provider_calls": redact(provider_calls or [{"endpoint": endpoint}]),
        "model_id": model_id,
        "model_revision": resolved_revision,
        "model_revision_kind": revision_kind,
        "esm_git_revision": esm_git_revision,
        "transformers_git_revision": transformers_git_revision,
        "input_sha256": input_sha256 or input_digest(inputs),
        "parameters": redact(parameters),
        "seed": seed,
        "started_at": started_at,
        "finished_at": finished_at or utc_now(),
        "artifacts": artifacts,
        "confidence_metrics": redact(confidence_metrics or {}),
    }
    if source_attribution is not None:
        result["source_attribution"] = redact(source_attribution)
    validate_provenance(result)
    return result


def validate_provenance(value: dict[str, Any]) -> None:
    for _ in _canonical_json_chunks(value):
        pass
    required = {
        "schema_version",
        "execution_route",
        "endpoint",
        "provider_calls",
        "model_id",
        "model_revision",
        "model_revision_kind",
        "esm_git_revision",
        "transformers_git_revision",
        "input_sha256",
        "parameters",
        "seed",
        "started_at",
        "finished_at",
        "artifacts",
        "confidence_metrics",
    }
    missing = sorted(required - set(value))
    if missing:
        raise ValidationError(f"provenance is missing required fields: {', '.join(missing)}")
    if value["schema_version"] != "1.0":
        raise ValidationError("unsupported provenance schema version")
    status = value.get("status")
    failure = value.get("failure")
    if status is not None:
        if status != "incomplete":
            raise ValidationError("provenance status must be incomplete when present")
        if (
            not isinstance(failure, dict)
            or not isinstance(failure.get("kind"), str)
            or not failure["kind"].strip()
            or not isinstance(failure.get("message"), str)
            or not failure["message"].strip()
        ):
            raise ValidationError("incomplete provenance requires a failure kind and message")
        failure_status = failure.get("status")
        provider_status = failure.get("provider_status")
        for field, candidate in (
            ("status", failure_status),
            ("provider_status", provider_status),
        ):
            if candidate is not None and (
                isinstance(candidate, bool)
                or not isinstance(candidate, int)
                or not 100 <= candidate <= 599
            ):
                raise ValidationError(f"provenance failure {field} is invalid")
        if (
            failure_status is not None
            and provider_status is not None
            and failure_status != provider_status
        ):
            raise ValidationError("provenance failure HTTP statuses disagree")
        for boolean_field in (
            "partial",
            "response_body_partial",
            "operation_indeterminate",
        ):
            if boolean_field in failure and not isinstance(failure[boolean_field], bool):
                raise ValidationError(f"provenance failure {boolean_field} must be boolean")
        if failure.get("operation_indeterminate") is True and (
            (failure_status is not None and failure_status >= 200)
            or (provider_status is not None and provider_status >= 200)
        ):
            raise ValidationError(
                "provenance failure with a final HTTP status cannot be indeterminate"
            )
        effective_failure_status = failure_status
        if effective_failure_status is None:
            effective_failure_status = provider_status
        if (
            isinstance(effective_failure_status, int)
            and 100 <= effective_failure_status < 200
            and failure.get("operation_indeterminate") is not True
        ):
            raise ValidationError(
                "provenance failure with an informational status must be indeterminate"
            )
    elif failure is not None:
        raise ValidationError("provenance failure requires incomplete status")
    source_attribution = value.get("source_attribution")
    if source_attribution is not None:
        required_attribution = {
            "name",
            "source_url",
            "license",
            "api_version",
            "schema_version",
        }
        if (
            not isinstance(source_attribution, dict)
            or set(source_attribution) != required_attribution
        ):
            raise ValidationError("provenance source_attribution has an invalid schema")
        if any(
            not isinstance(source_attribution[field], str) or not source_attribution[field].strip()
            for field in required_attribution
        ):
            raise ValidationError("provenance source_attribution values must be non-empty strings")
    if not SHA256_RE.fullmatch(str(value["input_sha256"])):
        raise ValidationError("provenance input_sha256 is invalid")
    route = value["execution_route"]
    if not isinstance(route, str) or not route:
        raise ValidationError("provenance execution_route is invalid")
    route_parts = route.split("+")
    if any(part not in BASE_EXECUTION_ROUTES for part in route_parts) or len(
        set(route_parts)
    ) != len(route_parts):
        raise ValidationError("provenance execution_route is invalid")
    if any(part in {"atlas-api", "atlas-s3"} for part in route_parts) and (
        source_attribution != atlas_source_attribution()
    ):
        raise ValidationError("Atlas provenance requires canonical source attribution")
    if not isinstance(value["endpoint"], str) or not value["endpoint"].strip():
        raise ValidationError("provenance endpoint must be non-empty")
    started_at = _utc_timestamp(value["started_at"], "started_at")
    finished_at = _utc_timestamp(value["finished_at"], "finished_at")
    if finished_at < started_at:
        raise ValidationError("provenance finished_at precedes started_at")
    seed = value["seed"]
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValidationError("provenance seed must be null or an integer")
    provider_calls = value["provider_calls"]
    if not isinstance(provider_calls, list) or not provider_calls:
        raise ValidationError("provenance provider_calls must be a non-empty list")
    for call in provider_calls:
        if (
            not isinstance(call, dict)
            or not isinstance(call.get("endpoint"), str)
            or not call["endpoint"].strip()
        ):
            raise ValidationError("each provenance provider call requires an endpoint")
        if "parameters" in call and not isinstance(call["parameters"], dict):
            raise ValidationError("provider call parameters must be an object")
        if "method" in call and call["method"] not in HTTP_METHODS:
            raise ValidationError("provider call method is invalid")
        if "operation" in call and (
            not isinstance(call["operation"], str) or not call["operation"].strip()
        ):
            raise ValidationError("provider call operation must be non-empty")
        if (
            "http_status" in call
            and call["http_status"] is not None
            and (
                isinstance(call["http_status"], bool)
                or not isinstance(call["http_status"], int)
                or not 100 <= call["http_status"] <= 599
            )
        ):
            raise ValidationError("provider call http_status is invalid")
        for boolean_field in (
            "partial",
            "response_body_partial",
            "operation_indeterminate",
        ):
            if boolean_field in call and not isinstance(call[boolean_field], bool):
                raise ValidationError(f"provider call {boolean_field} must be boolean")
        if call.get("operation_indeterminate") is True and call.get("outcome") != "indeterminate":
            raise ValidationError("an indeterminate provider call must have outcome indeterminate")
        if call.get("outcome") == "indeterminate" and (
            call.get("operation_indeterminate") is not True
        ):
            raise ValidationError(
                "an indeterminate provider-call outcome requires operation indeterminacy"
            )
        if (
            call.get("operation_indeterminate") is True
            and isinstance(call.get("http_status"), int)
            and call["http_status"] >= 200
        ):
            raise ValidationError(
                "a provider call with a final HTTP status cannot be indeterminate"
            )
        if (
            isinstance(call.get("http_status"), int)
            and 100 <= call["http_status"] < 200
            and (
                call.get("outcome") != "indeterminate"
                or call.get("operation_indeterminate") is not True
            )
        ):
            raise ValidationError(
                "an informational provider status requires an indeterminate provider call"
            )
        for timestamp_field in ("timestamp", "started_at", "finished_at"):
            if timestamp_field in call:
                _utc_timestamp(call[timestamp_field], f"provider_calls.{timestamp_field}")
        if (
            "started_at" in call
            and "finished_at" in call
            and _utc_timestamp(call["finished_at"], "provider_calls.finished_at")
            < _utc_timestamp(call["started_at"], "provider_calls.started_at")
        ):
            raise ValidationError("provider call finished_at precedes started_at")
    if status == "incomplete" and isinstance(failure, dict):
        last_http_status = provider_calls[-1].get("http_status")
        effective_failure_status = failure.get("status")
        if effective_failure_status is None:
            effective_failure_status = failure.get("provider_status")
        if (
            last_http_status is not None or effective_failure_status is not None
        ) and effective_failure_status != last_http_status:
            raise ValidationError(
                "incomplete failure status does not match the final provider call"
            )
    revision_kind = value["model_revision_kind"]
    if revision_kind not in {
        "not-applicable",
        "hugging-face-commit",
        "versioned-managed-model-id",
        "explicit",
    }:
        raise ValidationError("provenance model_revision_kind is invalid")
    model_id = value["model_id"]
    model_revision = value["model_revision"]
    uses_biohub_route = "biohub" in route_parts
    if revision_kind == "versioned-managed-model-id" and not uses_biohub_route:
        raise ValidationError("managed model provenance requires the Biohub execution route")
    if uses_biohub_route and model_id is not None and revision_kind != "versioned-managed-model-id":
        raise ValidationError("Biohub provenance requires a supported managed model ID")
    if revision_kind == "not-applicable":
        if model_id is not None or model_revision is not None:
            raise ValidationError("not-applicable model provenance requires null model fields")
    elif revision_kind == "hugging-face-commit":
        if model_id not in ALL_HF_REVISIONS or model_revision != ALL_HF_REVISIONS[model_id]:
            raise ValidationError("Hugging Face model provenance does not match a validated pin")
    elif revision_kind == "versioned-managed-model-id":
        if model_id not in MANAGED_MODEL_IDS or model_revision != model_id:
            raise ValidationError("managed model provenance requires its exact versioned ID")
    elif (
        not isinstance(model_id, str)
        or not model_id.strip()
        or not isinstance(model_revision, str)
        or not model_revision.strip()
        or model_id in ALL_HF_REVISIONS
        or model_id in MANAGED_MODEL_IDS
    ):
        raise ValidationError("explicit model provenance requires a non-managed ID and revision")
    for field in ("esm_git_revision", "transformers_git_revision"):
        revision = value[field]
        if revision is not None and not GIT_SHA_RE.fullmatch(str(revision)):
            raise ValidationError(f"provenance {field} must be null or a full commit SHA")
    if not isinstance(value["artifacts"], list):
        raise ValidationError("provenance artifacts must be a list")
    for artifact in value["artifacts"]:
        if not isinstance(artifact, dict):
            raise ValidationError("each provenance artifact must be an object")
        if not isinstance(artifact.get("path"), str) or not artifact["path"].strip():
            raise ValidationError("each provenance artifact requires a path")
        size = artifact.get("size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValidationError("each provenance artifact requires a nonnegative size")
        if not isinstance(artifact.get("media_type"), str) or not artifact["media_type"].strip():
            raise ValidationError("each provenance artifact requires a media type")
        if not SHA256_RE.fullmatch(str(artifact.get("sha256", ""))):
            raise ValidationError("each provenance artifact requires a SHA-256 checksum")
    if not isinstance(value["parameters"], dict) or not isinstance(
        value["confidence_metrics"], dict
    ):
        raise ValidationError("provenance parameters and confidence_metrics must be objects")


def materialize_pdb_fields(
    payload: Any,
    output_dir: Path,
    *,
    prefix: str,
    artifact_publisher: Callable[[Path, bytes, str], dict[str, Any]] | None = None,
) -> tuple[Any, list[dict[str, Any]]]:
    """Replace embedded PDB strings with checksummed artifact references."""

    planned_artifacts = 0
    planned_bytes = 0

    def preflight(value: Any) -> None:
        nonlocal planned_artifacts, planned_bytes
        if isinstance(value, dict):
            if "pdb_artifact" in value:
                raise SchemaDriftError(
                    "provider response contains reserved pdb_artifact",
                    raw=value,
                )
            pdb = value.get("pdb")
            if isinstance(pdb, str) and pdb.strip():
                try:
                    pdb_size = len(pdb.encode("utf-8"))
                except UnicodeEncodeError as exc:
                    raise SchemaDriftError(
                        "provider embedded PDB is not valid UTF-8 text",
                        raw=value,
                    ) from exc
                planned_artifacts += 1
                planned_bytes += pdb_size
                if planned_artifacts > MATERIALIZED_PDB_MAX_ARTIFACTS:
                    raise SchemaDriftError(
                        "provider response exceeds the embedded PDB artifact-count limit",
                        raw=value,
                    )
                if planned_bytes > MATERIALIZED_PDB_MAX_TOTAL_BYTES:
                    raise SchemaDriftError(
                        "provider response exceeds the embedded PDB byte limit",
                        raw=value,
                    )
            for item in value.values():
                preflight(item)
        elif isinstance(value, list):
            for item in value:
                preflight(item)

    # Reject every collision before writing the first coordinate artifact. A
    # later nested collision must not leave an earlier sibling partially
    # materialized on disk.
    preflight(payload)

    artifacts: list[dict[str, Any]] = []
    counter = 0

    def visit(value: Any) -> Any:
        nonlocal counter
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                if key == "pdb" and isinstance(item, str) and item.strip():
                    counter += 1
                    path = output_dir / f"{prefix}-{counter}.pdb"
                    encoded = item.encode("utf-8")
                    if artifact_publisher is None:
                        write_bytes_atomic(path, encoded)
                        record = artifact_record(path, media_type="chemical/x-pdb")
                    else:
                        record = artifact_publisher(path, encoded, "chemical/x-pdb")
                    record["evidence_class"] = "model_hypothesis"
                    artifacts.append(record)
                    result["pdb_artifact"] = record
                else:
                    result[key] = visit(item)
            return result
        if isinstance(value, list):
            return [visit(item) for item in value]
        return value

    return visit(payload), artifacts

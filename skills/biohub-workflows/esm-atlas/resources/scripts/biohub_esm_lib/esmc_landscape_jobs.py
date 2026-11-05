"""Durable, request-bound checkpoints for managed ESMC landscapes."""

from __future__ import annotations

import json
import fcntl
import math
import os
import stat
import time
from pathlib import Path
from typing import Any

from .errors import APIError, ValidationError
from .provenance import (
    canonical_json,
    sha256_file,
    utc_now,
    write_json_atomic,
    write_json_atomic_noreplace,
)

STATE_SCHEMA_VERSION = "1.0"
STATE_FILENAME = "landscape-state.json"
CHECKPOINT_DIRECTORY = ".landscape-checkpoints"
LOCK_FILENAME = ".landscape.lock"
SAFE_REJECTION_STATUSES = frozenset({400, 401, 402, 403, 404, 422, 429})
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_CHECKPOINT_BYTES = 64 * 1024 * 1024


def _load_json_file(path: Path, *, max_bytes: int, field: str) -> Any:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValidationError(f"could not read {field}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            raise ValidationError(f"{field} is not a safe bounded regular file")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ValidationError(f"{field} changed while it was read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValidationError(f"{field} changed while it was read")
    except OSError as exc:
        raise ValidationError(f"could not read {field}") from exc
    finally:
        os.close(descriptor)
    try:
        value = json.loads(b"".join(chunks))
        canonical_json(value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must contain finite interoperable JSON") from exc
    return value


def _acquire_lock(output_dir: Path) -> int:
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(output_dir / LOCK_FILENAME, flags, 0o600)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValidationError("ESMC landscape lock is not a safe regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise ValidationError("another ESMC landscape process owns this output directory") from exc
    except Exception:
        if "descriptor" in locals():
            os.close(descriptor)
        raise
    return descriptor


class ESMCLandscapeStore:
    """Own one landscape's durable state while the caller holds its lock."""

    def __init__(
        self,
        output_dir: Path,
        binding: dict[str, Any],
        state: dict[str, Any],
        lock_descriptor: int,
    ):
        self.output_dir = output_dir
        self.binding = binding
        self.state_path = output_dir / STATE_FILENAME
        self.checkpoint_dir = output_dir / CHECKPOINT_DIRECTORY
        self.state = state
        self._lock_descriptor: int | None = lock_descriptor

    @classmethod
    def create(
        cls,
        output_dir: Path,
        *,
        binding: dict[str, Any],
        request_sha256_by_position: dict[int, str],
    ) -> "ESMCLandscapeStore":
        lock_descriptor = _acquire_lock(output_dir)
        try:
            (output_dir / CHECKPOINT_DIRECTORY).mkdir(mode=0o700, exist_ok=False)
        except OSError as exc:
            os.close(lock_descriptor)
            raise ValidationError(
                "could not create the ESMC landscape checkpoint directory"
            ) from exc
        started_at = utc_now()
        state = {
            "schema_version": STATE_SCHEMA_VERSION,
            "kind": "managed-esmc-landscape",
            "status": "running",
            "binding": binding,
            "started_at": started_at,
            "updated_at": started_at,
            "resume_count": 0,
            "positions": {
                str(position): {
                    "status": "pending",
                    "request_sha256": request_sha256,
                    "attempt_count": 0,
                    "failed_provider_calls": [],
                }
                for position, request_sha256 in request_sha256_by_position.items()
            },
        }
        store = cls(output_dir, binding, state, lock_descriptor)
        try:
            write_json_atomic_noreplace(store.state_path, state)
        except Exception:
            store.close()
            raise
        return store

    @classmethod
    def resume(
        cls,
        output_dir: Path,
        *,
        binding: dict[str, Any],
        request_sha256_by_position: dict[int, str],
    ) -> "ESMCLandscapeStore":
        lock_descriptor = _acquire_lock(output_dir)
        state_path = output_dir / STATE_FILENAME
        try:
            state = _load_json_file(
                state_path,
                max_bytes=MAX_STATE_BYTES,
                field="ESMC landscape state",
            )
        except Exception:
            os.close(lock_descriptor)
            raise
        if not isinstance(state, dict):
            raise ValidationError("ESMC landscape state must be a JSON object")
        if (
            state.get("schema_version") != STATE_SCHEMA_VERSION
            or state.get("kind") != "managed-esmc-landscape"
            or state.get("binding") != binding
        ):
            raise ValidationError(
                "refusing to resume ESMC landscape state that is not bound to this exact request"
            )
        positions = state.get("positions")
        expected_keys = {str(position) for position in request_sha256_by_position}
        if not isinstance(positions, dict) or set(positions) != expected_keys:
            raise ValidationError("ESMC landscape state position set drifted")
        for position, request_sha256 in request_sha256_by_position.items():
            record = positions.get(str(position))
            if (
                not isinstance(record, dict)
                or record.get("request_sha256") != request_sha256
                or record.get("status")
                not in {
                    "pending",
                    "submitting",
                    "completed",
                    "submission-rejected",
                    "submission-indeterminate",
                }
            ):
                raise ValidationError("ESMC landscape state contains an invalid position record")
            attempts = record.get("attempt_count")
            failed_calls = record.get("failed_provider_calls")
            if (
                isinstance(attempts, bool)
                or not isinstance(attempts, int)
                or attempts < 0
                or not isinstance(failed_calls, list)
            ):
                raise ValidationError("ESMC landscape state contains invalid attempt history")
        checkpoint_dir = output_dir / CHECKPOINT_DIRECTORY
        if not checkpoint_dir.is_dir() or checkpoint_dir.is_symlink():
            raise ValidationError("ESMC landscape checkpoint directory is missing or unsafe")
        store = cls(output_dir, binding, state, lock_descriptor)
        try:
            store._reconcile_checkpoints()
            store._validate_resume_safety()
            resume_count = store.state.get("resume_count", 0)
            if (
                isinstance(resume_count, bool)
                or not isinstance(resume_count, int)
                or resume_count < 0
            ):
                raise ValidationError("ESMC landscape resume count is invalid")
            store.state["resume_count"] = resume_count + 1
            store.state["status"] = "running"
            store._persist()
        except Exception:
            store.close()
            raise
        return store

    def close(self) -> None:
        if self._lock_descriptor is not None:
            descriptor = self._lock_descriptor
            self._lock_descriptor = None
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def __del__(self) -> None:
        self.close()

    def _persist(self) -> None:
        self.state["updated_at"] = utc_now()
        write_json_atomic(self.state_path, self.state)

    def _checkpoint_path(self, position: int) -> Path:
        return self.checkpoint_dir / f"{position:06d}.json"

    def _load_checkpoint(self, position: int) -> dict[str, Any]:
        checkpoint = _load_json_file(
            self._checkpoint_path(position),
            max_bytes=MAX_CHECKPOINT_BYTES,
            field=f"ESMC landscape checkpoint {position}",
        )
        record = self.state["positions"][str(position)]
        if (
            not isinstance(checkpoint, dict)
            or checkpoint.get("schema_version") != STATE_SCHEMA_VERSION
            or checkpoint.get("position_one_based") != position
            or checkpoint.get("request_sha256") != record["request_sha256"]
            or checkpoint.get("wild_type") != self.binding["sequence"][position - 1]
            or not isinstance(checkpoint.get("response"), dict)
            or not isinstance(checkpoint.get("provider_calls"), list)
        ):
            raise ValidationError(f"ESMC landscape checkpoint {position} is not request-bound")
        recorded_digest = record.get("checkpoint_sha256")
        actual_digest = sha256_file(self._checkpoint_path(position))
        if recorded_digest is not None and recorded_digest != actual_digest:
            raise ValidationError(f"ESMC landscape checkpoint {position} changed after publication")
        return checkpoint

    def _reconcile_checkpoints(self) -> None:
        changed = False
        for position_text, record in self.state["positions"].items():
            position = int(position_text)
            checkpoint_path = self._checkpoint_path(position)
            if checkpoint_path.exists():
                self._load_checkpoint(position)
                if record["status"] != "completed":
                    record["status"] = "completed"
                    record["checkpoint_sha256"] = sha256_file(checkpoint_path)
                    record.pop("failure", None)
                    record.pop("retry_not_before_epoch_seconds", None)
                    changed = True
            elif record["status"] == "completed":
                raise ValidationError(f"ESMC landscape checkpoint {position} is missing")
        if changed:
            self._persist()

    def _validate_resume_safety(self) -> None:
        for position_text, record in self.state["positions"].items():
            status = record["status"]
            if status in {"submitting", "submission-indeterminate"}:
                raise ValidationError(
                    "refusing to replay ESMC landscape position "
                    f"{position_text}: its prior managed submission may have been accepted"
                )
            retry_not_before = record.get("retry_not_before_epoch_seconds")
            if status == "submission-rejected" and retry_not_before is not None:
                if (
                    isinstance(retry_not_before, bool)
                    or not isinstance(retry_not_before, (int, float))
                    or not math.isfinite(retry_not_before)
                    or retry_not_before < 0
                ):
                    raise ValidationError("ESMC landscape retry deadline is invalid")
                remaining = retry_not_before - time.time()
                if remaining > 0:
                    raise ValidationError(
                        "ESMC landscape position "
                        f"{position_text} is rate-limited; retry --resume in {math.ceil(remaining)}s"
                    )

    def runnable_positions(self) -> list[int]:
        return [
            int(position)
            for position, record in self.state["positions"].items()
            if record["status"] in {"pending", "submission-rejected"}
        ]

    def mark_submitting(self, position: int) -> None:
        record = self.state["positions"][str(position)]
        if record["status"] not in {"pending", "submission-rejected"}:
            raise ValidationError(f"ESMC landscape position {position} is not safe to submit")
        record["status"] = "submitting"
        record["attempt_count"] += 1
        record["submitted_at"] = utc_now()
        record.pop("failure", None)
        record.pop("retry_not_before_epoch_seconds", None)
        self._persist()

    def record_success(
        self,
        position: int,
        *,
        wild_type: str,
        response: dict[str, Any],
        provider_calls: list[dict[str, Any]],
    ) -> None:
        record = self.state["positions"][str(position)]
        checkpoint = {
            "schema_version": STATE_SCHEMA_VERSION,
            "position_one_based": position,
            "wild_type": wild_type,
            "request_sha256": record["request_sha256"],
            "completed_at": utc_now(),
            "response": response,
            "provider_calls": provider_calls,
        }
        checkpoint_path = self._checkpoint_path(position)
        try:
            write_json_atomic_noreplace(checkpoint_path, checkpoint)
        except ValidationError:
            self._load_checkpoint(position)
        record["checkpoint_sha256"] = sha256_file(checkpoint_path)
        record["status"] = "completed"
        record.pop("failure", None)
        self._persist()

    def record_failure(
        self,
        position: int,
        *,
        error: Exception,
        provider_calls: list[dict[str, Any]],
    ) -> None:
        record = self.state["positions"][str(position)]
        record["failed_provider_calls"].extend(provider_calls)
        status = getattr(error, "status", None)
        if status is None:
            status = getattr(error, "provider_status", None)
        if status is None and provider_calls:
            status = provider_calls[-1].get("http_status")
        operation_indeterminate = not (
            isinstance(status, int)
            and not isinstance(status, bool)
            and status in SAFE_REJECTION_STATUSES
            and not (isinstance(error, APIError) and error.operation_indeterminate)
        )
        record["status"] = (
            "submission-indeterminate" if operation_indeterminate else "submission-rejected"
        )
        failure: dict[str, Any] = {
            "kind": getattr(error, "kind", error.__class__.__name__),
            "message": str(error),
            "status": status,
            "operation_indeterminate": operation_indeterminate,
        }
        retry_after = getattr(error, "retry_after", None)
        if (
            not operation_indeterminate
            and status == 429
            and isinstance(retry_after, (int, float))
            and not isinstance(retry_after, bool)
            and math.isfinite(retry_after)
            and retry_after >= 0
        ):
            failure["retry_after"] = retry_after
            record["retry_not_before_epoch_seconds"] = time.time() + retry_after
        record["failure"] = failure
        self.state["status"] = "incomplete"
        self._persist()

    def completed_outcomes(self) -> list[dict[str, Any]]:
        outcomes: list[dict[str, Any]] = []
        for position_text, record in self.state["positions"].items():
            if record["status"] != "completed":
                continue
            checkpoint = self._load_checkpoint(int(position_text))
            outcomes.append(
                {
                    "position_one_based": checkpoint["position_one_based"],
                    "wild_type": checkpoint["wild_type"],
                    "response": checkpoint["response"],
                    "provider_calls": checkpoint["provider_calls"],
                }
            )
        outcomes.sort(key=lambda item: item["position_one_based"])
        return outcomes

    def provider_calls(self) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for position_text in sorted(self.state["positions"], key=int):
            position = int(position_text)
            record = self.state["positions"][position_text]
            calls.extend(record["failed_provider_calls"])
            if record["status"] == "completed":
                calls.extend(self._load_checkpoint(position)["provider_calls"])
        return calls

    def positions_with_status(self, *statuses: str) -> list[int]:
        return [
            int(position)
            for position, record in self.state["positions"].items()
            if record["status"] in statuses
        ]

    def mark_finalized(self) -> None:
        if self.positions_with_status(
            "pending", "submitting", "submission-rejected", "submission-indeterminate"
        ):
            raise ValidationError("cannot finalize an incomplete ESMC landscape")
        self.state["status"] = "complete"
        self.state["completed_at"] = utc_now()
        self._persist()

"""Durable, credential-safe state for public Atlas batch jobs."""

from __future__ import annotations

import fcntl
import json
import math
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable

from .atlas import validate_job_id
from .diagnostics import (
    DIAGNOSTIC_MAX_COLLECTION_ITEMS,
    bounded_provider_response_diagnostic,
)
from .errors import APIError, BiohubESMError, SchemaDriftError, ValidationError
from .provenance import input_digest, utc_now, write_json_atomic
from .security import redact

ATLAS_BATCH_STATE_SCHEMA = "1.1"
ATLAS_BATCH_LEGACY_SCHEMAS = {"1.0"}
ATLAS_BATCH_PROVIDER = "biohub-esm-atlas-v1alpha1"
ATLAS_BATCH_PROVIDER_CALL_HISTORY_LIMIT = 256
ATLAS_DEFINITIVE_SUBMISSION_REJECTION_STATUSES = {400, 401, 402, 403, 404, 422, 429}
ATLAS_BATCH_STATE_MAX_BYTES = 4 * 1024 * 1024
ATLAS_BATCH_ARTIFACT_LIMIT = 2_048
ATLAS_BATCH_STATE_MAX_NUMBER_CHARACTERS = 128
ATLAS_BATCH_TERMINAL_STATUSES = {"completed", "cancelled", "failed", "expired"}
ATLAS_BATCH_STATUSES = {
    "submitting",
    "submission-rejected",
    "submission-indeterminate",
    "pending",
    "completed",
    "cancelled",
    "cancellation-requested",
    "failed",
    "expired",
}


def _submission_reconciliation_guidance(provider_acceptance: str) -> str:
    prefix = {
        "accepted": "Provider acceptance was confirmed, but no job_id was durably captured. ",
        "not-proven": "The provider returned an error, but remote side effects were not proven. ",
        "unknown": "Provider acceptance is unknown and no job_id was durably captured. ",
    }.get(provider_acceptance)
    if prefix is None:
        raise ValidationError("Atlas submission acceptance reconciliation is invalid")
    return prefix + "Reconcile with Atlas operators before any new submission."


@contextmanager
def atlas_batch_sink_preparer(
    client: Any,
    *,
    temporary_file: Callable[..., BinaryIO],
) -> Iterator[Callable[[], BinaryIO | None]]:
    """Lazily reserve an anonymous sink before any durable submit transition."""

    handle: BinaryIO | None = None

    def prepare() -> BinaryIO | None:
        nonlocal handle
        if getattr(client, "_supports_synchronous_sink", False) is not True:
            return None
        if handle is None:
            try:
                handle = temporary_file(mode="w+b")
            except OSError as exc:
                raise ValidationError(
                    "Atlas synchronous response spool could not be created"
                ) from exc
        return handle

    active_failure: BaseException | None = None
    try:
        yield prepare
    except BaseException as exc:
        active_failure = exc
        raise
    finally:
        if handle is not None and not handle.closed:
            try:
                handle.close()
            except (OSError, ValueError) as exc:
                if active_failure is None:
                    raise ValidationError(
                        "Atlas synchronous response spool could not be closed"
                    ) from exc


def _batch_provider_call(
    *, endpoint: str, operation: str, http_status: int | None
) -> dict[str, Any]:
    call = {
        "endpoint": endpoint,
        "operation": operation,
        "http_status": http_status,
        "timestamp": utc_now(),
    }
    if http_status is not None:
        if http_status < 200:
            call["outcome"] = "indeterminate"
            call["operation_indeterminate"] = True
        else:
            call["outcome"] = "success"
            call["operation_indeterminate"] = False
    return call


def _atlas_exception_provider_call(
    client: Any,
    *,
    endpoint: str,
    operation: str,
    exc: BaseException,
) -> dict[str, Any]:
    error_http_status = getattr(exc, "status", None)
    if error_http_status is None:
        error_http_status = getattr(exc, "provider_status", None)
    if (
        isinstance(error_http_status, bool)
        or not isinstance(error_http_status, int)
        or not 100 <= error_http_status <= 599
    ):
        error_http_status = None
    calls = getattr(client, "provider_calls", None)
    matching_call = None
    if isinstance(calls, list):
        matching_call = next(
            (
                candidate
                for candidate in reversed(calls)
                if isinstance(candidate, dict) and candidate.get("endpoint") == endpoint
            ),
            None,
        )
    if matching_call is None:
        call = _batch_provider_call(
            endpoint=endpoint,
            operation=operation,
            http_status=error_http_status,
        )
    else:
        call = dict(matching_call)
    if error_http_status is None:
        candidate_status = call.get("http_status")
        if (
            isinstance(candidate_status, int)
            and not isinstance(candidate_status, bool)
            and 100 <= candidate_status <= 599
        ):
            error_http_status = candidate_status
    if isinstance(exc, BiohubESMError) and error_http_status is not None:
        exc.provider_status = error_http_status
    if isinstance(exc, APIError) and error_http_status is not None:
        if error_http_status < 200:
            exc.operation_indeterminate = True
            exc.response_body_partial = True
        else:
            exc.operation_indeterminate = False
    call["endpoint"] = endpoint
    call["operation"] = operation
    call["error_kind"] = getattr(exc, "kind", exc.__class__.__name__)
    if isinstance(exc, APIError):
        if error_http_status is not None:
            call["http_status"] = error_http_status
        call.pop("retry_after", None)
        call.update(
            {
                "outcome": ("indeterminate" if exc.operation_indeterminate else "error"),
                "partial": exc.partial,
                "response_body_partial": exc.response_body_partial,
                "operation_indeterminate": exc.operation_indeterminate,
            }
        )
        if exc.retry_after is not None:
            call["retry_after"] = exc.retry_after
    elif isinstance(exc, BiohubESMError):
        if call.get("http_status") is None and error_http_status is not None:
            call["http_status"] = error_http_status
        operation_indeterminate = bool(getattr(exc, "operation_indeterminate", False))
        call["outcome"] = "indeterminate" if operation_indeterminate else "error"
        call["operation_indeterminate"] = operation_indeterminate
        call["partial"] = bool(getattr(exc, "partial", False))
    else:
        operation_indeterminate = error_http_status is None or error_http_status < 200
        if error_http_status is not None:
            call["http_status"] = error_http_status
        call["outcome"] = "indeterminate" if operation_indeterminate else "error"
        call["operation_indeterminate"] = operation_indeterminate
    return call


def _atlas_failure_record(exc: BiohubESMError) -> dict[str, Any]:
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
        provider_status = getattr(exc, "provider_status", None)
        if (
            isinstance(provider_status, int)
            and not isinstance(provider_status, bool)
            and 100 <= provider_status <= 599
        ):
            failure["provider_status"] = provider_status
    if isinstance(exc, SchemaDriftError) and exc.diagnostic_path:
        failure["diagnostic_path"] = exc.diagnostic_path
    return redact(failure)


def _utc_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValidationError(f"Atlas batch {field} must be a UTC timestamp")
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError(f"Atlas batch {field} must be a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValidationError(f"Atlas batch {field} must be a UTC timestamp")
    return parsed


def _utc_string(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_state_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _bounded_state_json_int(value: str) -> int:
    if len(value) > ATLAS_BATCH_STATE_MAX_NUMBER_CHARACTERS:
        raise ValueError("Atlas batch state integer exceeds the numeric safety bound")
    return int(value)


def _finite_state_json_float(value: str) -> float:
    if len(value) > ATLAS_BATCH_STATE_MAX_NUMBER_CHARACTERS:
        raise ValueError("Atlas batch state float exceeds the numeric safety bound")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Atlas batch state contains a non-finite number")
    mantissa = value.lower().split("e", 1)[0]
    if result == 0.0 and any(character in "123456789" for character in mantissa):
        raise ValueError("Atlas batch state number underflows the finite float range")
    return result


_RESPONSE_PRIORITY_KEYS = (
    "job_id",
    "status",
    "delivery",
    "completed_count",
    "total_count",
    "download_url",
    "artifact_materialization",
    "download",
    "provider_call_result",
    "provider_acceptance",
    "retry_safe",
    "retry_after",
    "retry_not_before",
    "reason",
    "retry",
    "intent_persisted",
)


def _omit_download_capabilities(value: dict[str, Any]) -> None:
    """Remove capabilities from an already bounded diagnostic projection."""

    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                if key.lower() == "download_url":
                    item[key] = "[EPHEMERAL URL OMITTED]"
                elif isinstance(child, (dict, list)):
                    stack.append(child)
        elif isinstance(item, list):
            stack.extend(child for child in item if isinstance(child, (dict, list)))


def _safe_response(value: dict[str, Any]) -> dict[str, Any]:
    """Keep bounded alpha-schema diagnostics and required local state semantics."""

    prioritized: dict[str, Any] = {}
    for key in _RESPONSE_PRIORITY_KEYS:
        if key in value:
            prioritized[key] = value[key]
    for key, child in value.items():
        text_key = str(key)
        if text_key in prioritized:
            continue
        if len(prioritized) >= DIAGNOSTIC_MAX_COLLECTION_ITEMS:
            break
        prioritized[text_key] = child

    diagnostic = bounded_provider_response_diagnostic(prioritized)
    sanitized = diagnostic.get("projection")
    if not isinstance(sanitized, dict):  # pragma: no cover - defensive
        raise ValidationError("Atlas batch response must be an object")
    _omit_download_capabilities(sanitized)
    source_truncated = len(value) > len(prioritized)
    if diagnostic.get("truncated") or source_truncated:
        reasons = set(diagnostic.get("truncation_reasons", []))
        if source_truncated:
            reasons.add("collection-item-limit")
        sanitized["response_diagnostic"] = {
            "representation": diagnostic.get("representation"),
            "truncated": True,
            "truncation_reasons": sorted(reasons),
            "visited_nodes": diagnostic.get("visited_nodes"),
            "retained_text_bytes": diagnostic.get("retained_text_bytes"),
            "projection_sha256": diagnostic.get("projection_sha256"),
        }
    return sanitized


_PROVIDER_CALL_PRIORITY_KEYS = (
    "endpoint",
    "operation",
    "method",
    "outcome",
    "http_status",
    "started_at",
    "finished_at",
    "timestamp",
    "error_kind",
    "partial",
    "response_body_partial",
    "operation_indeterminate",
    "retry_after",
    "transport_attempts",
    "resume_recovery",
    "observed_status",
    "state_status_before",
    "state_status_after",
    "transition_ignored",
    "error",
)
_ARTIFACT_KEYS = (
    "path",
    "size_bytes",
    "media_type",
    "sha256",
    "evidence_class",
)


def _safe_provider_call(value: dict[str, Any]) -> dict[str, Any]:
    prioritized: dict[str, Any] = {}
    for key in _PROVIDER_CALL_PRIORITY_KEYS:
        if key in value:
            prioritized[key] = value[key]
    for key, child in value.items():
        text_key = str(key)
        if text_key in prioritized:
            continue
        if len(prioritized) >= DIAGNOSTIC_MAX_COLLECTION_ITEMS:
            break
        prioritized[text_key] = child
    safe = bounded_provider_response_diagnostic(prioritized).get("projection")
    if (
        not isinstance(safe, dict)
        or not isinstance(safe.get("endpoint"), str)
        or not safe["endpoint"].strip()
        or not isinstance(safe.get("operation"), str)
        or not safe["operation"].strip()
    ):
        raise ValidationError("Atlas batch provider call requires endpoint and operation")
    http_status = safe.get("http_status")
    if http_status is not None and (
        isinstance(http_status, bool)
        or not isinstance(http_status, int)
        or not 100 <= http_status <= 599
    ):
        raise ValidationError("Atlas batch provider call HTTP status is invalid")
    for boolean_field in (
        "partial",
        "response_body_partial",
        "operation_indeterminate",
    ):
        if boolean_field in safe and not isinstance(safe[boolean_field], bool):
            raise ValidationError(f"Atlas batch provider call {boolean_field} must be boolean")
    operation_indeterminate = safe.get("operation_indeterminate")
    outcome = safe.get("outcome")
    if operation_indeterminate is True and outcome != "indeterminate":
        raise ValidationError(
            "Atlas batch indeterminate provider call must have indeterminate outcome"
        )
    if outcome == "indeterminate" and operation_indeterminate is not True:
        raise ValidationError("Atlas batch indeterminate outcome requires operation indeterminacy")
    if operation_indeterminate is True and http_status is not None and http_status >= 200:
        raise ValidationError(
            "Atlas batch provider call with final HTTP status cannot be indeterminate"
        )
    if (
        isinstance(http_status, int)
        and 100 <= http_status < 200
        and (outcome != "indeterminate" or operation_indeterminate is not True)
    ):
        raise ValidationError(
            "Atlas batch informational status requires an indeterminate provider call"
        )
    return safe


def _state_value_changed(before: Any, after: Any) -> bool:
    try:
        return before != after
    except (RecursionError, MemoryError):
        return True


def _sanitize_state_collections(
    value: dict[str, Any], *, normalize_missing_indeterminate: bool = False
) -> bool:
    changed = False
    calls = value.get("provider_calls")
    if isinstance(calls, list):
        safe_calls = []
        certainty_migrated = False
        for call in calls:
            candidate = dict(call) if isinstance(call, dict) else call
            if normalize_missing_indeterminate and isinstance(candidate, dict):
                call_status = candidate.get("http_status")
                operation = candidate.get("operation")
                outcome = candidate.get("outcome")
                informational = (
                    isinstance(call_status, int)
                    and not isinstance(call_status, bool)
                    and 100 <= call_status < 200
                )
                final_status = (
                    isinstance(call_status, int)
                    and not isinstance(call_status, bool)
                    and call_status >= 200
                )
                if informational and (
                    outcome != "indeterminate"
                    or candidate.get("operation_indeterminate") is not True
                ):
                    candidate["outcome"] = "indeterminate"
                    candidate["operation_indeterminate"] = True
                    candidate["certainty_normalized_from_legacy"] = True
                    certainty_migrated = True
                elif outcome == "indeterminate" and final_status:
                    candidate["outcome"] = (
                        "accepted"
                        if operation in {"submit", "cancel"} and call_status < 300
                        else "error"
                    )
                    candidate["operation_indeterminate"] = False
                    candidate["certainty_normalized_from_legacy"] = True
                    certainty_migrated = True
                elif (
                    outcome == "indeterminate"
                    and candidate.get("operation_indeterminate") is not True
                ):
                    candidate["operation_indeterminate"] = True
                    candidate["certainty_normalized_from_legacy"] = True
                    certainty_migrated = True
            safe_calls.append(
                _safe_provider_call(candidate) if isinstance(candidate, dict) else candidate
            )
        changed = _state_value_changed(calls, safe_calls) or changed
        value["provider_calls"] = safe_calls
        if (
            normalize_missing_indeterminate
            and certainty_migrated
            and value.get("status") == "submission-indeterminate"
        ):
            latest_submit = next(
                (
                    call
                    for call in reversed(safe_calls)
                    if isinstance(call, dict) and call.get("operation") == "submit"
                ),
                None,
            )
            reconciliation = value.get("manual_reconciliation")
            if isinstance(latest_submit, dict) and isinstance(reconciliation, dict):
                provider_acceptance = {
                    "accepted": "accepted",
                    "error": "not-proven",
                    "indeterminate": "unknown",
                }.get(latest_submit.get("outcome"))
                call_status = latest_submit.get("http_status")
                legacy_definitive_rejection = (
                    latest_submit.get("outcome") == "error"
                    and call_status in ATLAS_DEFINITIVE_SUBMISSION_REJECTION_STATUSES
                )
                if legacy_definitive_rejection:
                    normalized_reconciliation = dict(reconciliation)
                    normalized_reconciliation.pop("provider_acceptance", None)
                    normalized_reconciliation["guidance"] = (
                        "The provider returned a definitive rejection, but this legacy "
                        "indeterminate record remains do-not-resubmit until Atlas operators "
                        "reconcile it."
                    )
                    changed = (
                        _state_value_changed(reconciliation, normalized_reconciliation) or changed
                    )
                    value["manual_reconciliation"] = normalized_reconciliation
                elif provider_acceptance is not None:
                    normalized_reconciliation = dict(reconciliation)
                    normalized_reconciliation["provider_acceptance"] = provider_acceptance
                    normalized_reconciliation["guidance"] = _submission_reconciliation_guidance(
                        provider_acceptance
                    )
                    changed = (
                        _state_value_changed(reconciliation, normalized_reconciliation) or changed
                    )
                    value["manual_reconciliation"] = normalized_reconciliation
                normalized_status = latest_submit.get("http_status")
                changed = (
                    _state_value_changed(value.get("last_http_status"), normalized_status)
                    or changed
                )
                value["last_http_status"] = normalized_status
        if (
            normalize_missing_indeterminate
            and certainty_migrated
            and value.get("status") == "cancellation-requested"
        ):
            latest_cancel = next(
                (
                    call
                    for call in reversed(safe_calls)
                    if isinstance(call, dict) and call.get("operation") == "cancel"
                ),
                None,
            )
            latest_call = safe_calls[-1] if safe_calls else None
            if (
                latest_cancel is latest_call
                and isinstance(latest_cancel, dict)
                and latest_cancel.get("outcome")
                in {
                    "accepted",
                    "error",
                }
            ):
                response = value.get("last_response")
                if isinstance(response, dict):
                    normalized_response = dict(response)
                    normalized_response["provider_acceptance"] = (
                        "confirmed" if latest_cancel["outcome"] == "accepted" else "rejected"
                    )
                    normalized_response["retry_safe"] = latest_cancel["outcome"] != "accepted"
                    changed = _state_value_changed(response, normalized_response) or changed
                    value["last_response"] = normalized_response
                normalized_status = latest_cancel.get("http_status")
                changed = (
                    _state_value_changed(value.get("last_http_status"), normalized_status)
                    or changed
                )
                value["last_http_status"] = normalized_status
    artifacts = value.get("artifacts")
    if isinstance(artifacts, list):
        if len(artifacts) > ATLAS_BATCH_ARTIFACT_LIMIT:
            raise ValidationError("Atlas batch artifact history exceeds the safety limit")
        safe_artifacts = [
            {key: artifact[key] for key in _ARTIFACT_KEYS if key in artifact}
            if isinstance(artifact, dict)
            else artifact
            for artifact in artifacts
        ]
        changed = _state_value_changed(artifacts, safe_artifacts) or changed
        value["artifacts"] = safe_artifacts
    response = value.get("last_response")
    if isinstance(response, dict):
        safe_response = _safe_response(response)
        changed = _state_value_changed(response, safe_response) or changed
        value["last_response"] = safe_response
    return changed


def _state_json_exceeds_limit(value: dict[str, Any]) -> bool:
    encoder = json.JSONEncoder(
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )
    size = 1
    for chunk in encoder.iterencode(value):
        size += len(chunk.encode("utf-8"))
        if size > ATLAS_BATCH_STATE_MAX_BYTES:
            return True
    return False


def _increment_history_count(counts: dict[str, int], value: Any) -> None:
    key = str(value) if value is not None else "unspecified"
    counts[key] = counts.get(key, 0) + 1


def _validated_provider_call_history(
    history: Any,
) -> tuple[int, str, dict[str, int], dict[str, int]]:
    required = {
        "schema_version",
        "compacted_call_count",
        "chain_sha256",
        "operation_counts",
        "outcome_counts",
    }
    if not isinstance(history, dict) or set(history) != required:
        raise ValidationError("Atlas batch provider call history is invalid")
    count = history.get("compacted_call_count")
    chain_sha256 = history.get("chain_sha256")
    if (
        history.get("schema_version") != "1.0"
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 1
        or not isinstance(chain_sha256, str)
        or len(chain_sha256) != 64
        or any(character not in "0123456789abcdef" for character in chain_sha256)
    ):
        raise ValidationError("Atlas batch provider call history is invalid")
    validated_counts: list[dict[str, int]] = []
    for field in ("operation_counts", "outcome_counts"):
        counts = history.get(field)
        if not isinstance(counts, dict) or any(
            not isinstance(key, str)
            or not key
            or isinstance(item_count, bool)
            or not isinstance(item_count, int)
            or item_count < 0
            for key, item_count in counts.items()
        ):
            raise ValidationError(f"Atlas batch provider call history {field} is invalid")
        if sum(counts.values()) != count:
            raise ValidationError(f"Atlas batch compacted {field} count is inconsistent")
        validated_counts.append(dict(counts))
    return count, chain_sha256, validated_counts[0], validated_counts[1]


def _semantic_provider_call_indices(value: dict[str, Any], calls: list[Any]) -> set[int]:
    """Retain calls still required to reconcile the durable control state."""

    status = value.get("status")
    required: set[int] = set()
    if status in {"submitting", "submission-rejected", "submission-indeterminate"}:
        for index in range(len(calls) - 1, -1, -1):
            call = calls[index]
            if isinstance(call, dict) and call.get("operation") == "submit":
                required.add(index)
                break
    if status == "cancellation-requested":
        for index in range(len(calls) - 1, -1, -1):
            call = calls[index]
            if not isinstance(call, dict) or call.get("operation") != "cancel":
                continue
            if call.get("outcome") in {"in-flight", "error", "indeterminate"}:
                required.add(index)
            break
    return required


def _compact_provider_calls(value: dict[str, Any]) -> bool:
    """Bound retained attempts while chaining deterministic evidence for older calls."""

    calls = value.get("provider_calls")
    limit = ATLAS_BATCH_PROVIDER_CALL_HISTORY_LIMIT
    if not isinstance(calls, list):
        return False
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValidationError("Atlas batch provider call history limit is invalid")
    if len(calls) <= limit:
        return False
    retained_indices = _semantic_provider_call_indices(value, calls)
    for index in range(len(calls) - 1, -1, -1):
        if len(retained_indices) >= limit:
            break
        retained_indices.add(index)
    dropped = [call for index, call in enumerate(calls) if index not in retained_indices]
    retained = [call for index, call in enumerate(calls) if index in retained_indices]
    existing = value.get("provider_call_history")
    if existing is None:
        count = 0
        previous_sha256 = "0" * 64
        operation_counts: dict[str, int] = {}
        outcome_counts: dict[str, int] = {}
    else:
        count, previous_sha256, operation_counts, outcome_counts = _validated_provider_call_history(
            existing
        )
    for call in dropped:
        if not isinstance(call, dict):
            raise ValidationError("Atlas batch provider calls must be objects")
        _increment_history_count(operation_counts, call.get("operation"))
        _increment_history_count(outcome_counts, call.get("outcome"))
    value["provider_call_history"] = {
        "schema_version": "1.0",
        "compacted_call_count": count + len(dropped),
        "chain_sha256": input_digest(
            {
                "previous_chain_sha256": previous_sha256,
                "compacted_calls": dropped,
            }
        ),
        "operation_counts": operation_counts,
        "outcome_counts": outcome_counts,
    }
    value["provider_calls"] = retained
    return True


class AtlasBatchStore:
    """Atomic, locked job-state persistence suitable across CLI invocations."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._thread_lock = threading.RLock()
        self._lock_depth = 0

    @property
    def provenance_path(self) -> Path:
        return self.path.with_name(f"{self.path.stem}.provenance.json")

    @property
    def lock_path(self) -> Path:
        return self.path.with_name(f".{self.path.name}.lock")

    @contextmanager
    def operation_lock(self, *, deadline: float | None = None) -> Iterator[None]:
        """Serialize one state/provider/provenance operation per durable path.

        The thread lock makes the flock safely reentrant for methods called by a
        command that already owns the operation lock. Separately constructed
        stores and other processes still contend on the same lock file. When a
        monotonic deadline is supplied, both contention points are bounded.
        """

        if deadline is not None and (
            isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or not math.isfinite(deadline)
        ):
            raise ValidationError("Atlas batch operation deadline must be finite")

        if deadline is None:
            acquired = self._thread_lock.acquire()
        else:
            remaining = deadline - time.monotonic()
            acquired = (
                self._thread_lock.acquire(blocking=False)
                if remaining <= 0
                else self._thread_lock.acquire(timeout=min(remaining, threading.TIMEOUT_MAX))
            )
        if not acquired:
            raise APIError(
                status=None,
                kind="timeout",
                message="Atlas batch operation lock timed out",
            )

        try:
            if self._lock_depth:
                self._lock_depth += 1
                try:
                    yield
                finally:
                    self._lock_depth -= 1
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+b") as handle:
                if deadline is None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                else:
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise APIError(
                                status=None,
                                kind="timeout",
                                message="Atlas batch operation lock timed out",
                            )
                        try:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            time.sleep(min(0.01, remaining))
                self._lock_depth = 1
                try:
                    yield
                finally:
                    self._lock_depth = 0
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._thread_lock.release()

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.is_file():
            raise ValidationError(f"Atlas batch state does not exist: {self.path}")
        try:
            with self.path.open("rb") as handle:
                encoded = handle.read(ATLAS_BATCH_STATE_MAX_BYTES + 1)
            if len(encoded) > ATLAS_BATCH_STATE_MAX_BYTES:
                raise ValidationError("Atlas batch state exceeds the file-size safety limit")
            value = json.loads(
                encoded.decode("utf-8"),
                parse_constant=_reject_state_json_constant,
                parse_float=_finite_state_json_float,
                parse_int=_bounded_state_json_int,
            )
        except ValidationError:
            raise
        except (OSError, UnicodeDecodeError, ValueError, RecursionError, MemoryError) as exc:
            raise ValidationError("Atlas batch state is not readable JSON") from exc
        if not isinstance(value, dict):
            raise ValidationError("Atlas batch state must be a JSON object")
        sanitized = _sanitize_state_collections(
            value,
            normalize_missing_indeterminate=True,
        )
        compacted = _compact_provider_calls(value)
        self.validate(value)
        if sanitized or compacted:
            return self._save_unlocked(value)
        return value

    def load(self) -> dict[str, Any]:
        with self.operation_lock():
            value = self._load_unlocked()
            if value["status"] == "submitting":
                value = self._mark_submission_indeterminate_unlocked(
                    value, "process ended during Atlas batch submission"
                )
            elif value["status"] == "cancellation-requested" and any(
                call.get("operation") == "cancel" and call.get("outcome") == "in-flight"
                for call in reversed(value["provider_calls"])
            ):
                value = self._mark_cancellation_indeterminate_unlocked(value)
            return value

    def _save_unlocked(self, value: dict[str, Any]) -> dict[str, Any]:
        _sanitize_state_collections(value)
        _compact_provider_calls(value)
        safe = redact(value)
        if not isinstance(safe, dict):  # pragma: no cover - defensive
            raise ValidationError("Atlas batch state must remain an object")
        safe["schema_version"] = ATLAS_BATCH_STATE_SCHEMA
        self.validate(safe)
        if _state_json_exceeds_limit(safe):
            raise ValidationError("Atlas batch state exceeds the file-size safety limit")
        write_json_atomic(self.path, safe)
        return safe

    def save(self, value: dict[str, Any]) -> dict[str, Any]:
        with self.operation_lock():
            return self._save_unlocked(value)

    @staticmethod
    def validate(value: Any) -> None:
        if not isinstance(value, dict):
            raise ValidationError("Atlas batch state must be a JSON object")
        required = {
            "schema_version",
            "provider",
            "job_id",
            "status",
            "submitted_at",
            "updated_at",
            "endpoint",
            "request",
            "last_http_status",
            "last_response",
            "provider_calls",
            "artifacts",
            "provenance_path",
        }
        missing = sorted(required - set(value))
        if missing:
            raise ValidationError(f"Atlas batch state is missing: {', '.join(missing)}")
        if value["schema_version"] not in {
            ATLAS_BATCH_STATE_SCHEMA,
            *ATLAS_BATCH_LEGACY_SCHEMAS,
        }:
            raise ValidationError("unsupported Atlas batch state schema")
        if value["provider"] != ATLAS_BATCH_PROVIDER:
            raise ValidationError("Atlas batch state provider is invalid")
        if value["job_id"] is not None:
            validate_job_id(value["job_id"])
        if value["status"] not in ATLAS_BATCH_STATUSES:
            raise ValidationError("Atlas batch state status is invalid")
        last_http_status = value["last_http_status"]
        if last_http_status is not None and (
            isinstance(last_http_status, bool)
            or not isinstance(last_http_status, int)
            or not 100 <= last_http_status <= 599
        ):
            raise ValidationError("Atlas batch last HTTP status is invalid")
        if (
            value["status"]
            in {"pending", "cancellation-requested", "cancelled", "failed", "expired"}
            and value["job_id"] is None
        ):
            raise ValidationError("resumable Atlas batch state requires a job_id")
        if not isinstance(value["endpoint"], str) or not value["endpoint"].strip():
            raise ValidationError("Atlas batch state endpoint is invalid")
        request = value["request"]
        if (
            not isinstance(request, dict)
            or not isinstance(request.get("input_sha256"), str)
            or len(request["input_sha256"]) != 64
        ):
            raise ValidationError("Atlas batch state request digest is invalid")
        if not isinstance(request.get("parameters"), dict):
            raise ValidationError("Atlas batch state parameters must be an object")
        calls = value["provider_calls"]
        if not isinstance(calls, list) or not calls:
            raise ValidationError("Atlas batch state requires provider calls")
        if len(calls) > ATLAS_BATCH_PROVIDER_CALL_HISTORY_LIMIT:
            raise ValidationError("Atlas batch retained provider call history exceeds its limit")
        for call in calls:
            if not isinstance(call, dict):
                raise ValidationError("Atlas batch provider calls must be objects")
            _safe_provider_call(call)
        history = value.get("provider_call_history")
        if history is not None:
            _validated_provider_call_history(history)
        if not isinstance(value["last_response"], dict):
            raise ValidationError("Atlas batch state last_response must be an object")
        if not isinstance(value["artifacts"], list):
            raise ValidationError("Atlas batch state artifacts must be a list")
        if len(value["artifacts"]) > ATLAS_BATCH_ARTIFACT_LIMIT:
            raise ValidationError("Atlas batch artifact history exceeds the safety limit")
        submission_call = None
        if value["status"] in {
            "submitting",
            "submission-rejected",
            "submission-indeterminate",
        }:
            submission_call = next(
                (call for call in reversed(calls) if call.get("operation") == "submit"),
                None,
            )
            if submission_call is None or (submission_call.get("http_status") != last_http_status):
                raise ValidationError(
                    "Atlas batch last HTTP status is not bound to its submit call"
                )
        if value["status"] == "submitting" and (
            calls[-1].get("operation") != "submit" or calls[-1].get("outcome") != "in-flight"
        ):
            raise ValidationError("submitting Atlas batch state requires an in-flight call")
        if value["status"] == "submission-rejected":
            rejection = calls[-1].get("error")
            if (
                value["job_id"] is not None
                or last_http_status not in ATLAS_DEFINITIVE_SUBMISSION_REJECTION_STATUSES
                or calls[-1].get("operation") != "submit"
                or calls[-1].get("outcome") != "rejected"
                or not isinstance(rejection, dict)
                or rejection.get("provider_acceptance") != "rejected"
                or rejection.get("retry_safe") is not True
                or rejection.get("rejected_at") != calls[-1].get("finished_at")
            ):
                raise ValidationError("rejected Atlas batch state requires a rejected submit call")
            rejected_at = _utc_datetime(calls[-1].get("finished_at"), "submission rejection time")
            retry_not_before = rejection.get("retry_not_before")
            if retry_not_before is not None and (
                _utc_datetime(retry_not_before, "retry-not-before time") < rejected_at
            ):
                raise ValidationError("Atlas batch retry-not-before precedes its rejection")
        if value["status"] == "submission-indeterminate":
            reconciliation = value.get("manual_reconciliation")
            if (
                not isinstance(reconciliation, dict)
                or reconciliation.get("input_sha256") != request["input_sha256"]
                or reconciliation.get("possible_remote_acceptance") is not True
                or reconciliation.get("do_not_resubmit") is not True
            ):
                raise ValidationError(
                    "indeterminate Atlas batch state requires manual reconciliation"
                )
            provider_acceptance = reconciliation.get("provider_acceptance")
            if provider_acceptance is not None and provider_acceptance not in {
                "unknown",
                "accepted",
                "not-proven",
            }:
                raise ValidationError("indeterminate Atlas batch provider acceptance is invalid")
            if provider_acceptance is not None:
                if submission_call is None:  # pragma: no cover - checked above
                    raise ValidationError("indeterminate Atlas batch submit call is missing")
                call_status = submission_call.get("http_status")
                call_outcome = submission_call.get("outcome")
                operation_indeterminate = submission_call.get("operation_indeterminate")
                accepted = (
                    call_outcome == "accepted"
                    and isinstance(call_status, int)
                    and not isinstance(call_status, bool)
                    and 200 <= call_status < 300
                    and operation_indeterminate is False
                )
                unknown = (
                    call_outcome == "indeterminate"
                    and (call_status is None or call_status < 200)
                    and operation_indeterminate is True
                )
                not_proven = (
                    call_outcome == "error"
                    and isinstance(call_status, int)
                    and not isinstance(call_status, bool)
                    and call_status >= 300
                    and call_status not in ATLAS_DEFINITIVE_SUBMISSION_REJECTION_STATUSES
                    and operation_indeterminate is False
                )
                if not {
                    "accepted": accepted,
                    "unknown": unknown,
                    "not-proven": not_proven,
                }[provider_acceptance]:
                    raise ValidationError(
                        "indeterminate Atlas batch provider acceptance contradicts its submit call"
                    )
        if value["status"] == "cancellation-requested":
            cancellation_response = value["last_response"]
            provider_acceptance = cancellation_response.get("provider_acceptance")
            if provider_acceptance is not None:
                latest_cancel = next(
                    (call for call in reversed(calls) if call.get("operation") == "cancel"),
                    None,
                )
                if latest_cancel is None:
                    raise ValidationError(
                        "Atlas cancellation response requires a matching cancel call"
                    )
                call_status = latest_cancel.get("http_status")
                call_outcome = latest_cancel.get("outcome")
                operation_indeterminate = latest_cancel.get("operation_indeterminate")
                if call_status != last_http_status:
                    raise ValidationError(
                        "Atlas batch last HTTP status is not bound to its cancel call"
                    )
                cancellation_contracts = {
                    "confirmed": (
                        call_outcome == "accepted"
                        and isinstance(call_status, int)
                        and not isinstance(call_status, bool)
                        and 200 <= call_status < 300
                        and operation_indeterminate is False
                        and cancellation_response.get("retry_safe") is False
                    ),
                    "rejected": (
                        call_outcome == "error"
                        and isinstance(call_status, int)
                        and not isinstance(call_status, bool)
                        and call_status >= 200
                        and operation_indeterminate is False
                        and cancellation_response.get("retry_safe") is True
                    ),
                    "unknown": (
                        call_outcome == "indeterminate"
                        and (call_status is None or call_status < 200)
                        and operation_indeterminate is True
                        and bool(cancellation_response.get("retry_safe"))
                    ),
                }
                if provider_acceptance not in cancellation_contracts:
                    raise ValidationError("Atlas cancellation provider acceptance is invalid")
                if not cancellation_contracts[provider_acceptance]:
                    raise ValidationError(
                        "Atlas cancellation provider acceptance contradicts its cancel call"
                    )

    def initialize(
        self,
        *,
        job_id: str | None,
        status: str,
        submitted_at: str,
        endpoint: str,
        input_sha256: str,
        parameters: dict[str, Any],
        http_status: int | None,
        response: dict[str, Any],
        provider_call: dict[str, Any],
        artifacts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self.operation_lock():
            if self.path.exists():
                raise ValidationError("refusing to overwrite an existing Atlas batch state")
            if job_id is not None:
                validate_job_id(job_id)
            now = utc_now()
            return self._save_unlocked(
                {
                    "schema_version": ATLAS_BATCH_STATE_SCHEMA,
                    "provider": ATLAS_BATCH_PROVIDER,
                    "job_id": job_id,
                    "status": status,
                    "submitted_at": submitted_at,
                    "updated_at": now,
                    "endpoint": endpoint,
                    "request": {
                        "input_sha256": input_sha256,
                        "parameters": redact(parameters),
                    },
                    "last_http_status": http_status,
                    "last_response": _safe_response(response),
                    "provider_calls": [_safe_provider_call(provider_call)],
                    "artifacts": redact(artifacts or []),
                    "provenance_path": str(self.provenance_path),
                }
            )

    def begin_submission(
        self,
        *,
        submitted_at: str,
        endpoint: str,
        input_sha256: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        return self.initialize(
            job_id=None,
            status="submitting",
            submitted_at=submitted_at,
            endpoint=endpoint,
            input_sha256=input_sha256,
            parameters=parameters,
            http_status=None,
            response={"status": "submitting"},
            provider_call={
                "endpoint": endpoint,
                "operation": "submit",
                "http_status": None,
                "started_at": submitted_at,
                "outcome": "in-flight",
            },
        )

    @staticmethod
    def _finish_in_flight_call(
        state: dict[str, Any],
        *,
        operation: str,
        outcome: str,
        http_status: int | None,
    ) -> None:
        call = next(
            (
                candidate
                for candidate in reversed(state["provider_calls"])
                if candidate.get("operation") == operation
                and candidate.get("outcome") == "in-flight"
            ),
            None,
        )
        if call is None:
            raise ValidationError(f"Atlas batch {operation} has no in-flight provider call")
        call["outcome"] = outcome
        call["http_status"] = http_status
        call["operation_indeterminate"] = outcome == "indeterminate"
        call["finished_at"] = utc_now()

    @staticmethod
    def _merge_provider_call_details(call: dict[str, Any], details: dict[str, Any] | None) -> None:
        if details is None:
            return
        for key, value in details.items():
            if key not in {
                "endpoint",
                "operation",
                "started_at",
                "finished_at",
                "outcome",
                "http_status",
                "operation_indeterminate",
            }:
                call[key] = value

    def reconcile_submission(
        self,
        *,
        job_id: str | None,
        status: str,
        endpoint: str,
        http_status: int,
        response: dict[str, Any],
        artifacts: list[dict[str, Any]] | None = None,
        provider_call: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.operation_lock():
            state = self._load_unlocked()
            if state["status"] != "submitting":
                raise ValidationError("Atlas batch submission is not awaiting reconciliation")
            if status not in {"pending", "completed"}:
                raise ValidationError("Atlas batch submission result status is invalid")
            if job_id is not None:
                validate_job_id(job_id)
            if (status == "pending") != (job_id is not None):
                raise ValidationError("pending Atlas batch submission requires a job_id")
            self._finish_in_flight_call(
                state,
                operation="submit",
                outcome="accepted",
                http_status=http_status,
            )
            details = _safe_provider_call(provider_call) if provider_call is not None else None
            self._merge_provider_call_details(state["provider_calls"][-1], details)
            state["job_id"] = job_id
            state["status"] = status
            state["endpoint"] = endpoint
            state["updated_at"] = utc_now()
            state["last_http_status"] = http_status
            state["last_response"] = _safe_response(response)
            if artifacts:
                state["artifacts"].extend(redact(artifacts))
            return self._save_unlocked(state)

    def reconcile_submission_failure(
        self,
        *,
        observed_status: int | None,
        endpoint: str,
        destination_path: str,
        error_name: str,
        failure: dict[str, Any],
        provider_call: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist a submit failure without conflating body loss with acceptance."""

        if observed_status == 200:
            call = dict(provider_call)
            call["operation_indeterminate"] = False
            call["partial"] = False
            return self.reconcile_submission(
                job_id=None,
                status="completed",
                endpoint=endpoint,
                http_status=observed_status,
                response={
                    "status": "completed",
                    "delivery": "synchronous",
                    "artifact_materialization": {
                        "status": "failed",
                        "destination_path": destination_path,
                        "partial_output": False,
                        "error": (
                            f"provider response artifact materialization ended with {error_name}"
                        ),
                        "failure": failure,
                    },
                },
                provider_call=call,
            )
        if observed_status in ATLAS_DEFINITIVE_SUBMISSION_REJECTION_STATUSES:
            return self.mark_submission_rejected(
                http_status=observed_status,
                response=failure,
                provider_call=provider_call,
            )
        provider_acceptance = "unknown"
        if observed_status is not None and 200 <= observed_status < 300:
            provider_acceptance = "accepted"
        elif observed_status is not None and observed_status >= 300:
            provider_acceptance = "not-proven"
        return self.mark_submission_indeterminate(
            f"Atlas submit ended with {error_name}",
            provider_call=provider_call,
            response=failure,
            provider_acceptance=provider_acceptance,
        )

    def recover_synchronous_submission(
        self,
        *,
        endpoint: str,
        input_sha256: str,
        parameters: dict[str, Any],
        response: dict[str, Any],
        artifacts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Reconcile a sync 200 proven durable before submission state was updated."""

        with self.operation_lock():
            state = self._load_unlocked()
            if state["status"] not in {"submitting", "submission-indeterminate"}:
                raise ValidationError("Atlas batch submission is not awaiting synchronous recovery")
            if state["job_id"] is not None or state["endpoint"] != endpoint:
                raise ValidationError("Atlas synchronous recovery does not match submission state")
            if state["request"]["input_sha256"] != input_sha256 or state["request"][
                "parameters"
            ] != redact(parameters):
                raise ValidationError("Atlas synchronous recovery request does not match state")

            call = state["provider_calls"][-1]
            previous_outcome = call.get("outcome")
            migrated_accepted = (
                previous_outcome == "accepted"
                and call.get("http_status") == 200
                and call.get("operation_indeterminate") is False
                and call.get("certainty_normalized_from_legacy") is True
            )
            if call.get("operation") != "submit" or (
                previous_outcome not in {"in-flight", "indeterminate"} and not migrated_accepted
            ):
                raise ValidationError(
                    "Atlas synchronous recovery requires the unresolved submit call"
                )

            recovered_at = utc_now()
            call["previous_outcome"] = previous_outcome
            call["outcome"] = "accepted"
            call["operation_indeterminate"] = False
            call["http_status"] = 200
            call.setdefault("finished_at", recovered_at)
            call["recovered_at"] = recovered_at
            call["recovered_from_artifact_provenance"] = True
            state["status"] = "completed"
            state["updated_at"] = recovered_at
            state["last_http_status"] = 200
            state["last_response"] = _safe_response(response)
            state["artifacts"] = redact(artifacts)
            state.pop("manual_reconciliation", None)
            return self._save_unlocked(state)

    def _mark_submission_indeterminate_unlocked(
        self,
        state: dict[str, Any],
        reason: str,
        *,
        provider_call: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        provider_acceptance: str = "unknown",
    ) -> dict[str, Any]:
        if provider_acceptance not in {"unknown", "accepted", "not-proven"}:
            raise ValidationError("Atlas submission acceptance reconciliation is invalid")
        details = _safe_provider_call(provider_call) if provider_call is not None else None
        http_status = details.get("http_status") if details is not None else None
        if state["status"] == "submitting":
            call_outcome = "indeterminate"
            if provider_acceptance == "accepted":
                call_outcome = "accepted"
            elif details is not None and details.get("outcome") == "error":
                call_outcome = "error"
            self._finish_in_flight_call(
                state,
                operation="submit",
                outcome=call_outcome,
                http_status=http_status,
            )
            self._merge_provider_call_details(state["provider_calls"][-1], details)
        elif state["status"] != "submission-indeterminate":
            raise ValidationError("Atlas batch submission is not indeterminate")
        safe_reason = redact(reason)
        state["status"] = "submission-indeterminate"
        state["updated_at"] = utc_now()
        state["last_http_status"] = http_status
        state["last_response"] = {
            "status": "submission-indeterminate",
            "reason": safe_reason,
        }
        if response is not None:
            state["last_response"]["error"] = _safe_response(response)
        state["manual_reconciliation"] = {
            "endpoint": state["endpoint"],
            "input_sha256": state["request"]["input_sha256"],
            "provider_acceptance": provider_acceptance,
            "possible_remote_acceptance": True,
            "do_not_resubmit": True,
            "guidance": _submission_reconciliation_guidance(provider_acceptance),
        }
        return self._save_unlocked(state)

    def mark_submission_indeterminate(
        self,
        reason: str,
        *,
        provider_call: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        provider_acceptance: str = "unknown",
    ) -> dict[str, Any]:
        with self.operation_lock():
            return self._mark_submission_indeterminate_unlocked(
                self._load_unlocked(),
                reason,
                provider_call=provider_call,
                response=response,
                provider_acceptance=provider_acceptance,
            )

    def mark_submission_rejected(
        self,
        *,
        http_status: int,
        response: dict[str, Any],
        provider_call: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist a definitive, retry-safe HTTP rejection of the POST."""

        with self.operation_lock():
            if http_status not in ATLAS_DEFINITIVE_SUBMISSION_REJECTION_STATUSES:
                raise ValidationError(
                    "Atlas submission rejection status is not a definitive retry-safe rejection"
                )
            state = self._load_unlocked()
            if state["status"] != "submitting":
                raise ValidationError("Atlas batch submission is not awaiting rejection")
            self._finish_in_flight_call(
                state,
                operation="submit",
                outcome="rejected",
                http_status=http_status,
            )
            details = _safe_provider_call(provider_call) if provider_call is not None else None
            self._merge_provider_call_details(state["provider_calls"][-1], details)
            rejected_at = state["provider_calls"][-1]["finished_at"]
            rejection = {
                **response,
                "status": "submission-rejected",
                "provider_acceptance": "rejected",
                "retry_safe": True,
                "rejected_at": rejected_at,
            }
            retry_after = response.get("retry_after")
            if retry_after is not None:
                if (
                    isinstance(retry_after, bool)
                    or not isinstance(retry_after, (int, float))
                    or not math.isfinite(retry_after)
                    or retry_after < 0
                ):
                    raise ValidationError("Atlas submission retry delay is invalid")
                rejected_time = _utc_datetime(rejected_at, "submission rejection time")
                try:
                    retry_deadline = rejected_time + timedelta(seconds=float(retry_after))
                except OverflowError:
                    retry_deadline = datetime.max.replace(tzinfo=timezone.utc)
                rejection["retry_not_before"] = _utc_string(retry_deadline)
            safe_rejection = _safe_response(rejection)
            state["provider_calls"][-1]["error"] = safe_rejection
            state["status"] = "submission-rejected"
            state["updated_at"] = rejected_at
            state["last_http_status"] = http_status
            state["last_response"] = safe_rejection
            return self._save_unlocked(state)

    def retry_rejected_submission(
        self,
        *,
        endpoint: str,
        input_sha256: str,
        parameters: dict[str, Any],
        invoked_at: str,
    ) -> dict[str, Any]:
        """Re-arm only the exact request that received a definitive rejection."""

        with self.operation_lock():
            state = self._load_unlocked()
            if state["status"] != "submission-rejected":
                raise ValidationError("Atlas batch submission is not retryable")
            if state["request"]["input_sha256"] != input_sha256 or state["request"][
                "parameters"
            ] != redact(parameters):
                raise ValidationError(
                    "retry request does not match the rejected Atlas batch submission"
                )
            rejection = state["provider_calls"][-1]["error"]
            rejected_at = _utc_datetime(rejection["rejected_at"], "submission rejection time")
            if _utc_datetime(invoked_at, "retry invocation time") <= rejected_at:
                raise ValidationError(
                    "Atlas batch retry must be invoked after the rejection is observed"
                )
            attempt_started_at = utc_now()
            attempt_started = _utc_datetime(attempt_started_at, "retry attempt start time")
            retry_not_before = rejection.get("retry_not_before")
            if retry_not_before is not None:
                deadline = _utc_datetime(retry_not_before, "retry-not-before time")
                if attempt_started < deadline:
                    raise APIError(
                        status=429,
                        kind="rate-limit",
                        message="Atlas batch retry is not yet permitted; honor Retry-After",
                        retry_after=(deadline - attempt_started).total_seconds(),
                    )
            state["status"] = "submitting"
            state["endpoint"] = endpoint
            state["updated_at"] = attempt_started_at
            state["last_http_status"] = None
            state["last_response"] = {"status": "submitting", "retry": True}
            state["provider_calls"].append(
                {
                    "endpoint": endpoint,
                    "operation": "submit",
                    "http_status": None,
                    "started_at": attempt_started_at,
                    "outcome": "in-flight",
                    "retry_after_rejection": True,
                }
            )
            return self._save_unlocked(state)

    def adopt(self, *, job_id: str, endpoint: str) -> dict[str, Any]:
        job_id = validate_job_id(job_id)
        now = utc_now()
        return self.initialize(
            job_id=job_id,
            status="pending",
            submitted_at=now,
            endpoint=endpoint,
            input_sha256=input_digest({"adopted_job_id": job_id}),
            parameters={"adopted": True},
            http_status=None,
            response={"job_id": job_id, "status": "pending", "adopted": True},
            provider_call={
                "endpoint": endpoint,
                "operation": "adopt",
                "timestamp": now,
            },
        )

    @staticmethod
    def cancellation_retry_delay(state: dict[str, Any]) -> float | None:
        """Return seconds until an idempotent DELETE retry, or None when resolved."""

        if state.get("status") != "cancellation-requested":
            return None
        calls = state.get("provider_calls")
        if not isinstance(calls, list) or not calls:
            return None
        latest_cancel = next(
            (call for call in reversed(calls) if call.get("operation") == "cancel"),
            None,
        )
        if not isinstance(latest_cancel, dict) or latest_cancel.get("outcome") not in {
            "error",
            "indeterminate",
        }:
            return None
        retry_after = latest_cancel.get("retry_after")
        if retry_after is None:
            return 0.0
        if (
            isinstance(retry_after, bool)
            or not isinstance(retry_after, (int, float))
            or not math.isfinite(retry_after)
            or retry_after < 0
        ):
            return None
        finished_at = _utc_datetime(latest_cancel.get("finished_at"), "cancellation failure time")
        try:
            retry_not_before = finished_at + timedelta(seconds=float(retry_after))
        except OverflowError:
            retry_not_before = datetime.max.replace(tzinfo=timezone.utc)
        return max(
            0.0,
            (retry_not_before - datetime.now(timezone.utc)).total_seconds(),
        )

    @staticmethod
    def cancellation_retry_allowed(state: dict[str, Any]) -> bool:
        return AtlasBatchStore.cancellation_retry_delay(state) == 0

    def begin_cancellation(self, *, provider_call: dict[str, Any]) -> dict[str, Any]:
        with self.operation_lock():
            state = self._load_unlocked()
            if state["status"] in ATLAS_BATCH_TERMINAL_STATUSES:
                return state
            if state["status"] == "cancellation-requested" and not self.cancellation_retry_allowed(
                state
            ):
                return state
            if (
                state["status"] not in {"pending", "cancellation-requested"}
                or state["job_id"] is None
            ):
                raise ValidationError("Atlas batch state cannot be cancelled")
            call = _safe_provider_call(provider_call)
            call["http_status"] = None
            call["started_at"] = call.pop("timestamp", utc_now())
            call["outcome"] = "in-flight"
            state["provider_calls"].append(call)
            state["status"] = "cancellation-requested"
            state["updated_at"] = utc_now()
            state["last_http_status"] = None
            state["last_response"] = {
                "job_id": state["job_id"],
                "status": "cancellation-requested",
                "intent_persisted": True,
            }
            return self._save_unlocked(state)

    def _mark_cancellation_indeterminate_unlocked(self, state: dict[str, Any]) -> dict[str, Any]:
        self._finish_in_flight_call(
            state,
            operation="cancel",
            outcome="indeterminate",
            http_status=None,
        )
        state["status"] = "cancellation-requested"
        state["updated_at"] = utc_now()
        state["last_http_status"] = None
        state["last_response"] = {
            "job_id": state["job_id"],
            "status": "cancellation-requested",
            "provider_acceptance": "unknown",
            "retry_safe": "DELETE is idempotent",
        }
        return self._save_unlocked(state)

    def reconcile_cancellation(
        self,
        *,
        http_status: int | None,
        accepted: bool,
        provider_call: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.operation_lock():
            state = self._load_unlocked()
            details = _safe_provider_call(provider_call) if provider_call is not None else None
            outcome = "accepted"
            if not accepted:
                outcome = (
                    details.get("outcome")
                    if details is not None and details.get("outcome") in {"error", "indeterminate"}
                    else "indeterminate"
                )
            self._finish_in_flight_call(
                state,
                operation="cancel",
                outcome=outcome,
                http_status=http_status,
            )
            call = state["provider_calls"][-1]
            self._merge_provider_call_details(call, details)
            if state["status"] not in ATLAS_BATCH_TERMINAL_STATUSES:
                state["status"] = "cancellation-requested"
                state["last_http_status"] = http_status
                state["last_response"] = {
                    "job_id": state["job_id"],
                    "status": "cancellation-requested",
                    "provider_acceptance": (
                        "confirmed"
                        if accepted
                        else ("rejected" if outcome == "error" else "unknown")
                    ),
                    "retry_safe": not accepted,
                }
                if not accepted and call.get("retry_after") is not None:
                    state["last_response"]["retry_after"] = call["retry_after"]
            state["updated_at"] = utc_now()
            return self._save_unlocked(state)

    @staticmethod
    def _merged_status(current: str, observed: str) -> tuple[str, bool]:
        if current in ATLAS_BATCH_TERMINAL_STATUSES:
            return current, observed != current
        if current == "cancellation-requested" and observed == "pending":
            return current, True
        allowed = {
            "pending": {
                "pending",
                "cancellation-requested",
                *ATLAS_BATCH_TERMINAL_STATUSES,
            },
            "cancellation-requested": {
                "cancellation-requested",
                *ATLAS_BATCH_TERMINAL_STATUSES,
            },
        }
        if observed not in allowed.get(current, set()):
            raise ValidationError(f"invalid Atlas batch state transition: {current} -> {observed}")
        return observed, False

    def update(
        self,
        *,
        response: dict[str, Any],
        http_status: int | None,
        provider_call: dict[str, Any] | None,
        status: str | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self.operation_lock():
            state = self._load_unlocked()
            response_job_id = response.get("job_id")
            if response_job_id is not None and response_job_id != state["job_id"]:
                raise ValidationError("Atlas batch response job_id does not match state")
            observed_status = status or response.get("status")
            if observed_status not in ATLAS_BATCH_STATUSES:
                raise ValidationError("Atlas batch update status is invalid")
            resolved_status, ignored = self._merged_status(state["status"], observed_status)
            if provider_call is not None:
                call = _safe_provider_call(provider_call)
                call["observed_status"] = observed_status
                call["state_status_before"] = state["status"]
                call["state_status_after"] = resolved_status
                if ignored:
                    call["transition_ignored"] = "monotonic-state-preserved"
                state["provider_calls"].append(call)
            state["status"] = resolved_status
            state["updated_at"] = utc_now()
            if not (resolved_status in ATLAS_BATCH_TERMINAL_STATUSES and ignored):
                state["last_http_status"] = http_status
                state["last_response"] = _safe_response(response)
                if artifacts:
                    state["artifacts"].extend(redact(artifacts))
            return self._save_unlocked(state)

    def record_provider_call(
        self,
        *,
        provider_call: dict[str, Any],
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """Append one completed attempt without changing the durable job status."""

        with self.operation_lock():
            state = self._load_unlocked()
            call = _safe_provider_call(provider_call)
            state["provider_calls"].append(call)
            state["updated_at"] = utc_now()
            state["last_http_status"] = call.get("http_status")
            state["last_response"] = _safe_response(
                {
                    "status": state["status"],
                    "provider_call_result": response,
                }
            )
            return self._save_unlocked(state)

    def resolve_job_id(self, requested: str | None, *, state: dict[str, Any] | None = None) -> str:
        state = self.load() if state is None else state
        self.validate(state)
        state_job_id = state["job_id"]
        if state_job_id is None:
            if state["status"] == "submission-indeterminate":
                raise ValidationError(
                    "Atlas batch submission is indeterminate and has no durable job_id; "
                    "do not resubmit automatically, reconcile it manually"
                )
            if state["status"] == "submission-rejected":
                raise ValidationError(
                    "Atlas batch submission was rejected and has no job_id; "
                    "remediate the provider error and retry batch-submit"
                )
            raise ValidationError("synchronous Atlas batch state has no resumable job_id")
        if requested is not None and validate_job_id(requested) != state_job_id:
            raise ValidationError("--job-id does not match the durable Atlas batch state")
        return state_job_id

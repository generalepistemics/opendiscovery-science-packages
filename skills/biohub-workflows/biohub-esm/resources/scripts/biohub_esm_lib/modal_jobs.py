"""Durable, adapter-driven Modal spawn/gather/cancel orchestration."""

from __future__ import annotations

import fcntl
import importlib.metadata as metadata
import json
import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .constants import (
    ESM_GIT_REVISION,
    ESMFOLD2_HF_MODELS,
    HF_REVISIONS,
    MODAL_CALL_ID_MAX_BYTES,
    MODAL_INPUT_MAX_BYTES,
    MODAL_JOB_STATE_MAX_BYTES,
    MODAL_JOB_STATE_MAX_DEPTH,
    MODAL_JOB_STATE_MAX_NODES,
    MODAL_JOB_STATE_MAX_NUMBER_BYTES,
    MODAL_JOB_STATE_MAX_TEXT_BYTES,
    MODAL_MAX_JOBS,
    MODAL_RESULT_MAX_BYTES,
    MODAL_RESULT_MAX_DEPTH,
    MODAL_RESULT_MAX_NODES,
    MODAL_SDK_VERSION,
    TRANSFORMERS_GIT_REVISION,
)
from .errors import ValidationError
from .provenance import SHA256_RE, input_digest, utc_now, validate_provenance, write_json_atomic
from .security import redact

MODAL_JOB_STATUSES = {
    "queued",
    "spawning",
    "submission-indeterminate",
    "pending",
    "cancellation-requested",
    "completed",
    "cancelled",
    "failed",
}
MODAL_STATE_STATUSES = {
    "submitting",
    "submission-indeterminate",
    "pending",
    "cancellation-requested",
    "completed",
    "cancelled",
    "failed",
    "partial",
}
MODAL_STATE_SCHEMA_VERSION = "1.5"
MODAL_PROVIDER_IDENTITY_FIELDS = {
    "workspace_name",
    "environment_name",
    "app_name",
    "function_name",
    "function_version",
    "modal_sdk_version",
}
MODAL_STATE_FIELDS = {
    "schema_version",
    "provider",
    "scope",
    "completion_contract",
    "provider_identity",
    "kind",
    "payload_count",
    "created_at",
    "updated_at",
    "jobs",
    "status",
}
MODAL_STATE_OPTIONAL_FIELDS = {"last_gather_error"}
MODAL_JOB_FIELDS = {
    "index",
    "payload_sha256",
    "status",
    "call_id",
    "result",
    "error",
    "spawn_started_at",
    "spawn_finished_at",
    "finished_at",
}
MODAL_JOB_OPTIONAL_FIELDS = {
    "manual_reconciliation",
    "spawn_error",
    "last_poll_error",
    "cancellation_requested_at",
    "cancellation_observed_at",
    "cancellation_reason",
    "cancellation_race",
}


def _nonempty_text(value: Any, *, field: str, max_bytes: int = 1024) -> str:
    try:
        encoded_size = len(value.encode("utf-8")) if isinstance(value, str) else None
    except UnicodeEncodeError as exc:
        raise ValidationError(f"{field} must contain valid Unicode") from exc
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or encoded_size is None
        or encoded_size > max_bytes
    ):
        raise ValidationError(f"{field} must be a non-empty bounded string")
    return value


def _validate_call_id(value: Any) -> str:
    return _nonempty_text(value, field="Modal call_id", max_bytes=MODAL_CALL_ID_MAX_BYTES)


def _preflight_modal_state_json(encoded: bytes) -> None:
    """Bound structural expansion before the JSON decoder allocates Python objects."""

    depth = 0
    nodes = 0
    text_bytes = 0
    in_string = False
    escaped = False
    string_bytes = 0
    index = 0
    length = len(encoded)

    def add_node() -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MODAL_JOB_STATE_MAX_NODES:
            raise ValidationError(
                f"Modal job state exceeds the {MODAL_JOB_STATE_MAX_NODES}-node limit"
            )

    while index < length:
        byte = encoded[index]
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:  # backslash
                escaped = True
            elif byte == 0x22:  # quote
                in_string = False
                text_bytes += string_bytes
                if text_bytes > MODAL_JOB_STATE_MAX_TEXT_BYTES:
                    raise ValidationError("Modal job state exceeds the aggregate text-token limit")
                string_bytes = 0
            else:
                string_bytes += 1
                if string_bytes > MODAL_RESULT_MAX_BYTES * 6:
                    raise ValidationError("Modal job state contains an oversized text token")
            index += 1
            continue

        if byte == 0x22:  # quote
            add_node()
            in_string = True
            index += 1
            continue
        if byte in (0x7B, 0x5B):  # { [
            add_node()
            depth += 1
            if depth > MODAL_JOB_STATE_MAX_DEPTH:
                raise ValidationError(
                    f"Modal job state exceeds the {MODAL_JOB_STATE_MAX_DEPTH}-level depth limit"
                )
            index += 1
            continue
        if byte in (0x7D, 0x5D):  # } ]
            depth -= 1
            index += 1
            continue
        if byte == 0x2D or 0x30 <= byte <= 0x39:  # - or digit
            add_node()
            end = index + 1
            while end < length and encoded[end] in b"0123456789+-.eE":
                end += 1
            if end - index > MODAL_JOB_STATE_MAX_NUMBER_BYTES:
                raise ValidationError("Modal job state contains an oversized numeric token")
            index = end
            continue
        if encoded.startswith(b"true", index):
            add_node()
            index += 4
            continue
        if encoded.startswith(b"false", index):
            add_node()
            index += 5
            continue
        if encoded.startswith(b"null", index):
            add_node()
            index += 4
            continue
        index += 1


def _parse_modal_state_float(token: str) -> float:
    if len(token.encode("ascii")) > MODAL_JOB_STATE_MAX_NUMBER_BYTES:
        raise ValidationError("Modal job state contains an oversized numeric token")
    value = float(token)
    if not math.isfinite(value):
        raise ValidationError("Modal job state contains a non-finite number")
    return value


def _parse_modal_state_int(token: str) -> int:
    if len(token.encode("ascii")) > MODAL_JOB_STATE_MAX_NUMBER_BYTES:
        raise ValidationError("Modal job state contains an oversized numeric token")
    return int(token)


def _validate_modal_state_tree_bounds(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    seen_containers: set[int] = set()
    nodes = 0
    text_bytes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MODAL_JOB_STATE_MAX_NODES:
            raise ValidationError(
                f"Modal job state exceeds the {MODAL_JOB_STATE_MAX_NODES}-node limit"
            )
        if depth > MODAL_JOB_STATE_MAX_DEPTH:
            raise ValidationError(
                f"Modal job state exceeds the {MODAL_JOB_STATE_MAX_DEPTH}-level depth limit"
            )
        if isinstance(item, dict):
            identity = id(item)
            if identity in seen_containers:
                raise ValidationError("Modal job state must be an acyclic JSON tree")
            seen_containers.add(identity)
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValidationError("Modal job state object keys must be strings")
                stack.append((key, depth + 1))
                stack.append((child, depth + 1))
        elif isinstance(item, list):
            identity = id(item)
            if identity in seen_containers:
                raise ValidationError("Modal job state must be an acyclic JSON tree")
            seen_containers.add(identity)
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, str):
            try:
                text_bytes += len(item.encode("utf-8"))
            except UnicodeEncodeError as exc:
                raise ValidationError("Modal job state contains invalid Unicode") from exc
            if text_bytes > MODAL_JOB_STATE_MAX_TEXT_BYTES:
                raise ValidationError("Modal job state exceeds the aggregate text limit")
        elif item is None or isinstance(item, bool):
            continue
        elif isinstance(item, int):
            if item.bit_length() > MODAL_JOB_STATE_MAX_NUMBER_BYTES * 4:
                raise ValidationError("Modal job state contains an oversized integer")
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValidationError("Modal job state contains a non-finite number")
        else:
            raise ValidationError("Modal job state contains a non-JSON value")


def _utc_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"Modal {field} must be a UTC timestamp")
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError(f"Modal {field} must be a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValidationError(f"Modal {field} must be a UTC timestamp")
    return parsed


def _bounded_json_size(value: Any, *, limit: int, field: str) -> int:
    encoder = json.JSONEncoder(
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    size = 0
    try:
        for chunk in encoder.iterencode(value):
            size += len(chunk.encode("utf-8"))
            if size > limit:
                raise ValidationError(f"{field} exceeds the {limit}-byte limit")
    except ValidationError:
        raise
    except (TypeError, ValueError, RecursionError, MemoryError) as exc:
        raise ValidationError(f"{field} must be interoperable bounded JSON") from exc
    return size


def _validate_result_tree_bounds(value: Any) -> None:
    """Reject pathological remote object graphs before recursive redaction."""

    stack: list[tuple[Any, int]] = [(value, 0)]
    seen_containers: set[int] = set()
    nodes = 0
    text_bytes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MODAL_RESULT_MAX_NODES:
            raise ValidationError(
                f"Modal result envelope exceeds the {MODAL_RESULT_MAX_NODES}-node limit"
            )
        if depth > MODAL_RESULT_MAX_DEPTH:
            raise ValidationError(
                f"Modal result envelope exceeds the {MODAL_RESULT_MAX_DEPTH}-level depth limit"
            )
        if isinstance(item, dict):
            identity = id(item)
            if identity in seen_containers:
                raise ValidationError("Modal result envelope must be an acyclic JSON tree")
            seen_containers.add(identity)
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValidationError("Modal result envelope object keys must be strings")
                stack.append((key, depth + 1))
                stack.append((child, depth + 1))
        elif isinstance(item, list):
            identity = id(item)
            if identity in seen_containers:
                raise ValidationError("Modal result envelope must be an acyclic JSON tree")
            seen_containers.add(identity)
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, str):
            try:
                text_bytes += len(item.encode("utf-8"))
            except UnicodeEncodeError as exc:
                raise ValidationError("Modal result envelope contains invalid Unicode") from exc
            if text_bytes > MODAL_RESULT_MAX_BYTES:
                raise ValidationError(
                    f"Modal result envelope exceeds the {MODAL_RESULT_MAX_BYTES}-byte text limit"
                )
        elif item is None or isinstance(item, bool):
            continue
        elif isinstance(item, int):
            # JSON decimal text is at most roughly one digit per three bits.
            if item.bit_length() > MODAL_RESULT_MAX_BYTES * 4:
                raise ValidationError("Modal result envelope contains an oversized integer")
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValidationError("Modal result envelope contains a non-finite number")
        else:
            raise ValidationError("Modal result envelope contains a non-JSON value")
    _bounded_json_size(
        value,
        limit=MODAL_RESULT_MAX_BYTES,
        field="Modal result envelope",
    )


def _aggregate_status(state: dict[str, Any]) -> str:
    statuses = {job["status"] for job in state["jobs"]}
    if "submission-indeterminate" in statuses:
        return "submission-indeterminate"
    if not statuses or statuses & {"queued", "spawning"}:
        return "submitting"
    if statuses == {"completed"}:
        return "completed"
    if statuses == {"cancelled"}:
        return "cancelled"
    if statuses == {"failed"}:
        return "failed"
    if statuses == {"pending"}:
        return "pending"
    if statuses == {"cancellation-requested"}:
        return "cancellation-requested"
    return "partial"


def mark_submission_indeterminate(
    job: dict[str, Any], identity: dict[str, Any], reason: str
) -> None:
    job["status"] = "submission-indeterminate"
    job["error"] = (
        f"{reason}; provider acceptance is unknown. Do not resubmit automatically. "
        "Inspect the Modal dashboard using the recorded app/function and reconcile "
        "this payload digest manually."
    )
    reconciliation = {
        "workspace_name": identity["workspace_name"],
        "environment_name": identity["environment_name"],
        "app_name": identity["app_name"],
        "function_name": identity["function_name"],
        "payload_sha256": job["payload_sha256"],
        "possible_remote_acceptance": True,
        "do_not_resubmit": True,
    }
    if identity.get("function_version") is not None:
        reconciliation["function_version"] = identity["function_version"]
    if identity.get("modal_sdk_version") is not None:
        reconciliation["modal_sdk_version"] = identity["modal_sdk_version"]
    job["manual_reconciliation"] = reconciliation


class ModalAdapter(Protocol):
    def provider_identity(self) -> dict[str, Any]: ...

    def spawn(self, payload: dict[str, Any]) -> str: ...

    def gather(self, call_ids: list[str], *, timeout: float) -> list[Any]: ...

    def cancel(self, call_id: str) -> None: ...


class CancelledCallError(RuntimeError):
    """Typed terminal result for a provider-confirmed call cancellation."""


def validate_modal_result_envelope(
    value: Any,
    *,
    submission_sha256: str,
    provider_identity: dict[str, Any],
    kind: str,
) -> dict[str, Any]:
    """Require scientific results to carry complete remote provenance metadata."""

    _validate_result_tree_bounds(value)
    _validate_provider_identity(provider_identity, strict=True)
    if not isinstance(value, dict):
        raise ValidationError("Modal result must be a JSON object")
    if set(value) != {"submission_sha256", "result", "provenance"}:
        raise ValidationError(
            "Modal scientific result requires submission_sha256, result, and provenance"
        )
    if value["submission_sha256"] != submission_sha256:
        raise ValidationError("Modal result does not match the submitted payload digest")
    provenance = value["provenance"]
    if not isinstance(provenance, dict):
        raise ValidationError("Modal result provenance must be an object")
    validate_provenance(provenance)
    if "modal" not in provenance["execution_route"].split("+"):
        raise ValidationError("Modal result provenance must include the modal route")
    if provenance["input_sha256"] != submission_sha256:
        raise ValidationError("Modal result provenance is not bound to the submission")
    expected_endpoint = (
        f"modal://{provider_identity['app_name']}/{provider_identity['function_name']}"
    )
    if provenance["endpoint"] != expected_endpoint or not any(
        call["endpoint"] == expected_endpoint for call in provenance["provider_calls"]
    ):
        raise ValidationError("Modal result provenance provider identity does not match")
    if provenance["parameters"].get("modal_provider_identity") != provider_identity:
        raise ValidationError(
            "Modal result provenance is not bound to the frozen workspace and environment"
        )
    if provenance["transformers_git_revision"] != TRANSFORMERS_GIT_REVISION:
        raise ValidationError("Modal ESM result requires the pinned Transformers revision")
    if kind == "fold":
        model_id = provenance["model_id"]
        if (
            model_id not in ESMFOLD2_HF_MODELS
            or provenance["model_revision"] != HF_REVISIONS[model_id]
            or provenance["esm_git_revision"] != ESM_GIT_REVISION
        ):
            raise ValidationError("Modal fold result does not match the pinned ESMFold2 stack")
    else:
        raise ValidationError("Modal job kind is invalid")
    if not provenance["artifacts"]:
        raise ValidationError(
            "Modal result provenance requires provider-declared artifact metadata with SHA-256 fields"
        )
    safe = redact(value)
    if not isinstance(safe, dict):  # pragma: no cover - defensive
        raise ValidationError("Modal result envelope must remain an object")
    _bounded_json_size(
        safe,
        limit=MODAL_RESULT_MAX_BYTES,
        field="Modal result envelope",
    )
    return safe


def _validate_provider_identity(identity: Any, *, strict: bool) -> dict[str, Any]:
    if not isinstance(identity, dict):
        raise ValidationError("Modal job state is missing validated provider identity")
    _nonempty_text(identity.get("app_name"), field="Modal app_name")
    _nonempty_text(identity.get("function_name"), field="Modal function_name")
    _nonempty_text(identity.get("workspace_name"), field="Modal workspace_name")
    _nonempty_text(identity.get("environment_name"), field="Modal environment_name")
    if strict:
        if set(identity) != MODAL_PROVIDER_IDENTITY_FIELDS:
            raise ValidationError("Modal provider identity has an invalid schema")
        function_version = identity.get("function_version")
        if (
            isinstance(function_version, bool)
            or not isinstance(function_version, int)
            or function_version < 1
        ):
            raise ValidationError("Modal function_version must be a positive integer")
        if identity.get("modal_sdk_version") != MODAL_SDK_VERSION:
            raise ValidationError(f"Modal job state requires SDK version {MODAL_SDK_VERSION}")
    return identity


def _validate_strict_job_state(
    job: dict[str, Any],
    *,
    created_at: datetime,
    identity: dict[str, Any],
    kind: str,
) -> None:
    fields = set(job)
    if (
        not MODAL_JOB_FIELDS.issubset(fields)
        or fields - MODAL_JOB_FIELDS - MODAL_JOB_OPTIONAL_FIELDS
    ):
        raise ValidationError("Modal job entry has an invalid schema")
    status = job["status"]
    call_id = job.get("call_id")
    if call_id is not None:
        _validate_call_id(call_id)

    parsed: dict[str, datetime] = {}
    for field in (
        "spawn_started_at",
        "spawn_finished_at",
        "cancellation_requested_at",
        "cancellation_observed_at",
        "finished_at",
    ):
        value = job.get(field)
        if value is not None:
            parsed[field] = _utc_timestamp(value, field=f"jobs.{field}")
            if parsed[field] < created_at:
                raise ValidationError(f"Modal jobs.{field} precedes state creation")
    if (
        "spawn_started_at" in parsed
        and "spawn_finished_at" in parsed
        and parsed["spawn_finished_at"] < parsed["spawn_started_at"]
    ):
        raise ValidationError("Modal spawn_finished_at precedes spawn_started_at")
    if (
        "spawn_finished_at" in parsed
        and "cancellation_requested_at" in parsed
        and parsed["cancellation_requested_at"] < parsed["spawn_finished_at"]
    ):
        raise ValidationError("Modal cancellation_requested_at precedes spawn completion")
    if (
        "spawn_finished_at" in parsed
        and "cancellation_observed_at" in parsed
        and parsed["cancellation_observed_at"] < parsed["spawn_finished_at"]
    ):
        raise ValidationError("Modal cancellation_observed_at precedes spawn completion")
    if "finished_at" in parsed:
        for earlier in (
            "spawn_started_at",
            "spawn_finished_at",
            "cancellation_requested_at",
            "cancellation_observed_at",
        ):
            if earlier in parsed and parsed["finished_at"] < parsed[earlier]:
                raise ValidationError(f"Modal finished_at precedes {earlier}")

    result = job.get("result")
    error = job.get("error")
    started = "spawn_started_at" in parsed
    spawn_finished = "spawn_finished_at" in parsed
    cancellation_requested = "cancellation_requested_at" in parsed
    cancellation_observed = "cancellation_observed_at" in parsed
    finished = "finished_at" in parsed

    reconciliation = job.get("manual_reconciliation")
    if reconciliation is not None:
        expected_reconciliation = {
            "workspace_name": identity["workspace_name"],
            "environment_name": identity["environment_name"],
            "app_name": identity["app_name"],
            "function_name": identity["function_name"],
            "function_version": identity["function_version"],
            "modal_sdk_version": identity["modal_sdk_version"],
            "payload_sha256": job["payload_sha256"],
            "possible_remote_acceptance": True,
            "do_not_resubmit": True,
        }
        if reconciliation != expected_reconciliation:
            raise ValidationError("indeterminate Modal submission reconciliation is invalid")
    if (reconciliation is not None) != (status == "submission-indeterminate"):
        raise ValidationError(
            "Modal manual_reconciliation is reserved for indeterminate submissions"
        )
    if "spawn_error" in job and (
        status != "submission-indeterminate"
        or not isinstance(job["spawn_error"], str)
        or not job["spawn_error"].strip()
    ):
        raise ValidationError("Modal spawn_error is inconsistent with job state")
    if "cancellation_reason" in job and (
        status != "cancelled" or job["cancellation_reason"] != "cancelled-before-submission"
    ):
        raise ValidationError("Modal cancellation_reason is inconsistent with job state")
    if "cancellation_race" in job and (
        status != "completed"
        or job["cancellation_race"] != "completed-before-cancellation-took-effect"
    ):
        raise ValidationError("Modal cancellation_race is inconsistent with job state")
    if cancellation_observed and status != "cancelled":
        raise ValidationError("Modal cancellation_observed_at requires cancelled job state")
    cancellation_race = job.get("cancellation_race")
    if status == "completed" and cancellation_requested != (
        cancellation_race == "completed-before-cancellation-took-effect"
    ):
        raise ValidationError(
            "completed Modal jobs require a cancellation race exactly when cancellation was requested"
        )

    if status == "queued":
        if call_id is not None or result is not None or error is not None or parsed:
            raise ValidationError("queued Modal job state contains execution data")
    elif status == "spawning":
        if call_id is not None or result is not None or error is not None:
            raise ValidationError("spawning Modal job state contains terminal data")
        if (
            not started
            or spawn_finished
            or cancellation_requested
            or cancellation_observed
            or finished
        ):
            raise ValidationError("spawning Modal job timestamps are inconsistent")
    elif status == "submission-indeterminate":
        if call_id is not None or result is not None:
            raise ValidationError("indeterminate Modal submission cannot have a call ID or result")
        if not isinstance(error, str) or not error.strip():
            raise ValidationError("indeterminate Modal submission requires an error")
        if (
            not (started and spawn_finished and finished)
            or cancellation_requested
            or cancellation_observed
        ):
            raise ValidationError("indeterminate Modal submission timestamps are inconsistent")
    elif status == "pending":
        if call_id is None or result is not None or not (started and spawn_finished) or finished:
            raise ValidationError("pending Modal job state is inconsistent")
        if cancellation_requested or cancellation_observed:
            raise ValidationError("pending Modal job cannot have cancellation timestamps")
        if error is not None and (not isinstance(error, str) or not error.strip()):
            raise ValidationError("pending Modal job error must be a non-empty string")
    elif status == "cancellation-requested":
        if (
            call_id is None
            or result is not None
            or error is not None
            or not (started and spawn_finished and cancellation_requested)
            or cancellation_observed
            or finished
        ):
            raise ValidationError("cancellation-requested Modal job state is inconsistent")
    elif status == "completed":
        if (
            call_id is None
            or not isinstance(result, dict)
            or error is not None
            or not (started and spawn_finished and finished)
        ):
            raise ValidationError("completed Modal job state is inconsistent")
        validated_result = validate_modal_result_envelope(
            result,
            submission_sha256=job["payload_sha256"],
            provider_identity=identity,
            kind=kind,
        )
        if validated_result != result:
            raise ValidationError("completed Modal job result is not fully redacted")
    elif status == "cancelled":
        if result is not None or error is not None or not finished:
            raise ValidationError("cancelled Modal job state is inconsistent")
        if call_id is None:
            if started or spawn_finished or cancellation_requested or cancellation_observed:
                raise ValidationError("locally cancelled Modal job has remote timestamps")
            if job.get("cancellation_reason") != "cancelled-before-submission":
                raise ValidationError("locally cancelled Modal job requires its reason")
        elif not (started and spawn_finished and (cancellation_requested or cancellation_observed)):
            raise ValidationError("provider-cancelled Modal job timestamps are inconsistent")
    elif status == "failed":
        if (
            call_id is None
            or result is not None
            or not isinstance(error, str)
            or not error.strip()
            or not (started and spawn_finished and finished)
        ):
            raise ValidationError("failed Modal job state is inconsistent")

    if "last_poll_error" in job and (
        status not in {"pending", "cancellation-requested"}
        or not isinstance(job["last_poll_error"], str)
        or not job["last_poll_error"].strip()
    ):
        raise ValidationError("Modal last_poll_error is inconsistent with job state")


def _validate_strict_state(value: dict[str, Any]) -> None:
    fields = set(value)
    if (
        not MODAL_STATE_FIELDS.issubset(fields)
        or fields - MODAL_STATE_FIELDS - MODAL_STATE_OPTIONAL_FIELDS
    ):
        raise ValidationError("Modal job state has an invalid schema")
    identity = _validate_provider_identity(value.get("provider_identity"), strict=True)
    if value.get("scope") != "control-plane-only":
        raise ValidationError("Modal job state scope is invalid")
    if value.get("completion_contract") != "compact-result-plus-schema-validated-provenance":
        raise ValidationError("Modal job state completion contract is invalid")
    created_at = _utc_timestamp(value.get("created_at"), field="created_at")
    updated_at = _utc_timestamp(value.get("updated_at"), field="updated_at")
    if updated_at < created_at:
        raise ValidationError("Modal updated_at precedes created_at")
    if value.get("status") not in MODAL_STATE_STATUSES:
        raise ValidationError("Modal job state has an invalid aggregate status")
    if "last_gather_error" in value:
        _nonempty_text(
            value["last_gather_error"],
            field="Modal last_gather_error",
            max_bytes=1000,
        )
    for job in value["jobs"]:
        _validate_strict_job_state(
            job,
            created_at=created_at,
            identity=identity,
            kind=value["kind"],
        )
    if value["status"] != _aggregate_status(value):
        raise ValidationError("Modal aggregate status does not match its jobs")


@dataclass
class ModalJobStore:
    path: Path

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            raise ValidationError(f"Modal job state does not exist: {self.path}")
        try:
            with self.path.open("rb") as handle:
                encoded = handle.read(MODAL_JOB_STATE_MAX_BYTES + 1)
            if len(encoded) > MODAL_JOB_STATE_MAX_BYTES:
                raise ValidationError(
                    f"Modal job state exceeds the {MODAL_JOB_STATE_MAX_BYTES}-byte limit"
                )
            _preflight_modal_state_json(encoded)

            def reject_constant(constant: str) -> None:
                raise ValidationError(f"Modal job state contains non-finite constant: {constant}")

            value = json.loads(
                encoded,
                parse_constant=reject_constant,
                parse_float=_parse_modal_state_float,
                parse_int=_parse_modal_state_int,
            )
        except ValidationError:
            raise
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            RecursionError,
            MemoryError,
            OverflowError,
            ValueError,
        ) as exc:
            raise ValidationError("Modal job state is not valid bounded JSON") from exc
        _validate_modal_state_tree_bounds(value)
        if not isinstance(value, dict) or value.get("schema_version") != MODAL_STATE_SCHEMA_VERSION:
            raise ValidationError("Modal job state has an unsupported schema")
        fields = set(value)
        if (
            not MODAL_STATE_FIELDS.issubset(fields)
            or fields - MODAL_STATE_FIELDS - MODAL_STATE_OPTIONAL_FIELDS
        ):
            raise ValidationError("Modal job state has an invalid schema")
        identity = _validate_provider_identity(value.get("provider_identity"), strict=True)
        if (
            value.get("provider") != "modal"
            or not isinstance(value.get("jobs"), list)
            or value.get("kind") != "fold"
        ):
            raise ValidationError("Modal job state is missing validated provider identity")
        recovered = False
        payload_count = value.get("payload_count")
        if (
            isinstance(payload_count, bool)
            or not isinstance(payload_count, int)
            or payload_count < 1
            or payload_count > MODAL_MAX_JOBS
            or payload_count != len(value["jobs"])
        ):
            raise ValidationError("Modal job state has an invalid payload count")
        for expected_index, job in enumerate(value["jobs"]):
            if (
                not isinstance(job, dict)
                or not MODAL_JOB_FIELDS.issubset(job)
                or set(job) - MODAL_JOB_FIELDS - MODAL_JOB_OPTIONAL_FIELDS
                or isinstance(job.get("index"), bool)
                or not isinstance(job.get("index"), int)
                or job["index"] != expected_index
                or not isinstance(job.get("payload_sha256"), str)
                or not SHA256_RE.fullmatch(job["payload_sha256"])
                or job.get("status") not in MODAL_JOB_STATUSES
            ):
                raise ValidationError("Modal job state contains an invalid job entry")
            if job.get("call_id") is not None:
                _validate_call_id(job["call_id"])
            if job["status"] in {"pending", "cancellation-requested"} and (
                not isinstance(job.get("call_id"), str) or not job["call_id"]
            ):
                raise ValidationError("pending Modal job state requires a call_id")
            if job["status"] == "spawning":
                mark_submission_indeterminate(
                    job, identity, "process ended during Modal submission"
                )
                job["spawn_finished_at"] = utc_now()
                job["finished_at"] = utc_now()
                recovered = True
        if recovered:
            value["status"] = _aggregate_status(value)
            self.save(value)
        _validate_strict_state(value)
        return value

    def save(self, value: dict[str, Any]) -> None:
        value["updated_at"] = utc_now()
        if value.get("schema_version") != MODAL_STATE_SCHEMA_VERSION:
            raise ValidationError("Modal job state has an unsupported schema")
        _validate_modal_state_tree_bounds(value)
        _validate_strict_state(value)
        _bounded_json_size(
            value,
            limit=MODAL_JOB_STATE_MAX_BYTES,
            field="Modal job state",
        )
        write_json_atomic(self.path, value)

    @contextmanager
    def operation_lock(self) -> Iterator[None]:
        """Serialize submissions and cancellation for this durable state path."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class ModalJobManager:
    def __init__(self, adapter: ModalAdapter, store: ModalJobStore) -> None:
        self.adapter = adapter
        self.store = store

    def _adapter_identity(self) -> dict[str, Any]:
        identity = self.adapter.provider_identity()
        return _validate_provider_identity(identity, strict=True)

    def _load_bound_state(self, identity: dict[str, Any]) -> dict[str, Any]:
        state = self.store.load()
        if state["provider_identity"] != identity:
            raise ValidationError(
                "Modal workspace, environment, app, function, function version, or SDK "
                "does not match saved state"
            )
        return state

    def spawn(self, payloads: list[dict[str, Any]], *, kind: str) -> dict[str, Any]:
        if not payloads:
            raise ValidationError("at least one Modal payload is required")
        if len(payloads) > MODAL_MAX_JOBS:
            raise ValidationError(f"Modal payload count exceeds the hard limit of {MODAL_MAX_JOBS}")
        _bounded_json_size(
            payloads,
            limit=MODAL_INPUT_MAX_BYTES,
            field="Modal payload manifest",
        )
        if kind != "fold":
            raise ValidationError("Modal job kind is invalid")
        identity = self._adapter_identity()
        with self.store.operation_lock():
            return self._spawn_locked(payloads, kind=kind, identity=identity)

    def _spawn_locked(
        self,
        payloads: list[dict[str, Any]],
        *,
        kind: str,
        identity: dict[str, Any],
    ) -> dict[str, Any]:
        state = self._prepare_spawn_state(payloads, kind=kind, identity=identity)
        for job, payload in zip(state["jobs"], payloads, strict=True):
            if job["status"] != "queued":
                continue
            job["status"] = "spawning"
            job["spawn_started_at"] = utc_now()
            state["status"] = self._aggregate_status(state)
            self.store.save(state)
            spawn_returned = False
            try:
                call_id = self.adapter.spawn(payload)
                spawn_returned = True
                job["call_id"] = _validate_call_id(call_id)
                job["status"] = "pending"
            except Exception as exc:  # provider adapters define their own exceptions
                reason = (
                    "Modal spawn returned an invalid call ID"
                    if spawn_returned
                    else f"Modal spawn returned {type(exc).__name__}"
                )
                mark_submission_indeterminate(job, identity, reason)
                job["spawn_error"] = redact(str(exc))[:1000]
            job["spawn_finished_at"] = utc_now()
            if job["status"] == "submission-indeterminate":
                job["finished_at"] = utc_now()
            state["status"] = self._aggregate_status(state)
            self.store.save(state)
        state["status"] = self._aggregate_status(state)
        self.store.save(state)
        return state

    @staticmethod
    def _queued_job(index: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "index": index,
            "payload_sha256": input_digest(payload),
            "status": "queued",
            "call_id": None,
            "result": None,
            "error": None,
            "spawn_started_at": None,
            "spawn_finished_at": None,
            "finished_at": None,
        }

    def _prepare_spawn_state(
        self,
        payloads: list[dict[str, Any]],
        *,
        kind: str,
        identity: dict[str, Any],
    ) -> dict[str, Any]:
        jobs = [self._queued_job(index, payload) for index, payload in enumerate(payloads)]
        if not self.store.path.exists():
            state: dict[str, Any] = {
                "schema_version": MODAL_STATE_SCHEMA_VERSION,
                "provider": "modal",
                "scope": "control-plane-only",
                "completion_contract": "compact-result-plus-schema-validated-provenance",
                "provider_identity": identity,
                "kind": kind,
                "payload_count": len(jobs),
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "jobs": jobs,
                "status": "submitting",
            }
            # Persist the complete ordered manifest before any provider call. A
            # crash now leaves every never-attempted payload safely resumable.
            self.store.save(state)
            return state

        state = self._load_bound_state(identity)
        if state["kind"] != kind:
            raise ValidationError("Modal resume kind does not match saved state")

        saved_jobs = state["jobs"]
        if len(saved_jobs) != len(jobs) or state.get("payload_count", len(saved_jobs)) != len(jobs):
            raise ValidationError("Modal resume payload count does not match saved state")
        if any(
            saved["index"] != expected["index"]
            or saved["payload_sha256"] != expected["payload_sha256"]
            for saved, expected in zip(saved_jobs, jobs, strict=True)
        ):
            raise ValidationError("Modal resume payload order or digest does not match saved state")
        if not any(job["status"] == "queued" for job in saved_jobs):
            raise ValidationError(
                "Modal state already exists with no queued submissions; gather, cancel, "
                "or choose a new path"
            )
        return state

    @staticmethod
    def _aggregate_status(state: dict[str, Any]) -> str:
        return _aggregate_status(state)

    def gather(self, *, timeout_per_call: float = 1800.0) -> dict[str, Any]:
        if not math.isfinite(timeout_per_call) or timeout_per_call <= 0:
            raise ValidationError("Modal gather timeout_per_call must be finite and positive")
        identity = self._adapter_identity()
        with self.store.operation_lock():
            state = self._load_bound_state(identity)
            pending = [
                (job["index"], job["call_id"])
                for job in state["jobs"]
                if job["status"] in {"pending", "cancellation-requested"}
            ]
        if not pending:
            return state
        for index, call_id in pending:
            if not isinstance(call_id, str) or not call_id:
                raise ValidationError("pending Modal jobs require call_id")
            try:
                results = self.adapter.gather([call_id], timeout=timeout_per_call)
            except Exception as exc:
                with self.store.operation_lock():
                    state = self._load_bound_state(identity)
                    job = self._pending_job(state, index=index, call_id=call_id)
                    if job is not None:
                        job["last_poll_error"] = redact(str(exc))[:1000]
                        state["last_gather_error"] = job["last_poll_error"]
                        state["status"] = self._aggregate_status(state)
                        self.store.save(state)
                continue
            with self.store.operation_lock():
                state = self._load_bound_state(identity)
                job = self._pending_job(state, index=index, call_id=call_id)
                if job is None:
                    continue
                if len(results) != 1:
                    job["last_poll_error"] = "Modal gather returned an unexpected result count"
                    state["status"] = self._aggregate_status(state)
                    self.store.save(state)
                    continue
                result = results[0]
                previous_status = job["status"]
                job.pop("last_poll_error", None)
                if isinstance(result, CancelledCallError):
                    job["status"] = "cancelled"
                    job["error"] = None
                    job["cancellation_observed_at"] = utc_now()
                    job["finished_at"] = utc_now()
                elif isinstance(result, BaseException):
                    job["status"] = "failed"
                    job["error"] = redact(str(result))[:1000]
                    job["finished_at"] = utc_now()
                else:
                    try:
                        safe_result = validate_modal_result_envelope(
                            result,
                            submission_sha256=job["payload_sha256"],
                            provider_identity=state["provider_identity"],
                            kind=state["kind"],
                        )
                    except ValidationError as exc:
                        job["status"] = "failed"
                        job["error"] = str(exc)
                        job["finished_at"] = utc_now()
                    else:
                        job["status"] = "completed"
                        job["error"] = None
                        job["result"] = safe_result
                        job["finished_at"] = utc_now()
                        if previous_status == "cancellation-requested":
                            job["cancellation_race"] = "completed-before-cancellation-took-effect"
                state["status"] = self._aggregate_status(state)
                self.store.save(state)
        with self.store.operation_lock():
            state = self._load_bound_state(identity)
            state["status"] = self._aggregate_status(state)
            self.store.save(state)
            return state

    @staticmethod
    def _pending_job(state: dict[str, Any], *, index: int, call_id: str) -> dict[str, Any] | None:
        if index >= len(state["jobs"]):
            raise ValidationError("Modal job state changed during gather")
        job = state["jobs"][index]
        if job["index"] != index or job.get("call_id") != call_id:
            raise ValidationError("Modal job identity changed during gather")
        if job["status"] not in {"pending", "cancellation-requested"}:
            return None
        return job

    def cancel(self) -> dict[str, Any]:
        with self.store.operation_lock():
            return self._cancel_locked()

    def _cancel_locked(self) -> dict[str, Any]:
        identity = self._adapter_identity()
        state = self._load_bound_state(identity)
        queued = [job for job in state["jobs"] if job["status"] == "queued"]
        if queued:
            # Persist the complete local do-not-submit intent in one atomic
            # state write before any remote cancellation calls. An interrupted
            # cancel can therefore never leave later queued payloads resumable.
            cancelled_at = utc_now()
            for job in queued:
                job["status"] = "cancelled"
                job["cancellation_reason"] = "cancelled-before-submission"
                job["finished_at"] = cancelled_at
            state["status"] = self._aggregate_status(state)
            self.store.save(state)
        for job in state["jobs"]:
            if job["status"] != "pending":
                continue
            try:
                self.adapter.cancel(job["call_id"])
                job["status"] = "cancellation-requested"
                job["error"] = None
                job["cancellation_requested_at"] = utc_now()
            except Exception as exc:
                job["error"] = redact(str(exc))[:1000]
            state["status"] = self._aggregate_status(state)
            self.store.save(state)
        state["status"] = self._aggregate_status(state)
        self.store.save(state)
        return state


class ModalFunctionAdapter:
    """Optional real adapter for a deployed Modal function accepting kwargs."""

    _TERMINAL_RESULT_ERRORS = (
        "ExecutionError",
        "FunctionTimeoutError",
        "OutputExpiredError",
        "RemoteError",
        "UserCodeException",
    )

    def __init__(
        self,
        app_name: str | None = None,
        function_name: str | None = None,
        function_version: int | None = None,
        *,
        workspace_name: str | None = None,
        environment_name: str | None = None,
    ) -> None:
        try:
            import modal
        except ImportError as exc:
            raise ValidationError(
                f"install the pinned Modal SDK ({MODAL_SDK_VERSION}) before using the real adapter"
            ) from exc
        sdk_version = getattr(modal, "__version__", None)
        if not isinstance(sdk_version, str) or not sdk_version:
            try:
                sdk_version = metadata.version("modal")
            except metadata.PackageNotFoundError as exc:
                raise ValidationError("could not resolve the installed Modal SDK version") from exc
        if sdk_version != MODAL_SDK_VERSION:
            raise ValidationError(
                f"Modal SDK version mismatch: expected {MODAL_SDK_VERSION}, found {sdk_version}"
            )
        if function_version is not None and (
            isinstance(function_version, bool)
            or not isinstance(function_version, int)
            or function_version < 1
        ):
            raise ValidationError("Modal function_version must be a positive integer")
        self.modal = modal
        self.sdk_version = sdk_version
        self.app_name = app_name
        self.function_name = function_name
        self.function_version = function_version
        self.workspace_name = workspace_name
        self.environment_name = environment_name
        self.function = None

    def provider_identity(self) -> dict[str, Any]:
        declared_workspace = _nonempty_text(
            self.workspace_name,
            field="Modal workspace_name",
        )
        try:
            workspace = self.modal.Workspace.from_context().hydrate()
            active_workspace = _nonempty_text(
                workspace.name,
                field="active Modal workspace name",
            )
        except Exception as exc:
            raise ValidationError("could not resolve the active Modal workspace") from exc
        if active_workspace != declared_workspace:
            raise ValidationError(
                "declared Modal workspace_name does not match the active credential-bound workspace"
            )
        return {
            "workspace_name": active_workspace,
            "environment_name": self.environment_name or "",
            "app_name": self.app_name or "",
            "function_name": self.function_name or "",
            "function_version": self.function_version,
            "modal_sdk_version": self.sdk_version,
        }

    def spawn(self, payload: dict[str, Any]) -> str:
        if (
            not self.workspace_name
            or not self.environment_name
            or not self.app_name
            or not self.function_name
            or self.function_version is None
        ):
            raise ValidationError(
                "Modal spawn requires workspace, environment, app, function, and pinned "
                "function version"
            )
        if self.function is None:
            self.function = self.modal.Function.from_name(
                self.app_name,
                self.function_name,
                version=self.function_version,
                environment_name=self.environment_name,
            )
        call = self.function.spawn(**payload)
        return _validate_call_id(call.object_id)

    def _is_terminal_result_error(self, exc: BaseException) -> bool:
        """Classify errors raised while decoding a completed Modal call.

        Modal's own non-terminal ``Error`` subclasses describe control-plane or
        polling failures, so the durable call ID remains resumable. The SDK raises
        deserialized user-code exceptions directly, however; an ordinary Python
        exception therefore represents a terminal remote result rather than a
        retryable polling failure.
        """

        exception_namespace = getattr(self.modal, "exception", None)
        if exception_namespace is None:
            return True
        terminal_types = tuple(
            candidate
            for name in self._TERMINAL_RESULT_ERRORS
            if isinstance((candidate := getattr(exception_namespace, name, None)), type)
            and issubclass(candidate, BaseException)
        )
        if terminal_types and isinstance(exc, terminal_types):
            return True
        modal_error = getattr(exception_namespace, "Error", None)
        if (
            isinstance(modal_error, type)
            and issubclass(modal_error, Exception)
            and isinstance(exc, modal_error)
        ):
            return False
        return True

    def gather(self, call_ids: list[str], *, timeout: float) -> list[Any]:
        calls = [self.modal.FunctionCall.from_id(call_id) for call_id in call_ids]
        results: list[Any] = []
        for call in calls:
            try:
                results.append(call.get(timeout=timeout))
            except TimeoutError:
                raise
            except self.modal.exception.InputCancellation:
                results.append(CancelledCallError("Modal call was cancelled"))
            except Exception as exc:
                if not self._is_terminal_result_error(exc):
                    raise
                results.append(exc)
        return results

    def cancel(self, call_id: str) -> None:
        self.modal.FunctionCall.from_id(call_id).cancel()

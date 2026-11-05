"""Small, mockable HTTP layer for Biohub managed and Atlas APIs."""

from __future__ import annotations

import errno
import json
import math
import os
import re
import socket
import ssl
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import IncompleteRead
from pathlib import Path
from typing import Any, BinaryIO, Callable, Protocol

# The installed plugin cannot depend on the monorepo-only HTTP client.
from urllib import error, request  # noqa: TID251

from .constants import (
    BIOHUB_BASE_URL,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ESMC_MANAGED_MODELS,
    ESMFOLD2_MANAGED_MODELS,
    MANAGED_ENDPOINTS,
)
from .diagnostics import (
    DIAGNOSTIC_PREVIEW_MAX_BYTES,
    PROVIDER_JSON_MAX_DEPTH,
    PROVIDER_JSON_MAX_NODES,
    PROVIDER_JSON_MAX_NUMBER_CHARACTERS,
    PROVIDER_JSON_MAX_TEXT_BYTES,
    PROVIDER_RESPONSE_MAX_BYTES,
    json_nesting_exceeds,
)
from .errors import APIError, BiohubESMError, SchemaDriftError, ValidationError
from .security import (
    missing_esm_api_key_message,
    redact_truncated_text,
    register_redaction_secret,
)

_RESPONSE_CONTEXT_ERRORS = (
    error.URLError,
    TimeoutError,
    socket.timeout,
    ssl.SSLError,
    OSError,
    AttributeError,
    TypeError,
    ValueError,
)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _bounded_json_int(value: str) -> int:
    if len(value) > PROVIDER_JSON_MAX_NUMBER_CHARACTERS:
        raise ValueError("JSON integer token exceeds the numeric safety bound")
    return int(value)


def _finite_json_float(value: str) -> float:
    if len(value) > PROVIDER_JSON_MAX_NUMBER_CHARACTERS:
        raise ValueError("JSON float token exceeds the numeric safety bound")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite JSON number")
    mantissa = value.lower().split("e", 1)[0]
    if result == 0.0 and any(character in "123456789" for character in mantissa):
        raise ValueError("JSON number underflows the finite float range")
    return result


def _validate_json_resource_budget(body: bytes) -> None:
    """Reject wire-compact JSON before Python object expansion can exhaust memory."""

    if len(body) > PROVIDER_RESPONSE_MAX_BYTES:
        raise SchemaDriftError(
            f"provider response exceeded the {PROVIDER_RESPONSE_MAX_BYTES}-byte safety limit",
            raw=body,
        )
    nodes = 1
    depth = 0
    text_bytes = 0
    number_characters = 0
    in_string = False
    escaped = False
    for byte in body:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
                continue
            text_bytes += 1
            if text_bytes > PROVIDER_JSON_MAX_TEXT_BYTES:
                raise SchemaDriftError(
                    "provider JSON exceeds the safe decoded text budget",
                    raw=body,
                )
            continue

        if byte == 0x22:
            in_string = True
            number_characters = 0
        elif byte in (0x7B, 0x5B):
            depth += 1
            nodes += 1
            number_characters = 0
            if depth > PROVIDER_JSON_MAX_DEPTH:
                raise SchemaDriftError(
                    "provider JSON exceeds the safe nesting depth",
                    raw=body,
                )
        elif byte in (0x7D, 0x5D):
            depth = max(0, depth - 1)
            number_characters = 0
        elif byte in (0x2C, 0x3A):
            nodes += 1
            number_characters = 0
        elif byte in b"+-.0123456789Ee":
            number_characters += 1
            if number_characters > PROVIDER_JSON_MAX_NUMBER_CHARACTERS:
                raise SchemaDriftError(
                    "provider JSON exceeds the numeric token safety bound",
                    raw=body,
                )
        elif byte not in b" \t\r\n":
            number_characters = 0

        if nodes > PROVIDER_JSON_MAX_NODES:
            raise SchemaDriftError(
                "provider JSON exceeds the safe decoded node budget",
                raw=body,
            )


def _json_contains_unpaired_surrogate(value: Any) -> bool:
    """Detect non-scalar Unicode in decoded JSON with O(depth) memory."""

    stack = [iter((value,))]
    while stack:
        iterator = stack[-1]
        try:
            item = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        if isinstance(item, str):
            if any("\ud800" <= character <= "\udfff" for character in item):
                return True
        elif isinstance(item, dict):
            if any(any("\ud800" <= character <= "\udfff" for character in key) for key in item):
                return True
            stack.append(iter(item.values()))
        elif isinstance(item, list):
            stack.append(iter(item))
    return False


def encode_json_body(value: Any) -> bytes:
    try:
        return json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValidationError(
            "outbound request must be interoperable JSON without non-finite numbers"
        ) from exc


def validate_timeout(value: float, context: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValidationError(f"{context} must be a finite positive number")
    return float(value)


def _absolute_deadline(timeout: float, deadline: float | None, context: str) -> float:
    validated_timeout = validate_timeout(timeout, context)
    if deadline is None:
        result = time.monotonic() + validated_timeout
        if not math.isfinite(result):
            raise ValidationError(f"{context} produces a non-finite deadline")
        return result
    if (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(deadline)
    ):
        raise ValidationError(f"{context} deadline must be finite")
    return float(deadline)


def _remaining_deadline(deadline: float, context: str, *, partial: bool = False) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise APIError(
            status=None,
            kind="timeout",
            message=f"{context} deadline expired",
            partial=partial,
        )
    return remaining


def _identity_bound_path_has_bytes(
    path: Path,
    expected_identity: tuple[int, int] | None,
) -> bool:
    """Report retained bytes only for the stream destination inode we opened."""

    if expected_identity is None:
        return False
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISREG(info.st_mode)
        and (info.st_dev, info.st_ino) == expected_identity
        and info.st_size > 0
    )


def _response_sink_has_bytes(sink: BinaryIO, *, flush: bool = False) -> bool:
    """Report bytes retained by an already-open regular response sink."""

    if flush:
        try:
            sink.flush()
        except (OSError, ValueError):
            pass
    try:
        info = os.fstat(sink.fileno())
    except (AttributeError, OSError, ValueError):
        return False
    return stat.S_ISREG(info.st_mode) and info.st_size > 0


def _local_stream_error(
    message: str,
    *,
    provider_status: int | None,
    partial: bool,
) -> ValidationError:
    """Describe a definitive local failure and bind a known response status."""

    result = ValidationError(message)
    if provider_status is not None:
        result.provider_status = provider_status
    result.partial = partial
    result.operation_indeterminate = provider_status is None or provider_status < 200
    return result


def _validated_provider_status(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599:
        return value
    return None


def _bind_provider_status(
    failure: BiohubESMError,
    provider_status: int | None,
) -> BiohubESMError:
    provider_status = _validated_provider_status(provider_status)
    if provider_status is not None:
        failure.provider_status = provider_status
        if isinstance(failure, APIError):
            if provider_status < 200:
                failure.operation_indeterminate = True
                failure.response_body_partial = True
            else:
                # A final HTTP status proves whether the provider accepted the
                # request. A later body/read failure can still leave response
                # evidence incomplete, but it does not make submission unknown.
                failure.operation_indeterminate = False
    return failure


def _merge_stream_failures(
    primary: BiohubESMError,
    secondary: BiohubESMError,
    *,
    provider_status: int | None,
    partial: bool,
) -> BiohubESMError:
    """Keep the first failure's certainty when local cleanup also fails."""

    _bind_provider_status(primary, provider_status)
    primary.partial = bool(
        getattr(primary, "partial", False) or getattr(secondary, "partial", False) or partial
    )
    return primary


def _create_status_bound_stream_parent(
    destination: Path,
    *,
    provider_status: int | None,
    expected_identity: tuple[int, int] | None,
) -> None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        raise _local_stream_error(
            "local stream destination directory could not be prepared",
            provider_status=provider_status,
            partial=_identity_bound_path_has_bytes(destination, expected_identity),
        ) from exc


def _open_status_bound_stream_destination(
    destination: Path,
    *,
    append: bool,
    expected_identity: tuple[int, int] | None,
    provider_status: int | None,
) -> tuple[Any, tuple[int, int]]:
    try:
        return _open_stream_destination(
            destination,
            append=append,
            expected_identity=expected_identity,
        )
    except BiohubESMError as exc:
        exc.partial = _identity_bound_path_has_bytes(destination, expected_identity)
        exc.operation_indeterminate = provider_status is None or provider_status < 200
        _bind_provider_status(exc, provider_status)
        raise
    except (OSError, ValueError) as exc:
        raise _local_stream_error(
            "local stream destination could not be opened",
            provider_status=provider_status,
            partial=_identity_bound_path_has_bytes(destination, expected_identity),
        ) from exc


def _status_bound_stream_size(
    handle: BinaryIO,
    *,
    provider_status: int | None,
    partial: bool,
) -> int:
    try:
        return os.fstat(handle.fileno()).st_size
    except (OSError, ValueError) as exc:
        raise _local_stream_error(
            "local stream destination size could not be read",
            provider_status=provider_status,
            partial=partial,
        ) from exc


def _write_stream_destination(
    handle: BinaryIO,
    data: bytes,
    *,
    provider_status: int | None,
    partial: bool,
) -> None:
    try:
        written = handle.write(data)
    except (OSError, ValueError) as exc:
        raise _local_stream_error(
            "local stream destination write failed",
            provider_status=provider_status,
            partial=partial,
        ) from exc
    if isinstance(written, bool) or not isinstance(written, int) or written != len(data):
        raise _local_stream_error(
            "local stream destination write was incomplete",
            provider_status=provider_status,
            partial=partial
            or (isinstance(written, int) and not isinstance(written, bool) and written > 0),
        )


def _sync_stream_destination(
    handle: BinaryIO,
    *,
    provider_status: int | None,
    partial: bool,
) -> None:
    try:
        handle.flush()
    except (OSError, ValueError) as exc:
        raise _local_stream_error(
            "local stream destination flush failed",
            provider_status=provider_status,
            partial=partial,
        ) from exc
    try:
        os.fsync(handle.fileno())
    except (OSError, ValueError) as exc:
        raise _local_stream_error(
            "local stream destination sync failed",
            provider_status=provider_status,
            partial=partial,
        ) from exc


@contextmanager
def _status_bound_stream_handle(
    handle: BinaryIO,
    destination: Path,
    *,
    provider_status: int | None,
    expected_identity: tuple[int, int] | None = None,
):
    """Prevent a close-time local I/O error from escaping unnormalized."""

    try:
        entered = handle.__enter__()
    except BiohubESMError:
        raise
    except (OSError, ValueError) as exc:
        raise _local_stream_error(
            "local stream destination could not be entered",
            provider_status=provider_status,
            partial=_identity_bound_path_has_bytes(destination, expected_identity),
        ) from exc
    try:
        yield entered
    except BaseException as active_failure:
        close_failure: BiohubESMError | None = None
        try:
            handle.__exit__(
                type(active_failure),
                active_failure,
                active_failure.__traceback__,
            )
        except BiohubESMError as exc:
            close_failure = exc
        except (OSError, ValueError):
            close_failure = _local_stream_error(
                "local stream destination close failed",
                provider_status=provider_status,
                partial=_identity_bound_path_has_bytes(destination, expected_identity),
            )
        if close_failure is not None:
            if isinstance(active_failure, IncompleteRead):
                retained_partial = _identity_bound_path_has_bytes(
                    destination,
                    expected_identity,
                )
                incomplete_failure = APIError(
                    status=None,
                    kind="network",
                    message="provider stream was incomplete",
                    partial=retained_partial,
                    response_body_partial=True,
                )
                _merge_stream_failures(
                    incomplete_failure,
                    close_failure,
                    provider_status=provider_status,
                    partial=retained_partial,
                )
                incomplete_failure.partial = retained_partial
                raise incomplete_failure from None
            if isinstance(active_failure, BiohubESMError):
                _merge_stream_failures(
                    active_failure,
                    close_failure,
                    provider_status=provider_status,
                    partial=_identity_bound_path_has_bytes(
                        destination,
                        expected_identity,
                    ),
                )
        # A close failure must not replace a provider timeout, incomplete read,
        # or other active failure. A failed close while IncompleteRead is active
        # is normalized above without reopening the possibly still-live file.
        raise
    else:
        try:
            handle.__exit__(None, None, None)
        except BiohubESMError:
            raise
        except (OSError, ValueError) as exc:
            raise _local_stream_error(
                "local stream destination close failed",
                provider_status=provider_status,
                partial=_identity_bound_path_has_bytes(destination, expected_identity),
            ) from exc


def _cap_response_timeout(response: Any, timeout: float) -> None:
    """Best-effort cap on the live response socket before each bounded read."""

    pending = [response]
    seen: set[int] = set()
    for _ in range(6):
        next_pending: list[Any] = []
        for value in pending:
            identity = id(value)
            if identity in seen:
                continue
            seen.add(identity)
            setter = getattr(value, "settimeout", None)
            if callable(setter):
                try:
                    setter(timeout)
                except (OSError, ValueError):
                    pass
                else:
                    return
            for attribute in ("fp", "raw", "_sock", "sock"):
                child = getattr(value, attribute, None)
                if child is not None:
                    next_pending.append(child)
        pending = next_pending
        if not pending:
            return


def _response_reader(response: Any) -> Any:
    for candidate in (response, getattr(response, "fp", None)):
        reader = getattr(candidate, "read1", None)
        if callable(reader):
            return reader
    return response.read


def _declared_response_length(response: Any) -> int | None:
    """Return the initial declared body length, excluding chunked responses."""

    headers = getattr(response, "headers", None)
    transfer_encoding = headers.get("transfer-encoding") if hasattr(headers, "get") else None
    if getattr(response, "chunked", False) is True or (
        isinstance(transfer_encoding, str) and "chunked" in transfer_encoding.lower()
    ):
        return None
    remaining = getattr(response, "length", None)
    if isinstance(remaining, int) and not isinstance(remaining, bool) and remaining >= 0:
        return remaining
    raw = headers.get("content-length") if hasattr(headers, "get") else None
    if isinstance(raw, str) and raw.isdecimal():
        try:
            return int(raw)
        except (ValueError, OverflowError):
            return None
    return None


def _read_failure_kind(exc: BaseException) -> str:
    reason = getattr(exc, "reason", exc)
    return "timeout" if isinstance(reason, (TimeoutError, socket.timeout)) else "network"


def _bounded_response_body(
    response: Any,
    deadline: float,
    context: str,
    max_timeout: float,
    *,
    max_bytes: int | None = None,
) -> bytes:
    limit = PROVIDER_RESPONSE_MAX_BYTES if max_bytes is None else max_bytes
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValidationError("provider response byte limit must be a positive integer")
    body = bytearray()
    declared_length = _declared_response_length(response)
    response_body_complete = declared_length == 0
    if declared_length is not None and declared_length > limit:
        raise SchemaDriftError(
            f"{context} exceeded the {limit}-byte safety limit",
            raw={
                "representation": "provider-response-byte-limit",
                "limit_bytes": limit,
                "declared_size_bytes": declared_length,
                "received_size_bytes": 0,
                "truncated": True,
            },
        )
    while True:
        try:
            remaining = _remaining_deadline(deadline, context)
        except APIError as failure:
            failure.partial = False
            failure.response_body_partial = not response_body_complete
            raise
        if response_body_complete:
            return bytes(body)
        _cap_response_timeout(response, min(max_timeout, remaining))
        try:
            chunk = _response_reader(response)(min(64 * 1024, limit + 1 - len(body)))
        except IncompleteRead:
            raise APIError(
                status=None,
                kind="network",
                message=f"{context} was incomplete",
                response_body_partial=True,
            ) from None
        except (TimeoutError, socket.timeout):
            raise APIError(
                status=None,
                kind="timeout",
                message=f"{context} timed out",
                response_body_partial=True,
            ) from None
        except (error.URLError, ssl.SSLError, OSError) as exc:
            kind = _read_failure_kind(exc)
            raise APIError(
                status=None,
                kind=kind,
                message=f"{context} failed: {kind}",
                response_body_partial=True,
            ) from None
        if chunk:
            observed_size = len(body) + len(chunk)
            if observed_size > limit:
                preview = bytes(body[:DIAGNOSTIC_PREVIEW_MAX_BYTES])
                if len(preview) < DIAGNOSTIC_PREVIEW_MAX_BYTES:
                    preview += chunk[: DIAGNOSTIC_PREVIEW_MAX_BYTES - len(preview)]
                raise SchemaDriftError(
                    f"{context} exceeded the {limit}-byte safety limit",
                    raw={
                        "representation": "provider-response-byte-limit",
                        "limit_bytes": limit,
                        "declared_size_bytes": declared_length,
                        "received_size_bytes": observed_size,
                        "truncated": True,
                        "body_prefix": preview.decode("utf-8", errors="replace"),
                    },
                )
            body.extend(chunk)
            if declared_length is not None and len(body) >= declared_length:
                response_body_complete = True
        else:
            response_body_complete = declared_length is None or len(body) >= declared_length
        try:
            _remaining_deadline(deadline, context)
        except APIError as failure:
            failure.partial = False
            failure.response_body_partial = not response_body_complete
            raise
        if not chunk:
            if declared_length is not None and len(body) < declared_length:
                raise APIError(
                    status=None,
                    kind="network",
                    message=f"{context} ended before its declared Content-Length",
                    response_body_partial=True,
                )
            return bytes(body)
        if response_body_complete:
            return bytes(body)


def _validate_empty_response_sink(sink: BinaryIO) -> None:
    try:
        sink_info = os.fstat(sink.fileno())
        sink_position = sink.tell()
    except (AttributeError, OSError, ValueError) as exc:
        raise ValidationError("provider stream sink is unavailable") from exc
    if not stat.S_ISREG(sink_info.st_mode) or sink_info.st_size != 0 or sink_position != 0:
        raise ValidationError("provider stream sink must be an empty regular file")


def _bounded_response_to_sink(
    response: Any,
    sink: BinaryIO,
    deadline: float,
    context: str,
    max_timeout: float,
    *,
    max_bytes: int,
) -> int:
    """Stream one response into an already-open empty regular file."""

    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValidationError("provider stream byte limit must be a positive integer")
    _validate_empty_response_sink(sink)

    declared_length = _declared_response_length(response)
    response_body_complete = declared_length == 0
    if declared_length is not None and declared_length > max_bytes:
        raise SchemaDriftError(
            f"{context} exceeded the {max_bytes}-byte safety limit",
            raw={
                "representation": "provider-stream-byte-limit",
                "limit_bytes": max_bytes,
                "declared_size_bytes": declared_length,
                "received_size_bytes": 0,
                "truncated": True,
            },
        )

    received = 0

    def finalize_sink() -> int:
        try:
            sink.flush()
            sink.seek(0)
        except (OSError, ValueError) as exc:
            raise ValidationError("provider stream sink could not be finalized") from exc
        return received

    while True:
        try:
            remaining = _remaining_deadline(
                deadline,
                context,
                partial=_response_sink_has_bytes(sink),
            )
        except APIError as failure:
            failure.partial = _response_sink_has_bytes(sink, flush=True)
            failure.response_body_partial = not response_body_complete
            raise
        if response_body_complete:
            return finalize_sink()
        _cap_response_timeout(response, min(max_timeout, remaining))
        try:
            chunk = _response_reader(response)(min(64 * 1024, max_bytes - received + 1))
        except IncompleteRead:
            raise APIError(
                status=None,
                kind="network",
                message=f"{context} was incomplete",
                partial=_response_sink_has_bytes(sink, flush=True),
                response_body_partial=True,
            ) from None
        except (TimeoutError, socket.timeout):
            raise APIError(
                status=None,
                kind="timeout",
                message=f"{context} timed out",
                partial=_response_sink_has_bytes(sink, flush=True),
                response_body_partial=True,
            ) from None
        except (error.URLError, ssl.SSLError, OSError) as exc:
            kind = _read_failure_kind(exc)
            raise APIError(
                status=None,
                kind=kind,
                message=f"{context} failed: {kind}",
                partial=_response_sink_has_bytes(sink, flush=True),
                response_body_partial=True,
            ) from None
        if chunk:
            observed_size = received + len(chunk)
            retained = min(len(chunk), max_bytes - received)
            if retained:
                try:
                    written = sink.write(chunk[:retained])
                except (OSError, ValueError) as exc:
                    raise ValidationError("provider stream sink write failed") from exc
                if written != retained:
                    raise ValidationError("provider stream sink write was incomplete")
                received += retained
            if observed_size > max_bytes:
                try:
                    sink.flush()
                except (OSError, ValueError) as exc:
                    raise ValidationError("provider stream sink flush failed") from exc
                raise SchemaDriftError(
                    f"{context} exceeded the {max_bytes}-byte safety limit",
                    raw={
                        "representation": "provider-stream-byte-limit",
                        "limit_bytes": max_bytes,
                        "declared_size_bytes": declared_length,
                        "received_size_bytes": observed_size,
                        "truncated": True,
                    },
                )
            if declared_length is not None and received >= declared_length:
                response_body_complete = True
        else:
            response_body_complete = declared_length is None or received >= declared_length
        try:
            _remaining_deadline(
                deadline,
                context,
                partial=_response_sink_has_bytes(sink),
            )
        except APIError as failure:
            failure.partial = _response_sink_has_bytes(sink, flush=True)
            failure.response_body_partial = not response_body_complete
            raise
        if not chunk:
            if declared_length is not None and received < declared_length:
                raise APIError(
                    status=None,
                    kind="network",
                    message=f"{context} ended before its declared Content-Length",
                    partial=_response_sink_has_bytes(sink, flush=True),
                    response_body_partial=True,
                )
            return finalize_sink()
        if response_body_complete:
            return finalize_sink()


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    headers: dict[str, str]
    body: bytes


def _http_error_kind(status: int) -> str:
    """Classify a known provider status independently of its response body."""

    kind = {
        400: "malformed-input",
        401: "authentication",
        403: "authorization-or-safety",
        404: "not-found",
        408: "timeout",
        409: "conflict",
        410: "expired",
        422: "validation",
        429: "rate-limit",
    }.get(status)
    if status == 402:
        return "credits"
    if status >= 500:
        return "provider"
    return kind or "http"


def _http_error_response(
    exc: error.HTTPError,
    deadline: float,
    context: str,
    max_timeout: float,
    *,
    artifact_partial: bool | None = None,
) -> HTTPResponse:
    """Read an HTTP error body without confusing evidence loss with call certainty."""

    try:
        try:
            headers = {key.lower(): value for key, value in exc.headers.items()}
        except _RESPONSE_CONTEXT_ERRORS:
            raise APIError(
                status=exc.code,
                kind=_http_error_kind(exc.code),
                message="provider error response headers could not be read",
                partial=bool(artifact_partial),
                response_body_partial=True,
                operation_indeterminate=100 <= exc.code < 200,
            ) from None
        if 300 <= exc.code < 400:
            # Redirects are intentionally not followed. Their body is irrelevant
            # to that decision and can be unreadable after urllib rejects the
            # redirect, so preserve only the status and headers.
            return HTTPResponse(status=exc.code, headers=headers, body=b"")
        try:
            body = _bounded_response_body(exc, deadline, context, max_timeout)
        except SchemaDriftError:
            raise APIError(
                status=exc.code,
                kind=_http_error_kind(exc.code),
                message="provider error response exceeded the configured byte limit",
                retry_after=_retry_after(headers),
                partial=bool(artifact_partial),
                response_body_partial=True,
            ) from None
        except APIError as read_error:
            raise APIError(
                status=exc.code,
                kind=_http_error_kind(exc.code),
                message=f"provider error response read failed: {read_error.kind}",
                retry_after=_retry_after(headers),
                partial=bool(artifact_partial),
                response_body_partial=read_error.response_body_partial,
            ) from None
        except _RESPONSE_CONTEXT_ERRORS as read_error:
            read_kind = _read_failure_kind(read_error)
            raise APIError(
                status=exc.code,
                kind=_http_error_kind(exc.code),
                message=f"provider error response read failed: {read_kind}",
                retry_after=_retry_after(headers),
                partial=bool(artifact_partial),
                response_body_partial=True,
            ) from None
        return HTTPResponse(status=exc.code, headers=headers, body=body)
    finally:
        try:
            exc.close()
        except _RESPONSE_CONTEXT_ERRORS:
            pass


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        deadline: float | None = None,
    ) -> HTTPResponse: ...


class _RejectRedirectHandler(request.HTTPRedirectHandler):
    """Return every redirect as a response; never forward sensitive headers."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _open_provider_response(
    opener: Any,
    req: request.Request,
    *,
    timeout: float,
    context: str,
    partial: bool = False,
) -> Any:
    """Normalize connection-establishment failures without catching local file I/O."""

    try:
        return opener.open(req, timeout=timeout)
    except error.HTTPError:
        raise
    except IncompleteRead:
        raise APIError(
            status=None,
            kind="network",
            message=f"{context} was incomplete",
            partial=partial,
            response_body_partial=True,
        ) from None
    except (error.URLError, TimeoutError, socket.timeout, ssl.SSLError, OSError) as exc:
        kind = _read_failure_kind(exc)
        raise APIError(
            status=None,
            kind=kind,
            message=f"{context} failed: {kind}",
            partial=partial,
        ) from None


class _ProviderResponseContext:
    """Normalize provider context entry/exit without catching local body I/O."""

    def __init__(
        self,
        response: Any,
        *,
        context: str,
        partial: bool | Callable[[], bool] = False,
        completed: bool | Callable[[], bool] = False,
    ) -> None:
        self.response = response
        self.context = context
        self.partial = partial
        self.completed = completed

    def _has_partial(self) -> bool:
        return bool(self.partial() if callable(self.partial) else self.partial)

    def _is_completed(self) -> bool:
        return bool(self.completed() if callable(self.completed) else self.completed)

    def _normalized(self, exc: BaseException) -> APIError:
        kind = _read_failure_kind(exc)
        return APIError(
            status=None,
            kind=kind,
            message=f"{self.context} failed: {kind}",
            partial=self._has_partial(),
            response_body_partial=True,
        )

    def __enter__(self) -> Any:
        try:
            enter = getattr(self.response, "__enter__", None)
            if not callable(enter):
                return self.response
            return enter()
        except _RESPONSE_CONTEXT_ERRORS as exc:
            raise self._normalized(exc) from None

    def __exit__(self, exc_type, exc, traceback):  # type: ignore[no-untyped-def]
        try:
            exit_method = getattr(self.response, "__exit__", None)
            if not callable(exit_method):
                return False
            return exit_method(exc_type, exc, traceback)
        except _RESPONSE_CONTEXT_ERRORS as close_error:
            if exc_type is not None or self._is_completed():
                return False
            raise self._normalized(close_error) from None


class UrllibTransport:
    def __init__(self) -> None:
        self._opener = request.build_opener(_RejectRedirectHandler())

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        deadline: float | None = None,
    ) -> HTTPResponse:
        timeout = validate_timeout(timeout, "request timeout")
        deadline = _absolute_deadline(timeout, deadline, "provider request")
        req = request.Request(url, data=body, headers=headers or {}, method=method)
        known_provider_status: int | None = None
        try:
            open_timeout = min(
                timeout,
                _remaining_deadline(deadline, "provider request"),
            )
            opened_response = _open_provider_response(
                self._opener,
                req,
                timeout=open_timeout,
                context="provider request",
            )
            known_provider_status = _validated_provider_status(
                getattr(opened_response, "status", None)
            )
            response_complete = [False]
            with _ProviderResponseContext(
                opened_response,
                context="provider response close",
                completed=lambda: response_complete[0],
            ) as response:
                response_status = response.status
                known_provider_status = _validated_provider_status(response_status)
                try:
                    _remaining_deadline(deadline, "provider request")
                except APIError as failure:
                    failure.response_body_partial = True
                    raise
                result = HTTPResponse(
                    status=response_status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=_bounded_response_body(
                        response,
                        deadline,
                        "provider response",
                        timeout,
                    ),
                )
                response_complete[0] = True
                return result
        except error.HTTPError as exc:
            return _http_error_response(
                exc,
                deadline,
                "provider error response",
                timeout,
            )
        except IncompleteRead:
            failure = APIError(
                status=None,
                kind="network",
                message="provider response was incomplete",
                response_body_partial=True,
            )
            raise _bind_provider_status(failure, known_provider_status) from None
        except BiohubESMError as failure:
            if isinstance(failure, APIError):
                failure.partial = False
            _bind_provider_status(failure, known_provider_status)
            raise
        except (
            error.URLError,
            TimeoutError,
            socket.timeout,
            ssl.SSLError,
            OSError,
            ConnectionError,
            AttributeError,
            TypeError,
            ValueError,
        ) as exc:
            reason = getattr(exc, "reason", exc)
            kind = "timeout" if isinstance(reason, (TimeoutError, socket.timeout)) else "network"
            failure = APIError(
                status=None,
                kind=kind,
                message=f"provider request failed: {kind}",
                response_body_partial=known_provider_status is not None,
            )
            raise _bind_provider_status(failure, known_provider_status) from None

    def request_stream_status_to(
        self,
        method: str,
        url: str,
        sink: BinaryIO,
        *,
        stream_status: int,
        max_stream_bytes: int,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        deadline: float | None = None,
    ) -> HTTPResponse:
        """Stream one selected success status; generically bound every other body."""

        if (
            isinstance(stream_status, bool)
            or not isinstance(stream_status, int)
            or not 200 <= stream_status <= 299
        ):
            raise ValidationError("provider stream status must be a successful HTTP status")
        if (
            isinstance(max_stream_bytes, bool)
            or not isinstance(max_stream_bytes, int)
            or max_stream_bytes <= 0
        ):
            raise ValidationError("provider stream byte limit must be a positive integer")
        _validate_empty_response_sink(sink)
        timeout = validate_timeout(timeout, "request timeout")
        deadline = _absolute_deadline(timeout, deadline, "provider request")
        req = request.Request(url, data=body, headers=headers or {}, method=method)
        known_provider_status: int | None = None
        try:
            open_timeout = min(timeout, _remaining_deadline(deadline, "provider request"))
            opened_response = _open_provider_response(
                self._opener,
                req,
                timeout=open_timeout,
                context="provider request",
            )
            known_provider_status = _validated_provider_status(
                getattr(opened_response, "status", None)
            )
            response_complete = [False]
            with _ProviderResponseContext(
                opened_response,
                context="provider response close",
                partial=lambda: _response_sink_has_bytes(sink),
                completed=lambda: response_complete[0],
            ) as response:
                response_status = response.status
                known_provider_status = _validated_provider_status(response_status)
                try:
                    _remaining_deadline(deadline, "provider request")
                except APIError as failure:
                    failure.response_body_partial = True
                    raise
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                try:
                    if response_status == stream_status:
                        _bounded_response_to_sink(
                            response,
                            sink,
                            deadline,
                            "provider response stream",
                            timeout,
                            max_bytes=max_stream_bytes,
                        )
                        body_bytes = b""
                    else:
                        body_bytes = _bounded_response_body(
                            response,
                            deadline,
                            "provider response",
                            timeout,
                        )
                except BiohubESMError as exc:
                    _bind_provider_status(exc, known_provider_status)
                    raise
                result = HTTPResponse(response_status, response_headers, body_bytes)
                response_complete[0] = True
                return result
        except error.HTTPError as exc:
            return _http_error_response(
                exc,
                deadline,
                "provider error response",
                timeout,
                artifact_partial=_response_sink_has_bytes(sink),
            )
        except IncompleteRead:
            failure = APIError(
                status=None,
                kind="network",
                message="provider response was incomplete",
                partial=_response_sink_has_bytes(sink, flush=True),
                response_body_partial=True,
            )
            raise _bind_provider_status(failure, known_provider_status) from None
        except BiohubESMError as failure:
            if isinstance(failure, APIError):
                failure.partial = _response_sink_has_bytes(sink)
            _bind_provider_status(failure, known_provider_status)
            raise
        except (
            error.URLError,
            TimeoutError,
            socket.timeout,
            ssl.SSLError,
            OSError,
            ConnectionError,
            AttributeError,
            TypeError,
            ValueError,
        ) as exc:
            reason = getattr(exc, "reason", exc)
            kind = "timeout" if isinstance(reason, (TimeoutError, socket.timeout)) else "network"
            failure = APIError(
                status=None,
                kind=kind,
                message=f"provider request failed: {kind}",
                partial=_response_sink_has_bytes(sink, flush=True),
                response_body_partial=known_provider_status is not None,
            )
            raise _bind_provider_status(failure, known_provider_status) from None

    def stream_to(
        self,
        method: str,
        url: str,
        destination: Path,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        append_on_partial: bool = False,
        expected_offset: int = 0,
        deadline: float | None = None,
        max_total_bytes: int | None = None,
        expected_destination_identity: tuple[int, int] | None = None,
    ) -> HTTPResponse:
        """Stream a successful response to disk and retain partial bytes on interruption."""

        timeout = validate_timeout(timeout, "stream timeout")
        deadline = _absolute_deadline(timeout, deadline, "provider stream")
        expected_destination_identity = _validated_file_identity(expected_destination_identity)
        stream_identity = expected_destination_identity
        if stream_identity is None and append_on_partial and destination.exists():
            stream_identity = _existing_stream_destination_identity(destination)

        def retained_output_present() -> bool:
            return _identity_bound_path_has_bytes(destination, stream_identity)

        if max_total_bytes is not None and (
            isinstance(max_total_bytes, bool)
            or not isinstance(max_total_bytes, int)
            or max_total_bytes <= 0
        ):
            raise ValidationError("stream total-byte limit must be a positive integer")
        if max_total_bytes is not None and expected_offset > max_total_bytes:
            raise SchemaDriftError(
                "provider stream resume offset exceeds the total-byte limit",
                raw={
                    "representation": "provider-stream-byte-limit",
                    "limit_bytes": max_total_bytes,
                    "resume_offset_bytes": expected_offset,
                    "truncated": True,
                },
            )
        req = request.Request(url, headers=headers or {}, method=method)
        known_provider_status: int | None = None
        response_body_complete = False
        try:
            open_timeout = min(
                timeout,
                _remaining_deadline(
                    deadline,
                    "provider stream",
                    partial=retained_output_present(),
                ),
            )
            opened_response = _open_provider_response(
                self._opener,
                req,
                timeout=open_timeout,
                context="provider stream",
                partial=retained_output_present(),
            )
            known_provider_status = _validated_provider_status(
                getattr(opened_response, "status", None)
            )
            stream_complete = [False]
            with _ProviderResponseContext(
                opened_response,
                context="provider stream close",
                partial=retained_output_present,
                completed=lambda: stream_complete[0],
            ) as response:
                response_status = response.status
                known_provider_status = _validated_provider_status(response_status)
                _remaining_deadline(
                    deadline,
                    "provider stream",
                    partial=retained_output_present(),
                )
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                if response_status == 206:
                    validate_content_range(response_headers, expected_offset)
                declared_length = _declared_response_length(response)
                response_body_complete = declared_length == 0
                mode = "ab" if append_on_partial and response_status == 206 else "wb"
                preflight_base_size = expected_offset if mode == "ab" else 0
                if (
                    max_total_bytes is not None
                    and declared_length is not None
                    and preflight_base_size + declared_length > max_total_bytes
                ):
                    raise SchemaDriftError(
                        "provider stream exceeds the total-byte limit",
                        raw={
                            "representation": "provider-stream-byte-limit",
                            "limit_bytes": max_total_bytes,
                            "resume_offset_bytes": preflight_base_size,
                            "declared_size_bytes": declared_length,
                            "truncated": True,
                        },
                    )
                _create_status_bound_stream_parent(
                    destination,
                    provider_status=known_provider_status,
                    expected_identity=stream_identity,
                )
                handle, stream_identity = _open_status_bound_stream_destination(
                    destination,
                    append=mode == "ab",
                    expected_identity=stream_identity,
                    provider_status=known_provider_status,
                )
                with _status_bound_stream_handle(
                    handle,
                    destination,
                    provider_status=known_provider_status,
                    expected_identity=stream_identity,
                ):
                    base_size = _status_bound_stream_size(
                        handle,
                        provider_status=known_provider_status,
                        partial=retained_output_present(),
                    )
                    if mode == "ab" and base_size != expected_offset:
                        raise ValidationError(
                            "stream destination size changed before resumed writing"
                        )
                    if max_total_bytes is not None and (
                        base_size > max_total_bytes
                        or (
                            declared_length is not None
                            and base_size + declared_length > max_total_bytes
                        )
                    ):
                        raise SchemaDriftError(
                            "provider stream exceeds the total-byte limit",
                            raw={
                                "representation": "provider-stream-byte-limit",
                                "limit_bytes": max_total_bytes,
                                "resume_offset_bytes": base_size,
                                "declared_size_bytes": declared_length,
                                "truncated": True,
                            },
                        )
                    partial_output = base_size > 0
                    received = 0
                    try:
                        while True:
                            if response_body_complete:
                                break
                            remaining = _remaining_deadline(
                                deadline,
                                "provider stream",
                                partial=partial_output,
                            )
                            _cap_response_timeout(response, min(timeout, remaining))
                            read_size = 64 * 1024
                            if max_total_bytes is not None:
                                read_size = min(
                                    read_size,
                                    max(1, max_total_bytes - base_size - received + 1),
                                )
                            try:
                                chunk = _response_reader(response)(read_size)
                            except (TimeoutError, socket.timeout):
                                raise APIError(
                                    status=None,
                                    kind="timeout",
                                    message="provider stream timed out",
                                    partial=partial_output,
                                    response_body_partial=True,
                                ) from None
                            except (error.URLError, ssl.SSLError, OSError) as exc:
                                kind = _read_failure_kind(exc)
                                raise APIError(
                                    status=None,
                                    kind=kind,
                                    message=f"provider stream failed: {kind}",
                                    partial=partial_output,
                                    response_body_partial=True,
                                ) from None
                            if chunk:
                                observed_size = base_size + received + len(chunk)
                                if max_total_bytes is not None and observed_size > max_total_bytes:
                                    retained = max_total_bytes - base_size - received
                                    if retained > 0:
                                        _write_stream_destination(
                                            handle,
                                            chunk[:retained],
                                            provider_status=known_provider_status,
                                            partial=partial_output,
                                        )
                                        received += retained
                                        partial_output = True
                                    raise SchemaDriftError(
                                        "provider stream exceeds the total-byte limit",
                                        raw={
                                            "representation": "provider-stream-byte-limit",
                                            "limit_bytes": max_total_bytes,
                                            "resume_offset_bytes": base_size,
                                            "received_size_bytes": observed_size,
                                            "truncated": True,
                                        },
                                    )
                                _write_stream_destination(
                                    handle,
                                    chunk,
                                    provider_status=known_provider_status,
                                    partial=partial_output,
                                )
                                received += len(chunk)
                                partial_output = True
                                if declared_length is not None and received >= declared_length:
                                    response_body_complete = True
                            _remaining_deadline(
                                deadline,
                                "provider stream",
                                partial=partial_output,
                            )
                            if response_body_complete:
                                break
                            if not chunk:
                                if declared_length is not None and received < declared_length:
                                    raise APIError(
                                        status=None,
                                        kind="network",
                                        message=(
                                            "provider stream ended before its declared Content-Length"
                                        ),
                                        partial=partial_output,
                                        response_body_partial=True,
                                    )
                                response_body_complete = True
                                break
                    except (APIError, SchemaDriftError) as stream_failure:
                        try:
                            _sync_stream_destination(
                                handle,
                                provider_status=known_provider_status,
                                partial=partial_output,
                            )
                        except BiohubESMError as sync_failure:
                            _merge_stream_failures(
                                stream_failure,
                                sync_failure,
                                provider_status=known_provider_status,
                                partial=partial_output,
                            )
                        raise
                    _sync_stream_destination(
                        handle,
                        provider_status=known_provider_status,
                        partial=partial_output,
                    )
                if response_status == 206:
                    validate_content_range(
                        response_headers,
                        expected_offset,
                        final_size=base_size + received,
                    )
                _remaining_deadline(
                    deadline,
                    "provider stream",
                    partial=retained_output_present(),
                )
                result = HTTPResponse(response_status, response_headers, b"")
                stream_complete[0] = True
                return result
        except error.HTTPError as exc:
            return _http_error_response(
                exc,
                deadline,
                "provider stream error response",
                timeout,
                artifact_partial=retained_output_present(),
            )
        except IncompleteRead as exc:
            retained_partial = _identity_bound_path_has_bytes(
                destination,
                stream_identity,
            )
            incomplete_failure = APIError(
                status=None,
                kind="network",
                message="provider stream was incomplete",
                partial=retained_partial,
                response_body_partial=True,
            )
            _bind_provider_status(incomplete_failure, known_provider_status)
            try:
                if exc.partial:
                    _create_status_bound_stream_parent(
                        destination,
                        provider_status=known_provider_status,
                        expected_identity=stream_identity,
                    )
                    handle, stream_identity = _open_status_bound_stream_destination(
                        destination,
                        append=True,
                        expected_identity=stream_identity,
                        provider_status=known_provider_status,
                    )
                    with _status_bound_stream_handle(
                        handle,
                        destination,
                        provider_status=known_provider_status,
                        expected_identity=stream_identity,
                    ):
                        current_size = _status_bound_stream_size(
                            handle,
                            provider_status=known_provider_status,
                            partial=retained_output_present(),
                        )
                        retained = len(exc.partial)
                        overflowed = False
                        if (
                            max_total_bytes is not None
                            and current_size + retained > max_total_bytes
                        ):
                            retained = max(0, max_total_bytes - current_size)
                            overflowed = True
                        _write_stream_destination(
                            handle,
                            exc.partial[:retained],
                            provider_status=known_provider_status,
                            partial=current_size > 0,
                        )
                        _sync_stream_destination(
                            handle,
                            provider_status=known_provider_status,
                            partial=current_size + retained > 0,
                        )
                    if overflowed:
                        raise SchemaDriftError(
                            "provider stream exceeds the total-byte limit",
                            raw={
                                "representation": "provider-stream-byte-limit",
                                "limit_bytes": max_total_bytes,
                                "resume_offset_bytes": current_size,
                                "received_size_bytes": current_size + len(exc.partial),
                                "truncated": True,
                            },
                        ) from None
            except ValidationError as failure:
                retained_partial = _identity_bound_path_has_bytes(
                    destination,
                    stream_identity,
                )
                _merge_stream_failures(
                    incomplete_failure,
                    failure,
                    provider_status=known_provider_status,
                    partial=retained_partial,
                )
                incomplete_failure.partial = retained_partial
                raise incomplete_failure from None
            except BiohubESMError as failure:
                raise _bind_provider_status(failure, known_provider_status) from None
            incomplete_failure.partial = _identity_bound_path_has_bytes(
                destination,
                stream_identity,
            )
            raise incomplete_failure from None
        except BiohubESMError as failure:
            if isinstance(failure, APIError):
                failure.partial = retained_output_present()
                if (
                    known_provider_status is not None
                    and not response_body_complete
                    and failure.status is None
                    and failure.kind in {"network", "timeout"}
                ):
                    failure.response_body_partial = True
            _bind_provider_status(failure, known_provider_status)
            raise
        except (
            error.URLError,
            TimeoutError,
            socket.timeout,
            ssl.SSLError,
            OSError,
            ConnectionError,
            AttributeError,
            TypeError,
            ValueError,
        ) as exc:
            reason = getattr(exc, "reason", exc)
            kind = "timeout" if isinstance(reason, (TimeoutError, socket.timeout)) else "network"
            failure = APIError(
                status=None,
                kind=kind,
                message=f"provider stream failed: {kind}",
                partial=retained_output_present(),
                response_body_partial=(
                    known_provider_status is not None and not response_body_complete
                ),
            )
            raise _bind_provider_status(failure, known_provider_status) from None


CONTENT_RANGE_RE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$", re.IGNORECASE)


def validate_content_range(
    headers: dict[str, str], expected_offset: int, *, final_size: int | None = None
) -> None:
    value = headers.get("content-range", "")
    matched = CONTENT_RANGE_RE.fullmatch(value.strip())
    if not matched or int(matched.group(1)) != expected_offset:
        raise SchemaDriftError(
            "provider returned a mismatched Content-Range for resumed download",
            raw={"content-range": value, "expected_offset": expected_offset},
        )
    start = int(matched.group(1))
    end = int(matched.group(2))
    total = None if matched.group(3) == "*" else int(matched.group(3))
    if end < start or (total is not None and (end >= total or start >= total)):
        raise SchemaDriftError(
            "provider returned an invalid Content-Range",
            raw={"content-range": value, "expected_offset": expected_offset},
        )
    if final_size is not None and (
        final_size != end + 1 or (total is not None and final_size != total)
    ):
        raise SchemaDriftError(
            "provider returned an incomplete ranged download",
            raw={
                "content-range": value,
                "expected_offset": expected_offset,
                "final_size": final_size,
            },
        )


def _retry_after(headers: dict[str, str], *, now: datetime | None = None) -> float | None:
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        seconds = float(raw)
        return max(0.0, seconds) if math.isfinite(seconds) else None
    except ValueError:
        try:
            target = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        return max(0.0, (target.astimezone(timezone.utc) - current).total_seconds())


def _safe_error_message(response: HTTPResponse) -> str:
    generic = f"provider returned HTTP {response.status}"
    if not response.body or len(response.body) > PROVIDER_RESPONSE_MAX_BYTES:
        return generic
    try:
        _validate_json_resource_budget(response.body)
        payload = json.loads(
            response.body.decode("utf-8"),
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
            parse_int=_bounded_json_int,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
        MemoryError,
        SchemaDriftError,
    ):
        return generic
    if _json_contains_unpaired_surrogate(payload):
        return generic
    if isinstance(payload, dict):
        for key in ("message", "detail", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                preview = redact_truncated_text(
                    value[:2048],
                    truncated=len(value) > 2048,
                )
                return f"{generic}: {preview[:500]}"
    return generic


def raise_for_status(response: HTTPResponse, *, expected: set[int]) -> None:
    if response.status in expected:
        if len(response.body) > PROVIDER_RESPONSE_MAX_BYTES:
            raise SchemaDriftError(
                f"provider response exceeded the {PROVIDER_RESPONSE_MAX_BYTES}-byte safety limit",
                raw={
                    "representation": "provider-response-byte-limit",
                    "limit_bytes": PROVIDER_RESPONSE_MAX_BYTES,
                    "received_size_bytes": len(response.body),
                    "truncated": True,
                    "body_prefix": response.body[:DIAGNOSTIC_PREVIEW_MAX_BYTES].decode(
                        "utf-8", errors="replace"
                    ),
                },
            )
        return
    informational = 100 <= response.status < 200
    raise APIError(
        status=response.status,
        kind=_http_error_kind(response.status),
        message=_safe_error_message(response),
        retry_after=_retry_after(response.headers),
        response_body_partial=informational,
        operation_indeterminate=informational,
    )


def decode_json(response: HTTPResponse) -> Any:
    _validate_json_resource_budget(response.body)
    try:
        result = json.loads(
            response.body.decode("utf-8"),
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
            parse_int=_bounded_json_int,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
        MemoryError,
    ) as exc:
        raise SchemaDriftError("provider returned malformed JSON", raw=response.body) from exc
    if json_nesting_exceeds(result):
        raise SchemaDriftError(
            "provider JSON exceeds the safe nesting depth",
            raw=response.body,
        )
    if _json_contains_unpaired_surrogate(result):
        raise SchemaDriftError(
            "provider JSON contains an unpaired Unicode surrogate",
            raw=response.body,
        )
    return result


class BiohubClient:
    """Minimal allowlisted managed-API transport.

    The official pinned ``esm`` SDK remains the preferred semantic client. This
    layer exists to make auth, status, timeout, and redaction behavior testable.
    """

    def __init__(
        self,
        *,
        token: str,
        base_url: str = BIOHUB_BASE_URL,
        transport: Transport | None = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        credential_source: str = "none",
    ) -> None:
        self.token = token
        self.credential_source = credential_source
        register_redaction_secret(token)
        self.timeout = validate_timeout(timeout, "Biohub request timeout")
        self.base_url = base_url.rstrip("/")
        if self.base_url != BIOHUB_BASE_URL:
            raise ValidationError(
                "managed Biohub credentials may only be sent to https://biohub.ai"
            )
        self.transport = transport or UrllibTransport()
        self.last_http_status: int | None = None

    def post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_http_status = None
        if endpoint not in MANAGED_ENDPOINTS:
            raise ValidationError(f"managed endpoint is not allowlisted: {endpoint}")
        if not self.token:
            raise APIError(
                status=None,
                kind="missing-credentials",
                message=missing_esm_api_key_message(self.credential_source),
            )
        model = payload.get("model")
        allowed_models = (
            ESMC_MANAGED_MODELS if endpoint in {"encode", "logits"} else ESMFOLD2_MANAGED_MODELS
        )
        if model not in allowed_models:
            raise ValidationError(f"{endpoint} requires an exact supported managed model ID")
        body = encode_json_body(payload)
        response = self.transport.request(
            "POST",
            f"{self.base_url}/api/v1/{endpoint}",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.token}",
                "content-type": "application/json",
            },
            body=body,
            timeout=self.timeout,
        )
        self.last_http_status = response.status
        raise_for_status(response, expected={200})
        result = decode_json(response)
        if not isinstance(result, dict):
            raise SchemaDriftError("managed API response must be a JSON object", raw=result)
        return result


def _validated_file_identity(value: tuple[int, int] | None) -> tuple[int, int] | None:
    if value is None:
        return None
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in value)
    ):
        raise ValidationError("stream destination identity must contain device and inode integers")
    return value


def _existing_stream_destination_identity(destination: Path) -> tuple[int, int]:
    flags = os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(destination, flags)
    except OSError as exc:
        if exc.errno in {
            errno.ELOOP,
            errno.ENOENT,
            errno.ENOTDIR,
            errno.EISDIR,
            errno.ENXIO,
        }:
            raise ValidationError("stream destination is not a safe regular file") from exc
        raise
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValidationError("stream destination is not a safe regular file")
        return info.st_dev, info.st_ino
    finally:
        os.close(descriptor)


def _open_stream_destination(
    destination: Path,
    *,
    append: bool,
    expected_identity: tuple[int, int] | None,
) -> tuple[Any, tuple[int, int]]:
    """Open a regular stream target without following a raced symbolic link."""

    flags = os.O_WRONLY | (os.O_APPEND if append else 0)
    if expected_identity is None:
        flags |= os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(destination, flags, 0o600)
    except OSError as exc:
        if exc.errno in {
            errno.EEXIST,
            errno.ELOOP,
            errno.ENOENT,
            errno.ENOTDIR,
            errno.EISDIR,
            errno.ENXIO,
        }:
            raise ValidationError("stream destination is not a safe regular file") from exc
        raise
    try:
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino)
        if not stat.S_ISREG(info.st_mode) or (
            expected_identity is not None and identity != expected_identity
        ):
            raise ValidationError("stream destination identity changed before writing")
        if not append:
            os.ftruncate(descriptor, 0)
        return os.fdopen(descriptor, "ab" if append else "wb"), identity
    except BaseException:
        os.close(descriptor)
        raise

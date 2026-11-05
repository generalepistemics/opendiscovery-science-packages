"""Bounded, redacted diagnostics for untrusted provider responses."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .security import (
    redact,
    redact_bounded_bytes_preview,
    redact_mapping_key,
    redact_text,
    redact_truncated_text,
)

# The response ceiling must accommodate a maximum-length ESMC hidden-state
# response while still placing a deterministic upper bound on in-memory reads.
PROVIDER_RESPONSE_MAX_BYTES = 256 * 1024 * 1024
PROVIDER_JSON_MAX_DEPTH = 64
PROVIDER_JSON_MAX_NUMBER_CHARACTERS = 128
PROVIDER_JSON_MAX_NODES = 8_000_000
PROVIDER_JSON_MAX_TEXT_BYTES = 64 * 1024 * 1024

DIAGNOSTIC_ARTIFACT_MAX_BYTES = 64 * 1024
DIAGNOSTIC_PREVIEW_MAX_BYTES = 8 * 1024
DIAGNOSTIC_MAX_DEPTH = 16
DIAGNOSTIC_MAX_NODES = 256
DIAGNOSTIC_MAX_COLLECTION_ITEMS = 64
DIAGNOSTIC_MAX_STRING_BYTES = 1024
DIAGNOSTIC_MAX_KEY_BYTES = 256
DIAGNOSTIC_MAX_TOTAL_TEXT_BYTES = 8 * 1024


@dataclass
class _ProjectionState:
    nodes: int = 0
    retained_text_bytes: int = 0
    active_container_ids: set[int] = field(default_factory=set)
    truncation_reasons: set[str] = field(default_factory=set)


def _bounded_utf8_prefix(value: str, limit: int) -> tuple[str, bool, int]:
    """Return at most ``limit`` UTF-8 bytes without encoding the full string."""

    candidate = value[:limit]
    encoded = candidate.encode("utf-8", errors="replace")
    if len(encoded) > limit:
        encoded = encoded[:limit]
    # Round-trip even an in-bound prefix so lone surrogate code points are
    # replaced deterministically and cannot escape into a later strict UTF-8
    # serializer.  Decoding also discards an incomplete multibyte character at
    # the byte ceiling, so ``retained`` is the size of the actual returned text.
    candidate = encoded.decode("utf-8", errors="ignore")
    retained = len(candidate.encode("utf-8"))
    return candidate, len(value) > len(candidate), retained


def _secret_key(key: str) -> bool:
    """Use the canonical recursive redactor only on one bounded scalar pair."""

    redacted = redact({key: None})
    return len(redacted) == 1 and next(iter(redacted.values())) == "[REDACTED]"


def _bounded_big_integer(value: int) -> dict[str, Any]:
    magnitude = abs(value)
    bit_length = magnitude.bit_length()
    retained_bits = 256
    low = magnitude & ((1 << retained_bits) - 1)
    high = magnitude >> max(0, bit_length - retained_bits)
    fingerprint = f"{value < 0}:{bit_length}:{high:x}:{low:x}".encode("ascii")
    return {
        "provider_numeric_rejected": "integer-exceeds-local-json-bound",
        "negative": value < 0,
        "bit_length": bit_length,
        "magnitude_sha256": hashlib.sha256(fingerprint).hexdigest(),
        "magnitude_sha256_scope": "sign-bit-length-and-top-bottom-256-bits",
    }


def _truncation_marker(reason: str) -> dict[str, str]:
    return {"diagnostic_truncated": reason}


def _project(value: Any, *, depth: int, state: _ProjectionState) -> Any:
    if state.nodes >= DIAGNOSTIC_MAX_NODES:
        state.truncation_reasons.add("node-limit")
        return _truncation_marker("node-limit")
    state.nodes += 1

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if value.bit_length() <= 4096 else _bounded_big_integer(value)
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return {
            "provider_numeric_rejected": "non-finite-float",
            "representation": repr(value),
        }
    if isinstance(value, str):
        remaining = max(0, DIAGNOSTIC_MAX_TOTAL_TEXT_BYTES - state.retained_text_bytes)
        limit = min(DIAGNOSTIC_MAX_STRING_BYTES, remaining)
        if limit == 0:
            state.truncation_reasons.add("text-byte-limit")
            return _truncation_marker("text-byte-limit")
        preview, truncated, retained = _bounded_utf8_prefix(value, limit)
        state.retained_text_bytes += retained
        redacted_preview = redact_truncated_text(preview, truncated=truncated)
        if truncated:
            state.truncation_reasons.add("string-byte-limit")
            return {
                "diagnostic_truncated": "string-byte-limit",
                "original_characters": len(value),
                "preview": redacted_preview,
            }
        return redacted_preview

    if depth >= DIAGNOSTIC_MAX_DEPTH:
        state.truncation_reasons.add("depth-limit")
        return _truncation_marker("depth-limit")

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in state.active_container_ids:
            state.truncation_reasons.add("cycle")
            return _truncation_marker("cycle")
        state.active_container_ids.add(identity)
        result: dict[str, Any] = {}
        try:
            total_items = len(value)
        except Exception:
            total_items = None
        processed_items = 0
        try:
            iterator = iter(value.items())
            for index in range(DIAGNOSTIC_MAX_COLLECTION_ITEMS):
                try:
                    key, item = next(iterator)
                except StopIteration:
                    break
                except Exception:
                    state.truncation_reasons.add("mapping-iteration-error")
                    result["[diagnostic-mapping-error]"] = _truncation_marker(
                        "mapping-iteration-error"
                    )
                    break
                processed_items += 1
                raw_key = str(key)
                bounded_key, key_truncated, retained = _bounded_utf8_prefix(
                    raw_key, DIAGNOSTIC_MAX_KEY_BYTES
                )
                remaining = DIAGNOSTIC_MAX_TOTAL_TEXT_BYTES - state.retained_text_bytes
                if key_truncated or retained > remaining:
                    state.truncation_reasons.add("key-byte-limit")
                    bounded_key = f"[truncated-key-{index}]"
                    result[bounded_key] = "[REDACTED]"
                    continue
                state.retained_text_bytes += retained
                base_key = redact_text(bounded_key)
                bounded_key = base_key
                suffix = 1
                while bounded_key in result:
                    bounded_key = f"{base_key} [duplicate-{index}-{suffix}]"
                    suffix += 1
                if _secret_key(raw_key):
                    result[bounded_key] = "[REDACTED]"
                else:
                    result[bounded_key] = _project(item, depth=depth + 1, state=state)
            if processed_items == DIAGNOSTIC_MAX_COLLECTION_ITEMS and (
                total_items is None or total_items > processed_items
            ):
                state.truncation_reasons.add("collection-item-limit")
                result["[diagnostic-truncated]"] = _truncation_marker("collection-item-limit")
        finally:
            state.active_container_ids.discard(identity)
        return result

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in state.active_container_ids:
            state.truncation_reasons.add("cycle")
            return _truncation_marker("cycle")
        state.active_container_ids.add(identity)
        result: list[Any] = []
        try:
            for item in value[:DIAGNOSTIC_MAX_COLLECTION_ITEMS]:
                result.append(_project(item, depth=depth + 1, state=state))
            if len(value) > DIAGNOSTIC_MAX_COLLECTION_ITEMS:
                state.truncation_reasons.add("collection-item-limit")
                result.append(_truncation_marker("collection-item-limit"))
        finally:
            state.active_container_ids.discard(identity)
        return result

    return {"provider_value_rejected": type(value).__name__}


def bounded_provider_response_diagnostic(value: Any) -> dict[str, Any]:
    """Build a deterministic bounded projection without traversing all input data."""

    if isinstance(value, bytes):
        preview_bytes = value[:DIAGNOSTIC_PREVIEW_MAX_BYTES]
        preview = redact_bounded_bytes_preview(value, limit=DIAGNOSTIC_PREVIEW_MAX_BYTES)
        diagnostic: dict[str, Any] = {
            "representation": "bounded-redacted-utf8-preview",
            "provider_body_size_bytes": len(value),
            "retained_prefix_size_bytes": len(preview_bytes),
            "retained_prefix_sha256": hashlib.sha256(preview_bytes).hexdigest(),
            "truncated": len(value) > len(preview_bytes),
            "preview": preview,
        }
        if len(value) <= PROVIDER_RESPONSE_MAX_BYTES:
            diagnostic["provider_body_sha256"] = hashlib.sha256(value).hexdigest()
        else:
            diagnostic["truncation_reasons"] = ["response-byte-limit"]
        return diagnostic

    state = _ProjectionState()
    projection = _project(value, depth=0, state=state)
    encoded = json.dumps(
        projection,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "representation": "bounded-redacted-json-projection",
        "truncated": bool(state.truncation_reasons),
        "truncation_reasons": sorted(state.truncation_reasons),
        "visited_nodes": state.nodes,
        "retained_text_bytes": state.retained_text_bytes,
        "projection_sha256": hashlib.sha256(encoded).hexdigest(),
        "projection": projection,
    }


def safe_provider_response_diagnostic(value: Any) -> Any:
    """Compatibility view used by rejected-response artifacts."""

    return bounded_provider_response_diagnostic(value).get("projection", {})


def redact_provider_json_in_place(value: Any) -> Any:
    """Redact decoded provider JSON without duplicating the response tree."""

    stack: list[Any] = [value]
    visited: set[int] = set()
    while stack:
        item = stack.pop()
        if not isinstance(item, (dict, list)):
            continue
        identity = id(item)
        if identity in visited:
            continue
        visited.add(identity)
        if isinstance(item, dict):
            renamed_keys: list[tuple[Any, str, int]] = []
            for index, (key, child) in enumerate(item.items()):
                safe_key = redact_mapping_key(key)
                if safe_key != str(key):
                    renamed_keys.append((key, safe_key, index))
                if _secret_key(str(key)):
                    item[key] = "[REDACTED]"
                elif isinstance(child, str):
                    item[key] = redact_text(child)
                elif isinstance(child, (dict, list)):
                    stack.append(child)
            for original_key, safe_key, index in renamed_keys:
                child = item.pop(original_key)
                candidate = safe_key
                suffix = 1
                while candidate in item:
                    candidate = f"{safe_key} [duplicate-{index}-{suffix}]"
                    suffix += 1
                item[candidate] = child
        else:
            for index, child in enumerate(item):
                if isinstance(child, str):
                    item[index] = redact_text(child)
                elif isinstance(child, (dict, list)):
                    stack.append(child)
    return value


def json_nesting_exceeds(value: Any, *, max_depth: int = PROVIDER_JSON_MAX_DEPTH) -> bool:
    """Check decoded JSON nesting with O(depth) auxiliary memory."""

    stack: list[tuple[Any, int]] = [(iter((value,)), 0)]
    while stack:
        iterator, depth = stack[-1]
        try:
            item = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        if isinstance(item, dict):
            child_depth = depth + 1
            if child_depth > max_depth:
                return True
            stack.append((iter(item.values()), child_depth))
        elif isinstance(item, list):
            child_depth = depth + 1
            if child_depth > max_depth:
                return True
            stack.append((iter(item), child_depth))
    return False

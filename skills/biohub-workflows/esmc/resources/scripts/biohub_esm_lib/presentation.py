"""Renderer-neutral presentation intents for durable scientific artifacts."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Mapping

from .errors import ValidationError


PRESENTATION_SCHEMA_VERSION = "1.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STRUCTURE_MEDIA_TYPES = {
    "chemical/x-mmcif": "mmcif",
    "chemical/x-pdb": "pdb",
}


def _metric_mapping_status(metadata: Mapping[str, Any]) -> str | None:
    status = metadata.get("mapping_status", metadata.get("alignment_status"))
    return status if isinstance(status, str) else None


def build_structure_presentation_request(
    artifact: Mapping[str, Any],
    confidence_metrics: Mapping[str, Any],
    *,
    open_intent_id: str | None = None,
) -> dict[str, Any]:
    """Build the retained semantic handoff consumed by an available viewer.

    Tool names and viewer session identifiers intentionally do not appear here.
    They are host-local delivery state, while this record remains useful when no
    renderer is installed or the renderer is still mounting.
    """

    path_value = artifact.get("path")
    media_type = artifact.get("media_type")
    size_bytes = artifact.get("size_bytes")
    digest = artifact.get("sha256")
    if not isinstance(path_value, str) or not Path(path_value).is_absolute():
        raise ValidationError("structure presentation requires an absolute artifact path")
    if media_type not in STRUCTURE_MEDIA_TYPES:
        raise ValidationError("structure presentation requires a supported coordinate media type")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes <= 0:
        raise ValidationError("structure presentation requires a non-empty artifact")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        raise ValidationError("structure presentation requires an artifact SHA-256")
    if artifact.get("evidence_class") != "model_hypothesis":
        raise ValidationError("structure presentation requires an explicit evidence class")

    intent = open_intent_id or str(uuid.uuid4())
    try:
        parsed_intent = uuid.UUID(intent)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError("structure presentation openIntentId must be a UUID") from exc
    if str(parsed_intent) != intent.lower():
        raise ValidationError("structure presentation openIntentId must be canonical")

    metric_metadata = confidence_metrics.get("metric_metadata")
    if not isinstance(metric_metadata, Mapping):
        metric_metadata = {}
    plddt_metadata = metric_metadata.get("plddt")
    if not isinstance(plddt_metadata, Mapping):
        plddt_metadata = {}

    unmapped_metrics = sorted(
        str(name)
        for name, metadata in metric_metadata.items()
        if isinstance(name, str)
        and isinstance(metadata, Mapping)
        and _metric_mapping_status(metadata) == "unmapped"
    )
    completeness_record = confidence_metrics.get("confidence_completeness")
    declared_completeness = (
        completeness_record.get("status")
        if isinstance(completeness_record, Mapping)
        else confidence_metrics.get("completeness")
    )
    if declared_completeness not in {"complete", "partial", "unavailable"}:
        declared_completeness = "partial" if unmapped_metrics else "complete"

    value = {
        "schema_version": PRESENTATION_SCHEMA_VERSION,
        "type": "structure-presentation",
        "status": "pending-delivery",
        "openIntentId": intent,
        "artifact": {
            "path": str(Path(path_value)),
            "format": STRUCTURE_MEDIA_TYPES[str(media_type)],
            "media_type": media_type,
            "size_bytes": size_bytes,
            "sha256": digest,
        },
        "evidence_class": "model_hypothesis",
        "requested_view": {
            "representation": "cartoon",
            "color_by": "predicted_confidence",
            "serialized_field": "B-factor",
        },
        "confidence": {
            "metric": "plddt",
            "semantics": "predicted_confidence",
            "source_scale": plddt_metadata.get("scale"),
            "index_basis": plddt_metadata.get("index_basis"),
            "completeness": declared_completeness,
            "unmapped_metrics": unmapped_metrics,
        },
        "delivery": {
            "open_policy": "once",
            "delivery_retry": "reuse-openIntentId",
            "verify_primary_object": True,
            "style_when": "renderer-ready",
            "session_scope": "current-task",
        },
    }
    validate_structure_presentation_request(value)
    return value


def validate_structure_presentation_request(value: Mapping[str, Any]) -> None:
    """Validate the durable subset of the Biohub-to-viewer handoff."""

    required = {
        "schema_version",
        "type",
        "status",
        "openIntentId",
        "artifact",
        "evidence_class",
        "requested_view",
        "confidence",
        "delivery",
    }
    if set(value) != required:
        raise ValidationError("structure presentation request fields are invalid")
    if value["schema_version"] != PRESENTATION_SCHEMA_VERSION:
        raise ValidationError("unsupported structure presentation schema version")
    if value["type"] != "structure-presentation" or value["status"] != "pending-delivery":
        raise ValidationError("structure presentation type or status is invalid")
    if value["evidence_class"] != "model_hypothesis":
        raise ValidationError("structure presentation evidence class is invalid")

    try:
        intent = uuid.UUID(str(value["openIntentId"]))
    except (TypeError, ValueError) as exc:
        raise ValidationError("structure presentation openIntentId must be a UUID") from exc
    if str(intent) != value["openIntentId"]:
        raise ValidationError("structure presentation openIntentId must be canonical")

    artifact = value["artifact"]
    if not isinstance(artifact, Mapping) or set(artifact) != {
        "path",
        "format",
        "media_type",
        "size_bytes",
        "sha256",
    }:
        raise ValidationError("structure presentation artifact is invalid")
    if not isinstance(artifact["path"], str) or not Path(artifact["path"]).is_absolute():
        raise ValidationError("structure presentation artifact path must be absolute")
    expected_format = STRUCTURE_MEDIA_TYPES.get(artifact["media_type"])
    if expected_format is None or artifact["format"] != expected_format:
        raise ValidationError("structure presentation artifact format is invalid")
    if (
        isinstance(artifact["size_bytes"], bool)
        or not isinstance(artifact["size_bytes"], int)
        or artifact["size_bytes"] <= 0
        or not isinstance(artifact["sha256"], str)
        or SHA256_RE.fullmatch(artifact["sha256"]) is None
    ):
        raise ValidationError("structure presentation artifact identity is invalid")

    requested_view = value["requested_view"]
    if requested_view != {
        "representation": "cartoon",
        "color_by": "predicted_confidence",
        "serialized_field": "B-factor",
    }:
        raise ValidationError("structure presentation requested view is invalid")
    confidence = value["confidence"]
    if not isinstance(confidence, Mapping) or set(confidence) != {
        "metric",
        "semantics",
        "source_scale",
        "index_basis",
        "completeness",
        "unmapped_metrics",
    }:
        raise ValidationError("structure presentation confidence contract is invalid")
    if (
        confidence["metric"] != "plddt"
        or confidence["semantics"] != "predicted_confidence"
        or confidence["completeness"] not in {"complete", "partial", "unavailable"}
        or not isinstance(confidence["unmapped_metrics"], list)
        or any(not isinstance(item, str) or not item for item in confidence["unmapped_metrics"])
    ):
        raise ValidationError("structure presentation confidence values are invalid")
    if confidence["source_scale"] is not None and not isinstance(confidence["source_scale"], str):
        raise ValidationError("structure presentation confidence scale is invalid")
    if confidence["index_basis"] is not None and not isinstance(confidence["index_basis"], str):
        raise ValidationError("structure presentation confidence index basis is invalid")

    if value["delivery"] != {
        "open_policy": "once",
        "delivery_retry": "reuse-openIntentId",
        "verify_primary_object": True,
        "style_when": "renderer-ready",
        "session_scope": "current-task",
    }:
        raise ValidationError("structure presentation delivery contract is invalid")

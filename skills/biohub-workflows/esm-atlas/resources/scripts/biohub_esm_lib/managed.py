"""Managed Biohub response normalization and structure artifacts."""

from __future__ import annotations

import math
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from .errors import SchemaDriftError, ValidationError
from .managed_readiness import load_structure_serializer_sdk, protein_to_pdb_string
from .provenance import (
    artifact_record,
    numeric_metric_summary,
    verify_installed_distribution,
    write_bytes_atomic,
)

MANAGED_CONFIDENCE_FIELDS = (
    ("plddt", "plddt"),
    ("mean_plddt", "mean_plddt"),
    ("ptm", "ptm"),
    ("iptm", "iptm"),
    ("interface_ptm", "iptm"),
    ("pae", "pae"),
    ("pair_chains_iptm", "pair_chains_iptm"),
)

MANAGED_REQUESTED_OUTPUT_FIELDS = {
    "include_pae": ("pae",),
    "include_pair_chains_iptm": ("pair_chains_iptm",),
    "include_distogram": ("distogram",),
    "include_embeddings": (
        "output_embedding_sequence",
        "output_embedding_pair_pooled",
    ),
}

PLDDT_TRACK_REL_TOLERANCE = 1e-5
PLDDT_TRACK_ABS_TOLERANCE = 5e-4
COVALENT_BOND_SEVERE_MIN_ANGSTROM = 0.9
COVALENT_BOND_SEVERE_MAX_ANGSTROM = 2.5

PROTEIN_RESIDUE_TOKENS = {
    "A": "ALA",
    "R": "ARG",
    "N": "ASN",
    "D": "ASP",
    "C": "CYS",
    "Q": "GLN",
    "E": "GLU",
    "G": "GLY",
    "H": "HIS",
    "I": "ILE",
    "L": "LEU",
    "K": "LYS",
    "M": "MET",
    "F": "PHE",
    "P": "PRO",
    "S": "SER",
    "T": "THR",
    "W": "TRP",
    "Y": "TYR",
    "V": "VAL",
    "X": "UNK",
}
DNA_RESIDUE_TOKENS = {"A": "DA", "T": "DT", "C": "DC", "G": "DG"}
RNA_RESIDUE_TOKENS = {"A": "A", "U": "U", "C": "C", "G": "G"}


def _managed_confidence_containers(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every named confidence container once, including nested envelopes."""

    containers: list[dict[str, Any]] = []
    pending = [result]
    seen: set[int] = set()
    while pending:
        container = pending.pop()
        identity = id(container)
        if identity in seen:
            continue
        seen.add(identity)
        containers.append(container)
        pending.extend(
            value
            for key in ("result", "confidence", "metrics")
            if isinstance((value := container.get(key)), dict)
        )
    return containers


def normalize_managed_response(response: dict[str, Any]) -> dict[str, Any]:
    """Apply the pinned SDK's single optional data envelope."""

    if "data" in response and "outputs" not in response:
        data = response["data"]
        if not isinstance(data, dict):
            raise SchemaDriftError(
                "managed API data envelope must contain a JSON object",
                raw=response,
            )
        return data
    return response


def _expected_confidence_dimensions(
    result: dict[str, Any],
    *,
    endpoint: str | None,
    request: dict[str, Any] | None,
) -> tuple[int | None, int | None, str | None, int | None]:
    if endpoint in {"fold", "fold_all_atom"} and request is not None:
        sequence = request.get("sequence")
        if isinstance(sequence, str) and sequence:
            return (
                sum(residue != "|" for residue in sequence),
                len(sequence),
                sequence,
                sequence.count("|") + 1,
            )
    request_chain_count: int | None = None
    if endpoint == "fold_all_atom" and request is not None:
        all_atom_input = request.get("all_atom_input")
        if isinstance(all_atom_input, dict):
            entities = all_atom_input.get("sequences")
            if isinstance(entities, list) and entities:
                request_chain_count = 0
                for entity in entities:
                    if not isinstance(entity, dict):
                        request_chain_count = None
                        break
                    chain_ids = entity.get("id")
                    request_chain_count += len(chain_ids) if isinstance(chain_ids, list) else 1
    coordinates = result.get("coordinates")
    if isinstance(coordinates, list) and coordinates:
        return len(coordinates), len(coordinates), None, None
    complex_state = result.get("complex")
    if isinstance(complex_state, dict):
        sequence = complex_state.get("sequence")
        if isinstance(sequence, list) and sequence:
            return len(sequence), len(sequence), None, request_chain_count
    return None, None, None, request_chain_count


def _require_requested_outputs(
    result: dict[str, Any],
    *,
    endpoint: str | None,
    request: dict[str, Any] | None,
    normalized_confidence: dict[str, Any] | None = None,
) -> None:
    if endpoint not in {"fold", "fold_all_atom"} or request is None:
        return
    for request_field, response_fields in MANAGED_REQUESTED_OUTPUT_FIELDS.items():
        if request.get(request_field) is not True:
            continue
        missing = [
            field
            for field in response_fields
            if result.get(field) is None
            and (normalized_confidence is None or field not in normalized_confidence)
        ]
        if missing:
            display_names = {"pae": "pAE"}
            raise SchemaDriftError(
                f"managed {endpoint} response is missing requested "
                + ", ".join(display_names.get(field, field) for field in missing),
                raw=result,
            )


def _validate_metric_number(
    value: Any,
    *,
    field: str,
    raw: dict[str, Any],
    low: float | None = None,
    high: float | None = None,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SchemaDriftError(
            f"managed confidence field {field} must be finite numeric data",
            raw=raw,
        )
    if (low is not None and value < low) or (high is not None and value > high):
        raise SchemaDriftError(
            f"managed confidence field {field} is outside its validated range",
            raw=raw,
        )


def _normalized_plddt_vector(
    value: Any,
    *,
    field: str,
    raw: dict[str, Any],
    expected_residue_length: int | None,
    expected_track_length: int | None,
    sequence_track: str | None,
) -> tuple[list[Any], int | None]:
    expected_lengths = {
        length for length in (expected_residue_length, expected_track_length) if length is not None
    }
    if (
        not isinstance(value, list)
        or not value
        or (expected_lengths and len(value) not in expected_lengths)
    ):
        raise SchemaDriftError(
            f"managed confidence field {field} has an invalid vector shape",
            raw=raw,
        )
    provider_track = (
        sequence_track is not None and "|" in sequence_track and len(value) == len(sequence_track)
    )
    for index, item in enumerate(value):
        is_chain_break = provider_track and sequence_track[index] == "|"
        if is_chain_break:
            if item not in (None, 0, 0.0):
                raise SchemaDriftError(
                    "managed plddt chain-break placeholders must be null or zero",
                    raw=raw,
                )
            continue
        if item is None:
            raise SchemaDriftError(
                "managed plddt confidence cannot be null for an actual residue",
                raw=raw,
            )
        _validate_metric_number(
            item,
            field=field,
            raw=raw,
            low=0,
            high=1,
        )
    if provider_track:
        return (
            [item for item, residue in zip(value, sequence_track, strict=True) if residue != "|"],
            len(value),
        )
    return value, None


def _validate_metric_matrix(
    value: Any,
    *,
    field: str,
    raw: dict[str, Any],
    expected_length: int | None,
    low: float,
    high: float | None,
) -> None:
    if not isinstance(value, list) or not value:
        raise SchemaDriftError(
            f"managed confidence field {field} has an invalid matrix shape",
            raw=raw,
        )
    size = len(value)
    if expected_length is not None and size != expected_length:
        raise SchemaDriftError(
            f"managed confidence field {field} has an invalid matrix shape",
            raw=raw,
        )
    if any(not isinstance(row, list) or len(row) != size for row in value):
        raise SchemaDriftError(
            f"managed confidence field {field} has an invalid matrix shape",
            raw=raw,
        )
    for row in value:
        for item in row:
            if item is None:
                raise SchemaDriftError(
                    f"managed confidence field {field} cannot contain null values",
                    raw=raw,
                )
            _validate_metric_number(
                item,
                field=field,
                raw=raw,
                low=low,
                high=high,
            )


def _plddt_vectors_agree(left: list[Any], right: list[Any]) -> bool:
    return len(left) == len(right) and all(
        math.isclose(
            left_value,
            right_value,
            rel_tol=PLDDT_TRACK_REL_TOLERANCE,
            abs_tol=PLDDT_TRACK_ABS_TOLERANCE,
        )
        for left_value, right_value in zip(left, right, strict=True)
    )


def _all_atom_complex_plddt(
    result: dict[str, Any],
) -> tuple[int | None, list[Any] | None]:
    """Validate the confidence track embedded in the serializable complex state."""

    complex_state = result.get("complex")
    if not isinstance(complex_state, dict):
        return None, None
    sequence = complex_state.get("sequence")
    if not isinstance(sequence, list) or not sequence:
        return None, None
    token_count = len(sequence)
    complex_plddt = complex_state.get("plddt")
    if complex_plddt is None:
        return token_count, None
    if not isinstance(complex_plddt, list) or len(complex_plddt) != token_count:
        raise SchemaDriftError(
            "managed fold_all_atom complex plddt must align with tokens",
            raw=result,
        )
    for item in complex_plddt:
        _validate_metric_number(
            item,
            field="complex.plddt",
            raw=result,
            low=0,
            high=1,
        )
    return token_count, complex_plddt


def _normalized_all_atom_outer_plddt(
    value: Any,
    *,
    field: str,
    raw: dict[str, Any],
    expected_residue_length: int | None,
    expected_track_length: int | None,
    sequence_track: str | None,
    complex_token_count: int | None,
) -> tuple[list[Any], int | None, bool]:
    """Validate an outer pLDDT vector and classify whether its axis is mapped."""

    if (
        isinstance(value, list)
        and sequence_track is not None
        and "|" in sequence_track
        and len(value) == len(sequence_track)
    ):
        normalized, provider_track_length = _normalized_plddt_vector(
            value,
            field=field,
            raw=raw,
            expected_residue_length=expected_residue_length,
            expected_track_length=expected_track_length,
            sequence_track=sequence_track,
        )
    else:
        normalized, provider_track_length = _normalized_plddt_vector(
            value,
            field=field,
            raw=raw,
            expected_residue_length=None,
            expected_track_length=None,
            sequence_track=None,
        )
    mapped = complex_token_count is None or len(normalized) == complex_token_count
    return normalized, provider_track_length, mapped


def _validate_all_atom_plddt_consistency(
    result: dict[str, Any],
    *,
    request: dict[str, Any] | None,
) -> None:
    """Bind provenance confidence to the all-atom track serialized into mmCIF."""

    complex_state = result.get("complex")
    if not isinstance(complex_state, dict):
        return
    complex_plddt = complex_state.get("plddt")
    if not isinstance(complex_plddt, list):
        return

    (
        expected_residue_length,
        expected_track_length,
        sequence_track,
        _,
    ) = _expected_confidence_dimensions(
        result,
        endpoint="fold_all_atom",
        request=request,
    )
    containers = _managed_confidence_containers(result)
    for container in containers:
        value = container.get("plddt")
        if value is None:
            continue
        provider_plddt, _, mapped = _normalized_all_atom_outer_plddt(
            value,
            field="plddt",
            raw=result,
            expected_residue_length=expected_residue_length,
            expected_track_length=expected_track_length,
            sequence_track=sequence_track,
            complex_token_count=len(complex_plddt),
        )
        if mapped and not _plddt_vectors_agree(provider_plddt, complex_plddt):
            raise SchemaDriftError(
                "managed fold_all_atom pLDDT tracks disagree beyond the validated "
                "quantization tolerance",
                raw=result,
            )


def _managed_confidence_contract(
    result: dict[str, Any],
    *,
    endpoint: str | None = None,
    request: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate confidence once and return its summaries and canonical values."""

    containers = _managed_confidence_containers(result)
    (
        expected_residue_length,
        expected_track_length,
        sequence_track,
        expected_chain_count,
    ) = _expected_confidence_dimensions(
        result,
        endpoint=endpoint,
        request=request,
    )
    metrics: dict[str, Any] = {}
    normalized_values: dict[str, Any] = {}
    plddt_provider_track_length: int | None = None
    metadata: dict[str, dict[str, Any]] = {}
    observed_confidence_fields: set[str] = set()
    mapped_all_atom_fields: set[str] = set()
    unmapped_all_atom_fields: set[str] = set()
    complex_token_count: int | None = None
    complex_plddt: list[Any] | None = None
    if endpoint == "fold_all_atom":
        complex_token_count, complex_plddt = _all_atom_complex_plddt(result)
        if complex_plddt is not None:
            normalized_values["plddt"] = complex_plddt
            metadata["plddt"] = {
                "scale": "0-1",
                "scope": "per-token",
                "index_basis": "returned complex.sequence tokens",
                "source": "complex.plddt",
                "mapping_status": "mapped",
                "completeness": "complete",
            }
            summary = numeric_metric_summary(complex_plddt)
            if isinstance(summary, dict):
                summary.update(metadata["plddt"])
            metrics["plddt"] = summary
            mapped_all_atom_fields.add("complex.plddt")
    all_atom_index_metadata = (
        {"scope": "per-token", "index_basis": "returned complex.sequence tokens"}
        if endpoint == "fold_all_atom"
        else {"scope": "per-residue"}
    )
    all_atom_pair_index_metadata = (
        {"scope": "token-pair", "index_basis": "returned complex.sequence tokens"}
        if endpoint == "fold_all_atom"
        else {"scope": "residue-pair"}
    )
    for container in containers:
        for provider_field, canonical_field in MANAGED_CONFIDENCE_FIELDS:
            value = container.get(provider_field)
            if value is None:
                continue
            observed_confidence_fields.add(canonical_field)
            summary_value = value
            provider_track_length: int | None = None
            metric_field = canonical_field
            if canonical_field == "plddt":
                if endpoint == "fold_all_atom":
                    summary_value, provider_track_length, mapped = _normalized_all_atom_outer_plddt(
                        value,
                        field=provider_field,
                        raw=result,
                        expected_residue_length=expected_residue_length,
                        expected_track_length=expected_track_length,
                        sequence_track=sequence_track,
                        complex_token_count=complex_token_count,
                    )
                    if mapped:
                        metadata.setdefault(
                            canonical_field,
                            {
                                "scale": "0-1",
                                **all_atom_index_metadata,
                                "source": f"response.{provider_field}",
                                "mapping_status": "mapped",
                                "completeness": "complete",
                            },
                        )
                        metadata[canonical_field]["outer_mapping_status"] = "mapped"
                        mapped_all_atom_fields.add(provider_field)
                    else:
                        metric_field = "unmapped_plddt"
                        metadata[metric_field] = {
                            "scale": "0-1",
                            "scope": "unmapped",
                            "index_basis": (
                                "provider confidence axis; no mapping to returned "
                                "complex.sequence tokens"
                            ),
                            "source": f"response.{provider_field}",
                            "mapping_status": "unmapped",
                            "completeness": "partial",
                        }
                        unmapped_all_atom_fields.add(provider_field)
                else:
                    summary_value, provider_track_length = _normalized_plddt_vector(
                        value,
                        field=provider_field,
                        raw=result,
                        expected_residue_length=expected_residue_length,
                        expected_track_length=expected_track_length,
                        sequence_track=sequence_track,
                    )
                    metadata[canonical_field] = {
                        "scale": "0-1",
                        **all_atom_index_metadata,
                    }
                if provider_track_length is not None:
                    if (
                        plddt_provider_track_length is not None
                        and plddt_provider_track_length != provider_track_length
                    ):
                        raise SchemaDriftError(
                            "managed plddt provider track shapes disagree",
                            raw=result,
                        )
                    plddt_provider_track_length = provider_track_length
            elif canonical_field in {"ptm", "iptm", "mean_plddt"}:
                _validate_metric_number(
                    value,
                    field=provider_field,
                    raw=result,
                    low=0,
                    high=1,
                )
                metadata[canonical_field] = {"scale": "0-1"}
            elif canonical_field == "pae":
                if endpoint == "fold_all_atom":
                    _validate_metric_matrix(
                        value,
                        field=provider_field,
                        raw=result,
                        expected_length=None,
                        low=0,
                        high=None,
                    )
                    mapped = complex_token_count is None or len(value) == complex_token_count
                    if mapped:
                        metadata[canonical_field] = {
                            "units": "angstrom",
                            **all_atom_pair_index_metadata,
                            "source": f"response.{provider_field}",
                            "mapping_status": "mapped",
                            "completeness": "complete",
                        }
                        mapped_all_atom_fields.add(provider_field)
                    else:
                        metric_field = "unmapped_pae"
                        metadata[metric_field] = {
                            "units": "angstrom",
                            "scope": "unmapped-pair",
                            "index_basis": (
                                "provider confidence axis; no mapping to returned "
                                "complex.sequence tokens"
                            ),
                            "source": f"response.{provider_field}",
                            "mapping_status": "unmapped",
                            "completeness": "partial",
                        }
                        unmapped_all_atom_fields.add(provider_field)
                else:
                    _validate_metric_matrix(
                        value,
                        field=provider_field,
                        raw=result,
                        expected_length=expected_residue_length,
                        low=0,
                        high=None,
                    )
                    metadata[canonical_field] = {
                        "units": "angstrom",
                        **all_atom_pair_index_metadata,
                    }
            elif canonical_field == "pair_chains_iptm":
                _validate_metric_matrix(
                    value,
                    field=provider_field,
                    raw=result,
                    expected_length=expected_chain_count,
                    low=0,
                    high=1,
                )
                metadata[canonical_field] = {"scale": "0-1"}
            if metric_field in normalized_values:
                values_agree = summary_value == normalized_values[metric_field]
                if endpoint == "fold_all_atom" and metric_field == "plddt":
                    values_agree = _plddt_vectors_agree(
                        summary_value,
                        normalized_values[metric_field],
                    )
                if not values_agree:
                    if endpoint == "fold_all_atom" and metric_field == "plddt":
                        raise SchemaDriftError(
                            "managed fold_all_atom pLDDT tracks disagree beyond the "
                            "validated quantization tolerance",
                            raw=result,
                        )
                    raise SchemaDriftError(
                        f"managed confidence values disagree for normalized field {metric_field}",
                        raw=result,
                    )
                continue
            normalized_values[metric_field] = summary_value
            summary = numeric_metric_summary(summary_value)
            if isinstance(summary, dict):
                summary.update(metadata[metric_field])
                if provider_track_length is not None:
                    summary["provider_shape"] = [provider_track_length]
                    summary["chain_break_placeholders"] = provider_track_length - len(summary_value)
            metrics[metric_field] = summary
    plddt_summary = metrics.get("plddt")
    if isinstance(plddt_summary, dict) and plddt_provider_track_length is not None:
        plddt_summary["provider_shape"] = [plddt_provider_track_length]
        plddt_summary["chain_break_placeholders"] = plddt_provider_track_length - len(
            normalized_values["plddt"]
        )
    if endpoint in {"fold", "fold_all_atom"} and "plddt" not in metrics:
        raise SchemaDriftError(
            f"managed {endpoint} response is missing required pLDDT confidence",
            raw=result,
        )
    available_confidence = dict(normalized_values)
    available_confidence.update({field: True for field in observed_confidence_fields})
    _require_requested_outputs(
        result,
        endpoint=endpoint,
        request=request,
        normalized_confidence=available_confidence,
    )
    if endpoint == "fold_all_atom":
        metrics["confidence_completeness"] = {
            "status": "partial" if unmapped_all_atom_fields else "complete",
            "index_basis": "returned complex.sequence tokens",
            "mapped_fields": sorted(mapped_all_atom_fields),
            "unmapped_fields": sorted(unmapped_all_atom_fields),
        }
    if metadata:
        metrics["metric_metadata"] = metadata
    return metrics, normalized_values


def managed_confidence_metrics(
    result: dict[str, Any],
    *,
    endpoint: str | None = None,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and summarize confidence from a normalized managed response."""

    metrics, _ = _managed_confidence_contract(
        result,
        endpoint=endpoint,
        request=request,
    )
    return metrics


def _load_structure_sdk(endpoint: str):
    """Adapt the readiness-tested endpoint loader to the serializer call sites."""

    components = load_structure_serializer_sdk(endpoint)
    if endpoint == "fold":
        esm_protein, maybe_tensor = components
        return esm_protein, maybe_tensor, None
    (molecular_complex,) = components
    return None, None, molecular_complex


def _expand_compact_sequence_track(
    value: Any,
    *,
    sequence: str,
    field: str,
    chain_break_value: Any,
    raw: dict[str, Any],
) -> Any:
    """Align one residue-only JSON track to the SDK's separator-containing sequence."""

    if value is None or "|" not in sequence:
        return value
    if not isinstance(value, list):
        raise SchemaDriftError(f"managed fold {field} must be a sequence-aligned list", raw=raw)
    residue_count = sum(residue != "|" for residue in sequence)
    if len(value) == len(sequence):
        return value
    if len(value) != residue_count:
        raise SchemaDriftError(
            f"managed fold {field} does not match the submitted sequence length",
            raw=raw,
        )
    iterator = iter(value)
    return [
        deepcopy(chain_break_value) if residue == "|" else next(iterator) for residue in sequence
    ]


def _fold_to_pdb(
    result: dict[str, Any],
    request: dict[str, Any],
    confidence_values: dict[str, Any],
    esm_protein: Any,
    maybe_tensor: Any,
) -> str:
    sequence = request.get("sequence")
    if not isinstance(sequence, str) or not sequence.strip():
        raise ValidationError(
            "managed fold artifact materialization requires the submitted sequence"
        )
    coordinates = result.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise SchemaDriftError(
            "managed fold response is missing coordinates",
            raw=result,
        )
    sdk_coordinates = _expand_compact_sequence_track(
        coordinates,
        sequence=sequence,
        field="coordinates",
        chain_break_value=[[None, None, None] for _ in range(37)],
        raw=result,
    )
    sdk_plddt = _expand_compact_sequence_track(
        confidence_values.get("plddt"),
        sequence=sequence,
        field="pLDDT",
        chain_break_value=None,
        raw=result,
    )
    sdk_residue_index = _expand_compact_sequence_track(
        result.get("residue_index"),
        sequence=sequence,
        field="residue_index",
        chain_break_value=None,
        raw=result,
    )
    sdk_entity_id = _expand_compact_sequence_track(
        result.get("entity_id"),
        sequence=sequence,
        field="entity_id",
        chain_break_value=None,
        raw=result,
    )
    protein = esm_protein(
        sequence=sequence,
        coordinates=maybe_tensor(sdk_coordinates, convert_none_to_nan=True),
        ptm=maybe_tensor(confidence_values.get("ptm")),
        plddt=maybe_tensor(sdk_plddt, convert_none_to_nan=True),
        pae=maybe_tensor(confidence_values.get("pae")),
        interface_ptm=maybe_tensor(confidence_values.get("iptm")),
        pair_chains_iptm=maybe_tensor(confidence_values.get("pair_chains_iptm")),
        output_embedding_sequence=maybe_tensor(
            result.get("output_embedding_sequence"),
            convert_none_to_nan=True,
        ),
        output_embedding_pair_pooled=maybe_tensor(
            result.get("output_embedding_pair_pooled"),
            convert_none_to_nan=True,
        ),
        residue_index=maybe_tensor(
            sdk_residue_index,
            convert_none_to_nan=True,
        ),
        entity_id=maybe_tensor(
            sdk_entity_id,
            convert_none_to_nan=True,
        ),
    )
    return protein_to_pdb_string(protein)


def _fold_all_atom_to_mmcif(
    result: dict[str, Any],
    molecular_complex: Any,
) -> str:
    complex_state = result.get("complex")
    if not isinstance(complex_state, dict) or not complex_state:
        raise SchemaDriftError(
            "managed fold_all_atom response is missing the complex state",
            raw=result,
        )
    sdk_state = deepcopy(complex_state)
    metadata = sdk_state.get("metadata")
    if not isinstance(metadata, dict):
        raise SchemaDriftError(
            "managed fold_all_atom complex metadata must be an object",
            raw=result,
        )
    for field in ("entity_lookup", "chain_lookup"):
        lookup = metadata.get(field)
        if not isinstance(lookup, dict):
            raise SchemaDriftError(
                f"managed fold_all_atom complex {field} must be a string lookup",
                raw=result,
            )
        normalized: dict[int, Any] = {}
        original_keys: dict[int, str] = {}
        for key, item in lookup.items():
            if (
                not isinstance(key, str)
                or not key
                or any(character not in "0123456789" for character in key)
            ):
                raise SchemaDriftError(
                    f"managed fold_all_atom complex {field} keys must be nonnegative "
                    "decimal integers",
                    raw=result,
                )
            normalized_key = int(key)
            if normalized_key in normalized:
                raise SchemaDriftError(
                    f"managed fold_all_atom complex {field} keys "
                    f"{original_keys[normalized_key]!r} and {key!r} collide after integer "
                    "normalization",
                    raw=result,
                )
            normalized[normalized_key] = item
            original_keys[normalized_key] = key
        metadata[field] = normalized
    return molecular_complex.from_state_dict(sdk_state).to_mmcif()


def _serialized_atom_record_count(content: str) -> int:
    return sum(
        1
        for line in content.splitlines()
        if line.split(maxsplit=1) and line.split(maxsplit=1)[0] in {"ATOM", "HETATM"}
    )


def _validate_serialized_all_atom_count(
    result: dict[str, Any],
    *,
    observed_count: int,
) -> None:
    """Bind a serialized mmCIF to the validated returned atom array."""

    complex_state = result["complex"]
    expected_count = len(complex_state["atom_positions"])
    if observed_count != expected_count:
        raise SchemaDriftError(
            "managed fold_all_atom mmCIF atom count does not match returned coordinates",
            raw=result,
        )


def _validate_fold_coordinates(
    coordinates: Any,
    *,
    request: dict[str, Any] | None,
    raw: dict[str, Any],
) -> None:
    if not isinstance(coordinates, list) or not coordinates:
        raise SchemaDriftError("managed fold response is missing coordinates", raw=raw)
    sequence_track: list[str | None] = [None] * len(coordinates)
    if request is not None and isinstance((sequence := request.get("sequence")), str):
        biological_track = [residue for residue in sequence if residue != "|"]
        if len(coordinates) == len(sequence):
            sequence_track = list(sequence)
        elif len(coordinates) == len(biological_track):
            sequence_track = biological_track
        else:
            raise SchemaDriftError(
                "managed fold coordinates do not match the submitted sequence length",
                raw=raw,
            )
    for residue_index, (residue, sequence_token) in enumerate(
        zip(coordinates, sequence_track, strict=True)
    ):
        if not isinstance(residue, list) or len(residue) != 37:
            raise SchemaDriftError(
                "managed fold coordinates must use the pinned SDK atom37 shape",
                raw=raw,
            )
        missing_atoms: list[bool] = []
        for atom in residue:
            if not isinstance(atom, list) or len(atom) != 3:
                raise SchemaDriftError(
                    "managed fold coordinates must contain three-dimensional atom positions",
                    raw=raw,
                )
            missing_components = [component is None for component in atom]
            if any(missing_components) and not all(missing_components):
                raise SchemaDriftError(
                    "managed fold atom coordinates must be complete finite triples or all-null",
                    raw=raw,
                )
            missing_atoms.append(all(missing_components))
            for component in atom:
                if component is None:
                    continue
                if (
                    isinstance(component, bool)
                    or not isinstance(component, (int, float))
                    or not math.isfinite(component)
                ):
                    raise SchemaDriftError(
                        "managed fold coordinates must contain finite numbers or nulls",
                        raw=raw,
                    )
        if sequence_token == "|":
            if not all(missing_atoms):
                raise SchemaDriftError(
                    "managed fold chain-break coordinate placeholders must be all-null",
                    raw=raw,
                )
            continue
        if any(missing_atoms[index] for index in (0, 1, 2)):
            raise SchemaDriftError(
                "managed fold biological residues require finite N, CA, and C backbone coordinates "
                f"(missing at residue index {residue_index})",
                raw=raw,
            )


def _validate_string_lookup(value: Any, *, field: str, raw: dict[str, Any]) -> None:
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()
    ):
        raise SchemaDriftError(
            f"managed fold_all_atom complex {field} must be a string lookup",
            raw=raw,
        )


def _expected_molecular_complex_chains(
    request: dict[str, Any] | None,
) -> list[tuple[str | None, tuple[str, ...], bool]] | None:
    """Return submitted chain identities in the pinned SDK's output representation."""

    if request is None:
        return None
    sequence = request.get("sequence")
    if isinstance(sequence, str) and sequence:
        return [
            (
                None,
                tuple(PROTEIN_RESIDUE_TOKENS.get(residue, "UNK") for residue in chain),
                False,
            )
            for chain in sequence.split("|")
        ]

    all_atom_input = request.get("all_atom_input")
    if not isinstance(all_atom_input, dict):
        return None
    entities = all_atom_input.get("sequences")
    if not isinstance(entities, list) or not entities:
        return None

    chains: list[tuple[str | None, tuple[str, ...], bool]] = []
    for entity in entities:
        if not isinstance(entity, dict):
            return None
        entity_type = entity.get("type")
        if entity_type == "ligand":
            ccd = entity.get("ccd")
            tokens = (ccd[0],) if isinstance(ccd, list) and ccd else ("LIG",)
        elif entity_type in {"protein", "dna", "rna"}:
            entity_sequence = entity.get("sequence")
            if not isinstance(entity_sequence, str) or not entity_sequence:
                return None
            residue_tokens = {
                "protein": PROTEIN_RESIDUE_TOKENS,
                "dna": DNA_RESIDUE_TOKENS,
                "rna": RNA_RESIDUE_TOKENS,
            }[entity_type]
            mapped = [residue_tokens.get(residue, "UNK") for residue in entity_sequence]
            for modification in entity.get("modifications") or []:
                mapped[modification["position"]] = modification["ccd"]
            tokens = tuple(mapped)
        else:
            return None

        identity = entity.get("id")
        chain_names = identity if isinstance(identity, list) else [identity]
        chains.extend((name, tokens, entity_type == "ligand") for name in chain_names)
    return chains


def _bind_molecular_complex_chains(
    value: dict[str, Any],
    *,
    request: dict[str, Any] | None,
    raw: dict[str, Any],
) -> None:
    """Bind returned residue and chain identities to the normalized submitted request."""

    expected = _expected_molecular_complex_chains(request)
    if expected is None:
        return
    chain_ids = value.get("chain_id")
    if chain_ids is None:
        if len(expected) != 1:
            raise SchemaDriftError(
                "managed fold_all_atom multichain response is missing chain_id",
                raw=raw,
            )
        chain_ids = [0] * len(value["sequence"])

    lookup = value["metadata"]["chain_lookup"]
    if len(set(lookup.values())) != len(lookup):
        raise SchemaDriftError(
            "managed fold_all_atom complex chain_lookup repeats a chain identity",
            raw=raw,
        )
    observed: dict[str, list[str]] = {}
    observed_hetero: dict[str, set[bool]] = {}
    hetero = value.get("atom_hetero")
    for token, chain_index, atom_bounds in zip(
        value["sequence"], chain_ids, value["token_to_atoms"], strict=True
    ):
        name = lookup.get(str(chain_index))
        if name is None:
            raise SchemaDriftError(
                "managed fold_all_atom complex chain_id does not resolve in chain_lookup",
                raw=raw,
            )
        observed.setdefault(name, []).append(token)
        if hetero is not None:
            start, end = atom_bounds
            observed_hetero.setdefault(name, set()).update(hetero[start:end])

    if set(observed) != set(lookup.values()):
        raise SchemaDriftError(
            "managed fold_all_atom complex chain_lookup contains an unrepresented chain",
            raw=raw,
        )
    named = {name: (tokens, is_ligand) for name, tokens, is_ligand in expected if name is not None}
    anonymous = [(tokens, is_ligand) for name, tokens, is_ligand in expected if name is None]
    if len(named) + len(anonymous) != len(expected) or len(observed) != len(expected):
        raise SchemaDriftError(
            "managed fold_all_atom response chain composition does not match the request",
            raw=raw,
        )
    if not set(named).issubset(observed):
        raise SchemaDriftError(
            "managed fold_all_atom response chain identities do not match the request",
            raw=raw,
        )
    for name, (tokens, is_ligand) in named.items():
        if tuple(observed[name]) != tokens:
            raise SchemaDriftError(
                f"managed fold_all_atom response residue identities do not match requested chain {name}",
                raw=raw,
            )
        if hetero is not None and observed_hetero.get(name) != {is_ligand}:
            raise SchemaDriftError(
                f"managed fold_all_atom response entity type does not match requested chain {name}",
                raw=raw,
            )

    unmatched: list[tuple[tuple[str, ...], bool | None]] = []
    for name, tokens in observed.items():
        if name in named:
            continue
        if hetero is None:
            unmatched.append((tuple(tokens), None))
            continue
        identities = observed_hetero.get(name, set())
        if len(identities) != 1:
            raise SchemaDriftError(
                "managed fold_all_atom response chain mixes polymer and ligand atoms",
                raw=raw,
            )
        unmatched.append((tuple(tokens), next(iter(identities))))
    if hetero is None:
        expected_anonymous = Counter(tokens for tokens, _ in anonymous)
        actual_anonymous = Counter(tokens for tokens, _ in unmatched)
    else:
        expected_anonymous = Counter(anonymous)
        actual_anonymous = Counter(unmatched)
    if expected_anonymous != actual_anonymous:
        raise SchemaDriftError(
            "managed fold_all_atom response residue or entity identities do not match the request",
            raw=raw,
        )


def _validate_molecular_complex_state(
    value: Any,
    *,
    raw: dict[str, Any],
    request: dict[str, Any] | None,
) -> None:
    if not isinstance(value, dict) or not value:
        raise SchemaDriftError(
            "managed fold_all_atom response is missing the complex state",
            raw=raw,
        )
    required = {
        "id",
        "sequence",
        "atom_positions",
        "atom_elements",
        "token_to_atoms",
        "plddt",
        "metadata",
    }
    allowed = required | {"chain_id", "atom_names", "atom_hetero"}
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - allowed)
    if missing or unknown:
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if unknown:
            detail.append("unknown " + ", ".join(unknown))
        raise SchemaDriftError(
            "managed fold_all_atom complex state has " + "; ".join(detail),
            raw=raw,
        )
    if not isinstance(value["id"], str) or not value["id"]:
        raise SchemaDriftError(
            "managed fold_all_atom complex id must be a nonempty string",
            raw=raw,
        )
    sequence = value["sequence"]
    if (
        not isinstance(sequence, list)
        or not sequence
        or any(not isinstance(token, str) or not token for token in sequence)
    ):
        raise SchemaDriftError(
            "managed fold_all_atom complex sequence must contain token strings",
            raw=raw,
        )
    atom_positions = value["atom_positions"]
    if not isinstance(atom_positions, list) or not atom_positions:
        raise SchemaDriftError(
            "managed fold_all_atom complex atom_positions must be nonempty",
            raw=raw,
        )
    for position in atom_positions:
        if (
            not isinstance(position, list)
            or len(position) != 3
            or any(
                isinstance(component, bool)
                or not isinstance(component, (int, float))
                or not math.isfinite(component)
                for component in position
            )
        ):
            raise SchemaDriftError(
                "managed fold_all_atom complex atom_positions must be finite 3D coordinates",
                raw=raw,
            )
    atom_count = len(atom_positions)
    atom_elements = value["atom_elements"]
    if (
        not isinstance(atom_elements, list)
        or len(atom_elements) != atom_count
        or any(not isinstance(element, str) or not element for element in atom_elements)
    ):
        raise SchemaDriftError(
            "managed fold_all_atom complex atom_elements must align with atoms",
            raw=raw,
        )
    token_to_atoms = value["token_to_atoms"]
    if not isinstance(token_to_atoms, list) or len(token_to_atoms) != len(sequence):
        raise SchemaDriftError(
            "managed fold_all_atom complex token_to_atoms must align with tokens",
            raw=raw,
        )
    expected_start = 0
    for bounds in token_to_atoms:
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) for item in bounds)
        ):
            raise SchemaDriftError(
                "managed fold_all_atom complex token_to_atoms bounds are invalid",
                raw=raw,
            )
        start, end = bounds
        if start != expected_start or not start < end or end > atom_count:
            raise SchemaDriftError(
                "managed fold_all_atom complex token_to_atoms must partition the atom array",
                raw=raw,
            )
        expected_start = end
    if expected_start != atom_count:
        raise SchemaDriftError(
            "managed fold_all_atom complex token_to_atoms must cover every atom",
            raw=raw,
        )
    chain_id = value.get("chain_id")
    if chain_id is not None and (
        not isinstance(chain_id, list)
        or len(chain_id) != len(sequence)
        or any(isinstance(item, bool) or not isinstance(item, int) for item in chain_id)
    ):
        raise SchemaDriftError(
            "managed fold_all_atom complex chain_id must align with tokens",
            raw=raw,
        )
    inner_plddt = value["plddt"]
    if not isinstance(inner_plddt, list) or len(inner_plddt) != len(sequence):
        raise SchemaDriftError(
            "managed fold_all_atom complex plddt must align with tokens",
            raw=raw,
        )
    for item in inner_plddt:
        _validate_metric_number(item, field="complex.plddt", raw=raw, low=0, high=1)
    metadata = value["metadata"]
    if not isinstance(metadata, dict):
        raise SchemaDriftError(
            "managed fold_all_atom complex metadata must be an object",
            raw=raw,
        )
    metadata_allowed = {"entity_lookup", "chain_lookup", "assembly_composition"}
    if set(metadata) - metadata_allowed or not {
        "entity_lookup",
        "chain_lookup",
    }.issubset(metadata):
        raise SchemaDriftError(
            "managed fold_all_atom complex metadata fields are invalid",
            raw=raw,
        )
    _validate_string_lookup(metadata["entity_lookup"], field="entity_lookup", raw=raw)
    _validate_string_lookup(metadata["chain_lookup"], field="chain_lookup", raw=raw)
    assembly = metadata.get("assembly_composition")
    if assembly is not None and (
        not isinstance(assembly, dict)
        or any(
            not isinstance(key, str)
            or not isinstance(items, list)
            or any(not isinstance(item, str) for item in items)
            for key, items in assembly.items()
        )
    ):
        raise SchemaDriftError(
            "managed fold_all_atom complex assembly_composition is invalid",
            raw=raw,
        )
    atom_names = value.get("atom_names")
    if atom_names is not None and (
        not isinstance(atom_names, list)
        or len(atom_names) != atom_count
        or any(not isinstance(name, str) or not name for name in atom_names)
    ):
        raise SchemaDriftError(
            "managed fold_all_atom complex atom_names must align with atoms",
            raw=raw,
        )
    atom_hetero = value.get("atom_hetero")
    if atom_hetero is not None and (
        not isinstance(atom_hetero, list)
        or len(atom_hetero) != atom_count
        or any(not isinstance(item, bool) for item in atom_hetero)
    ):
        raise SchemaDriftError(
            "managed fold_all_atom complex atom_hetero must align with atoms",
            raw=raw,
        )
    _bind_molecular_complex_chains(value, request=request, raw=raw)


def validate_managed_structure_response(
    endpoint: str,
    result: dict[str, Any],
    request: dict[str, Any] | None = None,
) -> None:
    """Validate fold structures against the pinned SDK's JSON state contract."""

    if endpoint not in {"fold", "fold_all_atom"}:
        return
    artifact_key = "structure_artifact"
    if artifact_key in result:
        raise SchemaDriftError(
            f"managed {endpoint} response contains reserved {artifact_key}",
            raw=result,
        )
    if endpoint == "fold":
        _validate_fold_coordinates(result.get("coordinates"), request=request, raw=result)
        return
    _validate_molecular_complex_state(result.get("complex"), raw=result, request=request)
    _validate_all_atom_plddt_consistency(result, request=request)


def managed_structure_quality_warnings(
    endpoint: str,
    result: dict[str, Any],
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return conservative, non-mutating warnings for declared covalent geometry.

    This check runs only after the all-atom response contract has validated. It
    deliberately does not infer undeclared bonds, repair coordinates, or treat
    predicted confidence as evidence that the chemistry is sound.
    """

    if endpoint != "fold_all_atom":
        return []
    all_atom_input = request.get("all_atom_input")
    if not isinstance(all_atom_input, dict):
        return []
    bonds = all_atom_input.get("covalent_bonds")
    if not isinstance(bonds, list) or not bonds:
        return []
    complex_state = result.get("complex")
    if not isinstance(complex_state, dict):
        return []

    sequence = complex_state["sequence"]
    chain_ids = complex_state.get("chain_id")
    if chain_ids is None:
        chain_ids = [0] * len(sequence)
    chain_lookup = complex_state["metadata"]["chain_lookup"]
    tokens_by_chain: dict[str, list[int]] = {}
    for token_index, chain_index in enumerate(chain_ids):
        chain_name = chain_lookup.get(str(chain_index))
        if chain_name is not None:
            tokens_by_chain.setdefault(chain_name, []).append(token_index)

    atom_positions = complex_state["atom_positions"]
    atom_elements = complex_state["atom_elements"]
    atom_names = complex_state.get("atom_names")
    token_to_atoms = complex_state["token_to_atoms"]

    def resolve_endpoint(
        bond: dict[str, Any],
        suffix: str,
    ) -> tuple[dict[str, Any], list[float] | None]:
        chain_name = bond[f"chain_id{suffix}"]
        residue_index = bond[f"res_idx{suffix}"]
        atom_index = bond[f"atom_idx{suffix}"]
        description: dict[str, Any] = {
            "chain_id": chain_name,
            "residue_index_zero_based": residue_index,
            "atom_index_zero_based": atom_index,
        }
        chain_tokens = tokens_by_chain.get(chain_name, [])
        if residue_index >= len(chain_tokens):
            return description, None
        token_index = chain_tokens[residue_index]
        start, end = token_to_atoms[token_index]
        absolute_atom_index = start + atom_index
        if absolute_atom_index >= end:
            return description, None
        description["element"] = atom_elements[absolute_atom_index]
        if isinstance(atom_names, list):
            description["atom_name"] = atom_names[absolute_atom_index]
        return description, atom_positions[absolute_atom_index]

    warnings: list[dict[str, Any]] = []
    for bond_index, item in enumerate(bonds):
        if not isinstance(item, dict):
            continue
        endpoint_1, position_1 = resolve_endpoint(item, "1")
        endpoint_2, position_2 = resolve_endpoint(item, "2")
        endpoints = [endpoint_1, endpoint_2]
        if position_1 is None or position_2 is None:
            warnings.append(
                {
                    "code": "covalent-attachment-atom-unresolved",
                    "severity": "warning",
                    "category": "chemistry",
                    "bond_index_zero_based": bond_index,
                    "endpoints": endpoints,
                    "message": (
                        "A requested covalent attachment atom is absent from the returned "
                        "atom map; verify the zero-based indices against the molecular graph."
                    ),
                    "coordinates_modified": False,
                }
            )
            continue
        distance = math.dist(position_1, position_2)
        if (
            distance >= COVALENT_BOND_SEVERE_MIN_ANGSTROM
            and distance <= COVALENT_BOND_SEVERE_MAX_ANGSTROM
        ):
            continue
        warnings.append(
            {
                "code": "implausible-covalent-bond-length",
                "severity": "warning",
                "category": "severe-geometry",
                "bond_index_zero_based": bond_index,
                "endpoints": endpoints,
                "distance_angstrom": round(distance, 3),
                "conservative_expected_range_angstrom": {
                    "minimum": COVALENT_BOND_SEVERE_MIN_ANGSTROM,
                    "maximum": COVALENT_BOND_SEVERE_MAX_ANGSTROM,
                },
                "message": (
                    "The predicted attachment distance is outside a conservative generic "
                    "covalent-bond range. Verify the chemistry; predicted confidence is not "
                    "a chemistry check."
                ),
                "coordinates_modified": False,
            }
        )
    return warnings


def _normalize_all_atom_confidence_output(
    result: dict[str, Any],
    confidence_metrics: dict[str, Any],
    confidence_values: dict[str, Any],
) -> dict[str, Any]:
    """Separate returned-token confidence from provider-only unmapped axes."""

    normalized = deepcopy(result)
    metadata = confidence_metrics.get("metric_metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    # Remove provider arrays from every supported confidence envelope before
    # exposing a single canonical mapped value or an explicit quarantine.
    for container in _managed_confidence_containers(normalized):
        container.pop("plddt", None)
        container.pop("pae", None)

    mapped_plddt = confidence_values.get("plddt")
    if mapped_plddt is not None:
        normalized["plddt"] = deepcopy(mapped_plddt)
    mapped_pae = confidence_values.get("pae")
    if mapped_pae is not None:
        normalized["pae"] = deepcopy(mapped_pae)

    quarantine: dict[str, Any] = {}
    for canonical_name in ("plddt", "pae"):
        metric_name = f"unmapped_{canonical_name}"
        values = confidence_values.get(metric_name)
        metric_metadata = metadata.get(metric_name)
        if values is None or not isinstance(metric_metadata, dict):
            continue
        quarantine[canonical_name] = {
            "values": deepcopy(values),
            "metadata": deepcopy(metric_metadata),
        }
    if quarantine:
        normalized["unmapped_confidence"] = quarantine

    completeness = confidence_metrics.get("confidence_completeness")
    normalized["confidence_contract"] = {
        "completeness": deepcopy(completeness),
        "metric_metadata": deepcopy(metadata),
    }
    return normalized


def materialize_managed_structure(
    endpoint: str,
    result: dict[str, Any],
    request: dict[str, Any],
    output_dir: Path,
    *,
    artifact_publisher: Callable[[Path, bytes, str], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Serialize a real managed fold response with the exact pinned ESM SDK."""

    if endpoint not in {"fold", "fold_all_atom"}:
        raise ValidationError("managed structure materialization requires a fold endpoint")

    artifact_key = "structure_artifact"
    for reserved in (
        artifact_key,
        "confidence_contract",
        "unmapped_confidence",
        "quality_warnings",
        "presentation_request",
    ):
        if reserved in result:
            raise SchemaDriftError(
                f"managed {endpoint} response contains reserved {reserved}",
                raw=result,
            )
    validate_managed_structure_response(endpoint, result, request)

    if endpoint == "fold":
        sequence = request.get("sequence")
        if not isinstance(sequence, str) or not sequence.strip():
            raise ValidationError(
                "managed fold artifact materialization requires the submitted sequence"
            )
        confidence_metrics, confidence_values = _managed_confidence_contract(
            result,
            endpoint=endpoint,
            request=request,
        )
    else:
        confidence_metrics, confidence_values = _managed_confidence_contract(
            result,
            endpoint=endpoint,
            request=request,
        )

    esm_revision = verify_installed_distribution("esm")
    try:
        esm_protein, maybe_tensor, molecular_complex = _load_structure_sdk(endpoint)
    except ImportError as exc:
        raise ValidationError("pinned Biohub esm SDK is not installed") from exc

    try:
        if endpoint == "fold":
            content = _fold_to_pdb(
                result,
                request,
                confidence_values,
                esm_protein,
                maybe_tensor,
            )
            path = output_dir / "prediction.pdb"
            media_type = "chemical/x-pdb"
        else:
            content = _fold_all_atom_to_mmcif(result, molecular_complex)
            path = output_dir / "prediction.cif"
            media_type = "chemical/x-mmcif"
    except SchemaDriftError:
        raise
    except (
        AssertionError,
        AttributeError,
        IndexError,
        KeyError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise SchemaDriftError(
            f"managed {endpoint} response could not be serialized by the pinned SDK",
            raw=result,
        ) from exc

    if not isinstance(content, str) or not content.strip():
        raise SchemaDriftError(
            f"managed {endpoint} serialization produced an empty structure",
            raw=result,
        )
    atom_record_count = _serialized_atom_record_count(content)
    if atom_record_count == 0:
        raise SchemaDriftError(
            f"managed {endpoint} serialization produced no atom records",
            raw=result,
        )
    if endpoint == "fold_all_atom":
        _validate_serialized_all_atom_count(
            result,
            observed_count=atom_record_count,
        )

    encoded = content.encode("utf-8")
    if artifact_publisher is None:
        write_bytes_atomic(path, encoded)
        record = artifact_record(path, media_type=media_type)
    else:
        record = artifact_publisher(path, encoded, media_type)
    record["evidence_class"] = "model_hypothesis"
    normalized = (
        _normalize_all_atom_confidence_output(
            result,
            confidence_metrics,
            confidence_values,
        )
        if endpoint == "fold_all_atom"
        else dict(result)
    )
    normalized.pop("coordinates" if endpoint == "fold" else "complex", None)
    normalized[artifact_key] = record
    return normalized, [record], esm_revision

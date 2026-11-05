"""Deterministic ESMC single-mask mutation-landscape analysis."""

from __future__ import annotations

import csv
import io
import math
from typing import Any

from .errors import SchemaDriftError, ValidationError
from .validation import validate_esmc_sequence

CANONICAL_AMINO_ACIDS = tuple("ACDEFGHIKLMNPQRSTVWY")
# A complete landscape retains one full [L+2, V] response per residue, so its
# in-memory and raw-artifact footprint grows quadratically with sequence length.
ESMC_LANDSCAPE_MAX_RESIDUES = 512


def validate_landscape_sequence(sequence: str) -> str:
    """Require canonical residues for a complete substitution landscape."""

    normalized = validate_esmc_sequence(sequence)
    if len(normalized) > ESMC_LANDSCAPE_MAX_RESIDUES:
        raise ValidationError(
            "ESMC mutation landscapes are limited to "
            f"{ESMC_LANDSCAPE_MAX_RESIDUES} residues to bound raw-logit memory and artifact size"
        )
    if any(residue not in CANONICAL_AMINO_ACIDS for residue in normalized):
        raise ValidationError(
            "ESMC mutation landscapes require a sequence of 20 canonical amino acids"
        )
    return normalized


def _token_id(tokenizer: Any, token: str, label: str) -> int:
    value = tokenizer.convert_tokens_to_ids(token)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"pinned ESMC tokenizer returned an invalid {label} token id")
    return value


def encode_esmc_sequence(tokenizer: Any, sequence: str) -> dict[str, Any]:
    """Encode one validated sequence with exactly one BOS and one EOS token."""

    normalized = validate_esmc_sequence(sequence)
    bos_token_id = tokenizer.cls_token_id
    eos_token_id = tokenizer.eos_token_id
    mask_token_id = tokenizer.mask_token_id
    for label, token_id in (
        ("BOS", bos_token_id),
        ("EOS", eos_token_id),
        ("mask", mask_token_id),
    ):
        if isinstance(token_id, bool) or not isinstance(token_id, int) or token_id < 0:
            raise ValidationError(f"pinned ESMC tokenizer returned an invalid {label} token id")

    residue_token_ids = [
        _token_id(tokenizer, residue, f"residue {residue}") for residue in normalized
    ]
    encoded = [bos_token_id, *residue_token_ids, eos_token_id]
    if len(encoded) != len(normalized) + 2:
        raise ValidationError("pinned ESMC tokenizer must add exactly one BOS and one EOS token")
    if any(
        token_id in {bos_token_id, eos_token_id, mask_token_id} for token_id in residue_token_ids
    ):
        raise ValidationError("pinned ESMC tokenizer mapped a residue to a control token")
    return {
        "sequence": normalized,
        "tokens": encoded,
        "bos_token_id": bos_token_id,
        "eos_token_id": eos_token_id,
        "mask_token_id": mask_token_id,
        "bos_offset": 1,
    }


def canonical_token_ids(tokenizer: Any) -> dict[str, int]:
    """Resolve the 20 canonical amino-acid IDs from the pinned tokenizer."""

    result = {
        residue: _token_id(tokenizer, residue, f"canonical residue {residue}")
        for residue in CANONICAL_AMINO_ACIDS
    }
    if len(set(result.values())) != len(result):
        raise ValidationError("pinned ESMC tokenizer canonical residue IDs must be unique")
    return result


def mask_esmc_position(
    encoded_tokens: list[int],
    *,
    position_one_based: int,
    mask_token_id: int,
) -> list[int]:
    """Replace exactly one biological residue while preserving BOS/EOS."""

    residue_count = len(encoded_tokens) - 2
    if (
        isinstance(position_one_based, bool)
        or not isinstance(position_one_based, int)
        or not 1 <= position_one_based <= residue_count
    ):
        raise ValidationError("ESMC landscape position is outside the sequence")
    if isinstance(mask_token_id, bool) or not isinstance(mask_token_id, int) or mask_token_id < 0:
        raise ValidationError("ESMC landscape mask token id is invalid")
    masked = list(encoded_tokens)
    masked[position_one_based] = mask_token_id
    changed = [
        index
        for index, pair in enumerate(zip(encoded_tokens, masked, strict=True))
        if pair[0] != pair[1]
    ]
    if changed != [position_one_based]:
        raise ValidationError("ESMC landscape must replace exactly one encoded residue")
    return masked


def _full_vocabulary_entropy_bits(row: list[float]) -> float:
    maximum = max(row)
    shifted_total = math.fsum(math.exp(value - maximum) for value in row)
    log_normalizer = maximum + math.log(shifted_total)
    entropy = -math.fsum(
        probability * ((value - log_normalizer) / math.log(2.0))
        for value in row
        if (probability := math.exp(value - log_normalizer)) > 0.0
    )
    if not math.isfinite(entropy):
        raise SchemaDriftError("managed ESMC logits produce non-finite entropy")
    return entropy


def derive_mutation_landscape(
    sequence: str,
    masked_position_rows: list[list[float]],
    *,
    canonical_ids: dict[str, int],
    mask_token_id: int,
    summary_count: int = 5,
) -> dict[str, Any]:
    """Derive tutorial entropy and canonical LLRs from one row per mask."""

    normalized = validate_landscape_sequence(sequence)
    if len(masked_position_rows) != len(normalized):
        raise SchemaDriftError(
            "managed ESMC landscape must return one masked-position row per residue"
        )
    if set(canonical_ids) != set(CANONICAL_AMINO_ACIDS):
        raise ValidationError("ESMC landscape canonical tokenizer mapping is incomplete")
    if isinstance(summary_count, bool) or not isinstance(summary_count, int) or summary_count < 1:
        raise ValidationError("ESMC landscape summary count must be positive")
    minimum_width = max(*canonical_ids.values(), mask_token_id) + 1
    positions: list[dict[str, Any]] = []
    vocabulary_width: int | None = None
    for position, (wild_type, row) in enumerate(
        zip(normalized, masked_position_rows, strict=True), start=1
    ):
        if not isinstance(row, list) or len(row) < minimum_width:
            raise SchemaDriftError(
                "managed ESMC landscape row does not cover the pinned tokenizer IDs"
            )
        if vocabulary_width is None:
            vocabulary_width = len(row)
        elif len(row) != vocabulary_width:
            raise SchemaDriftError("managed ESMC landscape rows have inconsistent vocabularies")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in row
        ):
            raise SchemaDriftError("managed ESMC landscape row must contain finite numbers")
        normalized_row = [float(value) for value in row]
        wild_type_logit = normalized_row[canonical_ids[wild_type]]
        canonical_llr = {
            residue: normalized_row[token_id] - wild_type_logit
            for residue, token_id in canonical_ids.items()
        }
        negative_count = sum(
            canonical_llr[residue] < 0.0
            for residue in CANONICAL_AMINO_ACIDS
            if residue != wild_type
        )
        positions.append(
            {
                "position_one_based": position,
                "wild_type": wild_type,
                "tutorial_full_vocabulary_entropy_bits": _full_vocabulary_entropy_bits(
                    normalized_row
                ),
                "negative_substitution_fraction": negative_count / 19,
                "canonical_llr": canonical_llr,
            }
        )

    count = min(summary_count, len(positions))

    def summary_item(position: dict[str, Any]) -> dict[str, Any]:
        return {
            "position_one_based": position["position_one_based"],
            "wild_type": position["wild_type"],
            "label": f"{position['wild_type']}{position['position_one_based']}",
            "tutorial_full_vocabulary_entropy_bits": position[
                "tutorial_full_vocabulary_entropy_bits"
            ],
            "negative_substitution_fraction": position["negative_substitution_fraction"],
        }

    constrained = sorted(
        positions,
        key=lambda item: (
            item["tutorial_full_vocabulary_entropy_bits"],
            item["position_one_based"],
        ),
    )[:count]
    tolerant = sorted(
        positions,
        key=lambda item: (
            -item["tutorial_full_vocabulary_entropy_bits"],
            item["position_one_based"],
        ),
    )[:count]
    return {
        "schema_version": "1.0",
        "analysis": "single-mask-canonical-mutation-landscape",
        "evidence_class": "model-generated-hypothesis",
        "metrics": {
            "entropy": {
                "name": "tutorial_full_vocabulary_entropy_bits",
                "log_base": 2,
                "units": "bits",
                "token_set": "complete returned sequence-logit vocabulary",
                "vocabulary_width": vocabulary_width,
            },
            "negative_substitution_fraction": {
                "definition": "fraction of 19 non-wild-type canonical substitutions with LLR < 0",
                "denominator": 19,
            },
            "canonical_llr": {
                "definition": "alternate logit minus wild-type logit in the same masked context",
                "log_base": "e",
                "amino_acid_order": list(CANONICAL_AMINO_ACIDS),
            },
        },
        "positions": positions,
        "summary": {
            "most_constrained": [summary_item(item) for item in constrained],
            "most_tolerant": [summary_item(item) for item in tolerant],
        },
        "interpretation": (
            "A model-generated prioritization signal, not an experimental measurement of "
            "fitness, stability, activity, binding, or function."
        ),
    }


def render_mutation_landscape_csv(landscape: dict[str, Any]) -> bytes:
    """Render the per-position landscape in a deterministic tabular format."""

    positions = landscape.get("positions")
    if not isinstance(positions, list) or not positions:
        raise ValidationError("ESMC mutation landscape has no positions")
    fieldnames = [
        "position_one_based",
        "wild_type",
        "tutorial_full_vocabulary_entropy_bits",
        "negative_substitution_fraction",
        *(f"llr_{residue}" for residue in CANONICAL_AMINO_ACIDS),
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for position in positions:
        if not isinstance(position, dict) or not isinstance(position.get("canonical_llr"), dict):
            raise ValidationError("ESMC mutation landscape position is malformed")
        writer.writerow(
            {
                "position_one_based": position.get("position_one_based"),
                "wild_type": position.get("wild_type"),
                "tutorial_full_vocabulary_entropy_bits": position.get(
                    "tutorial_full_vocabulary_entropy_bits"
                ),
                "negative_substitution_fraction": position.get("negative_substitution_fraction"),
                **{
                    f"llr_{residue}": position["canonical_llr"].get(residue)
                    for residue in CANONICAL_AMINO_ACIDS
                },
            }
        )
    return output.getvalue().encode("utf-8")


def summarize_reported_usage(responses: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate only usage fields explicitly returned by the managed service."""

    result: dict[str, Any] = {"managed_request_count": len(responses)}
    for field in ("tokens_used", "credits_used"):
        values: list[float] = []
        for response in responses:
            container = response.get("data") if isinstance(response.get("data"), dict) else response
            value = container.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                continue
            values.append(float(value))
        result[f"responses_reporting_{field}"] = len(values)
        result[field] = math.fsum(values) if len(values) == len(responses) else None
    return result

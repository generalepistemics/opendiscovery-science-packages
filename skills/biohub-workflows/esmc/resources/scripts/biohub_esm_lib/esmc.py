"""Deterministic ESMC single-mask mutation scoring."""

from __future__ import annotations

import math
import re
from typing import Any

from .errors import SchemaDriftError, ValidationError
from .validation import validate_esmc_sequence

SUBSTITUTION_PATTERN = re.compile(r"^([A-Z])([1-9][0-9]*)([A-Z])$")


def _finite_score_number(scoring: dict[str, Any], field: str) -> float:
    value = scoring.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"mutation score {field} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValidationError(f"mutation score {field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValidationError(f"mutation score {field} must be a finite number")
    return number


def _format_score_number(value: float) -> str:
    if value == 0:
        value = 0.0
    return format(value, ".4g")


def render_mutation_score_svg(score: dict[str, Any]) -> bytes:
    """Render a deterministic, self-contained mutation-score summary card."""

    mutation = score.get("mutation")
    scoring = score.get("scoring")
    if not isinstance(mutation, dict) or not isinstance(scoring, dict):
        raise ValidationError("mutation score is missing mutation or scoring data")
    label = mutation.get("label")
    match = SUBSTITUTION_PATTERN.fullmatch(label) if isinstance(label, str) else None
    if match is None:
        raise ValidationError("mutation score label must be one uppercase substitution")
    wild_type, _, alternate = match.groups()

    llr = _finite_score_number(scoring, "log_likelihood_ratio")
    wild_type_log_probability = _finite_score_number(scoring, "wild_type_log_probability")
    alternate_log_probability = _finite_score_number(scoring, "alternate_log_probability")
    if llr > 0:
        accent = "#2563eb"
        comparison = "Alternate has higher model log probability"
    elif llr < 0:
        accent = "#d97706"
        comparison = "Alternate has lower model log probability"
    else:
        accent = "#64748b"
        comparison = "Model log probabilities are equal"

    llr_text = _format_score_number(llr)
    wild_type_text = _format_score_number(wild_type_log_probability)
    alternate_text = _format_score_number(alternate_log_probability)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="720" height="360" viewBox="0 0 720 360" role="img" aria-labelledby="title description">
  <title id="title">ESMC mutation score for {label}</title>
  <desc id="description">{comparison}. This is a model hypothesis, not experimental evidence.</desc>
  <rect width="720" height="360" rx="24" fill="#f8fafc"/>
  <rect x="1" y="1" width="718" height="358" rx="23" fill="none" stroke="#cbd5e1" stroke-width="2"/>
  <rect x="36" y="30" width="174" height="28" rx="14" fill="#e2e8f0"/>
  <text x="123" y="49" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" font-size="12" font-weight="700" letter-spacing="1.2" fill="#334155">MODEL HYPOTHESIS</text>
  <text x="36" y="94" font-family="ui-sans-serif, system-ui, sans-serif" font-size="26" font-weight="700" fill="#0f172a">{label} mutation score</text>
  <text x="36" y="120" font-family="ui-sans-serif, system-ui, sans-serif" font-size="15" fill="#475569">One masked-residue context · natural-log probabilities</text>
  <text x="36" y="176" font-family="ui-sans-serif, system-ui, sans-serif" font-size="54" font-weight="750" fill="{accent}">{llr_text}</text>
  <text x="36" y="204" font-family="ui-sans-serif, system-ui, sans-serif" font-size="14" font-weight="650" fill="#334155">log-likelihood ratio (alternate − wild type)</text>
  <text x="36" y="230" font-family="ui-sans-serif, system-ui, sans-serif" font-size="14" fill="{accent}">{comparison}</text>
  <rect x="400" y="78" width="132" height="130" rx="16" fill="#ffffff" stroke="#cbd5e1"/>
  <text x="466" y="108" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" font-size="12" font-weight="700" letter-spacing="1" fill="#64748b">WILD TYPE</text>
  <text x="466" y="157" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" font-size="38" font-weight="750" fill="#0f172a">{wild_type}</text>
  <text x="466" y="188" text-anchor="middle" font-family="ui-monospace, SFMono-Regular, monospace" font-size="14" fill="#475569">ln P = {wild_type_text}</text>
  <rect x="552" y="78" width="132" height="130" rx="16" fill="#ffffff" stroke="{accent}" stroke-width="2"/>
  <text x="618" y="108" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" font-size="12" font-weight="700" letter-spacing="1" fill="#64748b">ALTERNATE</text>
  <text x="618" y="157" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" font-size="38" font-weight="750" fill="{accent}">{alternate}</text>
  <text x="618" y="188" text-anchor="middle" font-family="ui-monospace, SFMono-Regular, monospace" font-size="14" fill="#475569">ln P = {alternate_text}</text>
  <line x1="36" y1="274" x2="684" y2="274" stroke="#cbd5e1"/>
  <text x="36" y="304" font-family="ui-sans-serif, system-ui, sans-serif" font-size="14" font-weight="650" fill="#334155">Interpret with care</text>
  <text x="36" y="329" font-family="ui-sans-serif, system-ui, sans-serif" font-size="13" fill="#475569">Model hypothesis — not experimental fitness, stability, activity, binding, or function.</text>
</svg>
"""
    return svg.encode("utf-8")


def validate_single_substitution(sequence: str, mutation: str) -> dict[str, Any]:
    """Validate one one-based substitution against an exact ESMC sequence."""

    normalized = validate_esmc_sequence(sequence)
    if not isinstance(mutation, str) or mutation != mutation.strip():
        raise ValidationError("mutation must be one uppercase substitution such as W43F")
    match = SUBSTITUTION_PATTERN.fullmatch(mutation)
    if match is None:
        raise ValidationError("mutation must be one uppercase substitution such as W43F")
    wild_type, position_text, alternate = match.groups()
    position = int(position_text)
    if position > len(normalized):
        raise ValidationError("mutation position is outside the normalized sequence")
    if normalized[position - 1] != wild_type:
        raise ValidationError("mutation wild-type residue does not match the normalized sequence")
    if alternate == wild_type:
        raise ValidationError("mutation alternate residue must differ from wild type")
    if alternate not in "ACDEFGHIKLMNPQRSTVWY":
        raise ValidationError("mutation alternate residue must be a canonical amino acid")
    return {
        "label": mutation,
        "wild_type": wild_type,
        "alternate": alternate,
        "position_one_based": position,
        "sequence_index_zero_based": position - 1,
        # The pinned ESMC tokenizer prepends exactly one BOS/CLS token.
        "logits_index_zero_based": position,
        "bos_offset": 1,
    }


def validate_sequence_logits(
    value: Any,
    *,
    expected_positions: int,
    minimum_width: int,
) -> list[list[float]]:
    """Validate the pinned single-sequence managed logits tensor as JSON data."""

    if not isinstance(value, list) or len(value) != expected_positions:
        raise SchemaDriftError(
            "managed ESMC sequence logits must be a two-dimensional [L+2, V] tensor",
            raw={"observed_type": type(value).__name__},
        )
    width: int | None = None
    result: list[list[float]] = []
    for row in value:
        if not isinstance(row, list) or not row:
            raise SchemaDriftError(
                "managed ESMC sequence logits contain an invalid row",
                raw={"positions": len(value)},
            )
        if width is None:
            width = len(row)
            if width < minimum_width:
                raise SchemaDriftError(
                    "managed ESMC sequence logits vocabulary is too small",
                    raw={"positions": len(value), "vocabulary_width": width},
                )
        elif len(row) != width:
            raise SchemaDriftError(
                "managed ESMC sequence logits contain jagged rows",
                raw={"positions": len(value)},
            )
        normalized_row: list[float] = []
        for item in row:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise SchemaDriftError(
                    "managed ESMC sequence logits must contain numeric values",
                    raw={"positions": len(value), "vocabulary_width": width},
                )
            try:
                number = float(item)
            except (OverflowError, ValueError) as exc:
                raise SchemaDriftError(
                    "managed ESMC sequence logits must contain finite numeric values",
                    raw={"positions": len(value), "vocabulary_width": width},
                ) from exc
            if not math.isfinite(number):
                raise SchemaDriftError(
                    "managed ESMC sequence logits must contain finite values",
                    raw={"positions": len(value), "vocabulary_width": width},
                )
            normalized_row.append(number)
        result.append(normalized_row)
    return result


def derive_single_mask_llr(
    sequence_logits: list[list[float]],
    mutation: dict[str, Any],
    *,
    wild_type_token_id: int,
    alternate_token_id: int,
    mask_token_id: int,
) -> dict[str, Any]:
    """Derive an LLR from one full-vocabulary logit row using natural logs."""

    for label, token_id in (
        ("wild-type", wild_type_token_id),
        ("alternate", alternate_token_id),
        ("mask", mask_token_id),
    ):
        if isinstance(token_id, bool) or not isinstance(token_id, int) or token_id < 0:
            raise ValidationError(f"{label} token id is invalid")
    row = sequence_logits[mutation["logits_index_zero_based"]]
    if max(wild_type_token_id, alternate_token_id, mask_token_id) >= len(row):
        raise SchemaDriftError(
            "managed ESMC sequence logits do not cover the pinned tokenizer ids",
            raw={"vocabulary_width": len(row)},
        )
    wild_type_logit = row[wild_type_token_id]
    alternate_logit = row[alternate_token_id]
    llr = alternate_logit - wild_type_logit
    maximum = max(row)
    shifted_log_normalizer = math.log(math.fsum(math.exp(value - maximum) for value in row))
    wild_type_log_probability = (wild_type_logit - maximum) - shifted_log_normalizer
    alternate_log_probability = (alternate_logit - maximum) - shifted_log_normalizer
    if not all(
        math.isfinite(value)
        for value in (
            shifted_log_normalizer,
            wild_type_log_probability,
            alternate_log_probability,
            llr,
        )
    ):
        raise SchemaDriftError(
            "managed ESMC logits produce non-finite log probabilities or LLR",
            raw={
                "wild_type_logit": wild_type_logit,
                "alternate_logit": alternate_logit,
            },
        )
    return {
        "schema_version": "1.0",
        "analysis": "single-masked-residue-log-likelihood-ratio",
        "evidence_class": "model-generated-hypothesis",
        "mutation": dict(mutation),
        "masking": {
            "context_count": 1,
            "masked_positions_one_based": [mutation["position_one_based"]],
            "mask_token_id": mask_token_id,
        },
        "scoring": {
            "definition": (
                f"ln P({mutation['alternate']} | {mutation['wild_type']}"
                f"{mutation['position_one_based']} masked) - "
                f"ln P({mutation['wild_type']} | {mutation['wild_type']}"
                f"{mutation['position_one_based']} masked)"
            ),
            "log_base": "e",
            "normalization": ("log_softmax over the full returned sequence-logit vocabulary"),
            "llr_computation": "alternate_logit - wild_type_logit in one masked context",
            "wild_type_vocabulary_index": wild_type_token_id,
            "alternate_vocabulary_index": alternate_token_id,
            "wild_type_logit": wild_type_logit,
            "alternate_logit": alternate_logit,
            "wild_type_log_probability": wild_type_log_probability,
            "alternate_log_probability": alternate_log_probability,
            "log_likelihood_ratio": llr,
        },
        "interpretation": (
            "A model hypothesis, not experimental fitness, stability, activity, "
            "binding, or function."
        ),
    }

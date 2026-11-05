"""Conservative validation for ESMC, ESMFold2, and Atlas inputs."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from .constants import (
    ATLAS_BATCH_MAX_UNIQUE_HASHES,
    ATLAS_FEATURE_COUNT,
    ATLAS_FOLD_MAX_RESIDUES,
    ATLAS_PROTEIN_ALPHABET,
    ATLAS_SEARCH_MAX_RESIDUES,
    DNA_ALPHABET,
    ESMC_CONSERVATIVE_MAX_RESIDUES,
    ESMC_MANAGED_MODELS,
    ESMC_MANAGED_SAE_MODELS,
    ESMC_MAX_TOKENS,
    ESMC_PROTEIN_ALPHABET,
    ESMFOLD2_HF_MODELS,
    ESMFOLD2_MANAGED_MODELS,
    HOSTED_FOLD_BOUNDS,
    PROTEIN_ALPHABET,
    RNA_ALPHABET,
)
from .errors import ValidationError

MD5_RE = re.compile(r"^[0-9a-f]{32}$")
MSA_PAIR_KEY_RE = re.compile(r"^key=([1-9][0-9]*)$")


def _reject_unknown_fields(value: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValidationError(f"unsupported {context} fields: {', '.join(unknown)}")


def normalize_sequence(value: str) -> str:
    """Normalize one raw or single-record FASTA sequence without guessing gaps."""

    if not isinstance(value, str):
        raise ValidationError("sequence must be a string")
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if lines and lines[0].startswith(">"):
        if any(line.startswith(">") for line in lines[1:]):
            raise ValidationError("expected one FASTA record, but multiple headers were found")
        lines = lines[1:]
    if any(line.startswith(">") for line in lines):
        raise ValidationError("expected one FASTA record, but multiple headers were found")
    sequence = "".join(lines).replace(" ", "").upper()
    if not sequence:
        raise ValidationError("sequence is empty")
    return sequence


def _validate_alphabet(sequence: str, alphabet: frozenset[str], modality: str) -> None:
    invalid = sorted(set(sequence) - alphabet)
    if invalid:
        rendered = "".join(invalid[:12])
        raise ValidationError(f"{modality} sequence contains unsupported symbols: {rendered}")


def _validate_protein_sequence(
    value: str,
    *,
    alphabet: frozenset[str],
    max_residues: int | None = None,
) -> str:
    sequence = normalize_sequence(value)
    _validate_alphabet(sequence, alphabet, "protein")
    if max_residues is not None and len(sequence) > max_residues:
        raise ValidationError(
            f"protein sequence has {len(sequence)} residues; conservative limit is {max_residues}"
        )
    return sequence


def validate_protein_sequence(value: str, *, max_residues: int | None = None) -> str:
    return _validate_protein_sequence(
        value,
        alphabet=PROTEIN_ALPHABET,
        max_residues=max_residues,
    )


def validate_esmc_sequence(value: str) -> str:
    return _validate_protein_sequence(
        value,
        alphabet=ESMC_PROTEIN_ALPHABET,
        max_residues=ESMC_CONSERVATIVE_MAX_RESIDUES,
    )


def _validate_managed_esmc_encode_sequence(value: Any) -> str:
    sequence = normalize_sequence(value)
    _validate_alphabet(sequence, ESMC_PROTEIN_ALPHABET | frozenset("_"), "protein")
    if len(sequence) > ESMC_CONSERVATIVE_MAX_RESIDUES:
        raise ValidationError(
            "managed ESMC encode sequence exceeds the "
            f"{ESMC_CONSERVATIVE_MAX_RESIDUES}-residue conservative limit"
        )
    return sequence


_ESMC_MANAGED_MAX_HIDDEN_LAYER = {
    "esmc-300m-2024-12": 30,
    "esmc-600m-2024-12": 36,
    "esmc-6b-2024-12": 80,
}
# Exact pinned ESMC sequence vocabulary has 33 entries, IDs 0 through 32.
_ESMC_SEQUENCE_TOKEN_MAX = 32
_ESMC_LOGITS_BOOLEAN_FIELDS = (
    "sequence",
    "return_embeddings",
    "return_mean_embedding",
    "return_mean_hidden_states",
    "return_hidden_states",
)
_ESMC_LOGITS_CONFIG_DEFAULTS: dict[str, Any] = {
    "sequence": False,
    "return_embeddings": False,
    "return_mean_embedding": False,
    "return_mean_hidden_states": False,
    "return_hidden_states": False,
    "ith_hidden_layer": -1,
    "sae_config": None,
}


def _validate_managed_esmc_tokens(value: Any) -> list[int]:
    if not isinstance(value, list) or len(value) < 3:
        raise ValidationError("managed ESMC inputs.sequence must contain BOS, residues, and EOS")
    if len(value) > ESMC_MAX_TOKENS:
        raise ValidationError(
            f"managed ESMC inputs.sequence exceeds the {ESMC_MAX_TOKENS}-token limit"
        )
    if any(
        isinstance(token, bool)
        or not isinstance(token, int)
        or not 0 <= token <= _ESMC_SEQUENCE_TOKEN_MAX
        for token in value
    ):
        raise ValidationError(
            "managed ESMC inputs.sequence token IDs must be integers between 0 and 32"
        )
    if value[0] != 0 or value[-1] != 2:
        raise ValidationError("managed ESMC inputs.sequence must use pinned BOS 0 and EOS 2")
    if any(token in {0, 2} for token in value[1:-1]):
        raise ValidationError("managed ESMC inputs.sequence cannot contain interior BOS or EOS")
    return list(value)


def _validate_managed_esmc_logits_config(value: Any, *, model: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("managed ESMC logits_config must be an object")
    _reject_unknown_fields(
        value,
        {*_ESMC_LOGITS_BOOLEAN_FIELDS, "ith_hidden_layer", "sae_config"},
        "managed ESMC logits_config",
    )
    result = {**_ESMC_LOGITS_CONFIG_DEFAULTS, **value}
    for field in _ESMC_LOGITS_BOOLEAN_FIELDS:
        if not isinstance(result[field], bool):
            raise ValidationError(f"managed ESMC logits_config.{field} must be boolean")

    layer = result["ith_hidden_layer"]
    if isinstance(layer, bool) or not isinstance(layer, int) or layer < -1:
        raise ValidationError("managed ESMC ith_hidden_layer must be -1 or a nonnegative integer")
    maximum = _ESMC_MANAGED_MAX_HIDDEN_LAYER[model]
    if layer > maximum:
        raise ValidationError(f"managed ESMC ith_hidden_layer exceeds layer {maximum} for {model}")
    requests_hidden_states = bool(
        result["return_hidden_states"] or result["return_mean_hidden_states"]
    )
    if layer >= 0 and not requests_hidden_states:
        raise ValidationError(
            "managed ESMC ith_hidden_layer requires hidden-state output to be enabled"
        )
    if model == "esmc-6b-2024-12" and requests_hidden_states and layer == -1:
        raise ValidationError("managed ESMC-6B hidden states require one explicit ith_hidden_layer")
    result["sae_config"] = _validate_managed_esmc_sae_config(result["sae_config"], model=model)
    if (
        not any(result[field] for field in _ESMC_LOGITS_BOOLEAN_FIELDS)
        and result["sae_config"] is None
    ):
        raise ValidationError("managed ESMC logits_config must request at least one output")
    return result


def _validate_managed_esmc_sae_config(value: Any, *, model: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValidationError("managed ESMC sae_config must be an object or null")
    _reject_unknown_fields(value, {"models", "normalize_features"}, "ESMC sae_config")
    models = value.get("models")
    if (
        not isinstance(models, list)
        or not models
        or any(not isinstance(sae_model, str) or not sae_model for sae_model in models)
    ):
        raise ValidationError("managed ESMC sae_config.models must be a non-empty string list")
    if len(models) != len(set(models)):
        raise ValidationError("managed ESMC sae_config.models must not contain duplicates")
    unsupported = sorted(set(models) - set(ESMC_MANAGED_SAE_MODELS))
    if unsupported:
        raise ValidationError("unsupported managed ESMC SAE model IDs: " + ", ".join(unsupported))
    mismatched = sorted(
        sae_model for sae_model in models if not sae_model.startswith(f"{model}-sae-")
    )
    if mismatched:
        raise ValidationError(
            f"managed ESMC SAE model IDs must match base model {model}: " + ", ".join(mismatched)
        )
    normalize_features = value.get("normalize_features", True)
    if not isinstance(normalize_features, bool):
        raise ValidationError("managed ESMC sae_config.normalize_features must be boolean")
    if normalize_features and any("300m" in sae_model.lower() for sae_model in models):
        raise ValidationError(
            "managed ESMC 300M SAE models require normalize_features=false "
            "for compatibility with the pinned official SDK"
        )
    return {"models": list(models), "normalize_features": normalize_features}


def _copy_potential_sequence_of_concern(payload: Mapping[str, Any], result: dict[str, Any]) -> None:
    if "potential_sequence_of_concern" not in payload:
        return
    value = payload["potential_sequence_of_concern"]
    if not isinstance(value, bool):
        raise ValidationError("potential_sequence_of_concern must be boolean")
    result["potential_sequence_of_concern"] = value


def validate_managed_esmc_request(endpoint: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one managed ESMC wire request before submission."""

    if endpoint not in {"encode", "logits"}:
        raise ValidationError("managed ESMC request endpoint must be encode or logits")
    if not isinstance(payload, Mapping):
        raise ValidationError("managed ESMC request must be an object")
    model = payload.get("model")
    if model not in ESMC_MANAGED_MODELS:
        raise ValidationError(f"{endpoint} requires an exact supported managed model ID")

    if endpoint == "encode":
        _reject_unknown_fields(
            payload,
            {"model", "inputs", "potential_sequence_of_concern"},
            "managed ESMC encode request",
        )
        inputs = payload.get("inputs")
        if not isinstance(inputs, Mapping):
            raise ValidationError("managed ESMC encode inputs must be an object")
        _reject_unknown_fields(inputs, {"sequence"}, "managed ESMC encode inputs")
        result = {
            "model": model,
            "inputs": {"sequence": _validate_managed_esmc_encode_sequence(inputs.get("sequence"))},
        }
        _copy_potential_sequence_of_concern(payload, result)
        return result

    _reject_unknown_fields(
        payload,
        {"model", "inputs", "logits_config", "potential_sequence_of_concern"},
        "managed ESMC logits request",
    )
    inputs = payload.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ValidationError("managed ESMC logits inputs must be an object")
    _reject_unknown_fields(inputs, {"sequence"}, "managed ESMC logits inputs")
    result = {
        "model": model,
        "inputs": {"sequence": _validate_managed_esmc_tokens(inputs.get("sequence"))},
        "logits_config": _validate_managed_esmc_logits_config(
            payload.get("logits_config"), model=model
        ),
    }
    _copy_potential_sequence_of_concern(payload, result)
    return result


def validate_atlas_search_sequence(value: str) -> str:
    return _validate_protein_sequence(
        value,
        alphabet=ATLAS_PROTEIN_ALPHABET,
        max_residues=ATLAS_SEARCH_MAX_RESIDUES,
    )


def validate_atlas_fold_sequence(value: str) -> str:
    return _validate_protein_sequence(
        value,
        alphabet=ATLAS_PROTEIN_ALPHABET,
        max_residues=ATLAS_FOLD_MAX_RESIDUES,
    )


def sequence_md5(
    value: str,
    *,
    provider: Literal["protein", "esmc", "atlas"] = "protein",
) -> str:
    """Hash a normalized sequence after a closed, provider-specific alphabet check."""

    alphabets = {
        "protein": PROTEIN_ALPHABET,
        "esmc": ESMC_PROTEIN_ALPHABET,
        "atlas": ATLAS_PROTEIN_ALPHABET,
    }
    try:
        alphabet = alphabets[provider]
    except KeyError as error:
        raise ValidationError(f"unsupported sequence MD5 provider: {provider}") from error
    sequence = _validate_protein_sequence(value, alphabet=alphabet)
    return hashlib.md5(sequence.encode("ascii"), usedforsecurity=False).hexdigest()


def validate_md5(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("protein hash must be a lowercase 32-character MD5 digest")
    normalized = value.strip().lower()
    if not MD5_RE.fullmatch(normalized):
        raise ValidationError("protein hash must be a lowercase 32-character MD5 digest")
    return normalized


def validate_feature_index(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("feature index must be an integer")
    if not 0 <= value < ATLAS_FEATURE_COUNT:
        raise ValidationError(f"feature index must be between 0 and {ATLAS_FEATURE_COUNT - 1}")
    return value


def validate_batch_hashes(values: Sequence[str]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ValidationError("protein_hashes must be a sequence of MD5 strings")
    normalized = [validate_md5(value) for value in values]
    unique = list(dict.fromkeys(normalized))
    if not unique:
        raise ValidationError("protein_hashes must contain at least one hash")
    if len(unique) > ATLAS_BATCH_MAX_UNIQUE_HASHES:
        raise ValidationError(
            f"Atlas accepts at most {ATLAS_BATCH_MAX_UNIQUE_HASHES} unique hashes per batch"
        )
    return unique


def _number_in_range(name: str, value: Any, low: float, high: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be numeric")
    if not low <= value <= high:
        raise ValidationError(f"{name} must be within [{low}, {high}]")


def validate_hosted_fold_config(
    config: Mapping[str, Any], *, endpoint: str | None = None
) -> dict[str, Any]:
    allowed = {
        "include_distogram",
        "include_pae",
        "include_pair_chains_iptm",
        "include_embeddings",
        *HOSTED_FOLD_BOUNDS.keys(),
    }
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ValidationError(f"unsupported hosted folding parameters: {', '.join(unknown)}")
    if endpoint not in {None, "fold", "fold_all_atom"}:
        raise ValidationError("hosted folding endpoint must be fold or fold_all_atom")
    result = dict(config)
    for name in (
        "include_distogram",
        "include_pae",
        "include_pair_chains_iptm",
        "include_embeddings",
    ):
        if name in result and not isinstance(result[name], bool):
            raise ValidationError(f"{name} must be boolean")
    for name, bounds in HOSTED_FOLD_BOUNDS.items():
        if name not in result or (name == "msa_max_depth" and result[name] is None):
            continue
        _number_in_range(name, result[name], *bounds)
        if name in {"num_loops", "num_sampling_steps", "msa_max_depth"} and not isinstance(
            result[name], int
        ):
            raise ValidationError(f"{name} must be an integer")
    return result


def validate_local_fold_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the pinned ESMFold2InputBuilder.fold keyword contract."""

    allowed = {
        "num_loops",
        "num_sampling_steps",
        "num_diffusion_samples",
        "seed",
        "noise_scale",
        "step_scale",
        "max_inference_sigma",
        "lm_mask_pct",
        "early_exit",
        "lm_dropout",
        "msa_max_depth",
        "msa_column_mask_rate",
        "complex_id",
    }
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ValidationError(f"unsupported local folding parameters: {', '.join(unknown)}")
    result = dict(config)
    for name in ("num_loops", "num_sampling_steps", "num_diffusion_samples"):
        if name not in result:
            continue
        value = result[name]
        minimum = 0 if name == "num_loops" else 1
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValidationError(f"{name} must be an integer at least {minimum}")
    if (
        "seed" in result
        and result["seed"] is not None
        and (isinstance(result["seed"], bool) or not isinstance(result["seed"], int))
    ):
        raise ValidationError("seed must be an integer or null")
    for name in ("noise_scale", "step_scale", "max_inference_sigma"):
        if name not in result or result[name] is None:
            continue
        value = result[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValidationError(f"{name} must be a finite number or null")
    for name in ("lm_mask_pct", "lm_dropout", "msa_column_mask_rate"):
        if name not in result or result[name] is None:
            continue
        _number_in_range(name, result[name], 0.0, 1.0)
    if "early_exit" in result and not isinstance(result["early_exit"], bool):
        raise ValidationError("early_exit must be boolean")
    if "msa_max_depth" in result and result["msa_max_depth"] is not None:
        value = result["msa_max_depth"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValidationError("msa_max_depth must be a positive integer or null")
    if "complex_id" in result and (
        not isinstance(result["complex_id"], str) or not result["complex_id"].strip()
    ):
        raise ValidationError("complex_id must be a non-empty string")
    return result


def validate_fold_config(
    config: Mapping[str, Any], *, model: str, endpoint: str | None = None
) -> dict[str, Any]:
    if model in ESMFOLD2_MANAGED_MODELS:
        return validate_hosted_fold_config(config, endpoint=endpoint)
    if model in ESMFOLD2_HF_MODELS:
        return validate_local_fold_config(config)
    raise ValidationError(f"unsupported ESMFold2 model: {model}")


def _validate_managed_sequence_fold_msa(msa: Any, sequence: str) -> dict[str, Any]:
    """Validate the serialized sequence ``/fold`` MSA used by the pinned SDK."""

    if not isinstance(msa, Mapping):
        raise ValidationError("sequence fold MSA must be null or an object")
    if "|" in sequence:
        raise ValidationError("sequence fold MSA is supported only for a single protein chain")
    _validate_msa(msa, sequence, allow_headers=True)
    result = dict(msa)
    # This top-level MSA is necessarily single-chain, so cross-chain taxonomy
    # pairing cannot apply. Keep the direct managed request on its documented
    # sequences/deletions surface instead of forwarding arbitrary metadata.
    # All-atom per-chain MSAs retain headers where pairing is meaningful.
    result.pop("headers", None)
    return result


def _validate_managed_sequence_fold_sequence(value: Any) -> str:
    sequence = normalize_sequence(value)
    chains = sequence.split("|")
    if any(not chain for chain in chains):
        raise ValidationError("sequence fold chains must be non-empty and separated by one pipe")
    for chain in chains:
        _validate_alphabet(chain, PROTEIN_ALPHABET, "protein")
    return "|".join(chains)


def validate_managed_fold_request(endpoint: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one managed ESMFold2 wire request before submission."""

    if endpoint not in {"fold", "fold_all_atom"}:
        raise ValidationError("managed fold request endpoint must be fold or fold_all_atom")
    if not isinstance(payload, Mapping):
        raise ValidationError("managed fold request must be an object")
    model = payload.get("model")
    if model not in ESMFOLD2_MANAGED_MODELS:
        raise ValidationError(f"{endpoint} requires an exact supported managed model ID")

    structural_fields = (
        {"model", "sequence", "msa", "potential_sequence_of_concern"}
        if endpoint == "fold"
        else {
            "model",
            "sequence",
            "msa",
            "all_atom_input",
            "potential_sequence_of_concern",
        }
    )
    config = {key: value for key, value in payload.items() if key not in structural_fields}
    normalized_config = validate_fold_config(config, model=model, endpoint=endpoint)

    result = dict(payload)
    if endpoint == "fold":
        result["sequence"] = _validate_managed_sequence_fold_sequence(payload.get("sequence"))
        msa = payload.get("msa")
        if msa is not None:
            if model == "esmfold2-fast-2026-05":
                raise ValidationError(
                    "ESMFold2-Fast is single-sequence only and does not accept MSA conditioning"
                )
            result["msa"] = _validate_managed_sequence_fold_msa(msa, result["sequence"])
    else:
        all_atom_input = payload.get("all_atom_input")
        sequence = payload.get("sequence")
        msa = payload.get("msa")
        if all_atom_input is not None and (sequence is not None or msa is not None):
            raise ValidationError(
                "fold_all_atom accepts either all_atom_input or sequence with optional MSA, not both"
            )
        if all_atom_input is not None:
            if not isinstance(all_atom_input, Mapping):
                raise ValidationError("fold_all_atom all_atom_input must be an object or null")
            result["all_atom_input"] = validate_fold_input(all_atom_input, model=model)
        else:
            if sequence is None:
                raise ValidationError("fold_all_atom requires either all_atom_input or a sequence")
            result["sequence"] = _validate_managed_sequence_fold_sequence(sequence)
            if msa is not None:
                if model == "esmfold2-fast-2026-05":
                    raise ValidationError(
                        "ESMFold2-Fast is single-sequence only and does not accept MSA conditioning"
                    )
                result["msa"] = _validate_managed_sequence_fold_msa(msa, result["sequence"])

    for key in config:
        result[key] = normalized_config[key]
    _copy_potential_sequence_of_concern(payload, result)
    return result


def _validate_chain_ids(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    ids = [raw] if isinstance(raw, str) else raw
    if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x for x in ids):
        raise ValidationError("each entity id must be a non-empty string or list of strings")
    if len(ids) != len(set(ids)):
        raise ValidationError("an entity cannot repeat a chain id")
    return ids


def _validate_msa(
    msa: Any,
    sequence: str,
    *,
    allow_headers: bool = True,
    require_insertions_removed: bool = False,
    max_depth: int | None = None,
) -> None:
    if not isinstance(msa, Mapping) or not isinstance(msa.get("sequences"), list):
        raise ValidationError("MSA must use the SDK state shape with a sequences list")
    allowed = {"sequences", "deletions"}
    if allow_headers:
        allowed.add("headers")
    _reject_unknown_fields(msa, allowed, "MSA")
    rows = msa["sequences"]
    if not rows or any(not isinstance(row, str) or not row for row in rows):
        raise ValidationError("MSA sequences must be non-empty strings")
    if max_depth is not None:
        if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 1:
            raise ValidationError("MSA maximum depth must be a positive integer")
        if len(rows) > max_depth:
            raise ValidationError(f"MSA depth exceeds the workflow maximum of {max_depth}")
    if any(re.search(r"[^A-Za-z.\-]", row) for row in rows):
        raise ValidationError("MSA rows contain unsupported alignment symbols")
    if require_insertions_removed and any(
        character == "." or character.islower() for row in rows for character in row
    ):
        raise ValidationError(
            "this workflow requires MSA.from_a3m(..., remove_insertions=True) before validation"
        )

    # A3M lowercase residues and dots are insertions, not alignment columns.
    # Raw row strings may therefore have different lengths even though they
    # describe the same number of match columns. This mirrors the pinned SDK's
    # ``is_a3m_insertion`` / ``msa_to_res_type_and_deletions`` semantics.
    match_rows = [
        "".join(character for character in row if character != "." and not character.islower())
        for row in rows
    ]
    match_width = len(match_rows[0])
    if match_width == 0 or any(len(row) != match_width for row in match_rows):
        raise ValidationError("all MSA rows must have the same aligned length in A3M match columns")
    query = match_rows[0].replace("-", "").upper()
    if query != sequence:
        raise ValidationError("the ungapped MSA query must match its chain sequence")
    headers = msa.get("headers")
    if headers is not None and (
        not isinstance(headers, list)
        or len(headers) != len(rows)
        or any(not isinstance(header, str) for header in headers)
    ):
        raise ValidationError("MSA headers must be a string list matching MSA depth")
    deletions = msa.get("deletions")
    if deletions is not None:
        if (
            not isinstance(deletions, list)
            or len(deletions) != len(rows)
            or any(not isinstance(row, list) or len(row) != match_width for row in deletions)
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                for row in deletions
                for value in row
            )
        ):
            raise ValidationError(
                "MSA deletions must be a nonnegative finite numeric matrix matching "
                "the A3M match-column shape"
            )


def _paired_msa_key(header: str, *, chain_id: str, row_index: int) -> str | None:
    key_tokens = [token for token in header.split() if token.startswith("key=")]
    if len(key_tokens) > 1:
        raise ValidationError(
            f"paired MSA chain {chain_id} row {row_index} has more than one key token"
        )
    if not key_tokens:
        if "key=" in header:
            raise ValidationError(
                f"paired MSA chain {chain_id} row {row_index} has a non-standalone key token"
            )
        return None
    match = MSA_PAIR_KEY_RE.fullmatch(key_tokens[0])
    if match is None:
        raise ValidationError(
            f"paired MSA chain {chain_id} row {row_index} key must be "
            "key=<positive-decimal-taxonomy-id>"
        )
    return match.group(1)


def _validate_paired_msa_headers(headers_by_chain: Mapping[str, list[str]]) -> None:
    if len(headers_by_chain) < 2:
        raise ValidationError("paired MSA validation requires MSAs for at least two chains")

    chains_by_key: dict[str, set[str]] = {}
    for chain_id, headers in headers_by_chain.items():
        if not headers:
            raise ValidationError(f"paired MSA chain {chain_id} requires headers")
        if _paired_msa_key(headers[0], chain_id=chain_id, row_index=0) is not None:
            raise ValidationError(
                f"paired MSA chain {chain_id} query row must not have a key token"
            )

        seen_keys: set[str] = set()
        for row_index, header in enumerate(headers[1:], start=1):
            key = _paired_msa_key(header, chain_id=chain_id, row_index=row_index)
            if key is None:
                continue
            if key in seen_keys:
                raise ValidationError(f"paired MSA chain {chain_id} repeats taxonomy key={key}")
            seen_keys.add(key)
            chains_by_key.setdefault(key, set()).add(chain_id)

    if not any(len(chain_ids) >= 2 for chain_ids in chains_by_key.values()):
        raise ValidationError(
            "paired MSA input requires at least one exact taxonomy key shared across chain MSAs"
        )


def _validate_modifications(entity: Mapping[str, Any], sequence_length: int) -> None:
    modifications = entity.get("modifications")
    if modifications is None:
        return
    if not isinstance(modifications, list):
        raise ValidationError("modifications must be a list")
    for modification in modifications:
        if not isinstance(modification, Mapping):
            raise ValidationError("each modification must be an object")
        _reject_unknown_fields(modification, {"position", "ccd"}, "modification")
        position = modification.get("position")
        ccd = modification.get("ccd")
        if isinstance(position, bool) or not isinstance(position, int):
            raise ValidationError("modification position must be a zero-based integer")
        if not 0 <= position < sequence_length:
            raise ValidationError("modification position is outside its sequence")
        if not isinstance(ccd, str) or not ccd.strip():
            raise ValidationError("modification ccd must be a non-empty string")


def _nonnegative_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{context} must be a nonnegative integer")
    return value


def _validate_residue_reference(
    chain_id: Any,
    residue_index: Any,
    *,
    chain_lengths: Mapping[str, int | None],
    context: str,
) -> tuple[str, int]:
    if not isinstance(chain_id, str) or chain_id not in chain_lengths:
        raise ValidationError(f"{context} references an unknown chain id")
    index = _nonnegative_int(residue_index, f"{context} residue index")
    length = chain_lengths[chain_id]
    if length is not None and index >= length:
        raise ValidationError(f"{context} residue index is outside chain {chain_id}")
    return chain_id, index


def _validate_pocket(value: Any, *, chain_lengths: Mapping[str, int | None]) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise ValidationError("pocket conditioning must be an object")
    _reject_unknown_fields(value, {"binder_chain_id", "contacts"}, "pocket")
    binder_chain_id = value.get("binder_chain_id")
    if not isinstance(binder_chain_id, str) or binder_chain_id not in chain_lengths:
        raise ValidationError("pocket binder_chain_id must reference an input chain")
    contacts = value.get("contacts")
    if not isinstance(contacts, list) or not contacts:
        raise ValidationError("pocket contacts must be a non-empty list")
    for contact in contacts:
        if not isinstance(contact, (list, tuple)) or len(contact) != 2:
            raise ValidationError("each pocket contact must be [chain_id, residue_index]")
        _validate_residue_reference(
            contact[0],
            contact[1],
            chain_lengths=chain_lengths,
            context="pocket contact",
        )


def _validate_distogram_conditioning(
    value: Any, *, chain_lengths: Mapping[str, int | None]
) -> None:
    if value is None:
        return
    if not isinstance(value, list) or not value:
        raise ValidationError("distogram_conditioning must be a non-empty list")
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise ValidationError("each distogram conditioning entry must be an object")
        _reject_unknown_fields(item, {"chain_id", "distogram"}, "distogram conditioning")
        chain_id = item.get("chain_id")
        if not isinstance(chain_id, str) or chain_id not in chain_lengths:
            raise ValidationError("distogram conditioning references an unknown chain id")
        if chain_id in seen:
            raise ValidationError("distogram conditioning repeats a chain id")
        seen.add(chain_id)
        length = chain_lengths[chain_id]
        if length is None:
            raise ValidationError("distogram conditioning requires a sequence-based chain")
        matrix = item.get("distogram")
        if (
            not isinstance(matrix, list)
            or len(matrix) != length
            or any(not isinstance(row, list) or len(row) != length for row in matrix)
            or any(
                isinstance(number, bool)
                or not isinstance(number, (int, float))
                or not math.isfinite(number)
                or number < 0
                for row in matrix
                for number in row
            )
        ):
            raise ValidationError(
                f"distogram for chain {chain_id} must be a finite nonnegative {length}x{length} matrix"
            )


def _validate_covalent_bonds(value: Any, *, chain_lengths: Mapping[str, int | None]) -> None:
    if value is None:
        return
    if not isinstance(value, list) or not value:
        raise ValidationError("covalent_bonds must be a non-empty list")
    required = {
        "chain_id1",
        "res_idx1",
        "atom_idx1",
        "chain_id2",
        "res_idx2",
        "atom_idx2",
    }
    for bond in value:
        if not isinstance(bond, Mapping):
            raise ValidationError("each covalent bond must be an object")
        _reject_unknown_fields(bond, required, "covalent bond")
        missing = sorted(required - set(bond))
        if missing:
            raise ValidationError(f"covalent bond is missing: {', '.join(missing)}")
        _validate_residue_reference(
            bond["chain_id1"],
            bond["res_idx1"],
            chain_lengths=chain_lengths,
            context="covalent bond endpoint 1",
        )
        _validate_residue_reference(
            bond["chain_id2"],
            bond["res_idx2"],
            chain_lengths=chain_lengths,
            context="covalent bond endpoint 2",
        )
        _nonnegative_int(bond["atom_idx1"], "covalent bond endpoint 1 atom index")
        _nonnegative_int(bond["atom_idx2"], "covalent bond endpoint 2 atom index")


def validate_fold_input(
    payload: Mapping[str, Any],
    *,
    model: str,
    require_msa: bool = False,
    require_msa_insertions_removed: bool = False,
    require_paired_msa_keys: bool = False,
    msa_max_depth: int | None = None,
) -> dict[str, Any]:
    """Validate the SDK's serialized all-atom input shape.

    This intentionally validates only stable, documented fields. It does not
    invent a universal sequence-length cap for ESMFold2.
    """

    if model not in {*ESMFOLD2_MANAGED_MODELS, *ESMFOLD2_HF_MODELS}:
        raise ValidationError(f"unsupported ESMFold2 model: {model}")
    if not isinstance(payload, Mapping):
        raise ValidationError("fold input must be an object")
    if msa_max_depth is not None and (
        isinstance(msa_max_depth, bool) or not isinstance(msa_max_depth, int) or msa_max_depth < 1
    ):
        raise ValidationError("MSA maximum depth must be a positive integer")
    _reject_unknown_fields(
        payload,
        {"sequences", "pocket", "distogram_conditioning", "covalent_bonds"},
        "fold input",
    )
    entities = payload.get("sequences")
    if not isinstance(entities, list) or not entities:
        raise ValidationError("fold input requires a non-empty sequences list")

    seen_ids: set[str] = set()
    chain_lengths: dict[str, int | None] = {}
    has_msa = False
    paired_msa_headers: dict[str, list[str]] = {}
    normalized_entities: list[dict[str, Any]] = []
    for entity in entities:
        if not isinstance(entity, Mapping):
            raise ValidationError("each fold entity must be an object")
        entity_type = entity.get("type")
        if entity_type not in {"protein", "dna", "rna", "ligand"}:
            raise ValidationError(f"unsupported fold modality: {entity_type!r}")
        entity_allowed = {
            "ligand": {"type", "id", "smiles", "ccd"},
            "dna": {"type", "id", "sequence", "modifications"},
            "protein": {"type", "id", "sequence", "modifications", "msa"},
            # The public managed schema omits RNA MSA, while the pinned SDK
            # serializer emits msa:null. Accept that compatibility sentinel and
            # strip it for managed requests; local SDK routes may use RNA MSA.
            "rna": {"type", "id", "sequence", "modifications", "msa"},
        }[entity_type]
        _reject_unknown_fields(entity, entity_allowed, f"{entity_type} entity")
        ids = _validate_chain_ids(entity.get("id"))
        if ids is None and model in ESMFOLD2_HF_MODELS:
            raise ValidationError("local ESMFold2 entities require an explicit chain id")
        if ids is not None:
            duplicates = seen_ids.intersection(ids)
            if duplicates:
                raise ValidationError(f"duplicate chain id: {min(duplicates)}")
            seen_ids.update(ids)

        copy = dict(entity)
        if entity_type == "ligand":
            smiles = entity.get("smiles")
            ccd = entity.get("ccd")
            has_smiles = isinstance(smiles, str) and bool(smiles.strip())
            has_ccd = (
                isinstance(ccd, list)
                and bool(ccd)
                and all(isinstance(item, str) and item.strip() for item in ccd)
            )
            if has_smiles == has_ccd:
                raise ValidationError("ligand requires exactly one of non-empty smiles or ccd")
            if entity.get("msa") is not None:
                raise ValidationError("ligands do not support MSA input")
            ligand_length = len(ccd) if has_ccd else None
            if ids is not None:
                for chain_id in ids:
                    chain_lengths[chain_id] = ligand_length
        else:
            sequence = normalize_sequence(entity.get("sequence", ""))
            alphabet = {
                "protein": PROTEIN_ALPHABET,
                "dna": DNA_ALPHABET,
                "rna": RNA_ALPHABET,
            }[entity_type]
            _validate_alphabet(sequence, alphabet, entity_type)
            copy["sequence"] = sequence
            if ids is not None:
                for chain_id in ids:
                    chain_lengths[chain_id] = len(sequence)
            _validate_modifications(entity, len(sequence))
            msa = entity.get("msa")
            if msa is not None:
                if entity_type == "rna" and model in ESMFOLD2_MANAGED_MODELS:
                    raise ValidationError("managed rna entities do not support non-null MSA input")
                if entity_type not in {"protein", "rna"}:
                    raise ValidationError(f"{entity_type} does not support MSA input")
                _validate_msa(
                    msa,
                    sequence,
                    allow_headers=True,
                    require_insertions_removed=require_msa_insertions_removed,
                    max_depth=msa_max_depth,
                )
                # Preserve headers for both managed and local routes. The exact
                # official serializer sends them, and paired complex MSAs use
                # their key=<taxonomy_id> tokens for cross-chain pairing.
                copy["msa"] = dict(msa)
                has_msa = True
                if require_paired_msa_keys and entity_type == "protein":
                    if ids is None or len(ids) != 1:
                        raise ValidationError(
                            "paired MSA validation requires one explicit chain id per protein input"
                        )
                    headers = msa.get("headers")
                    paired_msa_headers[ids[0]] = list(headers) if isinstance(headers, list) else []
            elif require_paired_msa_keys and entity_type == "protein":
                raise ValidationError(
                    "paired MSA validation requires an MSA for every protein input"
                )
            elif entity_type == "rna" and model in ESMFOLD2_MANAGED_MODELS:
                copy.pop("msa", None)
        normalized_entities.append(copy)

    if require_paired_msa_keys:
        _validate_paired_msa_headers(paired_msa_headers)

    _validate_pocket(payload.get("pocket"), chain_lengths=chain_lengths)
    _validate_distogram_conditioning(
        payload.get("distogram_conditioning"), chain_lengths=chain_lengths
    )
    _validate_covalent_bonds(payload.get("covalent_bonds"), chain_lengths=chain_lengths)

    is_fast = model in {"esmfold2-fast-2026-05", "biohub/ESMFold2-Fast"}
    if is_fast and has_msa:
        raise ValidationError(
            "ESMFold2-Fast is single-sequence only and does not accept MSA conditioning"
        )
    if require_msa and not has_msa:
        raise ValidationError("this full-model workflow requires an MSA, but none was provided")

    result = dict(payload)
    result["sequences"] = normalized_entities
    return result


def validate_esmc_model(model: str) -> str:
    if model not in ESMC_MANAGED_MODELS:
        raise ValidationError(f"unsupported managed ESMC model: {model}")
    return model

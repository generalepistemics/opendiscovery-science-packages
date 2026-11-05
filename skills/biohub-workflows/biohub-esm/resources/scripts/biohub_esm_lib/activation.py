"""Deterministic intent classifier used only for activation regression tests."""

from __future__ import annotations

import re


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def select_skill(prompt: str) -> str | None:
    text = prompt.strip()
    if not text:
        return None
    protein_context = _has(
        text,
        (
            r"\b(proteins?|peptides?|amino[- ]acids?|residues?|gb1|biomolecular|"
            r"biohub|esm)\b"
        ),
    )
    if _has(
        text, r"\b(boltz|alphafold|clustal|blast|gpt|language atlas|road atlas)\b"
    ) and not _has(text, r"\b(biohub|esmc|esmfold2|esm atlas|esm)\b"):
        return None
    if _has(
        text,
        r"\b(auth|authenticate|api key|credentials?|install|setup|preflight|ready|readiness|rate limit|credits?)\b",
    ) and _has(text, r"\b(biohub|esm|modal|hugging face|atlas)\b"):
        return "biohub-esm-setup"
    if _has(
        text,
        r"\b(esm atlas|atlas api|atlas cluster|protein hash|md5|feature catalog|anonymous s3)\b",
    ) or (
        _has(text, r"\b(similar|related|discover|search|nearest|neighbors?)\b|\bmost like\b")
        and _has(text, r"\b(proteins?|sae|functional signature|clusters?)\b")
    ):
        return "esm-atlas"
    if (
        _has(text, r"\b(esmfold2|all-atom|plddt|pae|iptm)\b")
        or (
            _has(text, r"\bptm\b")
            and protein_context
            and _has(text, r"\b(fold|folding|structure|confidence|prediction)\b")
        )
        or (_has(text, r"\b(fold|folding)\b") and protein_context)
    ) or (
        _has(text, r"\b(gb1|proteins?|biomolecular complex)\b")
        and (
            (
                _has(text, r"\b(show|display|visuali[sz]e|render|view|see)\b")
                and _has(text, r"\b(look|looks|shape|structure|3d)\b")
            )
            or _has(text, r"\bwhat (?:does|would)\b.*\blook like\b")
            or _has(text, r"\bpredict\b.*\bstructure\b")
        )
        or (
            _has(
                text,
                r"\b(a3m|paired msas?|covalent (?:lipid )?linker|lipid linker|modified (?:\S+ )?peptide|rna[- /]dna (?:hybrid|complex))\b",
            )
            and _has(text, r"\b(show|model|fold|predict|structure|engage|engages|engaged)\b")
        )
    ):
        return "esmfold2"
    if (
        (
            _has(text, r"\b(esmc|masked[- ]residue|mutation scoring|sae features?)\b")
            or (_has(text, r"\b(embeddings?|hidden states?|logits|entropy)\b") and protein_context)
        )
        or (
            _has(text, r"\b[a-z][1-9][0-9]{0,4}[a-z]\b")
            and _has(text, r"\b(gb1|proteins?|variants?|mutations?|substitutions?)\b")
        )
        or (
            _has(
                text,
                r"\b(explore mutations|mutational landscape|mutation[- ]tolerant|mutation hotspots?|constrained residues?)\b",
            )
            and _has(text, r"\b(proteins?|enzymes?|residues?|amino acids?|petase|gb1)\b")
        )
    ):
        return "esmc"
    if (
        protein_context
        and _has(
            text,
            r"\b(biohub esm|esm models?|which esm|private gpu|route.*compute|500 designed sequences)\b",
        )
    ) or (_has(text, r"\b(choose|pick|recommend|select|route|best)\b") and _has(text, r"\besm\b")):
        return "biohub-esm"
    return None

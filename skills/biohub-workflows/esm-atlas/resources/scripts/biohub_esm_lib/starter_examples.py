"""Deterministic validation for packaged Biohub ESM starter examples."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .activation import select_skill
from .errors import ValidationError
from .routing import RouteRequest, route_request
from .validation import (
    validate_esmc_sequence,
    validate_fold_config,
    validate_fold_input,
)

CANONICAL_AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"
EXPECTED_SEQUENCE = {
    "id": "gb1-1pga-chain-a",
    "name": "Streptococcal protein G B1 domain (GB1), RCSB PDB 1PGA chain A",
    "literal": "MTYKLILNGKTLKGETTTEAVDAATAEKVFKQYANDNGVDGEWTYDDATKTFTVTE",
    "source": {
        "title": "RCSB PDB 1PGA: B1 immunoglobulin-binding domain of streptococcal protein G",
        "reference": "https://www.rcsb.org/structure/1PGA",
        "fasta_url": "https://www.rcsb.org/fasta/entry/1PGA/display",
        "accession": "1PGA",
        "chain": "A",
        "entry_revision": "1.4",
        "snapshot_date": "2026-07-12",
        "raw_fasta_bytes": 115,
        "raw_fasta_sha256": ("a56ce69e9e80a566367b6b4b3a01a263d61e9b5c58dd55e9eb8e49a50bd6b561"),
        "usage": "Exact 56-residue chain A sequence from the experimentally determined 1PGA entry",
        "numbering": (
            "One-based residue positions on the exact 56-residue literal sequence in this contract"
        ),
    },
    "length": 56,
    "sha256": "7e859d82171047700fd3e9632f7a47eab4a39baedc8c3316d2fc62d3ce2260bb",
}
EXPECTED_PROMPTS = {
    "gb1-esmc-w43f-masked-llr": "What might W43F do to GB1?",
    "gb1-esmfold2-fast-fold": "Show me what GB1 looks like.",
    "gb1-atlas-similarity-search": "Find proteins similar to GB1.",
}
EXPECTED_ROUTES = {
    "gb1-esmc-w43f-masked-llr": {
        "skill": "esmc",
        "model": "esmc-600m-2024-12",
        "provider": "biohub-managed",
        "may_incur_cost": True,
        "confirmation_boundary": "not_required_for_managed_tutorial_scale",
        "prompt_authorizes_execution": True,
        "required_confirmation": (
            "not required; report the credits consumed with the result instead"
        ),
        "request_policy": ("exactly one managed logits request with no implicit retries"),
        "local_alternative": ("biohub/ESMC-600M at the pinned revision on user-owned compute"),
    },
    "gb1-esmfold2-fast-fold": {
        "skill": "esmfold2",
        "model": "esmfold2-fast-2026-05",
        "provider": "biohub-managed",
        "may_incur_cost": True,
        "confirmation_boundary": "not_required_for_managed_tutorial_scale",
        "prompt_authorizes_execution": True,
        "required_confirmation": (
            "not required; report the credits consumed with the result instead"
        ),
        "request_policy": "exactly one managed fold request with no implicit retries",
        "local_alternative": ("biohub/ESMFold2-Fast at the pinned revision on user-owned compute"),
    },
    "gb1-atlas-similarity-search": {
        "skill": "esm-atlas",
        "model": "not-applicable-public-data-api",
        "provider": "biohub-public-mcp",
        "may_incur_cost": False,
        "confirmation_boundary": "not_required_for_public_alpha_read",
        "prompt_authorizes_execution": True,
        "required_confirmation": "not required for the anonymous public Biohub MCP read",
        "request_policy": (
            "exactly one Biohub MCP similarity search and one structure view with zero "
            "detail follow-ups and zero script calls"
        ),
        "local_alternative": ("anonymous ESM Atlas S3 data for deliberately scoped bulk analysis"),
    },
}
EXPECTED_MANAGED_WORKFLOWS = {
    "gb1-esmc-w43f-masked-llr": (
        "Run status-only preflight first; if managed access is missing, give the user the key page from $biohub-esm-setup and resume automatically once it is configured.",
        "Resolve the natural launcher to the pinned GB1 fixture and validate its sequence, SHA-256, length, and mutation numbering without making a provider call.",
        "Validate the managed model ID, endpoint, and pinned client SDK revision, tokenize locally with the pinned SDK, and make exactly one managed logits request without implicit retries.",
        "Compute the W43F masked log-likelihood ratio with one documented masking and scoring method.",
        "Serialize the raw response, score, deterministic SVG score card, parameters, and provenance without claiming fitness, stability, or function, then display the SVG inline and note the credits consumed.",
    ),
    "gb1-esmfold2-fast-fold": (
        "Using the same resolved <python-3.12-with-pinned-esm> interpreter that will execute the request, run status-only preflight --endpoint fold first; if managed access is missing, give the user the key page from $biohub-esm-setup and resume automatically once it is configured.",
        "Resolve the natural launcher to the pinned GB1 fixture and validate its sequence, SHA-256, length, and Fast single-sequence constraints without making a provider call.",
        "Run the pinned managed-post --endpoint fold command exactly once, without implicit retries, from examples/gb1-esmfold2-fast-fold-request.json with include_pae=true and the validated Fast parameters.",
        "Write the PDB, retained presentation request, normalized confidence result, raw response, provenance, and cryptographic artifact hashes; after successful creation, call ui_show_protein_structure once with the exact query sequence and label the view as the Biohub MCP's Atlas or on-demand coordinates rather than this prediction; report a missing tool, error, or unavailable preview without switching viewers; only when the user asks to see the exact prediction file, consume presentation-request.json, open its verified absolute prediction.pdb path once with its exact retained openIntentId, retain and verify the same-task session, request predicted-confidence coloring only when ready, report pending or unavailable presentation separately, and note the credits consumed.",
    ),
}
EXPECTED_EXAMPLES = {example_id: route["skill"] for example_id, route in EXPECTED_ROUTES.items()}
EXPECTED_PRODUCTION_ROUTES = {
    "gb1-esmc-w43f-masked-llr": (
        RouteRequest(task="esmc"),
        "biohub",
        "esmc-600m-2024-12",
        "ESM_API_KEY",
    ),
    "gb1-esmfold2-fast-fold": (
        RouteRequest(task="fold"),
        "biohub",
        "esmfold2-fast-2026-05",
        "ESM_API_KEY",
    ),
    "gb1-atlas-similarity-search": (
        RouteRequest(task="atlas"),
        "biohub-mcp",
        None,
        None,
    ),
}
EXPECTED_PROVIDER_BY_PRODUCTION_ROUTE = {
    "biohub": "biohub-managed",
    "biohub-mcp": "biohub-public-mcp",
}
EXPECTED_ARTIFACTS = {
    "gb1-esmc-w43f-masked-llr": (
        {"name": "raw-response.json", "format": "JSON", "required": True},
        {
            "name": "mutation-score.json",
            "format": "JSON",
            "required": True,
            "derivation": (
                "Derive the documented masked log-likelihood ratio from the raw response, "
                "preserve both log probabilities and one-based numbering, checksum it, "
                "and include it in provenance."
            ),
        },
        {
            "name": "mutation-score.svg",
            "format": "SVG",
            "required": True,
            "derivation": (
                "Render a deterministic self-contained score card from mutation-score.json "
                "and label it as a model hypothesis rather than fitness, stability, or function."
            ),
        },
        {"name": "provenance.json", "format": "JSON", "required": True},
    ),
    "gb1-esmfold2-fast-fold": (
        {"name": "prediction.pdb", "format": "PDB", "required": True},
        {"name": "presentation-request.json", "format": "JSON", "required": True},
        {"name": "result.json", "format": "JSON", "required": True},
        {"name": "raw-response.json", "format": "JSON", "required": True},
        {"name": "provenance.json", "format": "JSON", "required": True},
    ),
    "gb1-atlas-similarity-search": (),
}
EXPECTED_ESMC_EXECUTION = {
    "request_count": 1,
    "method": "POST",
    "endpoint": "https://biohub.ai/api/v1/logits",
    "sequence": EXPECTED_SEQUENCE["literal"],
    "mutation": "W43F",
    "model": "esmc-600m-2024-12",
    "scoring_method": "masked-log-likelihood-ratio",
    "command": [
        "<python-3.12-with-pinned-esm>",
        "<skill-directory>/resources/scripts/biohub_esm.py",
        "esmc-mutation-score",
        "--sequence",
        EXPECTED_SEQUENCE["literal"],
        "--mutation",
        "W43F",
        "--model",
        "esmc-600m-2024-12",
        "--output-dir",
        "/absolute/path/gb1-esmc-w43f-masked-llr",
    ],
    "output_dir": "/absolute/path/gb1-esmc-w43f-masked-llr",
    "artifacts": [
        "raw-response.json",
        "mutation-score.json",
        "mutation-score.svg",
        "provenance.json",
    ],
    "follow_up_requests": [],
}
EXPECTED_ESMC_QUALIFICATION_RESPONSE = {
    "format": "exact-lines-v1",
    "lines": [
        (
            "ESMC input: GB1 1PGA chain A; 56 residues; mutation W43F in one-based residue "
            "numbering; sequence SHA-256 "
            "7e859d82171047700fd3e9632f7a47eab4a39baedc8c3316d2fc62d3ce2260bb."
        ),
        (
            "ESMC request: exactly one Biohub managed POST /api/v1/logits with model "
            "esmc-600m-2024-12 using ESM_API_KEY; no implicit retries."
        ),
        (
            "Mutation score formula: use one masked context and compute the alternate logit "
            "minus the wild-type logit."
        ),
        (
            "ESMC artifacts: raw-response.json, mutation-score.json, mutation-score.svg, "
            "and provenance.json with checksums."
        ),
        (
            "ESMC provenance: preserve the route, provider, endpoint, exact model ID, any "
            "managed model revision exposed, pinned ESM and Transformers SDK revisions, input "
            "digest, parameters, timestamps, raw-response and artifact checksums, masked "
            "context, both natural-log probabilities, one-based residue index, zero-based "
            "tensor index, and W43F score."
        ),
        (
            "ESMC cost: running this consumes a small number of provider credits, reported "
            "with the result. A managed request at this scale runs without a separate "
            "confirmation; Modal, self-hosted, and bulk transfers still ask first."
        ),
        (
            "Scientific status: model output is a model hypothesis, not an experimental truth, "
            "and experimental validation is required before biological interpretation."
        ),
        "No provider call or request was sent.",
    ],
}
EXPECTED_FOLD_EXECUTION = {
    "request_count": 1,
    "method": "POST",
    "endpoint": "https://biohub.ai/api/v1/fold",
    "request_file": "examples/gb1-esmfold2-fast-fold-request.json",
    "request": {
        "model": "esmfold2-fast-2026-05",
        "sequence": EXPECTED_SEQUENCE["literal"],
        "msa": None,
        "include_distogram": False,
        "include_pae": True,
        "include_pair_chains_iptm": False,
        "num_sampling_steps": 100,
        "num_loops": 20,
        "lm_dropout": 0.3,
        "lm_mask_pct": 0.1,
        "msa_max_depth": 1024,
        "msa_column_mask_rate": 0.1,
        "include_embeddings": False,
    },
    "command": [
        "<python-3.12-with-pinned-esm>",
        "<skill-directory>/resources/scripts/biohub_esm.py",
        "managed-post",
        "--endpoint",
        "fold",
        "--input",
        "<skill-directory>/resources/examples/gb1-esmfold2-fast-fold-request.json",
        "--output-dir",
        "/absolute/path/gb1-esmfold2-fast-fold",
    ],
    "output_dir": "/absolute/path/gb1-esmfold2-fast-fold",
    "offline_validation": {
        "function": "validate_fold_config",
        "model": "esmfold2-fast-2026-05",
        "endpoint": "fold",
    },
    "follow_up_requests": [],
}
EXPECTED_FOLD_QUALIFICATION_RESPONSE = {
    "format": "exact-lines-v1",
    "lines": [
        (
            "Fold input: GB1 1PGA chain A; 56 residues; sequence SHA-256 "
            "7e859d82171047700fd3e9632f7a47eab4a39baedc8c3316d2fc62d3ce2260bb; msa=null."
        ),
        (
            "Fold request: exactly one Biohub managed POST /api/v1/fold with model "
            "esmfold2-fast-2026-05 using examples/gb1-esmfold2-fast-fold-request.json; "
            "no implicit retries."
        ),
        (
            "Fold parameters: include_distogram=false; include_embeddings=false; "
            "include_pair_chains_iptm=false; num_sampling_steps=100; num_loops=20; "
            "lm_dropout=0.3; lm_mask_pct=0.1; msa_max_depth=1024; "
            "msa_column_mask_rate=0.1."
        ),
        "Fold pAE request parameter: include_pae=true.",
        (
            "Fold confidence scope: provider-native pLDDT=per-residue on the 0-1 scale; "
            "pAE=residue-pair in angstroms."
        ),
        (
            "Fold artifacts: prediction.pdb, presentation-request.json, result.json, "
            "raw-response.json, and provenance.json with checksums."
        ),
        (
            "Fold presentation: after successful artifact creation, call ui_show_protein_structure "
            "once with the exact GB1 query sequence and label the view as the Biohub MCP's "
            "Atlas or on-demand coordinates rather than this ESMFold2 prediction. A missing "
            "tool, error, or unavailable preview is reported without switching viewers. Only "
            "when the user asks to see the exact prediction file, consume the validated "
            "presentation-request.json and pass its "
            "verified absolute prediction.pdb path once to the OpenDiscovery Structure Viewer "
            "using its exact retained openIntentId. Generate a new stable ID only for a legacy artifact set "
            "without presentation-request.json. Retain the returned session within this task, "
            "verify the primary object, and request predicted-confidence coloring only when "
            "ready, labeling the coordinate B-factor field as serializer-scaled 0-100 pLDDT "
            "rather than an experimental temperature factor. If presentation is pending or "
            "unavailable, report that separately and return the checksummed artifacts without "
            "invalidating the fold."
        ),
        (
            "Fold cost: running this consumes a small number of provider credits, reported "
            "with the result. A managed request at this scale runs without a separate "
            "confirmation; Modal, self-hosted, and bulk transfers still ask first."
        ),
        (
            "Scientific status: model output is a static conformational model hypothesis, "
            "not an experimental truth, and experimental validation is required before "
            "biological interpretation."
        ),
        "No provider call or request was sent.",
    ],
}
EXPECTED_ATLAS_QUALIFICATION_RESPONSE = {
    "format": "exact-lines-v1",
    "lines": [
        (
            "Atlas authentication: ESM Atlas currently does not require a client-side "
            "API key or client authentication."
        ),
        "Atlas route: the anonymous public Biohub MCP; no plugin script call.",
        (
            "Atlas similarity-search ceiling: at most 2,048 residues; a longer sequence needs "
            "a user-chosen domain and is never clipped."
        ),
        (
            "Atlas fold ceiling: ui_show_protein_structure folds an Atlas miss of at most "
            "700 residues."
        ),
        (
            "Atlas starter search: 56-residue GB1 query; exactly one "
            "esm_atlas_search_similar_protein_clusters call with top_k=10 (up to 10 actual ranked "
            "hits) and uncharacterized_only=false."
        ),
        "Atlas execution plan: zero cluster, protein-detail, or feature-detail follow-ups.",
        (
            "Atlas presentation: exactly one ui_show_protein_structure call with the "
            "top-ranked hit's returned sequence; it opens the Mol* viewer where the host "
            "renders MCP Apps and otherwise returns a PNG preview to summarize in text."
        ),
        (
            "Atlas structure status: Atlas coordinates, on-demand folds, and previews are "
            "model hypotheses, not experimental structures or evidence; experimental "
            "validation is required."
        ),
        (
            "Atlas evidence: cite each tool called, ESM Atlas v1 through the v1alpha1 API, "
            "and CC-BY-4.0 attribution in the answer; the MCP route writes no "
            "raw-response.json, result.json, or provenance.json."
        ),
        "Atlas schema: v1alpha1 is alpha and unstable.",
        "No Atlas request was sent and no results were obtained.",
    ],
}
EXPECTED_ATLAS_EXECUTION = {
    "transport": "mcp",
    "server": "biohub",
    "request_count": 1,
    "tool": "esm_atlas_search_similar_protein_clusters",
    "arguments": {
        "sequence": EXPECTED_SEQUENCE["literal"],
        "top_k": 10,
        "uncharacterized_only": False,
    },
    "script_calls": [],
    "response_contract": {
        "maximum_hits": 10,
        "required_hit_fields": [
            "protein_accession",
            "sequence",
            "sequence_length",
            "similarity_score",
        ],
        "similarity_range": [0.0, 1.0],
        "order": "nonincreasing-similarity",
    },
    "detail_follow_up_requests": [],
    "presentation_request": {
        "condition": "non-empty search result",
        "maximum_request_count": 1,
        "tool": "ui_show_protein_structure",
        "arguments": {"sequence": "<top-ranked-hit-sequence>"},
        "resource": "ui://biohub-public/structure-viewer/v1",
        "fold_limit_residues": 700,
    },
}
EXPECTED_ATLAS_WORKFLOW = (
    "Resolve the natural launcher to the pinned GB1 fixture and validate its sequence, SHA-256, and length without a tool call.",
    "Call esm_atlas_search_similar_protein_clusters exactly once with the fixture sequence, top_k=10, and uncharacterized_only=false; make zero script calls.",
    "Return up to ten actual ranked hits in the returned order with accession, protein name, length, similarity score, and cluster size; never manufacture missing hits.",
    "Make zero cluster, protein-detail, or feature-detail follow-up calls.",
    "For a non-empty result, call ui_show_protein_structure exactly once with the top-ranked hit's returned sequence; hosts that render MCP Apps show the Mol* viewer, and other hosts get its PNG preview and a text summary.",
    "End the answer with a source line citing the tools called, ESM Atlas v1 through the v1alpha1 API, and CC-BY-4.0 attribution.",
)
EXPECTED_ATLAS_RESULTS = (
    "Up to ten actual returned hits with accession, protein name, length, similarity score, and cluster size in the returned order",
    "A Mol* view or PNG preview of the top-ranked hit, labeled as a model hypothesis",
    "A source line naming the Biohub MCP tools called, ESM Atlas v1 through the v1alpha1 API, and CC-BY-4.0 attribution",
)

EXPECTED_STRUCTURE_VIEWER_CONTRACT = {
    "viewer": "OpenDiscovery Structure Viewer",
    "unavailable_viewer_fallback": "agent-rendered-image-of-verified-artifact",
    "routing": {
        "supported_sequence": "biohub-mcp",
        "unsupported_structure": "structure-viewer",
        "exact_artifact": "structure-viewer",
        "mcp_operational_failure": "report-without-viewer-switch",
    },
    "capability": "interactive-molecular-structure-viewing",
    "request_artifact": "presentation-request.json",
    "artifact_path": "verified-absolute",
    "open_intent_field": "openIntentId",
    "open_intent_policy": "reuse-exact-emitted-value",
    "open_intent_reuse": "delivery-retry-only",
    "legacy_open_intent_policy": "generate-new-stable-only-when-request-artifact-missing",
    "open_policy": "once",
    "session_policy": "retain-returned-session-within-same-task",
    "verification": "list-primary-object",
    "style_when": "ready",
    "predicted_confidence_style": {
        "semantic": "predicted-confidence",
        "source": "coordinate-b-factor",
    },
    "timed_out_mutation": "inspect-acknowledged-state-before-retry",
    "blocked_outcomes": ["pending", "unavailable"],
    "scientific_success_independent": True,
}

# The ESMC tutorial launchers show their structure through the Biohub MCP view. An
# agent that had to satisfy an experimental-coordinate map drew its own figure
# instead, so the contract names the view and forbids a self-drawn replacement.
# The view draws chain A in blue, so the palette holds no blue.
MCP_STRUCTURE_VIEW_PALETTE = ["#D55E00", "#009E73", "#CC79A7"]
EXPECTED_MCP_STRUCTURE_VIEW_CONTRACT = {
    "tool": "ui_show_protein_structure",
    "server": "biohub",
    "calls_per_workflow": 1,
    "repeat_call": (
        "only when the user asks to see the structure again, with the same arguments; a "
        "repeated on-demand fold can return different coordinates"
    ),
    "input": (
        "one exact protein sequence of 1 to 4,000 residues; an ESM Atlas miss folds only up "
        "to 700 residues"
    ),
    "numbering": (
        "chain A; author_residue_number is the one-based position in the exact sequence "
        "passed; expected_residue is the three-letter code at that position"
    ),
    "max_highlights": 32,
    "highlight_palette": MCP_STRUCTURE_VIEW_PALETTE,
    "coordinates": (
        "a stored ESM Atlas prediction or an on-demand fold of the exact sequence; a model "
        "hypothesis, not an experimental structure"
    ),
    "presentation": (
        "hosts that render MCP Apps show the interactive Mol* viewer; every host gets the PNG "
        "preview when rendering succeeds"
    ),
    "cost": "a public Biohub MCP read; it uses no ESM_API_KEY credits",
    "on_failure": (
        "report the analysis without a structure view, and name the tool and the reason; "
        "record the planned arguments with called false, and after the Biohub MCP is "
        "connected make only that view call"
    ),
    "never": [
        "draw a structure image or a structure map with plotting, rendering, or viewer code",
        "show other coordinates, such as an experimental PDB entry, in place of the view",
    ],
    "scientific_success_independent": True,
}
MCP_STRUCTURE_VIEW_USE_CASES = ("esmc-mutation-landscape", "esmc-sae-feature-interpretation")
HIGHLIGHT_COLOR_PATTERN = re.compile(r"#[0-9A-F]{6}")
URL_PATTERN = re.compile(r"https?://[^\s\"'<>)]+")
COORDINATE_FILE_SUFFIXES = (".pdb", ".pdb.gz", ".ent", ".cif", ".cif.gz", ".bcif", ".mmtf")
EXPECTED_MCP_STRUCTURE_VIEWS = {
    "esmc-mutation-landscape": {
        "sequence": "the pinned CaPETase literal in target.sequence",
        "when": "after the runtime writes mutation-landscape.json",
        "highlight_groups": [
            {
                "label": "most constrained",
                "residues": "every position in mutation-landscape.json summary.most_constrained",
                "color": MCP_STRUCTURE_VIEW_PALETTE[0],
            },
            {
                "label": "most tolerant",
                "residues": "every position in mutation-landscape.json summary.most_tolerant",
                "color": MCP_STRUCTURE_VIEW_PALETTE[1],
            },
        ],
    },
    "esmc-sae-feature-interpretation": {
        "sequence": "the validated RCSB FASTA sequence of 2XND chain A that ESMC analyzed",
        "when": "after the rankings exist",
        "highlight_rule": (
            "For each of the top 3 maximum-activation features in rank order, highlight its 10 "
            "highest-activation residues with activation > 0.01 that no higher-ranked feature "
            "already highlights; break a tie by the lower position."
        ),
        "highlight_colors": MCP_STRUCTURE_VIEW_PALETTE,
        "record": "structure-view.json",
    },
}
# Each launcher discloses its one view in exactly this sentence. A looser substring
# check also accepted a sentence that forbade the view.
EXPECTED_MCP_STRUCTURE_VIEW_DISCLOSURES = {
    "esmc-mutation-landscape": (
        "After the runtime succeeds, the one Biohub MCP structure view in structure_view runs "
        "without asking first; it is a public read, not a managed request."
    ),
    "esmc-sae-feature-interpretation": (
        "The exact disclosed requests (one RCSB FASTA, one managed encode, one managed logits, "
        "five Atlas feature details, and one Biohub MCP structure view) then run once access is "
        "configured without asking first. Managed requests may incur cost. Report "
        "provider-returned credit or token usage when available; otherwise state that the API "
        "did not report usage or cost, and never invent an estimate."
    ),
}
EXPECTED_SAE_TARGET = {
    "name": "Mitochondrial ATP synthase F1 alpha subunit tutorial sequence",
    "pdb_id": "2XND",
    "chain_id": "A",
    "sequence_source": "https://www.rcsb.org/fasta/entry/2XND",
    "author_numbering": (
        "2XND chain A author residue number = one-based sequence position + 18 (DBREF 2XND A "
        "19-510, no insertion codes); highlights use the sequence position, never the author "
        "number"
    ),
    "structure_evidence_type": "biohub-mcp-model",
    "resolution": (
        "Fetch and validate the RCSB FASTA sequence of PDB entry 2XND chain A; do not resolve "
        "the generic name ATP synthase to another subunit or species. The Biohub MCP structure "
        "view shows a stored ESM Atlas prediction or an on-demand fold of that exact sequence, "
        "not the experimental 2XND coordinates. SAE activations and their interpretations are "
        "model-derived hypotheses."
    ),
}
EXPECTED_SAE_WORKFLOW = [
    "Fetch and validate the RCSB FASTA sequence of 2XND chain A once.",
    (
        "Use exactly one managed /api/v1/encode request for tokenization and exactly one "
        "managed /api/v1/logits request with normalize_features=true and canonical "
        "SAEConfig.models wire syntax; do not substitute local tokenization when reproducing "
        "this tutorial."
    ),
    "Decode the named sparse tensor, densify it, and remove BOS/EOS rows before residue analysis.",
    (
        "Use the strict active-value predicate activation > 0.01 for prevalence and "
        "mean-active magnitude; report the top 10 by maximum activation and top 10 by "
        "prevalence."
    ),
    (
        "Fetch exactly five Atlas descriptions for the top five maximum-activation features in "
        "the exact compatible 16,384-feature dictionary, then treat them as generated "
        "hypotheses."
    ),
    (
        "Map exactly the top three maximum-activation features onto the structure with one "
        "Biohub MCP structure view of the exact analyzed sequence, as structure_view describes; "
        "its residue numbers are one-based positions in that sequence, so it needs no "
        "sequence-to-coordinate alignment."
    ),
    (
        "Record the exact view arguments and the returned descriptor and preview status in "
        "structure-view.json, or the planned arguments with called false and the reason when "
        "the view could not run, and preserve every named reproducibility artifact."
    ),
]

EXPECTED_PRESENTATIONS = {
    "gb1-esmc-w43f-masked-llr": {
        "mode": "inline-image",
        "automatic": True,
        "primary_artifact": "mutation-score.svg",
        "capability": "inline-image-display",
        "style": (
            "Display the deterministic score card inline and label it as a model score rather "
            "than a biological effect."
        ),
        "fallback": (
            "Return the verified SVG and JSON artifact paths if inline image display is "
            "unavailable; the JSON artifacts remain authoritative."
        ),
    },
    "gb1-esmfold2-fast-fold": {
        "mode": "mcp-app-or-preview-or-exact-artifact",
        "automatic": True,
        "primary_artifact": "the ui_show_protein_structure result for the exact GB1 query sequence",
        "capability": "mcp-apps-structure-viewer-or-png-preview",
        "style": (
            "After successful artifact creation, call ui_show_protein_structure once with the exact "
            "GB1 query sequence; hosts that render MCP Apps show the interactive Mol* viewer. Label "
            "the view as the Biohub MCP's Atlas or on-demand coordinates rather than this ESMFold2 "
            "prediction, and take pLDDT and pAE only from result.json."
        ),
        "fallback_artifact": "prediction.pdb",
        "fallback_capability": "interactive-molecular-structure-viewing",
        "contract": "structure_viewer_contract",
        "fallback": "Report a missing tool, error, or unavailable preview without switching viewers. Return the verified PDB and result/provenance paths. Only an explicit request to view the exact prediction file uses the OpenDiscovery Structure Viewer through structure_viewer_contract, with predicted-confidence coloring when ready and coordinate B-factor values labeled as pLDDT. Pending or unavailable presentation never invalidates the fold.",
    },
    "gb1-atlas-similarity-search": {
        "mode": "mcp-app-or-preview",
        "automatic": True,
        "primary_artifact": "the ui_show_protein_structure result for the top-ranked hit",
        "capability": "mcp-apps-structure-viewer-or-png-preview",
        "style": (
            "Call ui_show_protein_structure once with the top-ranked hit's returned sequence; "
            "hosts that render MCP Apps show the interactive Mol* viewer."
        ),
        "fallback": (
            "Hosts without MCP Apps summarize the returned PNG preview and descriptor in text; "
            "an empty result or a fold-limit error ends with the text summary and is never "
            "retried."
        ),
    },
}
PLACEHOLDER_PATTERN = re.compile(
    r"(?:\bthis protein\b|\bthis sequence\b|\byour sequence\b|"
    r"\bthis complex\b|\bthese sequences\b|\bprotein sequence here\b|<sequence>|\.{3})",
    re.IGNORECASE,
)
MUTATION_PATTERN = re.compile(r"\b([A-Z])([1-9][0-9]*)([A-Z])\b")
MARKETPLACE_SEQUENCE_LITERAL_PATTERN = re.compile(
    r"\b[ACDEFGHIKLMNPQRSTVWY]{30,}\b",
    re.IGNORECASE,
)
MARKETPLACE_INVOCATION_PATTERN = re.compile(r"(?<![A-Za-z0-9_])@[A-Za-z0-9][A-Za-z0-9_-]*\b")


class StarterExampleError(ValueError):
    """Raised when the starter-example contract is incomplete or inconsistent."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StarterExampleError(f"{label} must be an object")
    return value


def _validate_structure_viewer_contract(contract: dict[str, Any]) -> None:
    viewer_contract = _object(
        contract.get("structure_viewer_contract"), "structure_viewer_contract"
    )
    if viewer_contract != EXPECTED_STRUCTURE_VIEWER_CONTRACT:
        raise StarterExampleError("structure_viewer_contract has drifted")


def _validate_mcp_structure_view_contract(contract: dict[str, Any]) -> None:
    view_contract = _object(
        contract.get("mcp_structure_view_contract"), "mcp_structure_view_contract"
    )
    if view_contract != EXPECTED_MCP_STRUCTURE_VIEW_CONTRACT:
        raise StarterExampleError("mcp_structure_view_contract has drifted")


def _coordinate_download_urls(value: Any) -> list[str]:
    """Return every URL in a contract value that downloads a coordinate file."""

    if isinstance(value, dict):
        return [url for item in value.values() for url in _coordinate_download_urls(item)]
    if isinstance(value, list):
        return [url for item in value for url in _coordinate_download_urls(item)]
    if not isinstance(value, str):
        return []
    found = []
    for url in URL_PATTERN.findall(value):
        parsed = urlsplit(url)
        if parsed.hostname == "files.rcsb.org" or parsed.path.lower().endswith(
            COORDINATE_FILE_SUFFIXES
        ):
            found.append(url)
    return found


def _highlight_color(value: Any, label: str) -> str:
    if not isinstance(value, str) or HIGHLIGHT_COLOR_PATTERN.fullmatch(value) is None:
        raise StarterExampleError(f"{label} must be an uppercase #RRGGBB color")
    return value


def _validate_mcp_structure_view(use_case_id: str, use_case: dict[str, Any]) -> None:
    """Bind an ESMC tutorial launcher to one Biohub MCP view of its analyzed sequence."""

    if use_case.get("presentation_contract") != "mcp_structure_view_contract":
        raise StarterExampleError(f"{use_case_id} must reference mcp_structure_view_contract")
    view = _object(use_case.get("structure_view"), f"{use_case_id}.structure_view")
    _nonempty_string(view.get("sequence"), f"{use_case_id}.structure_view.sequence")
    _nonempty_string(view.get("when"), f"{use_case_id}.structure_view.when")
    presentation = _string_list(use_case.get("presentation"), f"{use_case_id}.presentation")
    if "Biohub MCP structure view" not in presentation[0]:
        raise StarterExampleError(f"{use_case_id} must present the Biohub MCP view first")
    execution_policy = _string_list(
        use_case.get("execution_policy"), f"{use_case_id}.execution_policy"
    )
    if EXPECTED_MCP_STRUCTURE_VIEW_DISCLOSURES[use_case_id] not in execution_policy:
        raise StarterExampleError(f"{use_case_id} must disclose its one Biohub MCP view")
    if any(
        "structure view" in line.lower() and re.search(r"\b(?:never|not|no)\b", line.lower())
        for line in execution_policy
        if line != EXPECTED_MCP_STRUCTURE_VIEW_DISCLOSURES[use_case_id]
    ):
        raise StarterExampleError(f"{use_case_id} must not withhold its Biohub MCP view")

    if use_case_id == "esmc-mutation-landscape":
        groups = view.get("highlight_groups")
        if not isinstance(groups, list) or len(groups) != 2:
            raise StarterExampleError(
                "the PETase view must highlight the most constrained and most tolerant groups"
            )
        colors = []
        for index, group_value in enumerate(groups):
            group = _object(group_value, f"{use_case_id}.structure_view.highlight_groups[{index}]")
            _nonempty_string(group.get("label"), f"{use_case_id} highlight group label")
            residues = _nonempty_string(group.get("residues"), f"{use_case_id} highlight residues")
            if "mutation-landscape.json summary." not in residues:
                raise StarterExampleError(
                    "the PETase view must highlight the runtime's ranked summary positions"
                )
            colors.append(_highlight_color(group.get("color"), f"{use_case_id} highlight color"))
        if len(set(colors)) != len(colors):
            raise StarterExampleError("each PETase highlight group needs its own color")
    else:
        contract = _object(
            use_case.get("reproducibility_contract"), f"{use_case_id}.reproducibility_contract"
        )
        mapped = contract.get("map_top_k_by_max_activation")
        per_feature = contract.get("highlight_top_k_residues_per_mapped_feature")
        for value in (mapped, per_feature):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise StarterExampleError("the ATP view pins must be positive integers")
        colors = view.get("highlight_colors")
        if not isinstance(colors, list) or len(colors) != mapped:
            raise StarterExampleError("the ATP view needs one highlight color per mapped feature")
        checked = [
            _highlight_color(color, f"{use_case_id}.structure_view.highlight_colors[{index}]")
            for index, color in enumerate(colors)
        ]
        if len(set(checked)) != len(checked):
            raise StarterExampleError("each mapped ATP feature needs its own highlight color")
        if mapped * per_feature > EXPECTED_MCP_STRUCTURE_VIEW_CONTRACT["max_highlights"]:
            raise StarterExampleError("the ATP view must fit the Biohub MCP highlight limit")
        highlight_rule = _nonempty_string(
            view.get("highlight_rule"), f"{use_case_id}.structure_view.highlight_rule"
        )
        for term in (f"top {mapped} maximum-activation", f"{per_feature} highest-activation"):
            if term not in highlight_rule:
                raise StarterExampleError(
                    "the ATP highlight rule must match its reproducibility pins"
                )
        record = _nonempty_string(view.get("record"), f"{use_case_id}.structure_view.record")
        artifacts = _string_list(contract.get("artifacts"), f"{use_case_id} artifacts")
        if record != "structure-view.json" or record not in artifacts:
            raise StarterExampleError(
                "the ATP view record must be the named structure-view.json artifact"
            )
    # The whole view is pinned last, so a drifted rule, color, or group fails even
    # when every structural check above still passes.
    if view != EXPECTED_MCP_STRUCTURE_VIEWS[use_case_id]:
        raise StarterExampleError(f"{use_case_id}.structure_view has drifted")


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StarterExampleError(f"{label} must be a non-empty string")
    return value


def _string_list(value: Any, label: str, *, minimum: int = 1) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise StarterExampleError(f"{label} must contain at least {minimum} item(s)")
    for index, item in enumerate(value):
        _nonempty_string(item, f"{label}[{index}]")
    return value


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StarterExampleError(f"cannot load {label}: {exc}") from exc
    return _object(decoded, label)


def load_starter_examples(path: Path) -> dict[str, Any]:
    return _load_json_object(path, "starter example contract")


def load_tutorial_use_cases(path: Path) -> dict[str, Any]:
    return _load_json_object(path, "tutorial use-case contract")


def _validate_sequence(contract: dict[str, Any]) -> tuple[dict[str, Any], str]:
    sequence = _object(contract.get("sequence"), "sequence")
    for field in ("id", "name", "literal", "sha256"):
        _nonempty_string(sequence.get(field), f"sequence.{field}")
    literal = sequence["literal"]
    if literal != literal.upper() or not literal.isalpha():
        raise StarterExampleError("sequence.literal must be uppercase amino-acid letters")
    invalid = sorted(set(literal) - set(CANONICAL_AMINO_ACIDS))
    if invalid:
        raise StarterExampleError(
            f"sequence.literal contains non-canonical residue(s): {''.join(invalid)}"
        )
    if sequence.get("length") != len(literal):
        raise StarterExampleError("sequence.length does not match sequence.literal")
    digest = hashlib.sha256(literal.encode("ascii")).hexdigest()
    if sequence.get("sha256") != digest:
        raise StarterExampleError("sequence.sha256 does not match sequence.literal")

    source = _object(sequence.get("source"), "sequence.source")
    for field in (
        "title",
        "reference",
        "fasta_url",
        "accession",
        "chain",
        "entry_revision",
        "snapshot_date",
        "raw_fasta_sha256",
        "usage",
        "numbering",
    ):
        _nonempty_string(source.get(field), f"sequence.source.{field}")
    for field in ("reference", "fasta_url"):
        if not source[field].startswith("https://"):
            raise StarterExampleError(f"sequence.source.{field} must be an HTTPS URL")
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", source["snapshot_date"]) is None:
        raise StarterExampleError("sequence.source.snapshot_date must be YYYY-MM-DD")
    if source["accession"] != "1PGA" or source["chain"] != "A":
        raise StarterExampleError("sequence source must remain RCSB 1PGA chain A")
    if source["entry_revision"] != "1.4":
        raise StarterExampleError("sequence source entry_revision has drifted")
    if source.get("raw_fasta_bytes") != 115:
        raise StarterExampleError("sequence source raw_fasta_bytes has drifted")
    if source["raw_fasta_sha256"] != (
        "a56ce69e9e80a566367b6b4b3a01a263d61e9b5c58dd55e9eb8e49a50bd6b561"
    ):
        raise StarterExampleError("sequence source raw_fasta_sha256 has drifted")
    if sequence != EXPECTED_SEQUENCE:
        raise StarterExampleError(
            "sequence and source metadata must exactly match the pinned RCSB 1PGA chain A snapshot"
        )
    return sequence, literal


def _validate_mutations(
    example: dict[str, Any], sequence: str, input_validation: dict[str, Any]
) -> None:
    mutations = input_validation.get("mutations")
    if not isinstance(mutations, list):
        raise StarterExampleError(f"{example['id']}.input_validation.mutations must be a list")
    prompt_mutations = {"".join(parts) for parts in MUTATION_PATTERN.findall(example["prompt"])}
    if set(mutations) != prompt_mutations:
        raise StarterExampleError(
            f"{example['id']} mutations must exactly match mutations in its prompt"
        )
    for mutation in mutations:
        if not isinstance(mutation, str):
            raise StarterExampleError(f"{example['id']} mutation must be a string")
        match = MUTATION_PATTERN.fullmatch(mutation)
        if match is None:
            raise StarterExampleError(f"{example['id']} has invalid mutation {mutation!r}")
        wild_type, position_text, alternate = match.groups()
        position = int(position_text)
        if not 1 <= position <= len(sequence):
            raise StarterExampleError(
                f"{example['id']} mutation {mutation} is outside the literal sequence"
            )
        if sequence[position - 1] != wild_type:
            raise StarterExampleError(
                f"{example['id']} mutation {mutation} has the wrong wild-type residue"
            )
        if alternate not in CANONICAL_AMINO_ACIDS or alternate == wild_type:
            raise StarterExampleError(
                f"{example['id']} mutation {mutation} has an invalid alternate residue"
            )
    mutant = list(sequence)
    expected_differences: set[int] = set()
    for mutation in mutations:
        match = MUTATION_PATTERN.fullmatch(mutation)
        assert match is not None
        _, position_text, alternate = match.groups()
        position = int(position_text)
        mutant[position - 1] = alternate
        expected_differences.add(position)
    observed_differences = {
        index + 1
        for index, (wild_type, alternate) in enumerate(zip(sequence, mutant, strict=True))
        if wild_type != alternate
    }
    if len(mutant) != len(sequence) or observed_differences != expected_differences:
        raise StarterExampleError(
            f"{example['id']} mutation application does not preserve exact one-based identity"
        )


def _validate_route(example: dict[str, Any]) -> None:
    route = _object(example.get("route"), f"{example['id']}.route")
    for field in (
        "skill",
        "model",
        "provider",
        "confirmation_boundary",
        "required_confirmation",
        "request_policy",
        "local_alternative",
    ):
        _nonempty_string(route.get(field), f"{example['id']}.route.{field}")
    for field in ("may_incur_cost", "prompt_authorizes_execution"):
        if not isinstance(route.get(field), bool):
            raise StarterExampleError(f"{example['id']}.route.{field} must be boolean")
    if route["skill"] != EXPECTED_EXAMPLES[example["id"]]:
        raise StarterExampleError(f"{example['id']} is assigned to the wrong skill")
    # Confirmation is a function of the route, not of whether money moves at all.
    # Managed tutorial-scale calls cost fractions of a cent and the user already
    # chose the prompt, so they run; Modal, self-hosted, and bulk transfers confirm.
    if route["provider"] == "biohub-managed":
        if route["confirmation_boundary"] != "not_required_for_managed_tutorial_scale":
            raise StarterExampleError(
                f"{example['id']} managed starter must state its exact confirmation boundary"
            )
        if route["prompt_authorizes_execution"] is not True:
            raise StarterExampleError(
                f"{example['id']} managed starter must run without a separate confirmation"
            )
        if "credits" not in route["required_confirmation"].lower():
            raise StarterExampleError(
                f"{example['id']} managed starter must report consumed credits with the result"
            )
        if not route["may_incur_cost"]:
            raise StarterExampleError(
                f"{example['id']} managed starter must still declare that it may incur cost"
            )
    elif route["may_incur_cost"]:
        if route["prompt_authorizes_execution"] is not False:
            raise StarterExampleError(
                f"{example['id']} remote or bulk starter must never authorize execution"
            )
        if route["confirmation_boundary"] != "required_before_paid_or_remote_execution":
            raise StarterExampleError(
                f"{example['id']} must require confirmation before remote or bulk execution"
            )
        confirmation = route["required_confirmation"].lower()
        for term in ("separate", "current-turn", "scope and cost preview"):
            if term not in confirmation:
                raise StarterExampleError(
                    f"{example['id']} must require separate current-turn confirmation after scope and cost preview"
                )
    else:
        if route["confirmation_boundary"] != "not_required_for_public_alpha_read":
            raise StarterExampleError(
                f"{example['id']} public read must state its exact confirmation boundary"
            )
        if route["prompt_authorizes_execution"] is not True:
            raise StarterExampleError(f"{example['id']} public-read authorization must be explicit")
    if route != EXPECTED_ROUTES[example["id"]]:
        raise StarterExampleError(
            f"{example['id']}.route must exactly match its pinned model, provider, and confirmation policy"
        )


def _validate_managed_workflow(example: dict[str, Any]) -> None:
    """Managed tutorial-scale work must run, and must check access before planning.

    This previously required the inverse: a scope/cost preview, then a separate
    confirmation, then execution. That turned every starter into a multi-turn
    approval workflow for calls costing fractions of a cent, and a user with no
    credential only discovered it after the plan.
    """

    if example["route"]["provider"] != "biohub-managed":
        return
    steps = [step.lower() for step in example["ordered_workflow"]]
    workflow = " ".join(steps)
    # Each entry is a set of acceptable spellings; "exactly once" reads better for a
    # command than "exactly one request" does.
    required_terms = (
        ("preflight",),
        ("exactly one", "exactly once"),
        ("without implicit retries",),
        ("credits",),
    )
    missing = [
        alternatives[0]
        for alternatives in required_terms
        if not any(term in workflow for term in alternatives)
    ]
    if missing:
        raise StarterExampleError(
            f"{example['id']} managed workflow must preflight, make exactly one "
            f"no-retry request, and report consumed credits (missing: {', '.join(missing)})"
        )
    for prohibited in (
        "separate explicit current-turn confirmation",
        "scope and cost preview",
        "otherwise stop",
    ):
        if prohibited in workflow:
            raise StarterExampleError(
                f"{example['id']} managed workflow must not gate execution on {prohibited}"
            )
    if "silently" in workflow:
        raise StarterExampleError(f"{example['id']} managed workflow must not conceal its actions")
    preflight_index = next(
        (index for index, step in enumerate(steps) if "preflight" in step),
        -1,
    )
    request_index = next(
        (index for index, step in enumerate(steps) if "without implicit retries" in step),
        -1,
    )
    presentation_index = next(
        (index for index, step in enumerate(steps) if "credits" in step),
        -1,
    )
    if not 0 == preflight_index < request_index < presentation_index:
        raise StarterExampleError(
            f"{example['id']} workflow must preflight first, then request, then present"
        )
    if tuple(example["ordered_workflow"]) != EXPECTED_MANAGED_WORKFLOWS[example["id"]]:
        raise StarterExampleError(
            f"{example['id']} managed workflow must exactly match its pinned step sequence"
        )


def _validate_example(example: dict[str, Any], sequence_record: dict[str, Any]) -> None:
    example_id = _nonempty_string(example.get("id"), "example.id")
    if example_id not in EXPECTED_EXAMPLES:
        raise StarterExampleError(f"unexpected starter example id: {example_id}")
    prompt = _nonempty_string(example.get("prompt"), f"{example_id}.prompt")
    if len(prompt) > 128:
        raise StarterExampleError(f"{example_id}.prompt exceeds 128 characters")
    if sequence_record["literal"] in prompt:
        raise StarterExampleError(
            f"{example_id}.prompt must not expose the hidden literal sequence fixture"
        )
    if PLACEHOLDER_PATTERN.search(prompt):
        raise StarterExampleError(f"{example_id}.prompt contains a placeholder")
    if prompt != EXPECTED_PROMPTS[example_id]:
        raise StarterExampleError(
            f"{example_id}.prompt must exactly match its natural-language launcher"
        )

    _validate_route(example)
    input_validation = _object(example.get("input_validation"), f"{example_id}.input_validation")
    if input_validation.get("sequence_id") != sequence_record["id"]:
        raise StarterExampleError(f"{example_id} references the wrong sequence id")
    if input_validation.get("alphabet") != CANONICAL_AMINO_ACIDS:
        raise StarterExampleError(f"{example_id} must pin the canonical amino-acid alphabet")
    maximum = input_validation.get("maximum_sequence_length")
    if maximum is None:
        _nonempty_string(
            input_validation.get("length_policy"),
            f"{example_id}.input_validation.length_policy",
        )
    else:
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum <= 0:
            raise StarterExampleError(
                f"{example_id}.input_validation.maximum_sequence_length must be positive or null"
            )
        if sequence_record["length"] > maximum:
            raise StarterExampleError(f"{example_id} sequence exceeds its route-specific maximum")
    _string_list(
        input_validation.get("checks"),
        f"{example_id}.input_validation.checks",
        minimum=2,
    )
    _validate_mutations(example, sequence_record["literal"], input_validation)

    _string_list(example.get("ordered_workflow"), f"{example_id}.ordered_workflow", minimum=4)
    _validate_managed_workflow(example)
    artifacts = example.get("artifacts")
    if not isinstance(artifacts, list):
        raise StarterExampleError(f"{example_id}.artifacts must be a list")
    for index, artifact_value in enumerate(artifacts):
        artifact = _object(artifact_value, f"{example_id}.artifacts[{index}]")
        for field in ("name", "format"):
            _nonempty_string(artifact.get(field), f"{example_id}.artifacts[{index}].{field}")
        if not isinstance(artifact.get("required"), bool):
            raise StarterExampleError(f"{example_id}.artifacts[{index}].required must be boolean")
    _string_list(example.get("results"), f"{example_id}.results", minimum=2)
    _string_list(example.get("provenance"), f"{example_id}.provenance", minimum=2)
    _string_list(example.get("limits"), f"{example_id}.limits", minimum=2)

    presentation = _object(example.get("presentation"), f"{example_id}.presentation")
    for field in ("mode", "capability", "primary_artifact", "style", "fallback"):
        _nonempty_string(presentation.get(field), f"{example_id}.presentation.{field}")
    if presentation.get("automatic") is not True:
        raise StarterExampleError(f"{example_id}.presentation must be automatic")
    viewer_contract_modes = ("structure-viewer", "mcp-app-or-preview-or-exact-artifact")
    if presentation["mode"] in viewer_contract_modes and presentation.get("contract") != (
        "structure_viewer_contract"
    ):
        raise StarterExampleError(f"{example_id}.presentation must reference the viewer contract")
    if presentation["mode"] not in viewer_contract_modes and "contract" in presentation:
        raise StarterExampleError(
            f"{example_id}.presentation must not claim the fold viewer contract"
        )
    if presentation != EXPECTED_PRESENTATIONS[example_id]:
        raise StarterExampleError(f"{example_id}.presentation contract has drifted")

    failure = _object(
        example.get("failure_and_nondeterminism"),
        f"{example_id}.failure_and_nondeterminism",
    )
    _string_list(
        failure.get("failure_modes"),
        f"{example_id}.failure_and_nondeterminism.failure_modes",
        minimum=2,
    )
    for field in ("nondeterminism", "retry_policy"):
        _nonempty_string(failure.get(field), f"{example_id}.failure_and_nondeterminism.{field}")
    qualification_gates = _string_list(
        example.get("qualification_gates"),
        f"{example_id}.qualification_gates",
        minimum=2,
    )
    qualification_text = " ".join(qualification_gates).lower()
    if "no-provider" not in qualification_text:
        raise StarterExampleError(f"{example_id} qualification must include a no-provider trace")
    if example["route"]["provider"] == "biohub-managed":
        for term in ("scope/cost preview", "separate explicit current-turn confirmation"):
            if term not in qualification_text:
                raise StarterExampleError(
                    f"{example_id} qualification must prove the managed confirmation stop"
                )


def _validate_execution_contracts(by_skill: dict[str, dict[str, Any]], sequence: str) -> None:
    esmc_example = by_skill["esmc"]
    if esmc_example.get("qualification_response") != EXPECTED_ESMC_QUALIFICATION_RESPONSE:
        raise StarterExampleError(
            "ESMC starter qualification response must match its exact eight-line contract"
        )
    esmc_execution = _object(
        esmc_example.get("execution_contract"),
        "gb1-esmc-w43f-masked-llr.execution_contract",
    )
    if esmc_execution != EXPECTED_ESMC_EXECUTION:
        raise StarterExampleError(
            "ESMC starter execution contract must pin one exact logits request, command, and output"
        )
    if validate_esmc_sequence(esmc_execution["sequence"]) != sequence:
        raise StarterExampleError("ESMC starter request changed the literal sequence")

    fold_example = by_skill["esmfold2"]
    if fold_example.get("qualification_response") != EXPECTED_FOLD_QUALIFICATION_RESPONSE:
        raise StarterExampleError(
            "fold starter qualification response must match its exact ten-line contract"
        )
    fold_execution = _object(
        fold_example.get("execution_contract"),
        "gb1-esmfold2-fast-fold.execution_contract",
    )
    if fold_execution != EXPECTED_FOLD_EXECUTION:
        raise StarterExampleError(
            "fold starter execution contract must pin one exact /fold request, command, and output"
        )
    fold_request = fold_execution["request"]
    fold_config = {
        key: value for key, value in fold_request.items() if key not in {"model", "sequence", "msa"}
    }
    try:
        if validate_esmc_sequence(fold_request["sequence"]) != sequence:
            raise StarterExampleError("fold starter request changed the literal sequence")
        validated_config = validate_fold_config(
            fold_config,
            model=fold_request["model"],
            endpoint="fold",
        )
    except ValidationError as exc:
        raise StarterExampleError(
            f"fold starter request failed production validation: {exc}"
        ) from exc
    if validated_config != fold_config or fold_request["include_pae"] is not True:
        raise StarterExampleError("fold starter must request pAE with exact validated parameters")

    atlas_example = by_skill["esm-atlas"]
    if atlas_example.get("qualification_response") != EXPECTED_ATLAS_QUALIFICATION_RESPONSE:
        raise StarterExampleError(
            "Atlas starter qualification response must match its exact eleven-line contract"
        )
    atlas_execution = _object(
        atlas_example.get("execution_contract"),
        "gb1-atlas-similarity-search.execution_contract",
    )
    if atlas_execution != EXPECTED_ATLAS_EXECUTION:
        raise StarterExampleError(
            "Atlas starter execution contract must pin one MCP search, zero detail follow-ups, zero script calls, and one structure view"
        )
    if tuple(atlas_example["ordered_workflow"]) != EXPECTED_ATLAS_WORKFLOW:
        raise StarterExampleError(
            "Atlas starter workflow must exactly match its pinned step sequence"
        )
    if tuple(atlas_example["results"]) != EXPECTED_ATLAS_RESULTS:
        raise StarterExampleError("Atlas starter results must exactly match their pinned list")


def _validate_against_production_contracts(examples: list[dict[str, Any]], sequence: str) -> None:
    """Bind starter semantics to the production validators, router, and activator."""

    by_skill = {example["route"]["skill"]: example for example in examples}
    _validate_execution_contracts(by_skill, sequence)
    try:
        if validate_esmc_sequence(sequence) != sequence:
            raise StarterExampleError("production ESMC validation changed the literal sequence")
        fold_input = validate_fold_input(
            {"sequences": [{"type": "protein", "id": "A", "sequence": sequence, "msa": None}]},
            model="esmfold2-fast-2026-05",
        )
    except ValidationError as exc:
        raise StarterExampleError(f"production input validation rejected a starter: {exc}") from exc
    if fold_input["sequences"][0]["sequence"] != sequence:
        raise StarterExampleError("production fold validation changed the literal sequence")

    for example_id, (
        request,
        expected_route,
        expected_model,
        expected_authentication,
    ) in EXPECTED_PRODUCTION_ROUTES.items():
        expected_declared = EXPECTED_ROUTES[example_id]
        skill = expected_declared["skill"]
        example = by_skill[skill]
        if select_skill(example["prompt"]) != skill:
            raise StarterExampleError(f"production activation drifted for {example['id']}")
        routed = route_request(request)
        if (routed.route, routed.model, routed.required_authentication) != (
            expected_route,
            expected_model,
            expected_authentication,
        ):
            raise StarterExampleError(f"production routing drifted for {example['id']}")
        declared_model = routed.model or "not-applicable-public-data-api"
        declared_provider = EXPECTED_PROVIDER_BY_PRODUCTION_ROUTE.get(routed.route)
        if (example["route"]["model"], example["route"]["provider"]) != (
            declared_model,
            declared_provider,
        ):
            raise StarterExampleError(
                f"declared route is inconsistent with production routing for {example['id']}"
            )
        artifact_contract = tuple(dict(artifact) for artifact in example["artifacts"])
        if artifact_contract != EXPECTED_ARTIFACTS[example_id]:
            raise StarterExampleError(
                f"artifact contract drifted for {example['id']}: names, formats, order, and requiredness are pinned"
            )


def validate_starter_examples(contract: dict[str, Any]) -> dict[str, Any]:
    """Validate the self-contained contract without consulting repository surfaces."""

    if contract.get("schema_version") != "1.0":
        raise StarterExampleError("unsupported starter example schema_version")
    _validate_structure_viewer_contract(contract)
    if contract.get("prompt_max_characters") != 128:
        raise StarterExampleError("prompt_max_characters must be exactly 128")
    if contract.get("qualificationStatus") != "pending-clean-host-qualification":
        raise StarterExampleError(
            "qualificationStatus must remain pending-clean-host-qualification"
        )
    qualification = _object(contract.get("qualification"), "qualification")
    if qualification.get("cleanInstalledHostQualified") is not False:
        raise StarterExampleError("clean installed-host qualification must not be claimed")
    _nonempty_string(qualification.get("claim"), "qualification.claim")
    _string_list(qualification.get("gates"), "qualification.gates", minimum=3)
    sequence, _ = _validate_sequence(contract)
    surface_contract = _object(contract.get("surface_contract"), "surface_contract")
    for field in (
        "readme",
        "router_skill",
        "routing_reference",
        "activation_fixture",
    ):
        _nonempty_string(surface_contract.get(field), f"surface_contract.{field}")
    agent_defaults = _object(
        surface_contract.get("agent_defaults"), "surface_contract.agent_defaults"
    )
    if set(agent_defaults) != set(EXPECTED_EXAMPLES):
        raise StarterExampleError("surface_contract.agent_defaults does not cover every example")
    for example_id, path in agent_defaults.items():
        _nonempty_string(path, f"surface_contract.agent_defaults.{example_id}")

    examples = contract.get("examples")
    if not isinstance(examples, list) or len(examples) != len(EXPECTED_EXAMPLES):
        raise StarterExampleError("contract must contain exactly three starter examples")
    ids = [example.get("id") if isinstance(example, dict) else None for example in examples]
    if len(set(ids)) != len(ids) or set(ids) != set(EXPECTED_EXAMPLES):
        raise StarterExampleError("starter example ids must be unique and complete")
    for value in examples:
        _validate_example(_object(value, "example"), sequence)
    _validate_against_production_contracts(examples, sequence["literal"])
    return contract


def _read_default_prompt(path: Path) -> str:
    match = re.search(
        r"^\s*default_prompt:\s*(.+?)\s*$",
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if match is None:
        raise StarterExampleError(f"missing default_prompt in {path}")
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise StarterExampleError(f"default_prompt in {path} must be JSON-quoted") from exc
    return _nonempty_string(value, f"default_prompt in {path}")


def validate_starter_example_surfaces(
    plugin_root: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    """Reject prompt drift across the packaged focused-skill and activation surfaces."""

    validate_starter_examples(contract)
    plugin_root = plugin_root.resolve()
    surfaces = contract["surface_contract"]
    paths: dict[str, Path] = {}
    for field in (
        "readme",
        "router_skill",
        "routing_reference",
        "activation_fixture",
    ):
        path = (plugin_root / surfaces[field]).resolve()
        if not path.is_relative_to(plugin_root) or not path.is_file():
            raise StarterExampleError(f"surface {field} is missing or outside the plugin")
        paths[field] = path

    examples = contract["examples"]
    prompts = [example["prompt"] for example in examples]
    for field in ("readme", "router_skill", "routing_reference"):
        text = paths[field].read_text(encoding="utf-8")
        missing = [prompt for prompt in prompts if prompt not in text]
        if missing:
            raise StarterExampleError(f"{field} is missing {len(missing)} exact starter prompt(s)")

    fold_example = next(
        example for example in examples if example["id"] == "gb1-esmfold2-fast-fold"
    )
    request_path = (plugin_root / fold_example["execution_contract"]["request_file"]).resolve()
    if not request_path.is_relative_to(plugin_root) or not request_path.is_file():
        raise StarterExampleError("fold starter request file is missing or outside the plugin")
    try:
        request_payload = json.loads(request_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StarterExampleError("fold starter request file is not valid JSON") from exc
    if request_payload != EXPECTED_FOLD_EXECUTION["request"]:
        raise StarterExampleError("fold starter request file drifted from its execution contract")

    try:
        activation_cases = json.loads(paths["activation_fixture"].read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StarterExampleError("activation fixture is not valid JSON") from exc
    if not isinstance(activation_cases, list):
        raise StarterExampleError("activation fixture must be a list")
    activation_by_prompt = {
        case.get("prompt"): case.get("expected")
        for case in activation_cases
        if isinstance(case, dict)
    }
    for example in examples:
        if activation_by_prompt.get(example["prompt"]) != example["route"]["skill"]:
            raise StarterExampleError(f"activation fixture has drifted for {example['id']}")

    for example_id, relative in surfaces["agent_defaults"].items():
        path = (plugin_root / relative).resolve()
        if not path.is_relative_to(plugin_root) or not path.is_file():
            raise StarterExampleError(f"agent default for {example_id} is missing")
        expected = next(example["prompt"] for example in examples if example["id"] == example_id)
        if _read_default_prompt(path) != expected:
            raise StarterExampleError(f"agent default has drifted for {example_id}")

    public_readme = plugin_root / "PUBLIC_README.md"
    if public_readme.exists():
        text = public_readme.read_text(encoding="utf-8")
        if any(prompt not in text for prompt in prompts):
            raise StarterExampleError("PUBLIC_README.md is missing exact starter prompts")
    return contract


def resolve_marketplace_default_prompts(
    contract: dict[str, Any],
) -> list[dict[str, str]]:
    """Resolve and validate the tutorial prompt records selected for the plugin page."""

    if contract.get("schema_version") != "1.1":
        raise StarterExampleError("unsupported tutorial use-case schema_version")
    _validate_structure_viewer_contract(contract)
    _validate_mcp_structure_view_contract(contract)
    use_cases = contract.get("use_cases")
    if not isinstance(use_cases, list) or not use_cases:
        raise StarterExampleError("tutorial use_cases must be a non-empty list")

    prompts_by_id: dict[str, dict[str, str]] = {}
    prompt_ids_by_text: dict[str, str] = {}
    for use_case_index, use_case_value in enumerate(use_cases):
        use_case = _object(use_case_value, f"use_cases[{use_case_index}]")
        use_case_id = _nonempty_string(use_case.get("id"), f"use_cases[{use_case_index}].id")
        route = _object(use_case.get("route"), f"{use_case_id}.route")
        skill = _nonempty_string(route.get("skill"), f"{use_case_id}.route.skill")
        prompt_records = use_case.get("prompts")
        if not isinstance(prompt_records, list) or not prompt_records:
            raise StarterExampleError(f"{use_case_id}.prompts must be a non-empty list")
        for prompt_index, prompt_value in enumerate(prompt_records):
            prompt = _object(prompt_value, f"{use_case_id}.prompts[{prompt_index}]")
            prompt_id = _nonempty_string(
                prompt.get("id"), f"{use_case_id}.prompts[{prompt_index}].id"
            )
            text = _nonempty_string(
                prompt.get("text"), f"{use_case_id}.prompts[{prompt_index}].text"
            )
            if prompt_id in prompts_by_id:
                raise StarterExampleError(f"duplicate tutorial prompt id: {prompt_id}")
            if text in prompt_ids_by_text:
                raise StarterExampleError(
                    f"duplicate tutorial prompt text: {prompt_ids_by_text[text]} and {prompt_id}"
                )
            if text != " ".join(text.split()):
                raise StarterExampleError(f"{prompt_id} must use normalized whitespace")
            if len(text) > 128:
                raise StarterExampleError(f"{prompt_id} exceeds 128 characters")
            if MARKETPLACE_SEQUENCE_LITERAL_PATTERN.search(text):
                raise StarterExampleError(f"{prompt_id} exposes an amino-acid sequence")
            if PLACEHOLDER_PATTERN.search(text):
                raise StarterExampleError(f"{prompt_id} contains a placeholder")
            if "$" in text or MARKETPLACE_INVOCATION_PATTERN.search(text):
                raise StarterExampleError(f"{prompt_id} must not include invocation syntax")
            if select_skill(text) != skill:
                raise StarterExampleError(f"production activation drifted for {prompt_id}")
            prompts_by_id[prompt_id] = {
                "id": prompt_id,
                "text": text,
                "skill": skill,
                "use_case_id": use_case_id,
            }
            prompt_ids_by_text[text] = prompt_id

    default_ids = _string_list(
        contract.get("marketplace_default_prompt_ids"),
        "marketplace_default_prompt_ids",
        minimum=3,
    )
    if len(default_ids) != 3 or len(set(default_ids)) != 3:
        raise StarterExampleError(
            "marketplace_default_prompt_ids must contain exactly three unique prompt ids"
        )
    missing = [prompt_id for prompt_id in default_ids if prompt_id not in prompts_by_id]
    if missing:
        raise StarterExampleError(
            f"marketplace default prompt id is not defined: {', '.join(missing)}"
        )
    resolved = [prompts_by_id[prompt_id] for prompt_id in default_ids]
    if len({prompt["use_case_id"] for prompt in resolved}) != 3:
        raise StarterExampleError(
            "marketplace defaults must represent three distinct official tutorial workflows"
        )
    _validate_tutorial_execution_boundaries(contract, resolved)
    return resolved


def _validate_tutorial_execution_boundaries(
    contract: dict[str, Any], resolved: list[dict[str, str]]
) -> None:
    """Keep page-facing tutorial prompts fail-closed at target disclosure and exact scope."""

    policy = _object(contract.get("target_resolution_policy"), "target_resolution_policy")
    marketplace_policy = _nonempty_string(
        policy.get("marketplace_defaults"),
        "target_resolution_policy.marketplace_defaults",
    ).lower()
    # Target disclosure always matters. Execution authorization is use-case-specific:
    # each page-facing prompt runs only its exact disclosed requests, and the other
    # managed ESMFold2 tutorial folds run only their own exact disclosed fold.
    for term in (
        "disclose the exact pinned tutorial target or construct",
        "does not authorize target adoption",
    ):
        if term not in marketplace_policy:
            raise StarterExampleError(
                "marketplace default target policy must require exact target disclosure"
            )
    for term in (
        "petase prompt authorizes its disclosed, exact 259-request managed runtime and its one "
        "biohub mcp structure view",
        "atp-synthase prompt authorizes its disclosed, exact rcsb fasta, managed, and atlas "
        "requests and its one biohub mcp structure view",
        "glp-1r prompt authorizes",
        "every other managed esmfold2 tutorial fold runs its exact disclosed fold",
    ):
        if term not in marketplace_policy:
            raise StarterExampleError(
                "marketplace default policy must bind each prompt's exact authorization"
            )

    use_cases = {
        _nonempty_string(value.get("id"), "tutorial use-case id"): _object(
            value, "tutorial use case"
        )
        for value in contract["use_cases"]
        if isinstance(value, dict)
    }
    selected_use_case_ids = {prompt["use_case_id"] for prompt in resolved}
    for use_case_id in selected_use_case_ids:
        use_case = use_cases[use_case_id]
        execution_policy = " ".join(
            _string_list(use_case.get("execution_policy"), f"{use_case_id}.execution_policy")
        ).lower()
        if use_case_id == "esmc-mutation-landscape":
            for term in ("exact 259-request managed runtime", "indeterminate"):
                if term not in execution_policy:
                    raise StarterExampleError(
                        "the PETase execution policy must bind its exact replay-safe runtime"
                    )
            if "current-turn confirmation" in execution_policy:
                raise StarterExampleError(
                    "the PETase launcher must not contradict its exact managed runtime"
                )
        elif use_case_id == "esmc-sae-feature-interpretation":
            for term in (
                "disclose the rcsb fasta sequence of pdb 2xnd chain a",
                "without asking first",
            ):
                if term not in execution_policy:
                    raise StarterExampleError(
                        "the ATP-synthase execution policy must run its exact disclosed requests"
                    )
            if "current-turn confirmation" in execution_policy:
                raise StarterExampleError(
                    "the ATP-synthase launcher must not contradict its exact disclosed requests"
                )
        else:
            for term in (
                "modified_glp1r_peptide_linker fold",
                "exact one-request managed call",
                "without asking first",
            ):
                if term not in execution_policy:
                    raise StarterExampleError(
                        "the GLP-1R execution policy must run its exact one-request fold"
                    )
            if "every other tutorial target runs its exact disclosed managed call" not in (
                execution_policy
            ):
                raise StarterExampleError(
                    f"{use_case_id} must bind every other tutorial fold to its exact call"
                )
            if "current-turn confirmation" in execution_policy:
                raise StarterExampleError(
                    f"{use_case_id} must not contradict its exact disclosed folds"
                )

    fold_use_case = use_cases["esmfold2-all-atom-and-msa"]
    if fold_use_case.get("presentation_contract") != "structure_viewer_contract":
        raise StarterExampleError(
            "esmfold2-all-atom-and-msa must reference structure_viewer_contract"
        )
    for use_case_id in MCP_STRUCTURE_VIEW_USE_CASES:
        _validate_mcp_structure_view(use_case_id, use_cases[use_case_id])

    mutation = use_cases.get("esmc-mutation-landscape")
    if mutation is None:
        raise StarterExampleError("esmc-mutation-landscape tutorial contract is missing")
    mutation_route = _object(mutation.get("route"), "esmc-mutation-landscape.route")
    # The pinned notebook runs all 259 contexts against the managed API. Routing them
    # to Modal pointed at a function the plugin never ships.
    if mutation_route.get("execution_route") != "biohub":
        raise StarterExampleError("the PETase landscape must route to the managed Biohub API")
    if mutation_route.get("model_id") != "esmc-600m-2024-12":
        raise StarterExampleError("the PETase landscape must use the notebook's pinned model")
    if mutation_route.get("masked_context_count") != 259:
        raise StarterExampleError("the PETase landscape must disclose 259 masked contexts")
    concurrency = _nonempty_string(
        mutation_route.get("concurrency"), "esmc-mutation-landscape.route.concurrency"
    ).lower()
    for term in ("threadpoolexecutor", "bounded", "host-pinned"):
        if term not in concurrency:
            raise StarterExampleError(
                "the PETase landscape must run concurrent managed calls through a bounded, "
                "host-pinned pool as the quickstart documents"
            )
    mutation_runtime = _object(mutation.get("runtime"), "esmc-mutation-landscape.runtime")
    resume_command = mutation_runtime.get("resume_command")
    if (
        not isinstance(resume_command, list)
        or "--resume" not in resume_command
        or "<existing-output-dir>" not in resume_command
    ):
        raise StarterExampleError("the PETase runtime must publish its explicit resume command")
    checkpoint_contract = _nonempty_string(
        mutation_runtime.get("checkpoint_contract"),
        "esmc-mutation-landscape.runtime.checkpoint_contract",
    ).lower()
    for term in ("exact-request-bound", "retry-after", "indeterminate"):
        if term not in checkpoint_contract:
            raise StarterExampleError(
                "the PETase runtime must checkpoint exact requests and refuse unsafe replay"
            )

    sae = use_cases.get("esmc-sae-feature-interpretation")
    sae_target = _object(sae.get("target") if sae else None, "SAE tutorial target")
    if (
        sae_target.get("pdb_id") != "2XND"
        or sae_target.get("chain_id") != "A"
        or sae_target.get("structure_evidence_type") != "biohub-mcp-model"
    ):
        raise StarterExampleError(
            "the SAE marketplace prompt must disclose the PDB 2XND chain A sequence and "
            "its Biohub MCP model view"
        )
    # The Biohub MCP view cannot open a PDB entry, so fetching the experimental
    # coordinates only invited a self-drawn replacement figure.
    if _coordinate_download_urls(sae) or "structure_source" in sae_target:
        raise StarterExampleError(
            "the SAE marketplace prompt must not fetch experimental coordinates it cannot show"
        )
    if sae_target != EXPECTED_SAE_TARGET:
        raise StarterExampleError("the SAE marketplace prompt target has drifted")
    if sae.get("workflow") != EXPECTED_SAE_WORKFLOW:
        raise StarterExampleError("the SAE marketplace prompt workflow has drifted")
    sae_contract = _object(
        sae.get("reproducibility_contract") if sae else None,
        "SAE tutorial reproducibility contract",
    )
    expected_sae_contract = {
        "active_value_threshold": 0.01,
        "active_value_comparator": ">",
        "rank_top_k_by_max_activation": 10,
        "rank_top_k_by_prevalence": 10,
        "describe_top_k_by_max_activation": 5,
        "map_top_k_by_max_activation": 3,
        "highlight_top_k_residues_per_mapped_feature": 10,
        "managed_requests": {"encode": 1, "logits": 1},
        "public_data_requests": {
            "rcsb_fasta": 1,
            "atlas_feature_detail": 5,
            "biohub_mcp_structure_view": 1,
        },
        "tokenization": "managed-encode",
        "normalize_features": True,
        "artifacts": [
            "2xnd-chain-a.fasta",
            "encode-raw-response.json",
            "logits-raw-response.json",
            "sae-features.npz",
            "feature-rankings.json",
            "atlas-feature-responses.json",
            "per-residue-activations.csv",
            "structure-view.json",
            "provenance.json",
        ],
    }
    if sae_contract != expected_sae_contract:
        raise StarterExampleError(
            "the SAE marketplace prompt must pin the official threshold, ranking, request, tokenization, and artifact contract"
        )

    fold = use_cases.get("esmfold2-all-atom-and-msa")
    fold_targets = _object(fold.get("targets") if fold else None, "ESMFold2 tutorial targets")
    modified = _object(
        fold_targets.get("modified_glp1r_peptide_linker"),
        "modified GLP-1R tutorial target",
    )
    receptor = _object(modified.get("receptor"), "modified GLP-1R receptor")
    linker = _object(modified.get("linker"), "modified GLP-1R linker")
    if (
        "not canonical untagged glp1r"
        not in _nonempty_string(
            receptor.get("construct_note"), "modified GLP-1R construct note"
        ).lower()
    ):
        raise StarterExampleError(
            "the GLP-1R marketplace prompt must disclose the tagged construct"
        )
    if (
        "not the exact therapeutic linker"
        not in _nonempty_string(linker.get("identity"), "modified GLP-1R linker identity").lower()
    ):
        raise StarterExampleError(
            "the GLP-1R marketplace prompt must disclose the representative linker"
        )


def _validate_esmc_view_colors(esmc_text: str) -> None:
    """Keep the colors that the esmc skill names equal to the pinned view colors."""

    groups = EXPECTED_MCP_STRUCTURE_VIEWS["esmc-mutation-landscape"]["highlight_groups"]
    colors = EXPECTED_MCP_STRUCTURE_VIEWS["esmc-sae-feature-interpretation"]["highlight_colors"]
    expected = (
        f"`summary.most_constrained` of `mutation-landscape.json` in `{groups[0]['color']}`",
        f"`summary.most_tolerant` in `{groups[1]['color']}`",
        "`" + "`, `".join(colors[:-1]) + f"`, and `{colors[-1]}`",
    )
    if any(phrase not in esmc_text for phrase in expected):
        raise StarterExampleError("the esmc skill must name the pinned Biohub MCP view colors")


def validate_tutorial_marketplace_surfaces(
    plugin_root: Path, contract: dict[str, Any]
) -> list[dict[str, str]]:
    """Reject drift between the tutorial prompt owner and every plugin-page surface."""

    resolved = resolve_marketplace_default_prompts(contract)
    plugin_root = plugin_root.resolve()
    surfaces = _object(contract.get("surface_contract"), "tutorial surface_contract")
    paths: dict[str, Path] = {}
    for field in (
        "manifest",
        "readme",
        "router_skill",
        "routing_reference",
        "activation_fixture",
    ):
        relative = _nonempty_string(surfaces.get(field), f"surface_contract.{field}")
        path = (plugin_root / relative).resolve()
        if not path.is_relative_to(plugin_root) or not path.is_file():
            raise StarterExampleError(f"tutorial surface {field} is missing or outside the plugin")
        paths[field] = path

    manifest = _load_json_object(paths["manifest"], "plugin manifest")
    expected_texts = [prompt["text"] for prompt in resolved]
    if manifest.get("interface", {}).get("defaultPrompt") != expected_texts:
        raise StarterExampleError(
            "manifest defaultPrompt has drifted from tutorial marketplace defaults"
        )

    for field in ("readme", "router_skill", "routing_reference"):
        text = paths[field].read_text(encoding="utf-8")
        missing = [prompt for prompt in expected_texts if prompt not in text]
        if missing:
            raise StarterExampleError(
                f"{field} is missing {len(missing)} tutorial marketplace prompt(s)"
            )
    for field in ("router_skill", "routing_reference"):
        text = " ".join(paths[field].read_text(encoding="utf-8").split())
        for clause in (
            "259-request managed runtime and its one Biohub MCP structure view",
            "and Atlas requests and its one Biohub MCP structure view",
        ):
            if clause not in text:
                raise StarterExampleError(
                    f"{field} must authorize each ESMC launcher's one Biohub MCP view"
                )

    specialist_skills = _object(
        surfaces.get("specialist_skills"), "surface_contract.specialist_skills"
    )
    expected_specialists = {prompt["skill"] for prompt in resolved}
    if set(specialist_skills) != expected_specialists:
        raise StarterExampleError(
            "surface_contract.specialist_skills must cover every marketplace specialist"
        )
    for skill, relative_value in specialist_skills.items():
        relative = _nonempty_string(relative_value, f"surface_contract.specialist_skills.{skill}")
        path = (plugin_root / relative).resolve()
        if not path.is_relative_to(plugin_root) or not path.is_file():
            raise StarterExampleError(f"tutorial specialist surface for {skill} is missing")
        text = path.read_text(encoding="utf-8")
        missing = [
            prompt["text"]
            for prompt in resolved
            if prompt["skill"] == skill and prompt["text"] not in text
        ]
        if missing:
            raise StarterExampleError(
                f"specialist surface {skill} is missing {len(missing)} marketplace prompt(s)"
            )
        if skill == "esmc":
            _validate_esmc_view_colors(" ".join(text.split()))

    try:
        activation_cases = json.loads(paths["activation_fixture"].read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StarterExampleError("activation fixture is not valid JSON") from exc
    if not isinstance(activation_cases, list):
        raise StarterExampleError("activation fixture must be a list")
    activation_by_prompt = {
        case.get("prompt"): case.get("expected")
        for case in activation_cases
        if isinstance(case, dict)
    }
    for prompt in resolved:
        if activation_by_prompt.get(prompt["text"]) != prompt["skill"]:
            raise StarterExampleError(
                f"activation fixture has drifted for tutorial prompt {prompt['id']}"
            )
    return resolved


def validate_starter_examples_file(plugin_root: Path) -> dict[str, Any]:
    path = plugin_root / "examples" / "starter-examples.json"
    validated = validate_starter_example_surfaces(plugin_root, load_starter_examples(path))
    tutorial_path = plugin_root / "examples" / "tutorial-use-cases.json"
    validate_tutorial_marketplace_surfaces(
        plugin_root,
        load_tutorial_use_cases(tutorial_path),
    )
    return validated

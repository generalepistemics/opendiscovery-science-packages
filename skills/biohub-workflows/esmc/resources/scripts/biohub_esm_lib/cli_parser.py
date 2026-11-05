"""Argument parser for the Biohub ESM command-line interface."""

from __future__ import annotations

import argparse
from types import ModuleType

from .constants import BIOHUB_BASE_URL, ESMC_MANAGED_MODELS


def _bool_flag(parser: argparse.ArgumentParser, name: str, help_text: str) -> None:
    parser.add_argument(name, action="store_true", help=help_text)


def build_parser(commands: ModuleType, *, description: str | None) -> argparse.ArgumentParser:
    """Construct the CLI while resolving handlers from their existing module."""

    parser = argparse.ArgumentParser(description=description)
    sub = parser.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser(
        "preflight", help="report configured/missing/unverified credential status without values"
    )
    preflight.add_argument(
        "--endpoint",
        choices=["fold", "fold_all_atom"],
        help="also verify the selected managed structure serializer",
    )
    preflight.set_defaults(func=commands.command_preflight)
    pins = sub.add_parser("pins", help="print pinned SDK builds and upstream revisions")
    pins.set_defaults(func=commands.command_pins)
    verify_install = sub.add_parser(
        "verify-install",
        help="verify the installed esm and Transformers wheels match their pins",
    )
    verify_install.set_defaults(func=commands.command_verify_install)

    route = sub.add_parser("route", help="select the scientifically appropriate execution route")
    route.add_argument("--task", choices=["atlas", "esmc", "fold"], required=True)
    route.add_argument("--item-count", type=int, default=1)
    for flag, help_text in (
        ("--long-running", "workflow requires durable long-running execution"),
        ("--bulk-dataset", "request is for public Atlas bulk data"),
        ("--private", "input cannot leave user-owned infrastructure"),
        ("--offline", "execution must be offline or air-gapped"),
        ("--data-residency", "execution has data-residency constraints"),
        ("--custom-model", "custom model or head is required"),
        ("--fine-tune", "fine-tuning is required"),
        ("--sustained-workload", "workload is sustained rather than interactive"),
        ("--has-msa", "an MSA is available and should condition folding"),
        ("--accuracy-priority", "prefer accuracy over throughput"),
        ("--owns-gpu", "user owns suitable GPU infrastructure"),
    ):
        _bool_flag(route, flag, help_text)
    route.set_defaults(func=commands.command_route)

    sequence = sub.add_parser("validate-sequence", help="validate and digest a sequence")
    sequence.add_argument("--target", choices=["esmc", "atlas-search", "atlas-fold"], required=True)
    source = sequence.add_mutually_exclusive_group(required=True)
    source.add_argument("--sequence")
    source.add_argument("--sequence-file")
    sequence.set_defaults(func=commands.command_validate_sequence)

    fold = sub.add_parser(
        "validate-fold", help="validate ESMFold2 input and route-aware parameters"
    )
    fold.add_argument("--input", required=True)
    fold.add_argument("--config")
    fold.add_argument("--model", required=True)
    fold.add_argument(
        "--endpoint",
        choices=["fold", "fold_all_atom"],
        default="fold_all_atom",
    )
    fold.add_argument("--require-msa", action="store_true")
    fold.add_argument("--require-msa-insertions-removed", action="store_true")
    fold.add_argument("--require-paired-msa-keys", action="store_true")
    fold.add_argument("--msa-max-depth", type=int)
    fold.set_defaults(func=commands.command_validate_fold)

    managed = sub.add_parser("managed-post", help="send an allowlisted managed API JSON contract")
    managed.add_argument(
        "--endpoint", choices=["encode", "logits", "fold", "fold_all_atom"], required=True
    )
    managed.add_argument("--input", required=True)
    managed.add_argument("--output-dir")
    managed.add_argument("--timeout", type=float, default=120)
    managed.set_defaults(func=commands.command_managed_post)

    recover = sub.add_parser(
        "managed-recover",
        help="materialize one saved managed fold response without provider access",
    )
    recover.add_argument("--endpoint", choices=["fold", "fold_all_atom"], required=True)
    recover.add_argument("--input", required=True, help="the exact validated request JSON")
    recover.add_argument("--raw-response", required=True, help="the saved provider response JSON")
    recover.add_argument(
        "--source-provenance",
        help="original provenance; defaults to provenance.json beside the raw response",
    )
    recover.add_argument("--output-dir", required=True)
    recover.set_defaults(func=commands.command_managed_recover)

    mutation_score = sub.add_parser(
        "esmc-mutation-score",
        help="score one substitution in one exact masked ESMC context",
    )
    mutation_source = mutation_score.add_mutually_exclusive_group(required=True)
    mutation_source.add_argument("--sequence")
    mutation_source.add_argument("--sequence-file")
    mutation_score.add_argument("--mutation", required=True)
    mutation_score.add_argument(
        "--model",
        choices=sorted(ESMC_MANAGED_MODELS),
        default="esmc-600m-2024-12",
    )
    mutation_score.add_argument("--output-dir", required=True)
    mutation_score.add_argument("--timeout", type=float, default=120)
    mutation_score.set_defaults(func=commands.command_esmc_mutation_score)

    landscape = sub.add_parser(
        "esmc-landscape",
        help="run a deterministic managed ESMC single-mask mutation landscape",
    )
    landscape_source = landscape.add_mutually_exclusive_group(required=True)
    landscape_source.add_argument("--sequence")
    landscape_source.add_argument("--sequence-file")
    landscape_source.add_argument(
        "--tutorial",
        choices=["petase"],
        help="use the pinned official CaPETase tutorial sequence",
    )
    landscape.add_argument(
        "--model",
        choices=sorted(ESMC_MANAGED_MODELS),
        default="esmc-600m-2024-12",
    )
    landscape.add_argument("--output-dir", required=True)
    landscape.add_argument("--max-workers", type=int, default=16)
    landscape.add_argument("--timeout", type=float, default=120)
    landscape.add_argument(
        "--resume",
        action="store_true",
        help="resume only request-bound completed checkpoints from an existing output directory",
    )
    landscape.set_defaults(func=commands.command_esmc_landscape)

    atlas = sub.add_parser("atlas", help="call the public Atlas alpha API")
    atlas.set_defaults(base_url=BIOHUB_BASE_URL)
    atlas.add_argument("--timeout", type=float, default=120)
    atlas_sub = atlas.add_subparsers(dest="atlas_command", required=True)

    search = atlas_sub.add_parser("search")
    search.add_argument("--sequence", required=True)
    search.add_argument("--topk-results", type=int, default=10)
    search.add_argument("--topk-features", type=int, default=20)
    search.add_argument("--min-similarity", type=float, default=0.5)
    search.add_argument("--cluster-pct-characterized-max", type=int)
    search.add_argument("--include-cluster-info", action="store_true")
    search.add_argument("--output-dir")
    search.set_defaults(func=commands.command_atlas_search)

    protein = atlas_sub.add_parser("protein")
    protein.add_argument("--protein-hash", required=True)
    protein.add_argument("--topk-features", type=int, default=10)
    fold_on_miss = protein.add_mutually_exclusive_group()
    fold_on_miss.add_argument(
        "--fold-on-miss",
        dest="fold_on_miss",
        action="store_true",
        help="explicitly request an on-demand fold when the stored structure is missing",
    )
    fold_on_miss.add_argument(
        "--no-fold-on-miss",
        dest="fold_on_miss",
        action="store_false",
        help="return only structures already stored by Atlas",
    )
    protein.add_argument("--raw-features", action="store_true")
    protein.add_argument("--feature-index", type=int, action="append")
    protein.add_argument("--output-dir")
    protein.set_defaults(func=commands.command_atlas_protein, fold_on_miss=False)

    cluster = atlas_sub.add_parser("cluster")
    cluster.add_argument("--protein-hash", required=True)
    cluster.add_argument("--topk-features", type=int, default=10)
    cluster.add_argument("--output-dir")
    cluster.set_defaults(func=commands.command_atlas_cluster)

    features = atlas_sub.add_parser("features")
    features.add_argument("--output-dir")
    features.set_defaults(func=commands.command_atlas_features)
    feature = atlas_sub.add_parser("feature")
    feature.add_argument("--feature-index", type=int, required=True)
    feature.add_argument("--output-dir")
    feature.set_defaults(func=commands.command_atlas_feature)
    thumbnail = atlas_sub.add_parser("thumbnail")
    thumbnail.add_argument("--protein-hash", required=True)
    thumbnail.add_argument(
        "--thumbnail-type", choices=["pct-characterized", "plddt"], required=True
    )
    thumbnail.add_argument("--output", required=True)
    thumbnail.set_defaults(func=commands.command_atlas_thumbnail)

    batch_submit = atlas_sub.add_parser("batch-submit")
    batch_submit.add_argument("--hashes", required=True)
    batch_submit.add_argument("--topk-features", type=int, default=10)
    batch_submit.add_argument("--no-structure", action="store_true")
    batch_submit.add_argument("--no-cluster-info", action="store_true")
    batch_submit.add_argument("--no-sequence", action="store_true")
    batch_submit.add_argument("--no-features", action="store_true")
    batch_submit.add_argument("--no-per-residue-features", action="store_true")
    batch_submit.add_argument("--output", required=True)
    batch_submit.add_argument("--state", required=True)
    batch_submit.set_defaults(func=commands.command_atlas_batch_submit)
    batch_status = atlas_sub.add_parser("batch-status")
    batch_status.add_argument("--state", required=True)
    batch_status.add_argument("--job-id")
    batch_status.set_defaults(func=commands.command_atlas_batch_status)
    batch_cancel = atlas_sub.add_parser("batch-cancel")
    batch_cancel.add_argument("--state", required=True)
    batch_cancel.add_argument("--job-id")
    batch_cancel.set_defaults(func=commands.command_atlas_batch_cancel)
    batch_wait = atlas_sub.add_parser("batch-wait")
    batch_wait.add_argument("--state", required=True)
    batch_wait.add_argument("--job-id")
    batch_wait.add_argument("--poll-interval", type=float, default=5)
    batch_wait.add_argument("--poll-timeout", type=float, default=1800)
    batch_wait.add_argument("--output")
    batch_wait.set_defaults(func=commands.command_atlas_batch_wait)

    modal = sub.add_parser(
        "modal-jobs", help="durable spawn/gather/cancel for a deployed Modal function"
    )
    modal_sub = modal.add_subparsers(dest="modal_command", required=True)
    for name, function in (
        ("spawn", commands.command_modal_spawn),
        ("gather", commands.command_modal_gather),
        ("cancel", commands.command_modal_cancel),
    ):
        command = modal_sub.add_parser(name)
        command.add_argument("--state", required=True)
        command.add_argument("--workspace-name", required=True)
        command.add_argument("--environment-name", required=True)
        command.add_argument("--app-name", required=True)
        command.add_argument("--function-name", required=True)
        command.add_argument("--function-version", type=int, required=True)
        if name == "spawn":
            command.add_argument("--input", required=True)
            command.add_argument("--kind", choices=["fold"], required=True)
            command.add_argument("--max-jobs", type=int, required=True)
            command.add_argument(
                "--confirm-cost",
                action="store_true",
                help=argparse.SUPPRESS,
            )
        elif name == "gather":
            command.add_argument("--timeout-per-call", type=float, default=1800)
        command.set_defaults(func=function)
    return parser

"""Explicit scientific and compute routing decision table."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .errors import ValidationError

Task = Literal["atlas", "esmc", "fold"]
Route = Literal["atlas-s3", "biohub", "biohub-mcp", "modal", "self-hosted"]


@dataclass(frozen=True)
class RouteRequest:
    task: Task
    item_count: int = 1
    long_running: bool = False
    bulk_dataset: bool = False
    private: bool = False
    offline: bool = False
    data_residency: bool = False
    custom_model: bool = False
    fine_tune: bool = False
    sustained_workload: bool = False
    has_msa: bool = False
    accuracy_priority: bool = False
    owns_gpu: bool = False


@dataclass(frozen=True)
class RouteResult:
    route: Route
    model: str | None
    required_authentication: str | None
    rationale: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def route_request(request: RouteRequest) -> RouteResult:
    if request.task not in {"atlas", "esmc", "fold"}:
        raise ValidationError(f"unsupported task: {request.task}")
    if request.item_count < 1:
        raise ValidationError("item_count must be at least 1")

    private_execution = any(
        (
            request.private,
            request.offline,
            request.data_residency,
            request.custom_model,
            request.fine_tune,
            request.sustained_workload,
        )
    )

    if request.task == "atlas":
        if private_execution or request.bulk_dataset:
            rationale = (
                "Private/offline Atlas work must stage the public dataset locally; do not send "
                "a private query to the public API."
                if private_execution
                else "Atlas bulk datasets are public through anonymous S3."
            )
            return RouteResult(
                route="atlas-s3",
                model=None,
                required_authentication=None,
                rationale=(rationale,),
                warnings=(
                    "Atlas data is CC-BY-4.0; preserve attribution and dataset provenance.",
                    "Atlas data is very large; plan the transfer, storage, and local-search footprint.",
                    (
                        "Before any multi-gigabyte or multi-terabyte Atlas S3 transfer, "
                        "freeze the exact source prefix, destination, estimated bytes, "
                        "storage and egress impact, and cost ceiling; then obtain separate "
                        "explicit current-turn confirmation."
                    ),
                ),
            )
        return RouteResult(
            route="biohub-mcp",
            model=None,
            required_authentication=None,
            rationale=(
                "Protein discovery, cluster context, feature detail, and structure views go "
                "through the anonymous public Biohub MCP.",
            ),
            warnings=(
                "The plugin script still serves the Atlas feature catalog, thumbnails, batch "
                "jobs, and MD5-only records.",
            ),
        )

    if private_execution:
        hf_model = "biohub/ESMC-600M" if request.task == "esmc" else "biohub/ESMFold2"
        return RouteResult(
            route="self-hosted",
            model=hf_model,
            required_authentication=None,
            rationale=(
                (
                    "Private, offline, data-resident, customized, fine-tuned, or "
                    "sustained work belongs on user-owned compute."
                ),
                "Public weights do not require HF_TOKEN; it is optional for authenticated Hub access.",
            ),
        )

    if request.task == "esmc":
        if request.owns_gpu:
            return RouteResult(
                route="self-hosted",
                model="biohub/ESMC-600M",
                required_authentication=None,
                rationale=(
                    (
                        "Suitable user-owned GPUs favor pinned self-hosted public weights; "
                        "HF_TOKEN is optional for authenticated Hub access."
                    ),
                ),
            )
        return RouteResult(
            route="biohub",
            model="esmc-600m-2024-12",
            required_authentication="ESM_API_KEY",
            rationale=(
                (
                    "Biohub managed ESMC is the default for public inference, including "
                    "bounded concurrent calls that the managed backend can auto-batch."
                ),
                "The plugin does not ship an ESMC Modal function.",
            ),
        )

    # This is a folding orchestration heuristic, not an account quota. Account
    # credits and rate limits remain specific to the Biohub developer console at
    # https://biohub.ai/developer-console (keys: /developer-console/api-keys).
    scale_out = request.long_running or request.item_count > 32
    if scale_out:
        model = (
            "biohub/ESMFold2"
            if request.accuracy_priority or request.has_msa
            else "biohub/ESMFold2-Fast"
        )
        return RouteResult(
            route="self-hosted" if request.owns_gpu else "modal",
            model=model,
            required_authentication=(
                None if request.owns_gpu else "MODAL_TOKEN_ID + MODAL_TOKEN_SECRET or Modal profile"
            ),
            rationale=(
                "Independent bulk, parallel, or long-running inference should use durable scale-out compute.",
                (
                    "Suitable user-owned GPUs favor pinned self-hosted public weights; "
                    "HF_TOKEN is optional for authenticated Hub access."
                    if request.owns_gpu
                    else "Public weights on Modal do not require ESM_API_KEY."
                ),
            ),
            warnings=(
                ()
                if request.owns_gpu
                else (
                    (
                        "Before any Modal spawn, refresh current Modal pricing and "
                        "account/payment readiness; freeze and show the exact Modal "
                        "app/function, GPU type, job count, concurrency, timeout, "
                        "persistence plan, and cost ceiling."
                    ),
                    (
                        "Obtain separate explicit current-turn confirmation after that "
                        "frozen scope and current cost review. --confirm-cost is only an "
                        "execution backstop, not authorization."
                    ),
                )
            ),
        )

    model = (
        "esmfold2-2026-05"
        if request.accuracy_priority or request.has_msa
        else "esmfold2-fast-2026-05"
    )
    rationale = ["Biohub managed ESMFold2 is the default for modest interactive folding."]
    if request.has_msa:
        rationale.append("MSA conditioning requires the full ESMFold2 model, not Fast.")
    elif request.accuracy_priority:
        rationale.append("Accuracy-priority targets use full ESMFold2; Fast favors throughput.")
    else:
        rationale.append("ESMFold2-Fast favors single-sequence latency and throughput.")
    return RouteResult(
        route="biohub",
        model=model,
        required_authentication="ESM_API_KEY",
        rationale=tuple(rationale),
        warnings=(
            "Predicted structures are static hypotheses, not experimental truth or molecular dynamics.",
        ),
    )

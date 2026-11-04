#!/usr/bin/env python3
"""gtex-eqtl

Fetch GTEx single-tissue eQTL associations for one variant input.
Input JSON on stdin:
  - {"grch38":"10-112998590-C-T"}
  - {"grch37":"10:114758349:C:T","max_results":100}
  - {"rsid":"rs7903146","max_results":100}
  - "10-112998590-C-T"
Output JSON on stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "vendor"))

import requests
from variant_resolution import (
    VariantResolutionError,
    extract_variant_input,
    resolve_query_variant,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from database_source_contract import apply_source_contract  # noqa: E402

GTEX_API = "https://gtexportal.org/api/v2"
USER_AGENT = "gtex-eqtl-skill/1.0 (+requests)"
DEFAULT_TIMEOUT_S = 25
GTEX_MAX_ITEMS_PER_PAGE = 100_000


def error(code: str, message: str, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": code, "message": message},
        "warnings": warnings or [],
    }


def parse_input(payload: Any) -> tuple[str, str, int | None]:
    if isinstance(payload, str):
        return "grch38", payload.strip(), None

    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON string or object.")

    input_type, variant = extract_variant_input(payload, default_build_key="grch38")

    max_results = payload.get("max_results")
    if max_results is None:
        return input_type, variant, None

    if not isinstance(max_results, int) or max_results <= 0:
        raise ValueError("`max_results` must be a positive integer when provided.")
    return input_type, variant, max_results


def build_variant_id(parsed: dict[str, Any]) -> str:
    return f"chr{parsed['chr']}_{parsed['pos']}_{parsed['ref']}_{parsed['alt']}_b38"


def _paging_int(paging_info: Any, key: str) -> int | None:
    if not isinstance(paging_info, dict):
        return None
    value = paging_info.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def fetch_eqtls(
    variant_id: str, max_results: int | None
) -> tuple[list[Any], int, dict[str, Any] | None]:
    url = f"{GTEX_API}/association/singleTissueEqtl"
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }

    page_size = min(max_results or GTEX_MAX_ITEMS_PER_PAGE, GTEX_MAX_ITEMS_PER_PAGE)
    page = 0
    rows: list[Any] = []
    total: int | None = None
    first_paging_info: dict[str, Any] | None = None

    session = requests.Session()
    try:
        while True:
            params = {
                "variantId": variant_id,
                "page": page,
                "itemsPerPage": page_size,
            }
            resp = session.get(
                url,
                params=params,
                headers=headers,
                timeout=DEFAULT_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            page_rows = extract_rows(data)

            remaining = None if max_results is None else max_results - len(rows)
            if remaining is not None:
                page_rows = page_rows[:remaining]
            rows.extend(page_rows)

            paging_info = data.get("paging_info") if isinstance(data, dict) else None
            if first_paging_info is None and isinstance(paging_info, dict):
                first_paging_info = paging_info

            reported_total = _paging_int(paging_info, "totalNumberOfItems")
            if reported_total is not None:
                total = reported_total

            if max_results is not None and len(rows) >= max_results:
                break

            number_of_pages = _paging_int(paging_info, "numberOfPages")
            current_page = _paging_int(paging_info, "page")
            if current_page is None:
                current_page = page
            if number_of_pages is None or current_page + 1 >= number_of_pages or not page_rows:
                break
            page = current_page + 1
    finally:
        session.close()

    return rows, total if total is not None else len(rows), first_paging_info


def extract_rows(data: Any) -> list[Any]:
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data, list):
        return data
    return []


def main() -> int:
    warnings: list[str] = []

    try:
        payload = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001
        sys.stdout.write(json.dumps(error("invalid_json", f"Could not parse JSON input: {exc}")))
        return 2

    try:
        input_type, input_variant, max_results = parse_input(payload)
    except ValueError as exc:
        sys.stdout.write(json.dumps(error("invalid_input", str(exc))))
        return 2

    try:
        resolution = resolve_query_variant(
            input_type=input_type,
            input_value=input_variant,
            target_build="GRCh38",
        )
        parsed = dict(resolution["query_variant"])
        parsed["variant_id"] = build_variant_id(parsed)
        warnings.extend(resolution["warnings"])
    except VariantResolutionError as exc:
        sys.stdout.write(json.dumps(error(exc.code, exc.message, exc.warnings)))
        return 1
    except requests.RequestException as exc:
        sys.stdout.write(
            json.dumps(
                error(
                    "network_error",
                    f"Variant resolution failed ({type(exc).__name__}).",
                )
            )
        )
        return 1

    try:
        rows, total, paging_info = fetch_eqtls(parsed["variant_id"], max_results)
    except requests.RequestException as exc:
        sys.stdout.write(
            json.dumps(error("network_error", f"GTEx request failed ({type(exc).__name__})."))
        )
        return 1
    except ValueError as exc:
        sys.stdout.write(json.dumps(error("invalid_response", f"GTEx returned non-JSON: {exc}")))
        return 1

    truncated = total > len(rows)

    output = {
        "ok": True,
        "source": "gtex-v2",
        "input": resolution["input"],
        "query_variant": parsed,
        "eqtl_count": len(rows),
        "eqtl_count_total": total,
        "truncated": truncated,
        "eqtls": rows,
        "paging_info": paging_info,
        "warnings": warnings,
    }
    output = apply_source_contract(
        output,
        "gtex-eqtl-skill",
        f"{GTEX_API}/association/singleTissueEqtl",
    )
    sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

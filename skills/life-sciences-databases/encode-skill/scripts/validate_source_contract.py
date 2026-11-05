"""Validate exhaustive, standalone source coverage for every database skill."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PLUGIN_ROOT / "skills"
REGISTRY_PATH = PLUGIN_ROOT / "references" / "source-links.json"
CONTRACT_PATH = PLUGIN_ROOT / "references" / "source-presentation.md"
HELPER_PATH = PLUGIN_ROOT / "scripts" / "database_source_contract.py"
REST_CLIENT_PATH = PLUGIN_ROOT / "scripts" / "database_rest_client.py"
VARIANT_HELPER_PATH = PLUGIN_ROOT / "scripts" / "database_variant_resolution.py"
MARKER = "<!-- source-presentation-contract:v2 -->"


def _authority_has_port_delimiter(netloc: str) -> bool:
    """Return whether an authority explicitly delimits a port, including an empty one."""
    authority = netloc.rsplit("@", 1)[-1]
    if authority.startswith("["):
        closing_bracket = authority.find("]")
        return closing_bracket >= 0 and authority[closing_bracket + 1 :].startswith(":")
    return ":" in authority


def _is_valid_request_prefix(prefix: object) -> bool:
    if not isinstance(prefix, str):
        return False
    try:
        parts = urlsplit(prefix)
        port = parts.port
    except (TypeError, ValueError):
        return False
    return bool(
        parts.scheme == "https"
        and parts.hostname
        and parts.username is None
        and parts.password is None
        and port is None
        and not _authority_has_port_delimiter(parts.netloc)
        and not parts.query
        and not parts.fragment
    )


def _request_scope(url: str) -> tuple[str, str] | None:
    if not _is_valid_request_prefix(url):
        return None
    parts = urlsplit(url)
    hostname = parts.hostname
    if hostname is None:
        return None
    segments = [segment for segment in parts.path.split("/") if segment]
    path = "/" + "/".join(segments) if segments else "/"
    return hostname.casefold(), path


def _is_registered_base_url(
    url: object, request_prefixes: list[object], exact_base_urls: list[object]
) -> bool:
    if not isinstance(url, str):
        return False
    scope = _request_scope(url)
    if scope is None:
        return False
    hostname, path = scope
    for prefix in request_prefixes:
        if not isinstance(prefix, str):
            continue
        prefix_scope = _request_scope(prefix)
        if prefix_scope is None:
            continue
        prefix_host, prefix_path = prefix_scope
        if hostname == prefix_host and (
            prefix_path == "/"
            or path == prefix_path
            or path.startswith(prefix_path.rstrip("/") + "/")
        ):
            return True
    return any(
        isinstance(base_url, str) and scope == _request_scope(base_url)
        for base_url in exact_base_urls
    )


def _documented_rest_payloads(document: str) -> list[dict[str, object]]:
    heading = re.search(r"^- Common .* patterns:\s*$", document, flags=re.MULTILINE)
    if heading is None:
        return []
    section_end = document.find("\n## Output", heading.end())
    if section_end < 0:
        return []
    payloads: list[dict[str, object]] = []
    for line in document[heading.end() : section_end].splitlines():
        match = re.search(r"\{.*\}", line)
        if match is None:
            continue
        try:
            payload = json.loads(match.group(0))
        except ValueError:
            continue
        if isinstance(payload, dict) and "base_url" in payload:
            payloads.append(payload)
    return payloads


def _has_unsafe_exception_interpolation(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.FormattedValue)
        and isinstance(node.value, ast.Name)
        and node.value.id in {"exc", "error"}
        for node in ast.walk(tree)
    )


def validate() -> list[str]:
    errors: list[str] = []
    documented_rest_payload_count = 0
    skill_dirs = sorted(path for path in SKILLS_ROOT.iterdir() if (path / "SKILL.md").is_file())
    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"Could not read source registry: {exc}"]
    entries = registry.get("skills")
    if not isinstance(entries, dict):
        return ["Source registry must contain a skills object"]
    expected = {path.name for path in skill_dirs}
    for name in sorted(expected - entries.keys()):
        errors.append(f"Registry is missing skill: {name}")
    for name in sorted(entries.keys() - expected):
        errors.append(f"Registry contains unknown skill: {name}")

    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    for term in (
        "checked_sources",
        "supports_claim",
        "Raw JSON",
        "claim-adjacent",
        "never invent",
    ):
        if term.casefold() not in contract.casefold():
            errors.append(f"Source-presentation contract is missing: {term}")

    for skill_dir in skill_dirs:
        name = skill_dir.name
        document = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        if MARKER not in document:
            errors.append(f"{name}: missing source-presentation contract marker")
        for phrase in (
            "claim-adjacent",
            "checked_sources",
            "canonical_url",
            "raw or machine-readable output unchanged",
            f"Use the `{name}` entry in `../../references/source-links.json`",
            "../../references/source-presentation.md",
        ):
            if phrase not in document:
                errors.append(f"{name}: missing source-presentation rule: {phrase}")

        entry = entries.get(name)
        if not isinstance(entry, dict):
            continue
        if not isinstance(entry.get("source_name"), str) or not entry["source_name"].strip():
            errors.append(f"{name}: source_name must be a nonempty string")
        homepage = entry.get("homepage_url")
        if homepage is not None and (
            not isinstance(homepage, str)
            or urlsplit(homepage).scheme != "https"
            or not urlsplit(homepage).hostname
        ):
            errors.append(f"{name}: homepage_url must be a valid HTTPS URL")
        if (skill_dir / "scripts" / "rest_request.py").is_file():
            prefixes = entry.get("request_url_prefixes")
            if (
                not isinstance(prefixes, list)
                or not prefixes
                or not all(_is_valid_request_prefix(prefix) for prefix in prefixes)
            ):
                errors.append(
                    f"{name}: rest_request.py requires explicit HTTPS request_url_prefixes"
                )
                prefixes = []
            exact_base_urls = entry.get("request_base_urls", [])
            if not isinstance(exact_base_urls, list) or not all(
                _is_valid_request_prefix(base_url) for base_url in exact_base_urls
            ):
                errors.append(f"{name}: request_base_urls must be a list of exact HTTPS URLs")
                exact_base_urls = []
            prefix_origins = {
                _request_scope(prefix)[:1]
                for prefix in prefixes
                if isinstance(prefix, str) and _request_scope(prefix) is not None
            }
            for base_url in exact_base_urls:
                base_scope = _request_scope(base_url)
                if base_scope is not None and base_scope[:1] not in prefix_origins:
                    errors.append(
                        f"{name}: exceptional base URL must share a registered request origin: "
                        f"{base_url}"
                    )

            documented_payloads = _documented_rest_payloads(document)
            documented_rest_payload_count += len(documented_payloads)
            if not documented_payloads:
                errors.append(f"{name}: no documented common REST payloads were found")
            for index, payload in enumerate(documented_payloads):
                base_url = payload.get("base_url")
                if not _is_registered_base_url(base_url, prefixes, exact_base_urls):
                    errors.append(
                        f"{name}: documented REST payload {index} uses an unregistered "
                        f"base URL: {base_url}"
                    )
        templates = entry.get("record_url_templates")
        if not isinstance(templates, list):
            errors.append(f"{name}: record_url_templates must be a list")
            continue
        for index, template in enumerate(templates):
            if not isinstance(template, dict):
                errors.append(f"{name}: record URL template {index} must be an object")
                continue
            url = template.get("template")
            if not isinstance(url, str) or not url.startswith("https://") or "{id}" not in url:
                errors.append(
                    f"{name}: record URL template {index} must be HTTPS and contain {{id}}"
                )
            fields = template.get("identifier_fields")
            if (
                not isinstance(fields, list)
                or not fields
                or not all(isinstance(item, str) and item for item in fields)
            ):
                errors.append(
                    f"{name}: record URL template {index} must name explicit identifier fields"
                )
            if template.get("transform") not in (
                None,
                "strip_clinvar_vcv",
                "strip_rhea_prefix",
            ):
                errors.append(f"{name}: record URL template {index} has an unsupported transform")

        runtime_scripts = [
            path
            for path in sorted((skill_dir / "scripts").glob("*.py"))
            if not path.name.startswith("test_") and path.name != "variant_resolution.py"
        ]
        if not runtime_scripts:
            errors.append(f"{name}: no runtime client found")
        for script in runtime_scripts:
            source = script.read_text(encoding="utf-8")
            try:
                ast.parse(source, filename=str(script))
            except SyntaxError as exc:
                errors.append(f"{name}: invalid Python in {script.name}: {exc}")
            if "apply_source_contract" not in source:
                errors.append(
                    f"{name}: {script.name} does not apply evidence-aware source metadata"
                )
            if script.name == "rest_request.py" and "is_registered_source_base_url" not in source:
                errors.append(
                    f"{name}: rest_request.py does not independently validate its base URL scope"
                )

        variant_helper = skill_dir / "scripts" / "variant_resolution.py"
        if variant_helper.is_file():
            variant_source = variant_helper.read_text(encoding="utf-8")
            try:
                tree = ast.parse(variant_source, filename=str(variant_helper))
            except SyntaxError as exc:
                errors.append(f"{name}: invalid variant-resolution helper: {exc}")
                continue
            if _has_unsafe_exception_interpolation(tree):
                errors.append(
                    f"{name}: variant-resolution warning interpolates an unsafe upstream exception"
                )

    for path, label in (
        (HELPER_PATH, "source-contract helper"),
        (REST_CLIENT_PATH, "REST client"),
        (VARIANT_HELPER_PATH, "variant-resolution helper"),
    ):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            errors.append(f"Shared {label} is invalid: {exc}")
            continue
        if path == VARIANT_HELPER_PATH and _has_unsafe_exception_interpolation(tree):
            errors.append(
                "Shared variant-resolution helper interpolates an unsafe upstream exception"
            )
    rest_skill_count = sum(
        (skill_dir / "scripts" / "rest_request.py").is_file() for skill_dir in skill_dirs
    )
    if documented_rest_payload_count < rest_skill_count:
        errors.append(
            "Every REST-backed skill needs at least one documented request; "
            f"found {documented_rest_payload_count} requests for {rest_skill_count} skills"
        )
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    skills = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["skills"]
    template_count = sum(len(item["record_url_templates"]) for item in skills.values())
    print(
        f"Source contract validated: {len(skills)} skills and {template_count} canonical URL templates."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

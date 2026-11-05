"""Evidence-aware provenance and deterministic public record links."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "references" / "source-links.json"
REDACTED = "REDACTED"

_SECRET_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "bearer",
        "client_secret",
        "code",
        "credential",
        "credentials",
        "email",
        "jwt",
        "key",
        "password",
        "phpsessid",
        "private_key",
        "refresh_token",
        "secret",
        "session",
        "sessionid",
        "sig",
        "signature",
        "sid",
        "sas",
        "token",
        "web_env",
        "webenv",
    }
)
_PRIVATE_QUERY_KEYS = frozenset(
    {
        "criteria",
        "diagnosis",
        "expr",
        "expression",
        "filter",
        "input",
        "keyword",
        "keywords",
        "patient",
        "prompt",
        "q",
        "query",
        "search",
        "sequence",
        "subject",
        "term",
        "terms",
        "text",
        "variables",
        "where",
    }
)
_NON_EVIDENCE_MODES = frozenset(
    {
        "check",
        "connectivity",
        "config",
        "empty",
        "egquery",
        "einfo",
        "enums",
        "field_sizes",
        "field_values",
        "fields",
        "health",
        "healthz",
        "info",
        "introspection",
        "espell",
        "metadata",
        "ping",
        "routing",
        "schema",
        "search_areas",
        "stats_size",
        "status",
        "service_info",
    }
)
_METADATA_FIELDS = frozenset(
    {
        "available",
        "apiversion",
        "build",
        "capabilities",
        "config",
        "configuration",
        "cost",
        "count",
        "cursor",
        "description",
        "duration",
        "endpoint",
        "exclude",
        "extensions",
        "fields",
        "health",
        "healthcheck",
        "head",
        "limit",
        "message",
        "meta",
        "metadata",
        "name",
        "next",
        "offset",
        "options",
        "ok",
        "operations",
        "page",
        "pages",
        "pagesize",
        "pagination",
        "queryoptions",
        "reachable",
        "schema",
        "schemaversion",
        "service",
        "servicestatus",
        "skip",
        "status",
        "timestamp",
        "title",
        "tracing",
        "total",
        "totalcount",
        "typename",
        "updated",
        "uptime",
        "url",
        "vars",
        "variables",
        "version",
        "validation",
    }
)
_ERROR_FIELDS = frozenset({"error", "errors"})
_DIAGNOSTIC_FIELDS = _ERROR_FIELDS | frozenset({"message", "messages", "warning", "warnings"})
_STRUCTURAL_METADATA_FIELDS = frozenset(
    {
        "cursor",
        "extensions",
        "meta",
        "metadata",
        "schema",
        "tracing",
        "type",
        "typename",
    }
)
_EMPTY_COUNT_FIELDS = (
    "record_count_returned",
    "association_count",
    "eqtl_count",
    "result_count",
    "returned_rows",
    "hit_count",
    "matches_count",
)
_RECORD_COLLECTION_FIELDS = (
    "records",
    "rows",
    "associations",
    "eqtls",
    "results",
    "items",
    "studies",
    "variants",
    "genes",
    "matches",
    "hits",
)
_GENERAL_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_DOI = re.compile(r"^10[.][0-9]{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)
_UNIPROT_ACCESSION = re.compile(
    r"(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9][A-Z0-9]{3}[0-9](?:[A-Z0-9]{4})?)",
    re.IGNORECASE,
)
_ENSEMBL_GENE = re.compile(r"ENS[A-Z]*G[0-9]{6,}(?:[.][0-9]+)?", re.IGNORECASE)
_VARIANT_COORDINATE = re.compile(
    r"(?:chr)?(?:[0-9]{1,2}|X|Y|MT)[-_:][0-9]+[-_:][ACGTN]+[-_:][ACGTN]+",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["skills"]


def _authority_has_port_delimiter(netloc: str) -> bool:
    """Return whether an authority explicitly delimits a port, including an empty one."""
    authority = netloc.rsplit("@", 1)[-1]
    if authority.startswith("["):
        closing_bracket = authority.find("]")
        return closing_bracket >= 0 and authority[closing_bracket + 1 :].startswith(":")
    return ":" in authority


def _normalized_hostname(url: str) -> tuple[str, int] | None:
    """Return a credential-free HTTPS hostname and effective port."""
    if any(character.isspace() or ord(character) < 32 or character == "\\" for character in url):
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
    except (TypeError, ValueError):
        return None
    if (
        parts.scheme.casefold() != "https"
        or not parts.netloc
        or parts.hostname is None
        or parts.username is not None
        or parts.password is not None
        or _authority_has_port_delimiter(parts.netloc)
        or port is not None
    ):
        return None
    hostname = parts.hostname
    if not hostname or hostname.endswith(".") or not hostname.isascii():
        return None
    try:
        normalized = hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError:
        return None
    return normalized, 443


def _normalized_source_scope(url: str) -> tuple[str, int, str] | None:
    """Return an exact HTTPS host, port, and normalized path scope."""
    normalized_host = _normalized_hostname(url)
    if normalized_host is None:
        return None
    try:
        path = urlsplit(url).path
    except ValueError:
        return None
    for _ in range(len(path) + 1):
        decoded = unquote(path)
        if decoded == path:
            break
        path = decoded
    else:
        return None
    if any(character.isspace() or ord(character) < 32 or character == "\\" for character in path):
        return None
    segments = [segment for segment in path.split("/") if segment]
    if any(segment.split(";", 1)[0] in {".", ".."} for segment in segments):
        return None
    normalized_path = "/" + "/".join(segments) if segments else "/"
    hostname, port = normalized_host
    return hostname, port, normalized_path


@lru_cache(maxsize=None)
def _trusted_source_prefixes(skill_name: str) -> tuple[tuple[str, int, str], ...]:
    """Load exact per-skill request URL scopes from the source registry."""
    entry = _registry().get(skill_name)
    if not isinstance(entry, dict):
        return ()
    prefixes: list[tuple[str, int, str]] = []
    for url in entry.get("request_url_prefixes", []):
        if not isinstance(url, str):
            continue
        normalized = _normalized_source_scope(url)
        if normalized is None or normalized in prefixes:
            continue
        prefixes.append(normalized)
    return tuple(prefixes)


@lru_cache(maxsize=None)
def _trusted_source_base_urls(skill_name: str) -> tuple[tuple[str, int, str], ...]:
    """Load exact exceptional base URLs that sit above a request scope."""
    entry = _registry().get(skill_name)
    if not isinstance(entry, dict):
        return ()
    base_urls: list[tuple[str, int, str]] = []
    for url in entry.get("request_base_urls", []):
        if not isinstance(url, str):
            continue
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        if parts.query or parts.fragment:
            continue
        normalized = _normalized_source_scope(url)
        if normalized is None or normalized in base_urls:
            continue
        base_urls.append(normalized)
    return tuple(base_urls)


def is_registered_source_origin(skill_name: str, url: str | None) -> bool:
    """Return whether a URL uses an exact registered request origin."""
    if not isinstance(url, str) or not url:
        return False
    normalized = _normalized_hostname(url)
    if normalized is None:
        return False
    return any(normalized == prefix[:2] for prefix in _trusted_source_prefixes(skill_name))


def is_registered_source_base_url(skill_name: str, url: str | None) -> bool:
    """Return whether a base URL is independently registered for this skill.

    A base normally has to be inside the same host-and-path request scope as the
    final URL. A small exact allowlist supports documented API roots that sit
    above a narrower request scope without broadening that request scope.
    """
    if not isinstance(url, str) or not url:
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.query or parts.fragment:
        return False
    normalized = _normalized_source_scope(url)
    if normalized is None:
        return False
    return is_registered_source_url(skill_name, url) or normalized in _trusted_source_base_urls(
        skill_name
    )


def is_registered_source_url(skill_name: str, url: str | None) -> bool:
    """Return whether an HTTPS URL is within an exact per-skill request scope."""
    if not isinstance(url, str) or not url:
        return False
    normalized = _normalized_source_scope(url)
    if normalized is None:
        return False
    hostname, port, path = normalized
    return any(
        hostname == prefix_host
        and port == prefix_port
        and (
            prefix_path == "/"
            or path == prefix_path
            or path.startswith(prefix_path.rstrip("/") + "/")
        )
        for prefix_host, prefix_port, prefix_path in _trusted_source_prefixes(skill_name)
    )


def sanitize_request_url(url: str | None) -> str | None:
    """Remove credentials, fragments, secrets, and user-supplied search text."""
    if not isinstance(url, str) or not url.strip():
        return None
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    sanitized_query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key)
        separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", separated)
        normalized = re.sub(r"[^a-z0-9]+", "_", separated.casefold()).strip("_")
        tokens = frozenset(normalized.split("_"))
        private = (
            normalized in _SECRET_QUERY_KEYS
            or normalized in _PRIVATE_QUERY_KEYS
            or bool(tokens & (_SECRET_QUERY_KEYS | _PRIVATE_QUERY_KEYS))
            or re.fullmatch(r"q[0-9]+", normalized) is not None
            or normalized.startswith(("query_", "search_", "filter_"))
            or normalized.endswith(
                (
                    "_credential",
                    "_jwt",
                    "_key",
                    "_password",
                    "_query",
                    "_secret",
                    "_sequence",
                    "_signature",
                    "_term",
                    "_token",
                )
            )
        )
        sanitized_query.append((key, REDACTED if private else value))
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(sanitized_query), ""))


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", key.casefold())


def _find_record_value(record: Any, field: str, depth: int = 0) -> Any:
    if depth > 5:
        return None
    wanted = _normalized_key(field)
    if isinstance(record, dict):
        for key, value in record.items():
            normalized = _normalized_key(str(key))
            if normalized in _DIAGNOSTIC_FIELDS:
                continue
            if normalized == wanted and value not in (None, ""):
                return value
        for key, value in record.items():
            if _normalized_key(str(key)) in _DIAGNOSTIC_FIELDS:
                continue
            if isinstance(value, (dict, list)):
                found = _find_record_value(value, field, depth + 1)
                if found is not None:
                    return found
    elif isinstance(record, list):
        for item in record[:20]:
            found = _find_record_value(item, field, depth + 1)
            if found is not None:
                return found
    return None


def _normalize_identifier(
    identifier_type: str,
    value: Any,
    transform: str | None,
    *,
    skill_name: str,
) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    identifier = str(value).strip()
    if not identifier or len(identifier) > 256:
        return None
    kind = identifier_type.casefold()
    if transform == "strip_clinvar_vcv":
        matched = re.fullmatch(r"(?:VCV)?0*([0-9]+)(?:[.][0-9]+)?", identifier, re.IGNORECASE)
        return matched.group(1) if matched else None
    if transform == "strip_rhea_prefix":
        matched = re.fullmatch(r"(?:RHEA:)?([0-9]+)", identifier, re.IGNORECASE)
        return matched.group(1) if matched else None
    if kind == "doi":
        if not _DOI.fullmatch(identifier):
            return None
        if any(segment in {".", ".."} for segment in identifier.split("/")):
            return None
        return identifier
    if not _GENERAL_IDENTIFIER.fullmatch(identifier):
        return None
    if kind in {"uniprot accession", "uniprotkb accession"}:
        return identifier.upper() if _UNIPROT_ACCESSION.fullmatch(identifier) else None
    if kind == "variant":
        if skill_name == "gwas-catalog-skill":
            return (
                identifier.lower() if re.fullmatch(r"rs[0-9]+", identifier, re.IGNORECASE) else None
            )
        return identifier if _VARIANT_COORDINATE.fullmatch(identifier) else None
    if kind == "variant id":
        if skill_name == "civic-skill":
            return identifier if identifier.isdigit() else None
        if skill_name == "pharmgkb-skill":
            return (
                identifier.upper() if re.fullmatch(r"PA[0-9]+", identifier, re.IGNORECASE) else None
            )
        return None
    if kind == "collection id":
        return (
            identifier.lower()
            if re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                identifier,
                re.IGNORECASE,
            )
            else None
        )
    if kind == "compound id":
        return (
            identifier.upper() if re.fullmatch(r"CHEMBL[0-9]+", identifier, re.IGNORECASE) else None
        )
    if kind == "target id":
        if skill_name == "chembl-skill":
            return (
                identifier.upper()
                if re.fullmatch(r"CHEMBL[0-9]+", identifier, re.IGNORECASE)
                else None
            )
        if skill_name == "opentargets-skill":
            return identifier if _ENSEMBL_GENE.fullmatch(identifier) else None
        return None
    if kind == "gene id":
        if skill_name == "pharmgkb-skill":
            return (
                identifier.upper() if re.fullmatch(r"PA[0-9]+", identifier, re.IGNORECASE) else None
            )
        if skill_name in {"gnomad-graphql-skill", "gtex-eqtl-skill"}:
            return identifier if _ENSEMBL_GENE.fullmatch(identifier) else None
        return None
    if kind == "study accession":
        patterns = {
            "biostudies-arrayexpress-skill": r"(?:E-[A-Z]+-[0-9]+|S-[A-Z0-9-]+|GSE[0-9]+)",
            "gwas-catalog-skill": r"GCST[0-9]+",
            "mgnify-skill": r"MGYS[0-9]+",
        }
        pattern = patterns.get(skill_name)
        return (
            identifier.upper()
            if pattern and re.fullmatch(pattern, identifier, re.IGNORECASE)
            else None
        )
    if kind == "encode accession":
        return (
            identifier.upper()
            if re.fullmatch(r"ENC[A-Z0-9]{6,}", identifier, re.IGNORECASE)
            else None
        )
    if kind == "association accession":
        return identifier if identifier.isdigit() else None
    if kind == "phenotype":
        return identifier if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", identifier) else None
    if kind == "gene symbol or ensembl gene id":
        if _ENSEMBL_GENE.fullmatch(identifier):
            return identifier
        return (
            identifier
            if re.fullmatch(r"[A-Z][A-Z0-9]{1,14}(?:-[A-Z0-9]{1,10})?", identifier)
            else None
        )
    if kind in {
        "pmid",
        "ncbi gene id",
        "compound cid",
        "substance sid",
        "assay aid",
        "evidence id",
    }:
        return identifier if identifier.isdigit() else None
    if kind == "nct id":
        return (
            identifier.upper() if re.fullmatch(r"NCT[0-9]{8}", identifier, re.IGNORECASE) else None
        )
    if kind == "refsnp id":
        return identifier.lower() if re.fullmatch(r"rs[0-9]+", identifier, re.IGNORECASE) else None
    if kind == "geo accession":
        return (
            identifier.upper()
            if re.fullmatch(r"(?:GSE|GSM|GPL|GDS)[0-9]+", identifier, re.IGNORECASE)
            else None
        )
    if kind == "pmcid":
        return (
            identifier.upper()
            if re.fullmatch(r"PMC[0-9]+(?:[.][0-9]+)?", identifier, re.IGNORECASE)
            else None
        )
    if kind == "pdb id":
        return identifier.upper() if re.fullmatch(r"[A-Za-z0-9]{4}", identifier) else None
    if kind == "reactome stable id":
        return identifier.upper() if re.fullmatch(r"R-[A-Za-z]{3}-[0-9]+", identifier) else None
    if kind == "go term":
        return (
            identifier.upper() if re.fullmatch(r"GO:[0-9]{7}", identifier, re.IGNORECASE) else None
        )
    if kind == "chebi id":
        return (
            identifier.upper() if re.fullmatch(r"CHEBI:[0-9]+", identifier, re.IGNORECASE) else None
        )
    if kind == "metabolights study accession":
        return (
            identifier.upper() if re.fullmatch(r"MTBLS[0-9]+", identifier, re.IGNORECASE) else None
        )
    if kind == "analysis accession":
        return (
            identifier.upper() if re.fullmatch(r"MGYA[0-9]+", identifier, re.IGNORECASE) else None
        )
    if kind == "sample accession":
        return (
            identifier.upper()
            if re.fullmatch(r"(?:SAMN|SAMD|SAMEA|ERS|SRS)[0-9]+", identifier, re.IGNORECASE)
            else None
        )
    if kind == "genome accession":
        return (
            identifier.upper()
            if re.fullmatch(r"(?:GCF|GCA)_[0-9]{9}(?:[.][0-9]+)?", identifier, re.IGNORECASE)
            else None
        )
    if kind == "disease id":
        return (
            identifier
            if re.fullmatch(
                r"(?:EFO|MONDO|HP|DOID|NCIT|OTAR|Orphanet)[_:][0-9]+",
                identifier,
                re.IGNORECASE,
            )
            else None
        )
    if kind == "chemical id":
        return identifier.upper() if re.fullmatch(r"PA[0-9]+", identifier, re.IGNORECASE) else None
    if kind == "pride project accession" or kind == "proteomexchange accession":
        return identifier.upper() if re.fullmatch(r"PXD[0-9]+", identifier, re.IGNORECASE) else None
    if kind == "uniref cluster":
        return identifier if re.fullmatch(r"UniRef(?:50|90|100)_[A-Z0-9_]+", identifier) else None
    if kind == "uniparc accession":
        return (
            identifier.upper()
            if re.fullmatch(r"UPI[A-Z0-9]{7,}", identifier, re.IGNORECASE)
            else None
        )
    if kind == "stable ensembl id":
        return (
            identifier
            if re.fullmatch(r"ENS[A-Z]*[GTPER][0-9]{6,}(?:[.][0-9]+)?", identifier, re.IGNORECASE)
            else None
        )
    if kind == "rnacentral id":
        return (
            identifier.upper()
            if re.fullmatch(r"URS[0-9A-F]{10,}", identifier, re.IGNORECASE)
            else None
        )
    if kind == "string protein identifier":
        return identifier if re.fullmatch(r"[0-9]+[.][A-Za-z0-9_.-]+", identifier) else None
    return None


def _canonical_record_urls(
    skill_name: str,
    record: dict[str, Any],
    *,
    database: str | None = None,
    identifier_type: str | None = None,
) -> list[str]:
    """Construct every public record page backed by an explicit, safe mapping."""
    if not isinstance(record, dict):
        return []
    entry = _registry().get(skill_name)
    if not isinstance(entry, dict):
        return []
    database_name = str(database or record.get("database") or record.get("db") or "").casefold()
    canonical_urls: list[str] = []
    for mapping in entry.get("record_url_templates", []):
        kind = mapping.get("identifier_type")
        if not isinstance(kind, str) or (identifier_type is not None and kind != identifier_type):
            continue
        fields = list(mapping.get("identifier_fields", []))
        if (
            skill_name == "civic-skill"
            and identifier_type in {"variant ID", "evidence ID"}
            and kind == identifier_type
        ):
            fields.extend(("id", "uid"))
        if skill_name == "ncbi-entrez-skill":
            if kind == "PMID" and database_name == "pubmed":
                fields.extend(("id", "uid"))
            elif kind == "PMCID" and database_name == "pmc":
                fields.extend(("id", "uid"))
            elif kind == "NCBI Gene ID" and database_name == "gene":
                fields.extend(("id", "uid"))
            elif kind == "PMID" and database_name and database_name != "pubmed":
                continue
            elif kind == "PMCID" and database_name and database_name != "pmc":
                continue
            elif kind == "NCBI Gene ID" and database_name and database_name != "gene":
                continue
        for field in fields:
            value = _find_record_value(record, field)
            if (
                kind == "PMCID"
                and database_name == "pmc"
                and isinstance(value, (int, str))
                and not isinstance(value, bool)
                and str(value).isdigit()
            ):
                value = f"PMC{value}"
            identifier = _normalize_identifier(
                kind, value, mapping.get("transform"), skill_name=skill_name
            )
            if identifier is None:
                continue
            template = mapping.get("template")
            if (
                not isinstance(template, str)
                or not template.startswith("https://")
                or "{id}" not in template
            ):
                continue
            encoded = quote(identifier, safe="/" if kind.casefold() == "doi" else "")
            canonical = template.replace("{id}", encoded)
            if canonical not in canonical_urls:
                canonical_urls.append(canonical)
            break
    return canonical_urls


def canonical_record_url(
    skill_name: str,
    record: dict[str, Any],
    *,
    database: str | None = None,
    identifier_type: str | None = None,
) -> str | None:
    """Construct the first deterministic public page backed by a safe mapping."""
    canonical_urls = _canonical_record_urls(
        skill_name,
        record,
        database=database,
        identifier_type=identifier_type,
    )
    return canonical_urls[0] if canonical_urls else None


def _has_substantive_value(value: Any) -> bool:
    """Find a nonempty scalar without depth limits or cycle risk."""
    pending = [value]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if current is None or current is False or current == "":
            continue
        if isinstance(current, (dict, list)):
            if id(current) in seen:
                continue
            seen.add(id(current))
            pending.extend(current.values() if isinstance(current, dict) else current)
            continue
        return True
    return False


def _is_zero_count(value: Any) -> bool:
    """Recognize numeric zero counts without coercing arbitrary strings."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value == 0
    if not isinstance(value, str):
        return False
    return (
        re.fullmatch(
            r"[+-]?(?:0+(?:[.]0*)?|[.]0+)(?:[eE][+-]?[0-9]+)?",
            value.strip(),
        )
        is not None
    )


def _has_collection_value(value: Any) -> bool:
    """Find a record value while ignoring structural metadata wrappers."""
    if not isinstance(value, (dict, list)):
        return False
    pending = [value]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, (dict, list)):
            if id(current) in seen:
                continue
            seen.add(id(current))
            if isinstance(current, dict):
                pending.extend(
                    child
                    for key, child in current.items()
                    if _normalized_key(str(key))
                    not in _DIAGNOSTIC_FIELDS | _STRUCTURAL_METADATA_FIELDS
                )
            else:
                pending.extend(current)
        elif not isinstance(current, bool) and current is not None and current != "":
            return True
    return False


def _has_identifier_collection_value(value: Any) -> bool:
    """Accept containers or a single positive numeric Entrez identifier."""
    if isinstance(value, (dict, list)):
        return _has_collection_value(value)
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    return isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0


def _summary_mode(summary: Any) -> str:
    """Classify nested response summaries with metadata-wrapper suppression."""
    if not _has_substantive_value(summary):
        return "empty"
    if not isinstance(summary, dict):
        return "evidence"
    normalized_collections = {_normalized_key(name) for name in _RECORD_COLLECTION_FIELDS}
    identifier_collections = {"idlist", "ids", "uids"}
    normalized_counts = {
        "associationcount",
        "count",
        "eqtlcount",
        "hitcount",
        "matchescount",
        "numresults",
        "numtotalresults",
        "recordcount",
        "recordcountreturned",
        "returnedrows",
        "resultcount",
        "total",
        "totalcount",
    }
    saw_empty = False
    saw_evidence = False
    saw_failure = False
    pending: list[tuple[dict[str, Any] | list[Any], bool]] = [(summary, False)]
    seen: set[int] = set()
    while pending:
        current, suppress_leaves = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, list):
            for item in current:
                if isinstance(item, (dict, list)):
                    pending.append((item, suppress_leaves))
                elif (
                    not suppress_leaves
                    and not isinstance(item, bool)
                    and _has_substantive_value(item)
                ):
                    saw_evidence = True
            continue
        for key, value in current.items():
            normalized = _normalized_key(str(key))
            if normalized in _STRUCTURAL_METADATA_FIELDS:
                continue
            if normalized in _DIAGNOSTIC_FIELDS:
                if normalized in _ERROR_FIELDS and _has_substantive_value(value):
                    saw_failure = True
                continue
            if normalized in normalized_collections:
                if _has_collection_value(value):
                    saw_evidence = True
                else:
                    saw_empty = True
            elif normalized in identifier_collections:
                if _has_identifier_collection_value(value):
                    saw_evidence = True
                else:
                    saw_empty = True
            elif normalized in normalized_counts:
                if _is_zero_count(value):
                    saw_empty = True
            elif normalized == "data" and not _has_substantive_value(value):
                saw_empty = True
            elif isinstance(value, (dict, list)):
                pending.append((value, suppress_leaves or normalized in _METADATA_FIELDS))
            elif (
                not suppress_leaves
                and normalized not in _METADATA_FIELDS
                and not isinstance(value, bool)
                and _has_substantive_value(value)
            ):
                saw_evidence = True
    if saw_evidence:
        return "evidence"
    if saw_failure:
        return "failure"
    if saw_empty:
        return "empty"
    return "metadata"


def _strip_reserved_canonical_fields(value: Any) -> None:
    """Remove untrusted upstream annotations before deciding whether evidence exists."""
    pending = [value]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if not isinstance(current, (dict, list)) or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, list):
            pending.extend(current)
            continue
        current.pop("canonical_url", None)
        current.pop("canonical_urls", None)
        pending.extend(child for child in current.values() if isinstance(child, (dict, list)))


def _evidence_mode(output: dict[str, Any], requested_mode: str | None) -> str:
    mode = str(requested_mode or output.get("mode") or output.get("action") or "").casefold()
    if mode in _NON_EVIDENCE_MODES:
        return mode
    if output.get("endpoint") in {
        "einfo",
        "egquery",
        "espell",
        "schema",
        "status",
        "health",
    }:
        return "metadata"
    path = str(output.get("path") or "").casefold().split("?", 1)[0].rstrip("/")
    if "meta" in path.split("/"):
        return "metadata"
    if path.rsplit("/", 1)[-1] in {
        "capabilities",
        "config",
        "configuration",
        "fields",
        "health",
        "healthz",
        "info",
        "introspection",
        "liveness",
        "metadata",
        "openapi",
        "openapi.json",
        "ping",
        "readiness",
        "ready",
        "schema",
        "service-info",
        "service_info",
        "status",
    }:
        return "metadata"
    summary = output.get("summary")
    summary_mode = _summary_mode(summary) if "summary" in output else None
    if summary_mode == "evidence":
        return "evidence"
    saw_record_collection = False
    for field in _RECORD_COLLECTION_FIELDS:
        if field in output:
            saw_record_collection = True
            if _has_collection_value(output[field]):
                return "evidence"
    if summary_mode == "failure":
        return "failure"
    if saw_record_collection:
        return "empty"
    for field in _EMPTY_COUNT_FIELDS:
        if field in output:
            value = output[field]
            if (
                isinstance(value, int) and not isinstance(value, bool) and value <= 0
            ) or _is_zero_count(value):
                return "empty"
    if summary_mode is not None:
        return summary_mode
    if output.get("text_head") or output.get("raw_output_path"):
        return "evidence"
    return "metadata"


def _annotate_records(
    value: Any,
    skill_name: str,
    urls: list[str],
    database: str | None,
    depth: int = 0,
    identifier_type: str | None = None,
) -> None:
    if depth > 5:
        return
    if isinstance(value, list):
        for item in value[:100]:
            _annotate_records(item, skill_name, urls, database, depth + 1, identifier_type)
        return
    if not isinstance(value, dict):
        if isinstance(value, (int, str)) and not isinstance(value, bool):
            canonical = canonical_record_url(skill_name, {"id": value}, database=database)
            if canonical is not None and canonical not in urls:
                urls.append(canonical)
        return
    record = value
    if skill_name == "pharmgkb-skill":
        object_class = value.get("objCls")
        identifier = value.get("id")
        if isinstance(object_class, str) and isinstance(identifier, (int, str)):
            identifier_field = {
                "chemical": "chemical_id",
                "gene": "gene_id",
                "variant": "variant_id",
            }.get(object_class.casefold())
            if identifier_field is not None:
                record = {**value, identifier_field: identifier}
    elif skill_name == "rhea-skill":
        accession = value.get("accession")
        if isinstance(accession, dict) and isinstance(accession.get("value"), str):
            record = {**value, "rhea_id": accession["value"]}
    record_urls = _canonical_record_urls(
        skill_name, record, database=database, identifier_type=identifier_type
    )
    if record_urls:
        value["canonical_url"] = record_urls[0]
        if len(record_urls) > 1:
            value["canonical_urls"] = record_urls
        else:
            value.pop("canonical_urls", None)
        for canonical in record_urls:
            if canonical not in urls:
                urls.append(canonical)
    else:
        value.pop("canonical_url", None)
        value.pop("canonical_urls", None)
    for key, child in list(value.items()):
        if (
            _normalized_key(str(key)) not in _DIAGNOSTIC_FIELDS
            and key
            not in {
                "sources",
                "checked_sources",
                "canonical_url",
                "canonical_urls",
            }
            and isinstance(child, (dict, list))
        ):
            context_type = None
            if skill_name == "civic-skill":
                normalized = _normalized_key(str(key))
                if normalized in {"variant", "variants"}:
                    context_type = "variant ID"
                elif normalized in {"evidence", "evidenceitem", "evidenceitems"}:
                    context_type = "evidence ID"
            _annotate_records(child, skill_name, urls, database, depth + 1, context_type)


def apply_source_contract(
    output: dict[str, Any],
    skill_name: str,
    request_url: str | None = None,
    *,
    mode: str | None = None,
) -> dict[str, Any]:
    """Attach evidence-only sources; retain empty/metadata checks separately."""
    if not isinstance(output, dict) or output.get("ok") is not True:
        return output
    entry = _registry().get(skill_name)
    if not isinstance(entry, dict):
        return output
    _strip_reserved_canonical_fields(output)
    sanitized_url = sanitize_request_url(request_url)
    kind = _evidence_mode(output, mode)
    canonical_urls: list[str] = []
    database = output.get("database") or output.get("db")
    if kind == "evidence":
        for field in (
            *_RECORD_COLLECTION_FIELDS,
            "summary",
            "matrix",
            "variant",
            "query_variant",
        ):
            if field in output:
                _annotate_records(
                    output[field],
                    skill_name,
                    canonical_urls,
                    str(database) if database else None,
                )
    source: dict[str, Any] = {
        "name": entry["source_name"],
        "url": (
            canonical_urls[0]
            if len(canonical_urls) == 1
            else sanitized_url or entry.get("homepage_url")
        ),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "supports_claim": kind == "evidence",
        "kind": "evidence" if kind == "evidence" else "checked",
    }
    if sanitized_url is not None:
        source["request_url"] = sanitized_url
    if canonical_urls:
        source["canonical_url"] = canonical_urls[0]
    if len(canonical_urls) > 1:
        source["canonical_urls"] = canonical_urls
    if kind == "evidence":
        existing = [
            item
            for item in output.get("sources", [])
            if isinstance(item, dict) and item.get("supports_claim") is True
        ]
        output["sources"] = existing + [source]
    else:
        source["reason"] = kind
        output.pop("sources", None)
        output.setdefault("checked_sources", []).append(source)
    return output


def evidence_sources(outputs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Propagate only actual evidence; never promote checked-but-empty sources."""
    collected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for output in outputs:
        if not isinstance(output, dict) or output.get("ok") is not True:
            continue
        for source in output.get("sources", []):
            if not isinstance(source, dict) or source.get("supports_claim") is not True:
                continue
            if source.get("kind") != "evidence":
                continue
            key = (
                str(source.get("name", "")),
                str(source.get("canonical_url") or source.get("url", "")),
            )
            if key not in seen:
                seen.add(key)
                collected.append(source)
    return collected

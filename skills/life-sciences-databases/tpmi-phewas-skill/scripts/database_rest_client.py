#!/usr/bin/env python3
"""Shared compact REST implementation for source-scoped database skills."""

from __future__ import annotations

import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from database_source_contract import (
    apply_source_contract,
    is_registered_source_base_url,
    is_registered_source_url,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vendor"))

try:
    import requests
except ImportError as exc:  # pragma: no cover
    requests = None
    REQUESTS_IMPORT_ERROR = exc
else:
    REQUESTS_IMPORT_ERROR = None


def error(code: str, message: str, warnings: list[str] | None = None) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}, "warnings": warnings or []}


def _require_object(name: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"`{name}` must be an object.")
    return value


def _require_headers(name: str, value: Any) -> dict[str, str]:
    headers = _require_object(name, value)
    reserved = {
        "connection",
        "content-length",
        "forwarded",
        "host",
        "keep-alive",
        "max-forwards",
        "proxy",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "via",
        "x-backend-host",
        "x-envoy-original-path",
        "x-forwarded",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-port",
        "x-forwarded-prefix",
        "x-forwarded-proto",
        "x-forwarded-uri",
        "x-host",
        "x-http-host-override",
        "x-http-method",
        "x-http-method-override",
        "x-method-override",
        "x-original-host",
        "x-original-uri",
        "x-original-url",
        "x-real-ip",
        "x-rewrite-host",
        "x-rewrite-url",
    }
    token = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
    for key, item in headers.items():
        normalized_key = key.casefold().replace("_", "-") if isinstance(key, str) else ""
        if (
            not isinstance(key, str)
            or not isinstance(item, str)
            or token.fullmatch(key) is None
            or normalized_key in reserved
            or normalized_key.startswith(("proxy-", "x-forwarded-", "x-original-"))
            or not item.isascii()
            or item != item.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in item)
        ):
            raise ValueError(f"`{name}` contains an invalid header name or value.")
    return headers


def _require_bool(name: str, value: Any, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"`{name}` must be a boolean.")
    return value


def _require_int(name: str, value: Any, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"`{name}` must be a positive integer.")
    return value


def _require_str(name: str, value: Any, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"`{name}` is required.")
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"`{name}` must be a non-empty string.")
    return value.strip()


def _service_name(base_url: str) -> str:
    host = urlsplit(base_url).hostname or "source"
    return host.replace(".", "-")


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _authority_has_port_delimiter(netloc: str) -> bool:
    """Return whether an authority explicitly delimits a port, including an empty one."""
    authority = netloc.rsplit("@", 1)[-1]
    if authority.startswith("["):
        closing_bracket = authority.find("]")
        return closing_bracket >= 0 and authority[closing_bracket + 1 :].startswith(":")
    return ":" in authority


def _url_origin(url: str, field_name: str) -> tuple[str, str, int]:
    """Return a normalized HTTP origin or reject an unsafe URL."""
    if any(character.isspace() or ord(character) < 32 or character == "\\" for character in url):
        raise ValueError(f"`{field_name}` must be a well-formed HTTP(S) URL.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError(f"`{field_name}` must be a well-formed HTTP(S) URL.") from exc

    scheme = parsed.scheme.lower()
    if scheme not in _DEFAULT_PORTS or not parsed.netloc or parsed.hostname is None:
        raise ValueError(f"`{field_name}` must be an absolute HTTP(S) URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"`{field_name}` must not contain credentials.")
    if _authority_has_port_delimiter(parsed.netloc) and port is None:
        raise ValueError(f"`{field_name}` must not specify an empty port.")

    hostname = parsed.hostname
    if hostname.endswith("."):
        raise ValueError(f"`{field_name}` must not contain a trailing-dot hostname.")
    if port == _DEFAULT_PORTS[scheme]:
        raise ValueError(f"`{field_name}` must not specify an explicit default port.")
    if not hostname:
        raise ValueError(f"`{field_name}` must contain a valid hostname.")
    try:
        normalized_host = ipaddress.ip_address(hostname).compressed
    except ValueError:
        try:
            normalized_host = hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError(f"`{field_name}` must contain a valid hostname.") from exc
        labels = normalized_host.split(".")
        if any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or any(not (character.isalnum() or character == "-") for character in label)
            for label in labels
        ):
            raise ValueError(f"`{field_name}` must contain a valid hostname.") from None

    return scheme, normalized_host, port if port is not None else _DEFAULT_PORTS[scheme]


def build_url(base_url: str, path: str, *, skill_name: str) -> str:
    base_origin = _url_origin(base_url, "base_url")
    if not is_registered_source_base_url(skill_name, base_url):
        raise ValueError("`base_url` is not a registered HTTPS base for this skill.")
    try:
        parsed_path = urlsplit(path)
    except ValueError as exc:
        raise ValueError("`path` must be a well-formed relative path or HTTP(S) URL.") from exc
    if parsed_path.scheme or parsed_path.netloc:
        path_origin = _url_origin(path, "path")
        if path_origin != base_origin:
            raise ValueError("An absolute `path` URL must share the `base_url` origin.")
        candidate = path
    else:
        candidate = base_url.rstrip("/") + "/" + path.lstrip("/")
    if not is_registered_source_url(skill_name, candidate):
        raise ValueError("The requested URL is outside this skill's registered source scope.")
    return candidate


def _safe_output_path(path: str) -> str:
    """Keep endpoint classification while omitting all caller-supplied query values."""
    return urlsplit(path).path or "/"


def _validated_response_url(
    response: Any, request_url: str, base_url: str, *, skill_name: str
) -> str:
    """Reject redirect chains whose provenance leaves the configured origin."""
    status_code = getattr(response, "status_code", None)
    if (
        isinstance(status_code, int)
        and not isinstance(status_code, bool)
        and 300 <= status_code < 400
    ):
        raise ValueError("Redirect responses are not followed.")
    expected_origin = _url_origin(base_url, "base_url")
    history = getattr(response, "history", ())
    if isinstance(history, (list, tuple)) and history:
        raise ValueError("Unexpected redirect history for a non-redirecting request.")

    response_url = getattr(response, "url", None)
    # Real requests.Response objects always provide `url`; the fallback keeps
    # lightweight test doubles compatible without weakening runtime checks.
    if not isinstance(response_url, str) or not response_url:
        if isinstance(response, requests.Response):
            raise ValueError("The final response did not provide a valid URL.")
        response_url = request_url
    if _url_origin(response_url, "response URL") != expected_origin:
        raise ValueError("The final response URL changed origins.")
    if not is_registered_source_url(skill_name, response_url):
        raise ValueError("The final response URL left the registered source scope.")
    return response_url


def _get_by_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, list):
            if not part.isdigit():
                raise ValueError(f"`record_path` segment {part!r} must be a list index.")
            index = int(part)
            if index >= len(current):
                raise ValueError(f"`record_path` index {index} is out of range.")
            current = current[index]
        elif isinstance(current, dict):
            if part not in current:
                raise ValueError(f"`record_path` key {part!r} was not present in the response.")
            current = current[part]
        else:
            raise ValueError(f"`record_path` segment {part!r} could not be applied.")
    return current


def _infer_target(data: Any) -> tuple[str | None, Any]:
    if isinstance(data, list):
        return "$", data
    if isinstance(data, dict):
        embedded = data.get("_embedded")
        if isinstance(embedded, dict):
            for key, value in embedded.items():
                if isinstance(value, list):
                    return f"_embedded.{key}", value
        for key in (
            "collection",
            "results",
            "structures",
            "activities",
            "molecules",
            "mechanisms",
            "records",
            "items",
        ):
            value = data.get(key)
            if isinstance(value, list):
                return key, value
    return None, data


def _compact(value: Any, max_items: int, max_depth: int) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 240 else value[:240] + "..."
    if max_depth <= 0:
        if isinstance(value, (dict, list)):
            return "..."
        return value
    if isinstance(value, list):
        out = [_compact(item, max_items, max_depth - 1) for item in value[:max_items]]
        if len(value) > max_items:
            out.append(f"... (+{len(value) - max_items} more)")
        return out
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        items = list(value.items())
        for key, item in items[:max_items]:
            out[str(key)] = _compact(item, max_items, max_depth - 1)
        if len(items) > max_items:
            out["_truncated_keys"] = len(items) - max_items
        return out
    return value


def _raw_response_bytes(response: Any) -> bytes:
    content = getattr(response, "content", None)
    if isinstance(content, bytes):
        return content
    return response.text.encode("utf-8")


def _save_raw_output(
    raw_output: bytes, raw_output_path: str | None, base_url: str, suffix: str
) -> str:
    path = Path(raw_output_path or f"/tmp/{_service_name(base_url)}-raw.{suffix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw_output)
    return str(path)


def parse_input(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Input must be one JSON object.")
    base_url = _require_str("base_url", payload.get("base_url"), required=True)
    path = _require_str("path", payload.get("path"), required=True)
    method = (_require_str("method", payload.get("method")) or "GET").upper()
    if method not in {"GET", "POST"}:
        raise ValueError("`method` must be GET or POST.")
    json_body = payload.get("json_body")
    form_body = payload.get("form_body")
    if json_body is not None and form_body is not None:
        raise ValueError("Provide only one of `json_body` or `form_body`.")
    response_format = (
        _require_str("response_format", payload.get("response_format")) or "auto"
    ).lower()
    if response_format not in {"auto", "json", "text"}:
        raise ValueError("`response_format` must be auto, json, or text.")
    return {
        "base_url": base_url,
        "path": path,
        "method": method,
        "params": _require_object("params", payload.get("params")),
        "headers": _require_headers("headers", payload.get("headers")),
        "json_body": json_body,
        "form_body": _require_object("form_body", form_body) if form_body is not None else None,
        "record_path": _require_str("record_path", payload.get("record_path")),
        "response_format": response_format,
        "max_items": _require_int("max_items", payload.get("max_items"), 5),
        "max_depth": _require_int("max_depth", payload.get("max_depth"), 3),
        "timeout_sec": _require_int("timeout_sec", payload.get("timeout_sec"), 30),
        "save_raw": _require_bool("save_raw", payload.get("save_raw"), False),
        "raw_output_path": _require_str("raw_output_path", payload.get("raw_output_path")),
    }


def execute(payload: Any, *, skill_name: str) -> dict[str, Any]:
    if requests is None:
        return error("missing_dependency", f"`requests` is required: {REQUESTS_IMPORT_ERROR}")
    try:
        config = parse_input(payload)
        url = build_url(config["base_url"], config["path"], skill_name=skill_name)
    except ValueError as exc:
        return error("invalid_input", str(exc))

    session = None
    try:
        session = requests.Session()
        session.headers.update(config["headers"])
        request_kwargs: dict[str, Any] = {
            "params": config["params"],
            "timeout": config["timeout_sec"],
            "allow_redirects": False,
        }
        if config["json_body"] is not None:
            request_kwargs["json"] = config["json_body"]
        if config["form_body"] is not None:
            request_kwargs["data"] = config["form_body"]

        response = session.request(config["method"], url, **request_kwargs)
        response_url = _validated_response_url(
            response, url, config["base_url"], skill_name=skill_name
        )
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").lower()
        wants_json = config["response_format"] == "json"
        wants_text = config["response_format"] == "text"
        auto_json = not wants_text and (
            "json" in content_type or response.text.lstrip().startswith(("{", "["))
        )

        if wants_json or auto_json:
            data = response.json()
            raw_output = _raw_response_bytes(response)
            raw_output_path = None
            if config["save_raw"]:
                raw_output_path = _save_raw_output(
                    raw_output, config["raw_output_path"], config["base_url"], "json"
                )

            record_path = config["record_path"]
            path_used, target = (
                _infer_target(data)
                if record_path is None
                else (record_path, _get_by_path(data, record_path))
            )
            out = {
                "ok": True,
                "source": _service_name(config["base_url"]),
                "path": _safe_output_path(config["path"]),
                "method": config["method"],
                "status_code": response.status_code,
                "record_path": path_used,
                "raw_output_path": raw_output_path,
                "warnings": [],
            }
            if isinstance(target, list):
                records = target[: config["max_items"]]
                out.update(
                    {
                        "record_count_returned": len(records),
                        "record_count_available": len(target),
                        "truncated": len(records) < len(target),
                        "records": _compact(records, config["max_items"], config["max_depth"]),
                    }
                )
            else:
                out["summary"] = _compact(target, config["max_items"], config["max_depth"])
                if isinstance(target, dict):
                    out["top_keys"] = list(target)[: config["max_items"]]
            return apply_source_contract(out, skill_name, response_url)

        raw_output_path = None
        if config["save_raw"]:
            raw_output_path = _save_raw_output(
                _raw_response_bytes(response),
                config["raw_output_path"],
                config["base_url"],
                "txt",
            )
        text_head = response.text[:800]
        out = {
            "ok": True,
            "source": _service_name(config["base_url"]),
            "path": _safe_output_path(config["path"]),
            "method": config["method"],
            "status_code": response.status_code,
            "content_type": content_type,
            "text_head": None if raw_output_path else text_head,
            "text_head_truncated": False
            if raw_output_path
            else len(text_head) < len(response.text),
            "raw_output_path": raw_output_path,
            "warnings": [],
        }
        return apply_source_contract(out, skill_name, response_url)
    except ValueError:
        return error("invalid_response", f"Response validation failed for {skill_name}.")
    except requests.RequestException as exc:
        return error(
            "network_error",
            f"Request failed for {skill_name}: {type(exc).__name__}",
        )
    except Exception:  # noqa: BLE001
        return error(
            "invalid_response",
            f"Unexpected response processing failure for {skill_name}.",
        )
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass


def main(*, skill_name: str) -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001
        sys.stdout.write(json.dumps(error("invalid_json", f"Could not parse JSON input: {exc}")))
        return 2
    try:
        output = execute(payload, skill_name=skill_name)
    except ValueError as exc:
        output = error("invalid_input", str(exc))
        code = 2
    else:
        code = 0 if output.get("ok") else 1
    sys.stdout.write(json.dumps(output))
    return code

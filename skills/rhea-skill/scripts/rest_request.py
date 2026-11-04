#!/usr/bin/env python3
"""Preserve the skill-local CLI while delegating to the shared REST client."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PLUGIN_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(_PLUGIN_SCRIPTS))

import database_rest_client as _client  # noqa: E402

_SKILL_NAME = Path(__file__).resolve().parents[1].name
requests = _client.requests
apply_source_contract = _client.apply_source_contract
is_registered_source_base_url = _client.is_registered_source_base_url
is_registered_source_url = _client.is_registered_source_url
_require_headers = _client._require_headers


def _build_url(base_url: str, path: str) -> str:
    return _client.build_url(base_url, path, skill_name=_SKILL_NAME)


def execute(payload: Any) -> dict[str, Any]:
    return _client.execute(payload, skill_name=_SKILL_NAME)


def main() -> int:
    return _client.main(skill_name=_SKILL_NAME)


def __getattr__(name: str) -> Any:
    return getattr(_client, name)


if __name__ == "__main__":
    raise SystemExit(main())

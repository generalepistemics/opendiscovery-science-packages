"""Preserve the skill-local module path for the shared variant resolver."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

_PLUGIN_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(_PLUGIN_SCRIPTS))
sys.modules[__name__] = import_module("database_variant_resolution")

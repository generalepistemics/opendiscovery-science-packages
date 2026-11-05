#!/usr/bin/env python3
"""Validate the packaged Biohub ESM starter-example contract and all surfaces."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from biohub_esm_lib.starter_examples import validate_starter_examples_file


def main() -> None:
    plugin_root = Path(__file__).resolve().parents[1]
    contract = validate_starter_examples_file(plugin_root)
    print(
        f"validated {len(contract['examples'])} GB1 regression examples "
        "and 3 tutorial-derived marketplace prompts"
    )


if __name__ == "__main__":
    main()

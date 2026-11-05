#!/usr/bin/env python3
"""Preflight for the computational-chemistry-and-biology skill.

Loads a project `.env` (shell state doesn't persist between commands), then
calls rowan.whoami() to confirm the key is present AND valid, and prints
remaining credits. Exits non-zero with actionable guidance on every failure
mode: missing key, rejected key (invalid/expired), or API unreachable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def find_dotenv() -> Path | None:
    """Read only the selected working directory; never search unrelated parents."""
    candidate = Path.cwd() / ".env"
    return candidate if candidate.is_file() else None


def load_dotenv(path: Path) -> None:
    """Minimal, dependency-free .env loader. Existing env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def main() -> int:
    load_dotenv(find_dotenv() or Path(".env"))
    try:
        import httpx
        import rowan
    except ImportError:
        sys.stderr.write("Rowan Python setup is missing. Install rowan in this project's Python environment, or use the connected Rowan MCP service.\n")
        return 1

    try:
        print(f"Key OK: {rowan.whoami().credits_available_string()}")
        return 0
    except ValueError:  # no key resolved by rowan.get_api_key()
        env = Path(".env").resolve()
        sys.stderr.write(
            f"No ROWAN_API_KEY found (looked for {env}).\n"
            "Get a key at https://labs.rowansci.com/account, then add it with:\n"
            f"  echo 'ROWAN_API_KEY=your-key-here' >> {env}\n"
            "Make sure .env is gitignored.\n"
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            sys.stderr.write(
                "ROWAN_API_KEY was rejected (401 Unauthorized): invalid or expired.\n"
                "Regenerate it at https://labs.rowansci.com/account.\n"
            )
        else:
            sys.stderr.write(f"Rowan API returned HTTP {e.response.status_code}.\n")
    except httpx.HTTPError as e:
        sys.stderr.write("Could not reach the Rowan API. Check network access and retry.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())

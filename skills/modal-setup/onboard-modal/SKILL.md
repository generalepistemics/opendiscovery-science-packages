---
name: onboard-modal
description: Set up the Modal Python SDK and CLI on the selected OpenDiscovery engine host, authenticate through Modal, and install official workflow guidance. Use when Modal is missing, authentication fails or the user requests Modal setup before a deployment.
license: MIT
---

# Set up Modal

Run setup on the machine where the selected engine executes commands. A desktop, Docker server, remote engine and target compute machine are different locations. Installing this skill does not install Modal or authorize cloud work.

## Preserve an existing installation

Check `modal --version` first (`Get-Command modal` on PowerShell, `command -v modal` on POSIX). If it works, preserve it. Otherwise inspect an existing project Python environment, `uv`, `pipx`, and a supported Python interpreter in that order. Check current requirements at https://modal.com/docs/guide before installation. Do not assume a bundled application Python exists.

Use an existing supported environment when selected by the user. For an isolated CLI, prefer `uv tool install modal` or `pipx install modal` when available. Otherwise create an explicit virtual environment with a supported Python interpreter and install `modal` there. Never use `sudo pip`, change system Python, overwrite the project's lockfile or silently install into another host's environment. Explain the chosen install location before changing it. Preserve the verified interpreter path for subsequent shell calls.

Verify `modal --version`, or invoke `python -m modal --version` with the exact selected interpreter if its scripts directory is not on PATH. Do not edit shell startup files merely to hide a PATH issue.

## Authenticate

1. Run `modal token info`; preserve valid credentials.
2. If missing, run `modal setup` through the selected installation. Let the user complete Modal's own browser flow. Do not request or print secret values.
3. Verify with `modal token info`, `modal profile current` and `modal app list --json`. Report only the selected profile and whether verification passed; do not reproduce tokens or private account data.
4. Select a different profile/environment only when the intended target is explicit. Do not create, deploy, stop or delete an App to test sign-in.

Authentication requires the engine host's normal network access. A blocked network request does not mean credentials are invalid. Preserve security restrictions and report the actual blocker.

## Install official workflow guidance

Read `modal skills --help` and the supported installation options of the installed version. Generate the official skill into a private temporary directory using a documented output option, if supported. Inspect the generated `SKILL.md` and resources, then offer installation through OpenDiscovery's existing Skills controls at the requested user/project scope. Do not run a global installation that targets another agent's configuration.

If the installed CLI only provides another agent's global destination, leave that destination unchanged. Use the current official documentation at https://modal.com/docs/guide for the requested workload and report the skill-install limitation. Do not invent CLI output flags or claim generated guidance is installed when it is not.

## Finish

Report the CLI version, engine-host installation location, profile verification and guidance availability. Provider sign-in is separate from authorization to deploy or start billed compute. Continue the user's workload only within their explicit target, budget and action permissions.

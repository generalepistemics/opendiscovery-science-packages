---
name: onboard-baseten
description: Install, upgrade, detect, and authenticate the Baseten CLI on a local OpenDiscovery engine host host, then install Baseten's official skill globally. Use when the Baseten CLI is missing, `baseten` is not on PATH, a Baseten profile or credential is not configured, authentication fails, the global Baseten skill is missing, or the user asks to set up Baseten before model API, deployment, or monitoring work.
---

# Baseten Setup

Prepare the current local OpenDiscovery engine host host for general Baseten work. Keep credential entry in Baseten's browser flow, make no deployment during onboarding, and hand workload-specific work to Baseten's globally installed official skill.

## Check existing tools

Detect whether the host shell is POSIX-compatible or PowerShell, then use the matching commands throughout this skill.

On a POSIX-compatible shell, run:

```bash
command -v brew || true
command -v npx || true
if command -v baseten >/dev/null 2>&1; then
  baseten version
fi
```

On PowerShell, run:

```powershell
Get-Command npx -ErrorAction SilentlyContinue
$basetenCommand = Get-Command baseten -ErrorAction SilentlyContinue
if ($null -ne $basetenCommand) {
    baseten version
}
```

Preserve an existing Baseten CLI installation when `baseten version` succeeds. If the user explicitly asks for an upgrade and the CLI was installed with Homebrew, explain that it changes the host, obtain any approval required by the execution environment, run `brew update && brew upgrade baseten`, and verify the version again.

The Baseten CLI is in beta and under active development; commands and flags may change. If a documented command fails unexpectedly, fetch the current CLI reference at `https://docs.baseten.co/reference/cli/baseten/overview` rather than guessing.

Baseten's documented installation on macOS and Linux uses Homebrew. If `brew` is unavailable on those platforms, explain that prerequisite and stop before changing the host; offer the documented manual binary install from Baseten's GitHub releases only when the user explicitly chooses it. On Windows, the manual binary install is the documented path (see the next section). Installing Baseten's official skill requires Node.js and `npx`. If `npx` is unavailable, finish any valid Baseten CLI checks, report the missing prerequisite, and stop before skill installation.

## Install the Baseten CLI

Only reach this section when `baseten version` failed. Explain that this step installs the Baseten CLI and obtain any approval required by the execution environment.

On macOS or Linux with Homebrew, run:

```bash
brew tap basetenlabs/baseten
brew install baseten
```

On Windows, or when the user explicitly chooses a manual install, download the `baseten` archive for the host platform from `https://github.com/basetenlabs/baseten-cli/releases`, extract the binary, and place it on `PATH`. Do not pipe release archives through `sudo` without showing the user the exact command first.

Then run `baseten version`. If the command remains unavailable, explain that the install directory is not on `PATH`. Do not edit shell startup files unless the user asks.

## Install official workflow guidance

Use OpenDiscovery's existing Skills catalog with source `basetenlabs/baseten-skills`. Inspect the source's available skill directories, then install the `baseten` workflow skill at the chosen user/project scope. Preserve a preexisting installed copy and its edits; use the catalog's normal conflict controls. Verify it appears in Settings → Skills before relying on it in a session. Do not run an installer targeting another agent's global configuration or invent an OpenDiscovery option for a third-party CLI.

If the official repository cannot be scanned or the requested skill is unavailable, report that specific limitation and use the current Baseten documentation. Do not mark the workflow skill installed from a successful CLI login alone.

## Allow Baseten network access in OpenDiscovery

Baseten CLI commands that authenticate, inspect, or mutate Baseten cloud state require external network access. Use the selected engine host's existing permission and network controls. If an API-backed command stalls because egress is blocked, stop it and retry after access is approved; do not treat blocked egress as invalid credentials or bypass the network policy.

## Authenticate

The Baseten CLI stores each credential as a named profile, selected per command with `--profile` or the `BASETEN_PROFILE` environment variable, or set as default with `baseten auth switch`.

1. Check the resolved authentication state without printing or reading credential values by running `baseten auth status`. If it reports a valid profile, preserve the existing credential and continue to verification.
2. If no profile is configured or the credential is invalid, run `baseten auth login`. In a non-TTY environment, run `baseten auth login --web` to use browser login without interactive prompts.
3. Tell the user that the CLI will open or print a browser verification URL (OAuth device flow) and that they must complete sign-in themselves. Pause while that human interaction is required. Browser logins name the profile after the user's email.
4. For a non-default profile or remote, add `--profile NAME` or `--remote-url URL` only after the user names or confirms the intended target.

Do not ask the user to paste an API key into chat. Do not place `BASETEN_API_KEY` in command arguments, inspect the system keyring or Baseten config directory, or reproduce user, organization, token, or credential values in logs or final responses. Browser OAuth is the default for local onboarding. If the user explicitly requires API-key authentication, use `baseten auth login --with-api-key --profile NAME`, which reads the key from stdin or an interactive prompt, never from chat. A later inference workflow may use an already exported `BASETEN_API_KEY`, but must never echo or commit it.

## Verify configuration

After authentication, run read-only checks for the active profile:

```bash
baseten version
baseten auth status
baseten whoami
```

`baseten auth status` identifies the resolved profile, remote URL, and auth type without revealing the credential. `baseten whoami` verifies management API access. Report only the CLI version, profile name, auth type, and whether read-only verification succeeded; omit the user identity and credential storage details.

Do not create, deploy, promote, stop, or delete a model merely to test authentication. These operations can change cloud state or consume billed compute and require a separate explicit user request.

## Hand off

Report the Baseten CLI version, whether Baseten's official global skill was installed, the verified profile name, and whether read-only access succeeded. Then continue with the globally installed Baseten skill for Model APIs, deployment, development, monitoring, Chains, or training work. Note that authoring Chains, Training jobs, and Loops still uses the separate Truss CLI per Baseten's documentation; install it only when such a workload is actually requested. Fetch current Baseten documentation rather than relying on stale commands, confirm the target workspace before mutations, and obtain explicit approval before starting billed compute.

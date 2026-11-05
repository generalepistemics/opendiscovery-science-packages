# Setup details

Primary sources: [Biohub quickstart](https://biohub.ai/learn/getting-started) (API keys, install, managed client), API keys at https://biohub.ai/developer-console/api-keys, [Biohub get started](https://biohub.ai/esm/protein/get-started) (Atlas and S3), [Biohub/esm](https://github.com/Biohub/esm), [Modal config](https://modal.com/docs/sdk/py/latest/modal.config), and [Hugging Face ESMC-6B](https://huggingface.co/biohub/ESMC-6B).

## Runtime matrix

| Route | Required | Optional / note |
| --- | --- | --- |
| Atlas API | HTTPS client | no client key in current alpha |
| Atlas S3 | AWS CLI | use `--no-sign-request` |
| Biohub | pinned `esm`, `ESM_API_KEY` | credits/rate limits are account-specific |
| Modal | official `modal==1.5.2` SDK/CLI and profile or token env pair | durable generic jobs also require an immutable deployed Function version; public weights do not need `ESM_API_KEY` |
| Self-hosted HF | pinned `esm`, PyTorch/Transformers, suitable compute | `HF_TOKEN` optional for public repos |

Two different floors apply, and conflating them is the most common first-run failure.

- **Plugin runtime: Python 3.10 or newer.** Enough for Atlas, preflight, routing, and the Modal control plane. The runtime enforces it and exits with code 2 and a single stderr line naming the interpreter it found.
- **Any route that imports the pinned `esm` SDK: Python 3.12.**
  The pinned `esm==3.4.1.post1` distribution declares `requires-python = ">=3.12"`, so 3.10 and 3.11 cannot install it.
  The plugin validates the SDK on 3.12 only, and preflight reports 3.13 and newer as `unsupported`; 3.14 does not currently resolve at all because `zstd` and `biotite` publish no wheels for it.
  This covers managed ESMC mutation scoring, `esmc-landscape`, and ESMFold2 response serialization.

A 3.10 or 3.11 interpreter can run the status-only preflight, which reports the pinned-SDK runtime as `unsupported` before install. Use `python3.12` explicitly when creating the environment. The default `python3` on macOS is 3.9, which clears neither floor.
Treat the message as a host setup problem; do not retry the command with the same interpreter.

## Do not expose secrets

- Never accept a secret as a CLI flag, generated file, test fixture, screenshot, chat message, PR body, or Linear comment.
- Never ask the user to paste, repeat, or display a credential in chat. Never clear or overwrite a configured credential unless the user explicitly asks to replace or remove it.
- Do not run `env`, `set`, config dumps, or commands that interpolate a secret.
- Do not inspect `.modal.toml`; a native `modal profile current`/authenticated API check or simple file-presence preflight is sufficient.
- Redact nested keys containing API key, token, secret, password, or other credential-bearing values, and redact Bearer strings before diagnostics are persisted.

## Host credential handoff

The setup workflow owns preflight. Run `python3 <skill-directory>/resources/scripts/biohub_esm.py preflight` for the base credential and route report. For managed structure work, also run `<python-3.12-with-pinned-esm> <skill-directory>/resources/scripts/biohub_esm.py preflight --endpoint fold` or `--endpoint fold_all_atom`, matching the selected endpoint and the exact resolved interpreter that will execute `managed-post` (`.venv/bin/python` for the documented install). The endpoint-specific `managed_structure_materialization` report must pass before credential access or submission. Run these checks with the available execution tool; do not make the user run them or ask them to report their output when the agent can execute them directly.

For a missing `ESM_API_KEY`, use this single-handoff contract:

Before opening credential setup, inspect `esm_sdk_runtime`. If it is `unsupported` and the selected managed workflow imports the pinned `esm` SDK, include the Python 3.12 requirement and the returned interpreter/remedy in the same handoff as the key instruction. This applies to managed ESMC mutation scoring, `esmc-landscape`, and ESMFold2 response serialization. Do not wait for key setup or a restart to reveal the runtime blocker.

1. Prefer the host's existing secure credential action or persistent environment integration. Invoke at most one setup action for the missing credential.
2. Describe only a prompt surface that the action is verified to open. If it opens an app credential sheet, say that; if it opens a terminal prompt, say that. Never promise a terminal prompt based on assumption.
3. The host action, not chat, collects the value. The setup workflow must not read, echo, copy, screenshot, or persist the value itself.
4. After the action completes, automatically run the status-only preflight once. Resume a waiting tutorial-scale managed Biohub request immediately; it needs no separate confirmation. Resume Modal, self-hosted, or bulk-transfer work only when its exact frozen scope already has a still-current confirmation. Do not ask "done?" before checking.

If no interactive setup action is available, do not imply that one exists. Give one user-executed fallback for the user's platform, and write the URL as plain text, never behind Markdown link text.

- When preflight returns `macos_keychain_command`: the four Terminal steps in the setup skill's **No key yet** section, quoting that command exactly.
  The command prompts twice for the key without echoing it and saves the generic-password item whose service is exactly `com.generalepistemics.opendiscovery.biohub-esm.ESM_API_KEY`.
  Rerunning it replaces the key it saved, the plugin reads that item before any other, and no restart is needed.
  It works in the desktop app, which does not inherit variables set in Terminal.
  The agent never runs it, and never suggests the Keychain Access app instead.
- Otherwise, including a standalone skill install without the plugin's preflight: get a free key at https://biohub.ai/developer-console/api-keys, set it as `ESM_API_KEY` in the environment that launches OpenDiscovery, then restart OpenDiscovery so it inherits the setting.

Stop after that instruction. When the user next responds, run preflight once without another setup question.

A command sandbox can block the macOS Keychain, and the OpenDiscovery sandbox does when its network access is off, so a saved key looks absent from inside one.
Preflight reports that case as `unverified` with source `macos-keychain-unreachable`, and a managed command fails with a message that names the unreachable Keychain.
When you see either, rerun that command outside the sandbox before any key handoff, and act on that result.
If the host cannot leave its sandbox, give one handoff that asks the user to allow the plugin's commands to run outside it and, if no key is saved yet, includes the Terminal steps.
A managed command that reports a Keychain item macOS did not release gets the Terminal steps again, not a request for a new key.

Persistent host credentials, including the recognized macOS Keychain item, remain configured across runs until the user explicitly requests replacement or removal. Status-only preflight checks item presence without requesting its value. Execution-time resolution reads the item only when `ESM_API_KEY` is absent and the selected route is authorized to run; the plugin never mutates or removes it. Never unset a key after use.

## Pin verification

```bash
python3 <skill-directory>/resources/scripts/biohub_esm.py pins
python3 <skill-directory>/resources/scripts/biohub_esm.py verify-install
```

Compare against [`source-pins.md`](../../../references/source-pins.md) and update code, references, mocks, live smokes, and provenance together.
Do not update a pin without rerunning the entire validation loop.
`verify-install` checks each of `esm` and `transformers` in six steps:

1. The install is files on disk with a single metadata directory, and its version equals the pin exactly.
2. The install came from a package index or a wheel file.
   A PEP 610 `direct_url.json` with `vcs_info` or `dir_info`, or with a URL but no `archive_info`, is rejected; an index install has none, and a local wheel file records `archive_info`.
3. The installed `RECORD` rows for the importable package, excluding bytecode, all carry a `sha256` hash, and their sorted `path,hash` lines digest to the pinned payload SHA-256.
4. Every one of those `RECORD`-listed files is present and still hashes to its entry on disk, so edits made after install are caught.
5. No unlisted file sits in the package tree, so an added module, subpackage, or extension module cannot shadow a verified one.
   Bytecode caches for recorded sources are trusted rather than re-verified.
6. The import location is the verified install, so a shadowing directory earlier on `sys.path` is caught.

Only then does it print the upstream source commit that the pinned wheel was built from.

---
name: biohub-esm-setup
description: Set up and preflight Biohub ESM, Atlas, Modal, and Hugging Face access. Use when installing pinned ESM dependencies, checking credentials, connecting the Biohub MCP for Atlas tools and its Mol* structure viewer, or fixing auth, rate-limit, credits, PATH, SDK, or GPU setup. Never ask for secret values.
license: MIT
compatibility: Hosted MCP works through the connected service. Shared Python helpers require a POSIX engine host; managed ESM workflows require the pinned Python 3.12 environment.
---

The shared Python helper library uses POSIX file locks. On a Windows engine host, use the connected MCP capabilities or a selected POSIX remote engine for helper workflows. Do not run the helper through an unsupported interpreter or report a failed import as a missing credential. Provider accounts, managed inference credentials and compute permissions remain separate.

# Biohub ESM setup and auth

The user's instructions take precedence over guidelines provided in a skill.
If explicit user instructions conflict with a skill's instructions, prioritize the user's instructions.

## No key yet

When `biohub_managed.status` is `missing`, inspect `esm_sdk_runtime` before starting credential setup. If the selected managed workflow imports the pinned `esm` SDK and `esm_sdk_runtime.status` is `unsupported`, report both blockers in the same handoff: say that the workflow requires Python 3.12, and quote the reported interpreter and remedy. This applies to managed ESMC mutation scoring, `esmc-landscape`, and ESMFold2 response serialization. Do not wait until after the key is configured to reveal the Python blocker.

When `biohub_managed.status` is `unverified`, the key may already be saved: a sandbox blocked the macOS Keychain.
Rerun the status-only preflight outside the sandbox before giving any key instruction, as **Keychain access on macOS** describes.

When no verified host credential action is available, give the instruction for the user's platform, alongside the Python blocker when applicable.
When preflight returns `macos_keychain_command` (macOS with the plugin installed), give the user these steps and quote that command exactly:

1. Get a free API key at https://biohub.ai/developer-console/api-keys (existing Forge accounts can sign in), then copy it.
2. Open Terminal (press Command-Space, type Terminal, and press Return), paste this command, and press Return:

   ```bash
   security add-generic-password -U -a "$USER" -s com.generalepistemics.opendiscovery.biohub-esm.ESM_API_KEY -w
   ```

3. At `password data for new item:`, paste the key and press Return.
   Nothing appears as you paste, so paste only once.
   At `retype password for new item:`, paste it again and press Return.
   If you see `passwords don't match`, paste the key at both prompts again.
4. Come back and send any message.
   No restart is needed.

These steps work in the desktop app, which does not inherit variables set in Terminal, and in the CLI.
Running the command again replaces the key it saved, and the plugin reads that item before any other.
Never run the command yourself; the user types the key into it, outside the chat.
Never suggest creating the item in the Keychain Access app: only this command is verified to create an item the plugin can read without a macOS approval prompt.
If the user already created one there, have them delete it in Keychain Access, then run the command.

Otherwise, on Linux, on Windows, or in a standalone skill install without the plugin's preflight, use this instruction:

> Get a free API key at https://biohub.ai/developer-console/api-keys (existing Forge accounts can sign in), set it as `ESM_API_KEY` in the environment that launches OpenDiscovery, then restart OpenDiscovery.

Always write the full URL as plain text, exactly `https://biohub.ai/developer-console/api-keys`.
Never hide it behind Markdown link text such as "Biohub's API key page", because some hosts show only the link text and leave the user with no clickable link and no address.

Preflight returns `obtain_key_url`, `variable`, `esm_sdk_runtime`, and on macOS `macos_keychain_command` alongside the status, so quote those rather than composing your own setup requirements. If a verified credential action is available, follow **Seamless credential recovery** below instead. Apart from current setup blockers, do not describe routes, models, request counts, or costs before the key exists; none of it is actionable yet. Once the key and runtime are configured, resume the original request automatically without asking the user to repeat it.

## Safe preflight

The agent runs the base status-only check directly for credentials, Atlas, and
routes that do not materialize a managed structure:

```bash
python3 <skill-directory>/resources/scripts/biohub_esm.py preflight
```

For a managed fold, run the selected endpoint's capability preflight with the
same provisioned Python 3.12 interpreter that will execute the request:

```bash
<python-3.12-with-pinned-esm> <skill-directory>/resources/scripts/biohub_esm.py preflight --endpoint fold
<python-3.12-with-pinned-esm> <skill-directory>/resources/scripts/biohub_esm.py preflight --endpoint fold_all_atom
```

Run only the applicable endpoint command. Its
`managed_structure_materialization` report verifies the interpreter, the exact
pinned `esm` and `transformers` wheels, endpoint-specific imports, and a tiny offline
serialization. A blocked report must stop the workflow before credential access,
output creation, or provider submission; apply its bounded remediation and rerun
that endpoint preflight. Resolve the placeholder to the provisioned interpreter
(`.venv/bin/python` for the install below) and use that exact interpreter for the
subsequent managed command.

Credential entries report only `configured`, `missing`, `unverified`, `optional-missing`, or `not-required`; `esm_sdk_runtime` separately reports `supported` or `unsupported`. On macOS, preflight probes only whether the recognized Keychain item exists; it never requests the value or uses `security ... -w`. Execution-time resolution may retrieve the existing item only when the selected route is authorized to run: tutorial-scale managed Biohub requests, including every ESMFold2 tutorial fold, run without a separate confirmation; Modal, self-hosted, and bulk-transfer routes require the route-specific confirmation first. Run preflight and managed commands yourself when tool execution is available; the Keychain command under **No key yet** and the host command under **Biohub MCP connection** are the only commands the user runs. Never open or display `.modal.toml`; file presence is enough for preflight.

## Keychain access on macOS

When `ESM_API_KEY` is not set, the plugin reads the generic-password item that the Terminal command saves, then any other item whose service is `com.generalepistemics.opendiscovery.biohub-esm.ESM_API_KEY`.
A command sandbox can block the Keychain; the OpenDiscovery sandbox does when its network access is off.
Inside such a sandbox, `security` fails with `SecKeychainSearchCreateFromAttributes: One or more parameters passed to a function were not valid.`, so a saved key looks absent.
Preflight reports that case as `unverified` with source `macos-keychain-unreachable`, and a managed command fails with a message that says the Keychain was unreachable.
When you see either, rerun that command outside the sandbox: request escalated permissions, and say the plugin needs to read the Biohub API key from the macOS Keychain.
Act on the outside-sandbox result, and never tell the user a key is missing because of a sandboxed result alone.
If the host cannot run the command outside its sandbox, give one handoff: the plugin reads the Keychain only when its commands run outside the sandbox, so the user approves that request or switches to a permission mode that allows it, then sends any message.
If the user has not saved a key yet, put the Terminal steps under **No key yet** in that same handoff.
If a managed command reports that a Keychain item exists but macOS did not release its value, give the Terminal steps again without asking for a new key; the plugin reads the item that command saves first.

## Seamless credential recovery

When managed Biohub access reports `missing`, keep the current request intact while setup completes.

1. Use the host's existing secure credential setup action for `ESM_API_KEY`, when one is actually available. Invoke it once and tell the user the verified host surface where its masked prompt will appear, such as a credential sheet in the app. Never claim that a terminal prompt exists unless the invoked action actually opens one.
2. Let that host action collect and persist the credential. Never ask the user to paste, repeat, or reveal the value in chat, and never clear or overwrite a configured credential.
3. When the setup action completes, automatically run the status-only preflight once. Resume a waiting tutorial-scale managed Biohub request immediately; it needs no separate confirmation. Resume Modal, self-hosted, or bulk-transfer work only when its exact frozen scope already has a still-current confirmation. Report the status without exposing the value if it is not configured.

Do not ask the user to say "done" and do not create a repeated setup loop. If this host exposes no callable secure setup action, do not imply that it does. Give exactly one user-executed fallback for the user's platform. When preflight returned `macos_keychain_command`, give the Terminal steps under **No key yet**. Otherwise: get a free key at https://biohub.ai/developer-console/api-keys, set it as `ESM_API_KEY` in the environment that launches OpenDiscovery, then restart OpenDiscovery so it inherits the setting. Stop there; on the user's next message, run preflight automatically instead of asking whether setup was completed.

A configured credential persists in the host's secret, environment store, or recognized macOS Keychain item until the user explicitly asks to replace or remove it. The plugin never mutates or removes the Keychain item, and setup must not unset any credential after a run.

## Credentials

- Biohub managed ESMC/ESMFold2: `ESM_API_KEY`. Create a free key at https://biohub.ai/developer-console/api-keys: name it, click Create, copy it. Existing Forge users sign in with the same credentials and do not need a new account. Use a verified host credential action when one exists; otherwise the user saves it with the Terminal steps under **No key yet** when preflight returns `macos_keychain_command`, or sets it in the environment that launches OpenDiscovery and restarts OpenDiscovery. Never ask the user to paste it in chat, and preserve an existing configured value.
- Atlas API and `s3://esm-protein-atlas/v1/`: no client credential in the current alpha.
- Modal: `MODAL_TOKEN_ID` plus `MODAL_TOKEN_SECRET`, or an authenticated Modal profile. Environment values override the profile.
- Hugging Face public weights: no token required. `HF_TOKEN` is optional for authenticated Hub access and rate-limit handling.

## Biohub MCP connection

Install Biohub through OpenDiscovery Discover. The combined installation connects `https://biohub.ai/mcp` and provides all five companion skills. Complete provider sign-in through Settings → Extensions → MCP servers if requested. Do not invoke another agent's MCP configuration CLI. Use live tool discovery rather than a hardcoded tool prefix.

MCP OAuth and managed `ESM_API_KEY` inference authentication are separate. Connecting the MCP does not provision managed inference credits, a Python environment, Modal or model weights. Preserve exact saved prediction files when presenting them in OpenDiscovery Structure Viewer; provider-generated sequence views are a different result.

## Source/model-pinned install

Use an isolated environment and the pins in [`source-pins.md`](../../references/source-pins.md):

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install "esm==3.4.1.post1" "transformers==4.57.6"
.venv/bin/python <skill-directory>/resources/scripts/biohub_esm.py verify-install
```

Both pins are exact PyPI wheels.
`transformers==4.57.6` is the only release inside the range `esm==3.4.1.post1` declares, so the two resolve together in one install.
`verify-install` checks that each installed distribution is an index or wheel-file install whose version and payload digest match the pins, that every RECORD-listed file is present and unmodified, that no unlisted file sits in the package tree, and that the import location is the verified install.
Bytecode caches for recorded sources are trusted rather than re-verified.
It then prints the upstream source commits recorded in provenance.
On Linux without a GPU, add `--extra-index-url https://download.pytorch.org/whl/cpu` to the install to take the smaller CPU PyTorch build.
These commands pin first-party code and model selection, but they are not a complete environment lock: the ESM package retains broad transitive dependency ranges, and hardware/runtime details can also affect outputs.

For Modal, use an already authenticated official CLI and install the validated `modal==1.5.2` SDK in an isolated environment. The generic durable control plane also requires the immutable positive deployment version returned by Modal and passes it to `Function.from_name(..., version=...)`; an app/function name alone is mutable. Do not place tokens on a command line. The [Modal config reference](https://modal.com/docs/sdk/py/latest/modal.config) documents environment and profile resolution, and the [Modal changelog](https://modal.com/docs/sdk/py/changelog) is the authority to review before updating the client pin.

## Diagnose without weakening tests

- `401`: missing, invalid, or expired Biohub key. Report the auth failure without guessing other causes, then replace the key as below.
- `500` with an empty body on a managed call: most often a rejected key, because the managed API currently returns a bodyless `500` rather than `401` for an invalid bearer token. Say the key looks wrong and point at https://biohub.ai/developer-console/api-keys before treating it as an outage; a configured-but-rejected key is not the same as a missing one.
- Replacing a rejected key: point at https://biohub.ai/developer-console/api-keys for a new one. If preflight reports source `macos-keychain`, give the Terminal steps under **No key yet** again; the command replaces the key it saved. If it reports source `environment`, the user replaces `ESM_API_KEY` where it is set, because it takes precedence over the Keychain.
- `402` or credit message: account-specific credits; direct the user to https://biohub.ai/developer-console without inventing a quota.
- `429`: honor `Retry-After`; reduce concurrency or resume later.
- timeout/5xx: preserve durable state and partial artifacts. Retry only a proven-idempotent setup or public read with bounded backoff; never retry a managed call whose outcome is indeterminate.
- Atlas schema error: retain raw response, compare the live alpha schema, and update validation intentionally.
- OOM/hardware mismatch: for ESMC, select a smaller managed model or pinned weights on a suitable user-owned GPU; use Modal only for supported fold workflows. Do not silently lower scientific parameters.

Read [setup details](references/setup.md), the shared [source pins](../../references/source-pins.md), and [safety/provenance contract](../../references/safety-and-provenance.md).

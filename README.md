<p align="center"><img src="assets/opendiscovery.svg" width="80" alt="OpenDiscovery"></p>

# Sequence Viewer

Interactive scientific viewing in OpenDiscovery.

## Use

Install from Discover → Science and approve the declared capabilities.
Alternatively, use Settings → Extensions → Apps → Add app with the public Git URL:

`https://github.com/generalepistemics/opendiscovery-science-packages#sequence-viewer`

Open a supported workspace file from Files, or ask the agent to open
its exact absolute path. Expand a viewer into the workbench to continue working
with the same scientific session.

Scientific files use server-owned handles, bounded reads and revision checks.
They do not pass through the ordinary text editor or the model as whole files.
State and caches stay inside this installation's private OpenDiscovery directories.

## Updates

Open Settings → Extensions → Apps → Check for updates. Review the available
version and any capability changes before applying an update. Saved viewer data
belongs to the installation and remains separate from the package files.

For an existing folder or ZIP installation, add the Git URL above and confirm
replacement of the matching App. Keep the same App ID; do not uninstall first.
Future updates then use that Git source.

The public branch contains the prepared runtime, UI, companion skill and required
notices. It starts without downloading build dependencies. Maintainers build and
verify these files from the canonical source repository before publication.

## Scientific qualification

Registration and successful opening alone do not establish numerical accuracy,
rendering or export compatibility. Validate the affected scientific workflows and
published format limits when changing algorithms, persistence or browser code.

Supported data sources and format limits are described in the capability matrix
below. Public data availability, browser resources and optional native tools can
limit individual workflows; the viewer reports those failures explicitly.

Third-party licenses and notices are included in `LICENSE` and
`THIRD_PARTY_NOTICES.md`.

## Reference documentation

- [Capability matrix](CAPABILITY_MATRIX.md)
- [Starter examples](STARTER_EXAMPLES.md)

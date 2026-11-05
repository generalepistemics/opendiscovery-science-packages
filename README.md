<p align="center"><img src="assets/opendiscovery.svg" width="80" alt="OpenDiscovery"></p>

# Molecular Structure Viewer

Interactive scientific viewing in OpenDiscovery.

## Use

Install from Discover → Science and approve the declared capabilities.
Alternatively, use Settings → Extensions → Apps → Add app with the public Git URL:

`https://github.com/generalepistemics/opendiscovery-science-packages#structure-viewer`
 Open a supported workspace file from Files, or ask the agent to open
its exact absolute path. Expand a viewer into the workbench to continue working
with the same scientific session.

Scientific files use server-owned handles, bounded reads and revision checks.
They do not pass through the ordinary text editor or the model as whole files.
State and caches stay inside this installation's private OpenDiscovery directories.

## Development

Use Node.js 24 and the checked-in npm lockfile:

```sh
npm ci
npm run build
npm run bundle -- --output-dir bundle/extension
```

The MCP server lives in `src/server.mjs`; scientific modules are separated
under `src/` and `src/scientific-platform/`. The native scientific backend is
`src/structure-backend.mjs`. Browser startup, session control and the viewer
surface are in `src/views/app.js`, `controller.js` and `surface.js`; the shared
scientific rendering runtime remains in `src/views/viewer.js`.

The bundle command stages the installable extension under `bundle/extension` and
prints its content digest. ZIP the contents of that directory for installation;
keep source, development dependencies and runtime state out of the archive.

The build produces the server and self-contained UI under `dist/`. The extension
launcher starts the built server over stdio. It does not install dependencies or
read another agent's global configuration at startup.

## Scientific qualification

Registration and successful opening alone do not establish numerical accuracy,
rendering or export compatibility. Validate the affected scientific workflows and
published format limits when changing algorithms, persistence or browser code.

Third-party licenses and notices are included in `LICENSE` and
`THIRD_PARTY_NOTICES.md`.

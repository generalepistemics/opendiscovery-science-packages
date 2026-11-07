# Excalidraw for OpenDiscovery

Draw in `.excalidraw` files and Obsidian `.excalidraw.md` drawings right in OpenDiscovery's Files view.

Open a matching file and you get the Excalidraw canvas instead of the text. OpenDiscovery keeps the file: Cmd/Ctrl+S, autosave, the unsaved-changes prompt, and changes made on disk work the same as for any other file. The source toggle shows the file's text, and fullscreen gives the canvas the whole window.

Obsidian drawings are written back in place. Frontmatter, text elements, and everything outside the `## Drawing` block stay as they were, and compressed drawings stay compressed.

## Install

In OpenDiscovery, open Settings → Extensions → Apps and add `https://github.com/generalepistemics/opendiscovery-science-packages.git#excalidraw`. Web and desktop only; mobile delivery is not currently supported.

## What's not here

- Mermaid and text-to-diagram. The converter is about two thousand modules on its own, so this build leaves it out and hides its menu entries.
- Export and "save as image". OpenDiscovery owns the file, and the canvas can't write elsewhere.

Excalidraw loads its hand-drawn fonts from the esm.sh CDN the first time you open a drawing.

## Build

```bash
bun install --frozen-lockfile
bun run build   # writes editor/main.js and editor/main.css
bun run test
bun run typecheck
```

The built files are committed: OpenDiscovery installs extensions without building them. Bump `version` in `package.json` to ship an update through Git.

## Credits

The canvas integration started in OpenChamber, contributed by [Maksym Mospanenko](https://github.com/mmospanenko) in [openchamber#4064](https://github.com/openchamber/openchamber/pull/4064), before becoming an independent extension. OpenDiscovery maintains this adaptation.

## License

MIT. Excalidraw itself is MIT, © Excalidraw.

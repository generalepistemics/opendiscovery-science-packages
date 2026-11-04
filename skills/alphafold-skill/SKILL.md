---
name: alphafold-skill
description: Submit compact AlphaFold Protein Structure Database API requests for prediction, UniProt summary, sequence summary, and annotation lookups. Use when a user wants AlphaFold metadata or concise structure summaries
---

## Source presentation
<!-- source-presentation-contract:v2 -->
- Add claim-adjacent links only for substantive claims supported by returned `sources`; never cite empty, metadata-only, or failed lookups.
- Preserve `checked_sources`, use only supported `canonical_url` mappings, and leave requested raw or machine-readable output unchanged.
- Use the `alphafold-skill` entry in `../../references/source-links.json` and follow `../../references/source-presentation.md`.

## Operating rules
- Use `scripts/rest_request.py` for all AlphaFold API calls.
- Use `base_url=https://alphafold.ebi.ac.uk/api`.
- The script accepts `max_items`, but set it explicitly only when trimming array-heavy responses; single-entry lookups usually do not need it.
- For `sequence/summary` or `annotations`, start around `max_items=3` to `5`.
- Re-run the request if the conversation is long instead of trusting older tool output.
- Treat displayed `...` in tool previews as UI truncation, not part of the real request.
- If the user asks for full JSON, set `save_raw=true` and report the saved file path instead of pasting the payload into chat.

## Execution behavior
- Return concise markdown summaries from the script JSON by default.
- Return the script JSON verbatim only if the user explicitly asks for machine-readable output.
- Prefer these paths: `prediction/<qualifier>`, `uniprot/summary/<qualifier>.json`, `sequence/summary`, and `annotations/<qualifier>.json`.
- Keep sequence-style inputs compact and prefer rerunning instead of copying prior output back into context.

## Input
- Read one JSON object from stdin.
- Required fields: `base_url`, `path`
- Optional fields: `method`, `params`, `headers`, `json_body`, `form_body`, `record_path`, `response_format`, `max_items`, `max_depth`, `timeout_sec`, `save_raw`, `raw_output_path`
- Common AlphaFold patterns:
  - `{"base_url":"https://alphafold.ebi.ac.uk/api","path":"prediction/Q5VSL9"}`
  - `{"base_url":"https://alphafold.ebi.ac.uk/api","path":"uniprot/summary/Q5VSL9.json"}`
  - `{"base_url":"https://alphafold.ebi.ac.uk/api","path":"annotations/Q5VSL9.json","params":{"type":"MUTAGEN"},"max_items":3}`

## Output
- Success returns `ok`, `source`, `path`, `method`, `status_code`, `warnings`, and either compact `records` or a compact `summary`.
- Use `raw_output_path` when `save_raw=true`.
- Failure returns `ok=false` with `error.code` such as `invalid_json`, `invalid_input`, `network_error`, or `invalid_response`.

## Execution
```bash
echo '{"base_url":"https://alphafold.ebi.ac.uk/api","path":"prediction/Q5VSL9"}' | python scripts/rest_request.py
```

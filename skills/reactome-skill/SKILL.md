---
name: reactome-skill
description: Submit compact Reactome ContentService requests for pathway, event, participant, search, and diagram-related data. Use when a user wants concise Reactome summaries
---

## Source presentation
<!-- source-presentation-contract:v2 -->
- Add claim-adjacent links only for substantive claims supported by returned `sources`; never cite empty, metadata-only, or failed lookups.
- Preserve `checked_sources`, use only supported `canonical_url` mappings, and leave requested raw or machine-readable output unchanged.
- Use the `reactome-skill` entry in `../../references/source-links.json` and follow `../../references/source-presentation.md`.

## Operating rules
- Use `scripts/rest_request.py` for all Reactome ContentService calls.
- Use `base_url=https://reactome.org/ContentService`.
- Single pathway or event lookups usually do not need `max_items`; list-style pathway membership calls are better with `max_items=10`.
- Send `Accept: application/json` in `headers` when requesting JSON.
- Re-run requests in long conversations instead of relying on older tool output.
- Treat displayed `...` in tool previews as UI truncation, not literal request content.

## Execution behavior
- Return concise markdown summaries from the script JSON by default.
- Prefer these paths: `data/query/<eventId>`, `data/pathways/low/entity/<identifier>`, `data/participants/<eventId>`, and search endpoints.
- If the user needs the full payload, set `save_raw=true` and report the saved file path.

## Input
- Read one JSON object from stdin.
- Required fields: `base_url`, `path`
- Optional fields: `method`, `params`, `headers`, `json_body`, `form_body`, `record_path`, `response_format`, `max_items`, `max_depth`, `timeout_sec`, `save_raw`, `raw_output_path`
- Common Reactome patterns:
  - `{"base_url":"https://reactome.org/ContentService","path":"data/query/R-HSA-199420","headers":{"Accept":"application/json"}}`
  - `{"base_url":"https://reactome.org/ContentService","path":"data/pathways/low/entity/P38398","params":{"species":"Homo sapiens"},"headers":{"Accept":"application/json"},"max_items":10}`
  - `{"base_url":"https://reactome.org/ContentService","path":"data/participants/R-HSA-199420","headers":{"Accept":"application/json"},"max_items":10}`

## Output
- Success returns `ok`, `source`, `path`, `method`, `status_code`, `warnings`, and either compact `records` or a compact `summary`.
- Use `raw_output_path` when `save_raw=true`.
- Failure returns `ok=false` with `error.code` and `error.message`.

## Execution
```bash
echo '{"base_url":"https://reactome.org/ContentService","path":"data/query/R-HSA-199420","headers":{"Accept":"application/json"}}' | python scripts/rest_request.py
```

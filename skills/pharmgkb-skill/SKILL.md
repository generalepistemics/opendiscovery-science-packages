---
name: pharmgkb-skill
description: Submit compact PharmGKB API requests for genes, variants, clinical annotations, dosing guidelines, and search. Use when a user wants concise PharmGKB summaries
---

## Source presentation
<!-- source-presentation-contract:v2 -->
- Add claim-adjacent links only for substantive claims supported by returned `sources`; never cite empty, metadata-only, or failed lookups.
- Preserve `checked_sources`, use only supported `canonical_url` mappings, and leave requested raw or machine-readable output unchanged.
- Use the `pharmgkb-skill` entry in `../../references/source-links.json` and follow `../../references/source-presentation.md`.

## Operating rules
- Use `scripts/rest_request.py` for all PharmGKB API calls.
- Use the current `base_url=https://api.clinpgx.org/v1/data`; the former `api.pharmgkb.org` hostname was retired.
- Single object lookups usually do not need `max_items`; list and search endpoints are better with `max_items=10`.
- Re-run requests in long conversations instead of relying on older tool output.
- Treat displayed `...` in tool previews as UI truncation, not literal request content.

## Execution behavior
- Return concise markdown summaries from the script JSON by default.
- Prefer these paths: `gene/<id>`, `variant/<id>`, `clinicalAnnotation`, `dosingGuideline`, and search endpoints.
- If the user needs the full payload, set `save_raw=true` and report the saved file path.

## Input
- Read one JSON object from stdin.
- Required fields: `base_url`, `path`
- Optional fields: `method`, `params`, `headers`, `json_body`, `form_body`, `record_path`, `response_format`, `max_items`, `max_depth`, `timeout_sec`, `save_raw`, `raw_output_path`
- Common PharmGKB patterns:
  - `{"base_url":"https://api.clinpgx.org/v1/data","path":"gene/PA128","max_items":5}`
  - `{"base_url":"https://api.clinpgx.org/v1/data","path":"clinicalAnnotation","params":{"relatedChemicals.accessionId":"PA449726","limit":10},"max_items":10}`
  - `{"base_url":"https://api.clinpgx.org/v1/data","path":"variant/PA166158545","max_items":5}`

## Output
- Success returns `ok`, `source`, `path`, `method`, `status_code`, `warnings`, and either compact `records` or a compact `summary`.
- Use `raw_output_path` when `save_raw=true`.
- Failure returns `ok=false` with `error.code` and `error.message`.

## Execution
```bash
echo '{"base_url":"https://api.clinpgx.org/v1/data","path":"gene/PA128","max_items":5}' | python scripts/rest_request.py
```

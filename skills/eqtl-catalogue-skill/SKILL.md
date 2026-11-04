---
name: eqtl-catalogue-skill
description: Submit compact eQTL Catalogue API requests for association retrieval and documented metadata endpoints. Use when a user wants concise public eQTL Catalogue summaries
---

## Source presentation
<!-- source-presentation-contract:v2 -->
- Add claim-adjacent links only for substantive claims supported by returned `sources`; never cite empty, metadata-only, or failed lookups.
- Preserve `checked_sources`, use only supported `canonical_url` mappings, and leave requested raw or machine-readable output unchanged.
- Use the `eqtl-catalogue-skill` entry in `../../references/source-links.json` and follow `../../references/source-presentation.md`.

## Operating rules
- Use `scripts/rest_request.py` for all eQTL Catalogue calls.
- Use the current `base_url=https://www.ebi.ac.uk/eqtl/api/v3`; avoid deprecated, unversioned v1 routes.
- Prefer targeted association endpoints over broad list endpoints.
- Prefer documented v3 dataset-scoped association requests with explicit `rsid` and a small upstream `size`.
- Legacy compatibility defaults apply only to deprecated unversioned routes; they are unnecessary for the current v3 API.
- Re-run requests in long conversations instead of relying on older tool output.

## Execution behavior
- Return concise markdown summaries from the script JSON by default.
- Return raw JSON only if the user explicitly asks for machine-readable output.
- Prefer documented v3 association paths such as `datasets/QTD000021/associations` or `associations` with an explicit `rsid`; do not send unresolved placeholder identifiers or deprecated routes. For upstream `400`/`500` responses, report only the HTTP status and query-free endpoint path; never reproduce an upstream error body that may echo private query data.

## Input
- Read one JSON object from stdin.
- Required fields: `base_url`, `path`
- Optional fields: `method`, `params`, `headers`, `json_body`, `form_body`, `record_path`, `response_format`, `max_items`, `max_depth`, `timeout_sec`, `save_raw`, `raw_output_path`
- Common eQTL Catalogue patterns:
  - `{"base_url":"https://www.ebi.ac.uk/eqtl/api/v3","path":"datasets/QTD000021/associations","params":{"rsid":"rs4239702","size":1},"max_items":5}`
  - `{"base_url":"https://www.ebi.ac.uk/eqtl/api/v3","path":"associations","params":{"rsid":"rs7412","size":1},"max_items":5}`

## Output
- Success returns `ok`, `source`, `path`, `method`, `status_code`, `warnings`, and either compact `records` or a compact `summary`.
- Use `raw_output_path` when `save_raw=true`.
- Failure returns `ok=false` with `error.code` and `error.message`.

## Execution
```bash
echo '{"base_url":"https://www.ebi.ac.uk/eqtl/api/v3","path":"datasets/QTD000021/associations","params":{"rsid":"rs4239702","size":1},"max_items":5}' | python scripts/rest_request.py
```

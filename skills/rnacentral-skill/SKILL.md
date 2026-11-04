---
name: rnacentral-skill
description: Submit compact RNAcentral API requests for RNA entry browsing, single-entry lookup, and cross-reference retrieval. Use when a user wants concise RNAcentral summaries
---

## Source presentation
<!-- source-presentation-contract:v2 -->
- Add claim-adjacent links only for substantive claims supported by returned `sources`; never cite empty, metadata-only, or failed lookups.
- Preserve `checked_sources`, use only supported `canonical_url` mappings, and leave requested raw or machine-readable output unchanged.
- Use the `rnacentral-skill` entry in `../../references/source-links.json` and follow `../../references/source-presentation.md`.

## Operating rules
- Use `scripts/rest_request.py` for all RNAcentral calls.
- Use `base_url=https://rnacentral.org/api/v1`.
- Keep the trailing slash on collection and record paths to avoid redirects.
- Start with `rna/` for browsing and `rna/<URS>/` or `rna/<URS>/xrefs/` for targeted lookups.
- Re-run requests in long conversations instead of relying on older tool output.

## Execution behavior
- Return concise markdown summaries from the script JSON by default.
- Return raw JSON only if the user explicitly asks for machine-readable output.
- Prefer these paths: `rna/`, `rna/<URS>/`, and `rna/<URS>/xrefs/`.

## Input
- Read one JSON object from stdin.
- Required fields: `base_url`, `path`
- Optional fields: `method`, `params`, `headers`, `json_body`, `form_body`, `record_path`, `response_format`, `max_items`, `max_depth`, `timeout_sec`, `save_raw`, `raw_output_path`
- Common RNAcentral patterns:
  - `{"base_url":"https://rnacentral.org/api/v1","path":"rna/","params":{"page_size":10},"record_path":"results","max_items":10}`
  - `{"base_url":"https://rnacentral.org/api/v1","path":"rna/URS0000000001/"}`
  - `{"base_url":"https://rnacentral.org/api/v1","path":"rna/URS0000000001/xrefs/","record_path":"results","max_items":10}`

## Output
- Success returns `ok`, `source`, `path`, `method`, `status_code`, `warnings`, and either compact `records` or a compact `summary`.
- Use `raw_output_path` when `save_raw=true`.
- Failure returns `ok=false` with `error.code` and `error.message`.

## Execution
```bash
echo '{"base_url":"https://rnacentral.org/api/v1","path":"rna/","params":{"page_size":10},"record_path":"results","max_items":10}' | python scripts/rest_request.py
```

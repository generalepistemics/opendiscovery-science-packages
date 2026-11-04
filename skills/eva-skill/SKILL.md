---
name: eva-skill
description: Submit compact EVA REST requests for species metadata and archived variant lookups. Use when a user wants concise European Variation Archive summaries
---

## Source presentation
<!-- source-presentation-contract:v2 -->
- Add claim-adjacent links only for substantive claims supported by returned `sources`; never cite empty, metadata-only, or failed lookups.
- Preserve `checked_sources`, use only supported `canonical_url` mappings, and leave requested raw or machine-readable output unchanged.
- Use the `eva-skill` entry in `../../references/source-links.json` and follow `../../references/source-presentation.md`.

## Operating rules
- Use `scripts/rest_request.py` for all EVA calls.
- Use `base_url=https://www.ebi.ac.uk/eva/webservices/identifiers/v1` for compact clustered-variant records or `base_url=https://www.ebi.ac.uk/eva/webservices/rest/v1` for documented study and assembly routes.
- Prefer targeted, evidence-bearing variant or study lookups over broad genomic window pulls and metadata-only checks.
- Keep region queries narrow by species, assembly, or small coordinate windows when possible.
- Re-run requests in long conversations instead of relying on older tool output.

## Execution behavior
- Return concise markdown summaries from the script JSON by default.
- Return raw JSON only if the user explicitly asks for machine-readable output.
- Prefer compact paths such as `clustered-variants/17870277`; use `meta/species/list` only to discover supported assemblies, never as biological evidence.

## Input
- Read one JSON object from stdin.
- Required fields: `base_url`, `path`
- Optional fields: `method`, `params`, `headers`, `json_body`, `form_body`, `record_path`, `response_format`, `max_items`, `max_depth`, `timeout_sec`, `save_raw`, `raw_output_path`
- Common EVA patterns:
  - `{"base_url":"https://www.ebi.ac.uk/eva/webservices/identifiers/v1","path":"clustered-variants/17870277","max_items":5}`
  - `{"base_url":"https://www.ebi.ac.uk/eva/webservices/rest/v1","path":"studies/PRJEB4019/summary","record_path":"response.0.result","max_items":5}`

## Output
- Success returns `ok`, `source`, `path`, `method`, `status_code`, `warnings`, and either compact `records` or a compact `summary`.
- Use `raw_output_path` when `save_raw=true`.
- Failure returns `ok=false` with `error.code` and `error.message`.

## Execution
```bash
echo '{"base_url":"https://www.ebi.ac.uk/eva/webservices/identifiers/v1","path":"clustered-variants/17870277","max_items":5}' | python scripts/rest_request.py
```

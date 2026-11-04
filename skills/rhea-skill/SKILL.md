---
name: rhea-skill
description: Submit compact Rhea reaction search requests for biochemical reactions and reaction IDs. Use when a user wants concise Rhea summaries
---

## Source presentation
<!-- source-presentation-contract:v2 -->
- Add claim-adjacent links only for substantive claims supported by returned `sources`; never cite empty, metadata-only, or failed lookups.
- Preserve `checked_sources`, use only supported `canonical_url` mappings, and leave requested raw or machine-readable output unchanged.
- Use the `rhea-skill` entry in `../../references/source-links.json` and follow `../../references/source-presentation.md`.

## Operating rules
- Use `scripts/rest_request.py` for all Rhea calls.
- Use Rhea's official `base_url=https://sparql.rhea-db.org` SPARQL endpoint for compact JSON reaction records.
- The website search API supports TSV, not `format=json`; avoid website requests that fail with Cloudflare HTTP 403.
- Keep queries narrow by reaction ID, compound name, EC number, or free-text reaction term.
- Re-run requests in long conversations instead of relying on older tool output.

## Execution behavior
- Return concise markdown summaries from the script JSON by default.
- Return raw JSON only if the user explicitly asks for machine-readable output.
- Prefer a targeted SPARQL reaction identifier, `LIMIT 1`, `format=json`, and `record_path=results.bindings`.

## Input
- Read one JSON object from stdin.
- Required fields: `base_url`, `path`
- Optional fields: `method`, `params`, `headers`, `json_body`, `form_body`, `record_path`, `response_format`, `max_items`, `max_depth`, `timeout_sec`, `save_raw`, `raw_output_path`
- Common Rhea patterns:
  - `{"base_url":"https://sparql.rhea-db.org","path":"sparql","params":{"query":"PREFIX rh: <http://rdf.rhea-db.org/> SELECT ?accession ?equation WHERE { <http://rdf.rhea-db.org/47148> rh:accession ?accession ; rh:equation ?equation . } LIMIT 1","format":"json"},"headers":{"Accept":"application/sparql-results+json"},"record_path":"results.bindings","max_items":5}`

## Output
- Success returns `ok`, `source`, `path`, `method`, `status_code`, `warnings`, and either compact `records` or a compact `summary`.
- Use `raw_output_path` when `save_raw=true`.
- Failure returns `ok=false` with `error.code` and `error.message`.

## Execution
```bash
echo '{"base_url":"https://sparql.rhea-db.org","path":"sparql","params":{"query":"PREFIX rh: <http://rdf.rhea-db.org/> SELECT ?accession ?equation WHERE { <http://rdf.rhea-db.org/47148> rh:accession ?accession ; rh:equation ?equation . } LIMIT 1","format":"json"},"headers":{"Accept":"application/sparql-results+json"},"record_path":"results.bindings","max_items":5}' | python scripts/rest_request.py
```

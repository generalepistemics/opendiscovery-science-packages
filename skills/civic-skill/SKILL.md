---
name: civic-skill
description: Submit compact CIViC GraphQL requests for cancer variant interpretation schema inspection and targeted evidence retrieval. Use when a user wants concise CIViC summaries
---

## Source presentation
<!-- source-presentation-contract:v2 -->
- Add claim-adjacent links only for substantive claims supported by returned `sources`; never cite empty, metadata-only, or failed lookups.
- Preserve `checked_sources`, use only supported `canonical_url` mappings, and leave requested raw or machine-readable output unchanged.
- Use the `civic-skill` entry in `../../references/source-links.json` and follow `../../references/source-presentation.md`.

## Operating rules
- Use `scripts/civic_graphql.py` for all CIViC GraphQL work.
- Keep selection sets narrow and start with targeted, evidence-bearing entity queries; reserve schema introspection for resolving a concrete query failure.
- Use `query_path` for longer GraphQL documents instead of pasting large inline queries.
- Re-run requests in long conversations instead of relying on older tool output.

## Execution behavior
- Return concise markdown summaries from the script JSON by default.
- Return raw JSON only if the user explicitly asks for machine-readable output.
- Prefer targeted evidence queries over schema-only checks and broad graph dumps.

## Input
- Read one JSON object from stdin.
- Required field: `query` or `query_path`
- Optional fields: `variables`, `max_items`, `max_depth`, `timeout_sec`, `save_raw`, `raw_output_path`
- Common CIViC patterns:
  - `{"query":"query { search(query:\"BRAF\") { id name matchingText resultType } }","max_items":5}`

## Output
- Success returns `ok`, `source`, `top_keys`, a compact `summary`, and `raw_output_path` when `save_raw=true`.
- Failure returns `ok=false` with `error.code` such as `invalid_json`, `invalid_input`, `network_error`, `invalid_response`, or `graphql_error`.

## Execution
```bash
echo '{"query":"query { search(query:\"BRAF\") { id name matchingText resultType } }","max_items":5}' | python scripts/civic_graphql.py
```

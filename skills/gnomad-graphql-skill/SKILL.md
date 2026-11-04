---
name: gnomad-graphql-skill
description: Submit compact gnomAD GraphQL requests for frequency, gene constraint, and variant context queries. Use when a user wants concise gnomAD summaries
---

## Source presentation
<!-- source-presentation-contract:v2 -->
- Add claim-adjacent links only for substantive claims supported by returned `sources`; never cite empty, metadata-only, or failed lookups.
- Preserve `checked_sources`, use only supported `canonical_url` mappings, and leave requested raw or machine-readable output unchanged.
- Use the `gnomad-graphql-skill` entry in `../../references/source-links.json` and follow `../../references/source-presentation.md`.

## Operating rules
- Use `scripts/gnomad_graphql.py` for all gnomAD GraphQL work.
- For nested GraphQL results, start with `max_items=3` to `5`.
- Keep selection sets narrow and page or filter at the query level instead of asking for broad dumps.
- Use `query_path` for long GraphQL documents instead of pasting large inline queries.
- Re-run requests in long conversations instead of relying on earlier tool output.
- Treat displayed `...` in tool previews as UI truncation, not part of the real query.

## Execution behavior
- Return concise markdown summaries from the script JSON by default.
- Return raw JSON only if the user explicitly asks for machine-readable output.
- Prefer targeted queries for variant frequency, gene constraint, or transcript consequence context.
- If the user needs the full payload, set `save_raw=true` and report the saved file path.

## Input
- Read one JSON object from stdin.
- Required field: `query` or `query_path`
- Optional fields: `variables`, `max_items`, `max_depth`, `timeout_sec`, `save_raw`, `raw_output_path`
- Common gnomAD patterns:
  - `{"query":"query Variant($variantId: String!, $dataset: DatasetId!) { variant(variantId: $variantId, dataset: $dataset) { variantId genome { ac an af } } }","variables":{"variantId":"10-112998590-C-T","dataset":"gnomad_r4"},"max_items":5}`

## Output
- Success returns `ok`, `source`, `top_keys`, a compact `summary`, and `raw_output_path` when `save_raw=true`.
- Failure returns `ok=false` with `error.code` such as `invalid_json`, `invalid_input`, `network_error`, `invalid_response`, or `graphql_error`.

## Execution
```bash
echo '{"query":"query Variant($variantId: String!, $dataset: DatasetId!) { variant(variantId: $variantId, dataset: $dataset) { variantId genome { ac an af } } }","variables":{"variantId":"10-112998590-C-T","dataset":"gnomad_r4"},"max_items":5}' | python scripts/gnomad_graphql.py
```

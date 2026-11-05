# Evidence and source presentation

Every substantive externally sourced claim must be traceable to the specific response that supports it; a successful skill invocation does not automatically provide scientific evidence.

| Output mode | Source treatment |
| --- | --- |
| Record or evidence lookup | Attach the authoritative record link to the claim or tightly related claim cluster it supports. |
| Search or result list | Link discussed records individually where a supported canonical mapping exists; do not cite an unrelated result or every returned row. |
| Connectivity, schema, service metadata, or status | Preserve structured `checked_sources` provenance but do not present the endpoint as evidence. |
| Empty result or failed request | Explain what happened without adding an evidence citation; keep successful checked-but-empty sources in `checked_sources` only. |
| Routing or orchestration | Propagate only downstream `sources` entries explicitly marked `supports_claim=true` and `kind=evidence`. |
| Derived or multi-source synthesis | Cite each evidence-contributing source beside its supported claim and retain checked-but-empty sources only in methods or limitations. |
| Requested raw JSON, XML, FASTA, or text | Preserve the upstream response exactly and never insert Markdown or source metadata into the saved raw payload. |

Use the skill-specific entry in `source-links.json` and the runtime-emitted `canonical_url` whenever the source supports a deterministic authoritative public record page. Construct URLs only from explicitly mapped identifier fields and validated identifier formats. URL-encode identifier values, apply documented transforms, and never invent a deep link for an unsupported source, record, or identifier.

Structured evidence sources include an authoritative display name, a sanitized URL, retrieval time, `kind=evidence`, and `supports_claim=true`; successful connectivity, metadata, and empty checks instead appear under `checked_sources` with `supports_claim=false`. Remove URL credentials and fragments, redact API keys, tokens, passwords, signatures, email addresses, and free-text query or sequence values, and never expose request bodies or exception URLs. Generic database homepages identify provenance but must not be presented as record-specific evidence.

When synthesizing multiple downstream responses, use `evidence_sources()` to preserve only actual evidence-bearing source entries, deduplicate matching records, and avoid promoting failures or checked-but-empty responses into citation support. Keep an optional final source list supplemental to claim-adjacent citations rather than a replacement for them.

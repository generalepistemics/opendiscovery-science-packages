---
name: verify-citations
description: Check whether cited papers actually exist, are described correctly, and have not been retracted. Use when the user pastes a bibliography, reference list, or citations from a draft, asks whether a paper is real, or wants references from an AI-generated answer checked before relying on them.
metadata:
  short-description: Confirm papers exist, match their citation, and are not retracted
---

# Verify citations

Confirm each cited paper exists in the published record, that the citation
describes it accurately, and that it has not been retracted.

A citation that cannot be found is the finding. Report it as unverified and stop
there — never substitute the closest real paper, and never fill in a missing
DOI, year, or venue from memory. A confidently wrong reference is worse than an
acknowledged gap, because the user will submit it.

## Quick start

1. Split the input into individual citations. One `verify_paper` call per
   citation, never several at once in one string.
2. Pass whatever the user gave: a DOI, a bare title, or a full citation string
   all work. A `paper_id` from an earlier Pendar result also resolves exactly.
3. Classify each result — verified, ambiguous, retracted, or not found — using
   the rules below.
4. Report every citation in the order given, then a one-line tally.

## Reading the result

- `found: false` — the paper could not be resolved. Say so plainly and quote
  `reason`. Do not offer a different paper as though it were the one cited. If
  the user wants alternatives, offer to search the literature instead, as a
  separate step they asked for.
- `candidates` non-empty — the citation was too ambiguous to resolve. List the
  candidates with year, venue, and author so the user can choose. Ask which one
  they meant. Do not pick the top candidate silently.
- `match_confidence` below about 0.8 — the match is uncertain even though a
  paper came back. Show the resolved `title`, `year`, and `authors` next to what
  the user wrote so they can judge it themselves.
- `retraction_warning` non-empty, or `paper.is_retracted: true` — lead with the
  retraction. Say the paper is retracted before saying anything about its
  findings, and advise against citing it as standing evidence.
- `paper.work_type` of `preprint` — flag that it has not been peer reviewed. The
  user may have cited it as a journal article.
- Metadata that disagrees with the user's citation — a different year, venue, or
  author list — report the discrepancy and give the canonical values from
  `paper`. Do not quietly correct it; the user needs to know their source was
  wrong.

## Never

- Invent or guess a DOI, a `paper_id`, or a URL. Use `paper.doi` and
  `paper.landing_url` as returned, or say they are unavailable.
- Claim a paper is retracted unless `is_retracted` is true.
- Treat `found: false` as proof of fabrication. It means the paper is not in the
  indexed record, which is strong evidence for a mainstream journal article and
  weak evidence for a book chapter, thesis, technical report, or very recent
  preprint. Say which case you think it is.
- Report `citation_count` as a measure of quality. It measures attention, and a
  recent paper has had less time to accumulate any.

## Reporting

Give one line per citation, in the user's order, each with a clear verdict:

- **Verified** — canonical title, authors, year, venue, DOI.
- **Retracted** — the same, with the retraction stated first.
- **Ambiguous** — the candidates, and the question of which was meant.
- **Not found** — what was searched for, and why it may be missing.

Close with the tally: how many verified, how many retracted, how many
unresolved. If anything was retracted or unresolved, say explicitly that the
draft needs those references fixed before submission.

## Related workflows

- To measure a paper's influence rather than its existence, use
  `trace-citation-impact`.
- To find what else exists on the subject, use `survey-a-research-field`.

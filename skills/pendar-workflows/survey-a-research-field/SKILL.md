---
name: survey-a-research-field
description: Size and characterise a research area from exact publication counts — how many papers exist, whether output is growing or fading, which sub-areas and disciplines it divides into, which countries and institutions produce it, where it is published, and what to read first. Use when the user asks how large, how active, or how crowded a field is, wants an overview of a topic's literature, or is deciding whether to enter an area.
metadata:
  short-description: Measure a research field by exact publication counts
---

# Survey a research field

Describe a body of literature by counting it. `survey_literature` returns exact
counts over every paper matching the topic — not a sample — so the answer can
state how many papers exist, how that number moved year by year, and who
produced them.

The counts are the substance here. A list of relevant papers comes back too, but
it is the smaller half of the answer, and leading with it wastes what the tool is
for.

## Quick start

1. Reduce the user's question to a **short noun phrase of two to six words**.
   "How much work has been done on solid-state electrolytes for lithium metal
   batteries?" becomes `solid state electrolytes lithium metal`.
2. Call `survey_literature` once. Add `year_from` or `year_to` only if the user
   asked about a period.
3. Read `corpus.total_papers` together with `corpus.matched_on` before saying
   anything about size — the second changes what the first means.
4. Lead with size and trend, then composition, then the reading list.
5. Repeat every caveat in `notes` that bears on what you claim.

## Choosing the query

The search requires **every** word to appear, so each extra word shrinks the
corpus, and question words are stripped before searching.

- Drop question framing, verbs, and articles: keep the subject.
- Keep the phrase specific enough to mean one field and no more.
- If `total_papers` is 0 or in the low single digits, the terms were too narrow.
  Retry once with the two or three most central words, and tell the user you
  broadened it and to what.
- If the number looks implausibly large for the subject, the terms were too
  generic. Retry with the distinguishing term restored.

Never present a retry as a different question. State which phrase produced the
numbers you are reporting; `corpus.searched_for` shows what was actually
searched after stripping.

## Reading the result

- `corpus.total_papers` with `corpus.matched_on`:
  - `title_and_abstract` — a conservative count. Papers that mention the topic
    only in passing are excluded.
  - `full_text` — too few papers had the topic in title or abstract, so the
    corpus was widened to anything whose full text mentions it. Report the total
    as an **upper bound**, because passing mentions are now included.
- `corpus.trend` — `interpretation` is already written from the exact per-year
  counts; use it rather than recomputing a trend from `papers_by_year`. Treat
  `too_new` as insufficient history, not as a lack of growth. The current year is
  partial, so never describe a field as declining on the strength of the latest
  bar alone.
- `corpus.topics` versus `corpus.disciplines` — topics are the **sub-areas the
  work divides into**; disciplines are the **fields whose researchers produce
  it**. Keep them apart. A topic list answers "what is this field about", and a
  discipline list answers "who works on it".
- `corpus.countries` and `corpus.institutions` — shares overlap and total well
  above 100%, because a paper written across four institutions counts once in
  each. Say so if you quote them.
- `corpus.venues` — preprint servers and repositories rank here beside journals.
  A repository near the top is a finding: the field circulates before peer
  review.
- `corpus.work_types` — a large preprint share means a fast-moving field where
  the published record lags.
- `corpus.retracted_papers` — mention any retractions if the user intends to rely
  on the field's findings.
- `papers` — the most relevant papers, with abstract snippets. Summarise what
  they cover; do not present them as the field's most important work, since they
  are ranked by relevance to the query rather than by influence.

## Never

- Read percentages from a small corpus as proportions of a research area. Exact
  arithmetic over six papers still prints as "33%". When `notes` flags a small
  corpus, describe the individual papers instead.
- Compare two topics' totals without saying whether both were matched the same
  way. A `full_text` total against a `title_and_abstract` total is not a
  comparison.
- Add papers, counts, or trends from memory. Everything reported must come from
  the response.
- Call the tool repeatedly to page through a field. One survey covers the whole
  corpus; more calls only re-count it.

## Reporting

1. **Size** — the total, what it was matched on, and the years covered.
2. **Trajectory** — the trend, with the recent versus prior three-year counts
   behind it and the peak year.
3. **Composition** — sub-areas, then the disciplines and countries producing the
   work, then where it is published and how much is peer reviewed.
4. **What to read** — the returned papers, grouped by what they address.
5. **Caveats** — the corpus definition and any small-corpus or retraction note.

## Related workflows

- To measure one paper's influence rather than a field's size, use
  `trace-citation-impact`.
- To check a specific reference the user already has, use `verify-citations`.

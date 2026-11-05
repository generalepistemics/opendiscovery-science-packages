---
name: trace-citation-impact
description: Trace who has built on a specific paper — whether its citations are accelerating or fading, which research fields picked it up, whether universities or industry or hospitals are citing it, and which authors cite it most. Use when the user asks how influential a paper is, whether it is still relevant, where a method spread, which labs are working on it, or what it was built on.
metadata:
  short-description: Follow who has built on a paper, and where it spread
---

# Trace citation impact

Take one paper and report how the literature has used it: the exact per-year
citation history, the fields the citing work comes from, the kinds of institution
doing the citing, and the authors citing it most. `graph_hopper` resolves the
paper, walks one hop forward to its citers and one hop back to its references,
and returns counts over the citing set.

The value is in *who* cited it, not how many did. A citation total is available
anywhere; the composition of the citing set is what says whether a method
travelled beyond its home field and who is carrying it.

## Quick start

1. Call `graph_hopper` with the paper as a DOI, title, or full citation string.
   A `paper_id` from an earlier Pendar result also works and resolves exactly.
2. Leave `direction` as `both` unless the user asked only about influence
   (`forward`) or only about foundations (`backward`).
3. Leave `analyze_citers` at 50, or raise it toward 100 for a heavily cited
   paper. It widens the breakdowns at almost no cost, since they come back as
   counts.
4. Keep `papers_per_direction` small — 10 is usually enough. The breakdowns
   already summarise the rest.
5. Set `include_graph: true` **only** when the user wants a diagram of the
   neighbourhood. It is large and adds nothing the breakdowns do not cover.

If `found` is false, present `candidates` and ask which paper was meant. Do not
analyse a paper the user did not ask about.

## Reading the result

- `momentum.trend` is one of `accelerating`, `steady`, `declining`, `too_new`,
  `unreliable`, or `unknown`.
  - **`unreliable` means report no trend at all.** The paper's own per-year
    history contradicts itself, which happens when duplicate records for one
    paper are merged or split and most of its citations follow the other copy.
    Say the citation record for this paper appears damaged and that a trend
    cannot be read from it. Do not describe such a paper as declining — that is
    the artefact talking, and it will be wrong about famous papers in particular.
  - `too_new` means too little history, not lack of impact.
  - Use `momentum.interpretation` as written; it is derived from the exact
    histogram. `recent_3y_citations` against `prior_3y_citations` is the evidence
    behind it.
- `field_mix` — the research areas the citing papers belong to, from a standard
  discipline taxonomy. Name both `subfield` and `field`. Subfields far from the paper's
  own are the interesting part: they are where the work crossed over. Do not
  reduce this to a single "interdisciplinarity" figure; field boundaries are
  administrative and such a number would mislead.
- `institution_mix` — universities, industry, hospitals, government labs. An
  industry or hospital share is the signal that research became practice.
  `representative_institutions` are examples from that bucket, not the full list,
  so do not present them as the only ones.
- `top_citing_authors` — the corresponding authors citing the work most, ranked
  by their own citation totals. These are the people building on it: useful for
  finding collaborators, reviewers, or labs to approach. They are **not**
  co-authors of the seed paper, and citing a paper does not imply endorsing it.
- `cited_by` and `references` — the most-cited individual papers in each
  direction. Abstracts are omitted; call `verify_paper` on one if the user wants
  its full record.
- `notes` — carries the sample size behind the breakdowns ("breakdowns cover N
  citing papers") and flags an absent citer or reference list. Quote the sample
  size whenever you quote a percentage.

## Never

- Equate citation count with quality or correctness. It measures attention.
  Retracted papers accumulate citations too, so check `seed.is_retracted`.
- Report a decline when `trend` is `unreliable`.
- Say a paper is uncited when `notes` reports that no citers were indexed — a
  recent paper and an unindexed one look identical from here, and the note
  distinguishes them.
- Infer a lab's research agenda, a company's product plans, or an author's
  opinion from a single citation.
- Compare two papers' raw citation totals across different years or fields
  without saying that both vary by publication age and field size.

## Reporting

1. **The paper** — canonical title, authors, year, venue, total citations, and
   any retraction.
2. **Trajectory** — accelerating, steady, declining, or unreadable, with the
   three-year counts and peak year behind it.
3. **Where it spread** — the citing fields, calling out any far from the paper's
   own subfield.
4. **Who is citing** — the institution mix, then the leading citing authors.
5. **What to read next** — the most-cited citing papers, and the references if
   the user asked what it was built on.
6. **Sample size and caveats** — how many citers the breakdowns cover.

## Related workflows

- To size the whole field rather than one paper's reach, use
  `survey-a-research-field`.
- To confirm a reference exists and is not retracted, use `verify-citations`.

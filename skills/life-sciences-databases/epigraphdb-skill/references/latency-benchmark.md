# Life Sciences Databases latency benchmark

Measured on August 6, 2026 against the actual plugin-owned Python clients running on an authorized Linux AgentBox with access to the public scientific APIs.

## Coverage and method

- All 44 database skills and all three independently packaged literature skills were discovered at runtime and invoked with documented, substantive biological tasks. The duplicate NCBI Entrez implementations were measured separately.
- Six supplemental workflows exercised Open Targets multi-page disease evidence and `rs7412` resolution across all five variant-backed skills.
- Each of the 53 workflows received two fresh-process cold invocations and 20 same-interpreter warm invocations. Reported p50 and p95 are empirical values from the 20 warm samples.
- A result counted as successful only when the real backend returned a nonempty biological record and a claim-supporting `sources` entry. Connectivity, metadata, empty responses, and request failures were never counted as evidence.
- Baseline and optimized runs executed byte-for-byte copies of the corresponding plugin worktrees; request URLs and logged HTTP data excluded private queries and credentials.
- Final exact-commit verification passed all 53 workflows, covering every one of the 47 packaged skills and all six supplemental workflows without skips.

## Measured hot paths

| Workflow | Baseline p50 | Optimized p50 | Change | HTTP requests |
| --- | ---: | ---: | ---: | --- |
| BioBank Japan `rs7412` | 1,487 ms | 886 ms | -40.4% | 3 to 2 |
| FinnGen `rs7412` | 2,137 ms | 1,483 ms | -30.6% | 3 to 2 |
| GTEx `rs7412` | 1,355 ms | 771 ms | -43.1% | 3 to 2 |
| TPMI `rs7412` | 2,105 ms | 1,506 ms | -28.4% | 3 to 2 |
| UKB TOPMed `rs7412` | 1,579 ms | 972 ms | -38.4% | 3 to 2 |
| Open Targets two-page heatmap | 411 ms | 366 ms | -11.1% | 2; shared connection |
| GeneBass gene plus phenotype descriptions | 1,123 ms | 1,071 ms | -4.7% | 2; shared connection |

The variant clients now request only the genome build required by the downstream database. GTEx pagination, Open Targets disease pagination, and GeneBass metadata retrieval share one scoped HTTP session while preserving full result coverage, timeouts, raw response bytes, error handling, and evidence provenance.

## API compatibility findings

- eQTL Catalogue: use the current `/eqtl/api/v3` dataset-association endpoints; deprecated unversioned routes produced 25-second timeouts and 400/500 errors.
- EVA: use the supported clustered-variant identifier endpoint rather than a metadata-only species list or an empty deprecated variant lookup.
- PharmGKB: `api.pharmgkb.org` was retired. Use `api.clinpgx.org/v1/data` and current `www.clinpgx.org` record pages; CYP2D6 `PA128` is a validated fixture.
- Rhea: the website search API does not support JSON and returns HTTP 403 from the benchmark runtime. The official Rhea SPARQL endpoint returns compact, evidence-bearing JSON reaction records without bypassing access controls.
- gnomAD: the previous documented variant is absent from the current dataset; `10-112998590-C-T` is a validated nonempty replacement.
- ProteomeXchange and Reactome intermittently failed during sustained repeated sampling despite independently verified successful documented requests.

Existing raw-output preservation, source redaction, unsupported-link rejection, and metadata/empty-result exclusions remain covered by the plugin test suite.

# Starter examples

These examples use authoritative public records and OpenDiscovery's authorized
research and workspace tools. The complete prompts, source pins, validation
bounds, expected outputs, and failure behavior are maintained in
[`starter-examples.json`](starter-examples.json).

| Workflow | User-facing request | Reference result |
| --- | --- | --- |
| ENA FASTQ | Fetch `DRR037765`, open the first 500 reads, and report live length, GC, Q30, and subset provenance. | 500 reads; 469–471 bp; 28.8% GC; 95.4% Q30. The output is a verified bounded subset with its own provenance. |
| RAS alignment | Fetch UniProt `P01116`, `P01111`, and `P01112`; map conserved KRAS motifs; compare distances and inspect a tree. | A verified three-row alignment, mapped motifs, distance matrix, and exploratory uncorrected p-distance tree. The topology is not a publication phylogeny. |
| Lambda cI | Fetch NCBI `NC_001416.1`, map cI to OR1–OR3, and translate using code 11. | A verified 48,502-base record and the 237-aa cI translation derived from `complement(37227..37940)` using genetic code 11. |

For every workflow, verify the live source identity and returned viewer state.
Do not infer a successful open or scientific result from a prompt, accession,
or expected value alone. A retrieval or validation error must not fall back to
bundled or synthetic data.

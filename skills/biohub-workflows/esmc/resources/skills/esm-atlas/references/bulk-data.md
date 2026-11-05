# Atlas batch and anonymous S3

## Batch lifecycle

The raw request accepts a nonempty list, deduplicates it to at most 500 entries, reports malformed hashes as per-protein errors, and supports flags for sequence, structure, cluster info, and protein/per-residue features. The plugin instead validates every hash locally and rejects mixed-validity input before submission. Small requests may return a zip with HTTP 200. Larger requests return HTTP 202 with `job_id` and polling state.

Persist `job_id`, status, counts, and timestamps. Treat these as terminal: `completed`, `cancelled`, `failed`, `expired`. A cancel returns 204 idempotently for a known job and 404 for an unknown job; if output was already produced, later GET may still return it. Signed download URLs are ephemeral capabilities: keep one in memory only, never durable state, and reacquire it by polling when resuming. Use `.partial` plus HTTPS Range resume when supported, then validate the complete ZIP, atomically rename, and SHA-256 checksum.

The CLI writes a request-bound `submitting` state immediately before POST. If the process ends before a `job_id` is durably recorded, provider acceptance is unknown: preserve the resulting `submission-indeterminate` state, never resume or resubmit that state, and reconcile manually with Atlas operators. Atlas has no public recovery endpoint for a lost job ID; only consider a distinct new state and submission after separate explicit confirmation and a duplicate-work warning. Definitive non-accepting HTTP responses (`400`, `401`, `402`, `403`, `404`, `422`, and `429`) are durably classified as `submission-rejected`; remediate the error, then use a newly invoked command to retry only the exact request bound to that state and never before the persisted `Retry-After` deadline. A synchronous completion has no remote job to poll: status/wait return persisted evidence and cancellation is a no-op. State replacement is atomic and locked; provenance is a separate sidecar repaired from state on the next command after a crash. An unknown cancellation result may retry the documented idempotent DELETE; a provider-accepted cancellation request is not sent twice.

## Anonymous data

The [Biohub get-started guide](https://biohub.ai/esm/protein/get-started) publishes data under `s3://esm-protein-atlas/v1/` with CC-BY-4.0 licensing.

```bash
aws s3 sync --no-sign-request \
  s3://esm-protein-atlas/v1/clusters/indexes/secondary/cluster_members/ \
  /absolute/path/atlas-cluster-members
```

Use the narrowest dataset prefix. Approximate published sizes are large: sequences ~2.2 TB, structures ~68.9 TB, SAE feature data ~306 TB, and the full release ~377 TB. Cluster membership (~26 GB) is the recommended manageable starting point. Record bucket prefix, transferred bytes, ETag/checksum where available, download timestamp, and license attribution.

The current get-started guide publishes these exact anonymous locations:

| Dataset | Published size | S3 source |
| --- | ---: | --- |
| Sequences | 2.20 TB | `s3://esm-protein-atlas/v1/sequences/` |
| Structures | 68.9 TB | `s3://esm-protein-atlas/v1/folds/` |
| SAE features | 306 TB | `s3://esm-protein-atlas/v1/sae/data_shards/` |
| SAE clusters | 26.0 GB | `s3://esm-protein-atlas/v1/clusters/indexes/secondary/cluster_members/` |
| HMM results | 653 MB | `s3://esm-protein-atlas/v1/clusters/data/representative_proteins.parquet` |
| Protein-to-accession indexes | 162 GB | `s3://esm-protein-atlas/v1/shared_indexes/` |
| Feature normalization | 192 KB | `s3://esm-protein-atlas/v1/normalization/max_idf_log10.pkl` |
| Full release | 377 TB | `s3://esm-protein-atlas/v1/` |

Use `aws s3 sync --no-sign-request` for prefixes and `aws s3 cp --no-sign-request` for the two single files. Do not silently widen a requested subset to the full release.

Atlas provides these anonymous downloads without charging the downloader for source transfer. Destination storage, downstream processing, third-party networks, or later egress may still cost money. Before a multi-gigabyte or multi-terabyte sync, estimate the selected prefix size and local/cloud storage impact, show the exact source and destination plus any available cost information, and obtain separate explicit current-turn confirmation. A small public API read is not authorization for a bulk S3 transfer.

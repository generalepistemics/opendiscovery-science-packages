# Safety, licensing, and provenance contract

## Scientific claims

- Treat every structure, feature interpretation, mutation score, and functional label as a model-generated hypothesis.
- Require experimental validation appropriate to the claim. Do not present a predicted structure as experimental truth, a static structure as molecular dynamics, an SAE label as established function, or an untrained classifier head as a biological prediction.
- ESMFold2 output is one static conformational hypothesis. It does not capture kinetics, ensembles, environment-dependent dynamics, binding affinity, or experimental uncertainty by itself.
- Treat a managed fold as incomplete when any biological residue lacks finite N, CA, and C backbone coordinates. All-null atom37 rows are accepted only as explicitly aligned `|` chain-break placeholders, never as biological residues.
- Record an explicit evidence class for every displayed structure. A PDB or mmCIF container does not establish experimental provenance. In particular, ESM Atlas coordinates remain model hypotheses unless an authoritative source explicitly proves an experimentally determined structure.

## Biosafety and acceptable use

Follow the [Biohub Acceptable Use Policy](https://biohub.org/acceptable-use-policy/). The managed platform may restrict controlled pathogen/toxin inputs. Do not bypass those restrictions. Legitimate researchers affected by a restriction should use Biohub's elevated-access process. Never infer that open weights remove the user's responsibility to follow institutional, legal, and biosafety review.

## Durable execution

Resolve inputs and validate locally, then execute. Status-only preflight runs first and is never gated: it reads no secret and costs nothing. Managed inference at tutorial scale, including every ESMFold2 tutorial fold, then runs without a separate confirmation. Managed requests may incur cost. Report provider-returned credit or token usage when available; otherwise state that the API did not report usage or cost, and never invent an estimate. For Modal, self-hosted GPU campaigns, or bulk transfers, freeze the exact remote request, artifact plan, and cost ceiling, show that scope, and obtain a plain yes/no confirmation before spending; a runtime confirmation flag is a post-consent backstop, not consent. After confirmation, run preflight, complete credential setup, execute the pinned request, and materialize outputs as one uninterrupted workflow. Never retry an indeterminate provider call. Reconcile provider state first; if the call succeeded but local materialization failed, recover from the preserved raw response without another provider request.

Script-route Atlas protein lookup defaults to `fold_on_miss=false`. An on-demand Atlas fold is a separate explicit opt-in and is allowed only after a non-folding lookup returns the actual sequence, whose Atlas alphabet, MD5 binding, and length of at most 699 residues are validated; otherwise stop before the folding request.

Small public Atlas API reads need no spend confirmation. Before any multi-gigabyte or multi-terabyte anonymous-S3 transfer, freeze the exact source prefix, destination, estimated bytes, storage and egress impact, and cost ceiling, then obtain separate explicit current-turn confirmation.

## Licensing

- Released ESM model code and weights are MIT licensed; verify the exact model card and bundled notices at the pinned revision.
- ESM Atlas data is CC-BY-4.0. Preserve attribution, source hash/accession, retrieval timestamp, and dataset/API version in derived work.

## Required provenance sidecar

For every generated or downloaded artifact, record:

1. execution route (`atlas-api`, `atlas-s3`, `biohub`, `modal`, or `self-hosted`)
2. exact endpoint/base URL
3. exact managed model ID or Hugging Face repository and revision
4. the verified source commits of the pinned `esm` and `transformers` PyPI wheels when those dependencies execute locally or on Modal
5. SHA-256 digest of normalized input (do not duplicate sensitive input unless the user explicitly wants it stored)
6. complete inference parameters, MSA provenance, and seed
7. UTC start and finish timestamps
8. every output path, size, media type, and SHA-256 checksum
9. available confidence metrics: pLDDT, pAE, pTM, iPTM, pair-chain iPTM, similarity, or feature activation statistics
10. provider job/call ID when asynchronous

The helper CLI writes atomic JSON sidecars. Never put credentials, credential-bearing headers, Modal config contents, or raw provider errors that could echo a secret into provenance.

Use `null` for a local code revision when that dependency did not execute.
Before recording a revision for an installed SDK or model library, run `verify-install`; do not infer it from documentation alone.
`verify-install` checks that the installed version and payload digest match the pins, every RECORD-listed file is present and unmodified, no unlisted file sits in the package tree, and the import location is the verified install.
Bytecode caches for recorded sources are trusted rather than re-verified.
Only then does it return the source commit that the pinned wheel was built from.

# Source pins and primary references

The SDK pins were verified on 2026-09-23; the model and tutorial pins on 2026-07-14.
These pins fix first-party source and model selection; re-resolve and test before deliberately upgrading them.
They do not constitute a complete environment lock because the pinned ESM package retains broad transitive dependency ranges and execution still depends on the Python, accelerator, driver, and hardware runtime.

## SDK wheels

| Distribution | Wheel SHA-256 | Payload SHA-256 | Source commit |
| --- | --- | --- | --- |
| `esm==3.4.1.post1` | `f9e62b363519860d27762989871a531cdbd02d69c824cc8c8a1047b16dce3ef6` | `02e6bbe94ac6b4362fddd56ab622d7be20d151291001392c0dd1d509db50f535` | `Biohub/esm` tag `v3.4.1.post1`, `43b4548b86762edfa747b07d5f440aad3c33acee` |
| `transformers==4.57.6` | `4c9e9de11333ddfe5114bc872c9f370509198acf0b87a832a0ab9458e2bd0550` | `ca8339a7d7a3c5e7616e3e792b0ccfc93c8aa5f1717ba4c09242927bf9cbf3bd` | `huggingface/transformers` tag `v4.57.6`, `753d61104116eefc8ffc977327b441ee0c8d599f` |

Install both from PyPI in one command: `pip install "esm==3.4.1.post1" "transformers==4.57.6"`.
`transformers==4.57.6` is the only release inside the `>=4.57.6,<5` range that `esm==3.4.1.post1` declares.
The payload SHA-256 is the digest of the sorted `path,hash` lines from the wheel `RECORD` for the importable package, with bytecode excluded.
It is the same whether it is computed from the wheel file or from an installed copy, which lets `verify-install` check an install without the original wheel.
Every file of the `transformers` wheel matches its source tag byte for byte.
The `esm` wheel matches its tag for all 158 tracked `esm/` files, but was built from a tree with five untracked leftovers: four `*_test.py` files and an `esm/models/esmc.py` module that the `esm/models/esmc/` package shadows, so it can never be imported.
The recorded `esm_git_revision` therefore identifies the tag the published wheel corresponds to, not a clean build of that commit; the payload digest is what binds the installed files.

## Model revisions

| Artifact | Revision |
| --- | --- |
| `biohub/ESMC-300M` | `a59b831785f907e96e6a246b1d142bfb76df31ee` |
| `biohub/ESMC-600M` | `a7e82012c83126b9eedb055fea9fa84b6c02f094` |
| `biohub/ESMC-6B` | `45b0fa5d7fb06faefbd5e3b89bdcef35d564e79a` |
| `biohub/ESMFold2` | `1ebf0e3481a5184eb6171d40615c79e384b48796` |
| `biohub/ESMFold2-Fast` | `b28d8ace5e05e61e5bec1e6820cfd3e221819d12` |
| Modal Python SDK | `1.5.2` |

## Official tutorial snapshots

The plugin's expanded use cases are derived from these notebooks at `Biohub/esm` commit `ba4d7124864eed323a93bf3cfefcd958f573b75a` (`TUTORIAL_SOURCE_REVISION`).
This is pinned separately from the SDK: all three notebooks changed by the `v3.4.1.post1` tag, and the ESMFold2 notebook replaced the antibody-antigen example this contract uses.
SHA-256 values cover the raw notebook bytes retrieved from that revision on 2026-07-14; the machine-readable mapping lives in [`examples/tutorial-use-cases.json`](../examples/tutorial-use-cases.json).

| Notebook | Repository path | SHA-256 |
| --- | --- | --- |
| ESMC mutation scoring | `cookbook/tutorials/esmc_mutation_scoring.ipynb` | `40b49cecb80c18a1076013999a06b90f9f77bb6c06f81789d071335d09ae1482` |
| ESMC SAE feature interpretation | `cookbook/tutorials/esmc_sae_feature_interpretation.ipynb` | `4ac0dd7b39d694787f3ce858221f1d045fd225c16c580762e3c2af5919ed59d2` |
| ESMFold2 | `cookbook/tutorials/esmfold2.ipynb` | `efc47094be02ea99c409e09830a1275fc1fe46c46accda2e942bbef876c357b3` |

Use the exact versions in installs and the full revisions, not `main`, in `from_pretrained(..., revision=...)`.
The pinned ESMFold2 configs name their `biohub/ESMC-6B` backbone without a revision, so self-hosted and Modal code loads the trunk with `load_esmc=False` and attaches ESMC-6B at its pinned revision explicitly.
Run `verify-install` before execution.
Record both code revisions and the Hugging Face model revision in every self-hosted or Modal provenance sidecar.
Atlas and raw-HTTP paths record these code revisions as `null` because those dependencies did not execute.
Live SDK/local smokes verify the installed wheels before asserting a local code commit.

The generic Modal job controller requires the exact SDK version above because its resumability decisions depend on the documented `FunctionCall` methods and exception classes. It also requires a positive deployed Function version and uses Modal's version-pinned `Function.from_name` lookup. Both values are recorded in durable job state; update the SDK pin only after revalidating spawn, reattachment, polling, cancellation, and exception classification against the new release. Modal's official changelog and PyPI release metadata both identify `1.5.2` as the current stable release on 2026-07-13; the version-pinned Function lookup used here was introduced in 1.5.0.

## Primary sources

- [Biohub protein world model](https://biohub.ai/esm/protein)
- [Biohub ESM get-started guide](https://biohub.ai/esm/protein/get-started)
- [ESMC model page](https://biohub.ai/models/esmc)
- [ESMFold2 model page](https://biohub.ai/models/esmfold2)
- [Biohub managed API reference](https://biohub.ai/api-reference)
- [ESM Atlas API overview](https://biohub.ai/esm/protein/atlas/api-docs/overview.html)
- [ESM Atlas API reference](https://biohub.ai/esm/protein/atlas/api-docs/api_reference.html)
- [ESM Atlas OpenAPI document](https://biohub.ai/esm/protein/atlas/api-docs/_static/openapi.json)
- [Biohub/esm source](https://github.com/Biohub/esm)
- [esm on PyPI](https://pypi.org/project/esm/3.4.1.post1/)
- [transformers on PyPI](https://pypi.org/project/transformers/4.57.6/)
- [Official ESMC mutation-scoring tutorial](https://github.com/Biohub/esm/blob/ba4d7124864eed323a93bf3cfefcd958f573b75a/cookbook/tutorials/esmc_mutation_scoring.ipynb)
- [Official ESMC SAE-interpretation tutorial](https://github.com/Biohub/esm/blob/ba4d7124864eed323a93bf3cfefcd958f573b75a/cookbook/tutorials/esmc_sae_feature_interpretation.ipynb)
- [Official ESMFold2 tutorial](https://github.com/Biohub/esm/blob/ba4d7124864eed323a93bf3cfefcd958f573b75a/cookbook/tutorials/esmfold2.ipynb)
- [ESMC-6B model card](https://huggingface.co/biohub/ESMC-6B)
- [ESMFold2 model card](https://huggingface.co/biohub/ESMFold2)
- [Modal ESMFold2 example](https://modal.com/docs/examples/esmfold2)
- [Modal authentication configuration](https://modal.com/docs/sdk/py/latest/modal.config)
- [Modal Python SDK changelog](https://modal.com/docs/sdk/py/changelog)
- [Modal Function and version-pinned lookup](https://modal.com/docs/sdk/py/latest/modal.Function)
- [Modal FunctionCall lifecycle](https://modal.com/docs/sdk/py/latest/modal.FunctionCall)
- [Modal scale-out guide and limits](https://modal.com/docs/guide/scale)
- [Language Modeling Materializes a World Model of Protein Biology, bioRxiv v1](https://www.biorxiv.org/content/10.64898/2026.06.03.729735v1)

The Atlas reference explicitly labels the API alpha, unauthenticated, mutable, and unsuitable for production assumptions. Preserve raw responses alongside normalized artifacts so schema drift can be diagnosed.

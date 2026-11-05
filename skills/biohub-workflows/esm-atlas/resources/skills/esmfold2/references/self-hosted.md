# ESMFold2 on Modal or user-owned compute

The [official Modal ESMFold2 example](https://modal.com/docs/examples/esmfold2) shows a pinned `Biohub/esm` install, Hugging Face revision, H100 function, persistent model Volume, and mmCIF output.
Treat it as a starting point and update its pins to the plugin's validated [`source-pins.md`](../../../references/source-pins.md), including the explicitly attached ESMC-6B backbone below.

## Route

- Modal: many independent folds, parameter sweeps, durable/long jobs, or burst capacity. Requires Modal auth but not `ESM_API_KEY` for public weights.
- Self-hosted: privacy, offline/data-resident requirements, custom code, owned GPUs, fine-tuning, or sustained utilization. `HF_TOKEN` is optional for public weights.

## Local full-model skeleton

Install `esm==3.4.1.post1` and `transformers==4.57.6` from PyPI and run `verify-install`; see [`source-pins.md`](../../../references/source-pins.md).
Load the weights with esm's own `EsmFold2Model`, because `transformers==4.57.6` has no ESMFold2 model.
The pinned ESMFold2 configs name their `biohub/ESMC-6B` language-model backbone without a revision, so the default load would fetch ESMC-6B from mutable `main`.
Skip that load and attach the backbone at its pinned revision instead:

```python
import torch
from esm.models.esmc import EsmcModel
from esm.models.esmfold2 import EsmFold2Model

repo = "biohub/ESMFold2"
revision = "1ebf0e3481a5184eb6171d40615c79e384b48796"
model = EsmFold2Model.from_pretrained(repo, revision=revision, device="cuda", load_esmc=False)
model.esmc = EsmcModel.from_pretrained(
    "biohub/ESMC-6B",
    revision="45b0fa5d7fb06faefbd5e3b89bdcef35d564e79a",
    device="cuda",
    dtype=torch.bfloat16,
)
model.set_esmc_precision("bf16")
model.eval()
```

Record the ESMC-6B backbone revision in provenance alongside the ESMFold2 revision.
Numerical parity with the earlier Transformers-fork loader has not been re-measured on a GPU, so treat the first local run as an integration check.

The pinned `ESMFold2InputBuilder.fold` default is 200 sampling steps, not the managed API's maximum of 100. Use `validate-fold --model biohub/ESMFold2` (or `biohub/ESMFold2-Fast`) to validate local builder keywords separately from the hosted `FoldingConfig` contract.

Use `biohub/ESMFold2-Fast` revision `b28d8ace5e05e61e5bec1e6820cfd3e221819d12` for fast single-sequence throughput. Verify CUDA/ROCm compatibility, model dtype, deterministic settings, and output checksums. Never silently fall back to CPU, a different revision, or reduced parameters and then compare results as equivalent.

For hundreds of calls, use Modal map/spawn with bounded concurrency and `return_exceptions=True` semantics. Persist call IDs and per-input provenance so partial successes survive client interruption.

Before any Modal call, refresh current pricing and payment readiness, freeze the model revision, GPU type, job count, concurrency, timeout, persistent-volume plan, and cost ceiling, and obtain separate explicit current-turn confirmation. Never treat a prompt, authenticated profile, or `--confirm-cost` flag as authorization by itself.

## Bounded Modal smoke

The internal fold smoke uses one H100 with a 20-minute timeout and a ticket-scoped model Volume capped at 20 GiB. It records evidence in a fresh output directory and removes the temporary Volume after every outcome. Use it as an integration check only; preserve its exact pins, timeout, output checksums, and cleanup record. It remains blocked until the current H100 price/payment state is visible and the exact ceiling receives explicit approval.

# ESMC self-hosting

Public IDs and pinned revisions are in [`source-pins.md`](../../../references/source-pins.md).
Public weights do not require `HF_TOKEN`.
Install `esm==3.4.1.post1` and `transformers==4.57.6` from PyPI and run `verify-install`, as the setup skill describes.
Load the weights with esm's own classes: the pinned checkpoints declare `model_type: esmc`, which `transformers==4.57.6` does not recognize, so `AutoModelForMaskedLM` and `AutoTokenizer` cannot load them.

```python
import torch
from esm.models.esmc import EsmcForMaskedLM, EsmcTokenizer

repo = "biohub/ESMC-300M"
revision = "a59b831785f907e96e6a246b1d142bfb76df31ee"
tokenizer = EsmcTokenizer()
model = EsmcForMaskedLM.from_pretrained(repo, revision=revision).eval()
inputs = tokenizer([sequence], return_tensors="pt", padding=True).to(model.device)
with torch.inference_mode():
    output = model(**inputs, output_hidden_states=True)
```

`EsmcForMaskedLM.from_pretrained` places the model on CUDA when one is present, so move the tokenized inputs to `model.device`.
Loading may warn that a pinned config uses older field names; the pinned revisions still load with the expected tensor names and shapes.
Numerical parity with the earlier Transformers-fork loader has not been re-measured, so compare against a known reference before relying on exact values.

Use 300M for a quick smoke, then choose 600M or 6B according to the scientific goal and available memory/latency envelope. For private/offline work, stage the exact model snapshot and dependencies inside the controlled environment, verify checksums, disable network access as required, and record the snapshot revision. Do not send telemetry or input sequences outside the intended environment and security boundary.

For public independent ESMC calls, use the managed API with a bounded concurrent pool so the backend can auto-batch them. The plugin ships no ESMC Modal function. Use this self-hosted route when privacy, offline execution, customization, fine-tuning, sustained ownership, or an explicit requirement to use owned compute justifies operating the pinned public weights locally.

# ESMC analysis guidance

The [current world-model paper](https://www.biorxiv.org/content/10.64898/2026.06.03.729735v1) and [Biohub ESMC tutorials/model page](https://biohub.ai/models/esmc) describe representation, zero-shot mutation, layer-sweep, and SAE workflows.

## Embeddings and hidden states

- Record whether the tensor is per-residue, mean-pooled, final-layer, or a selected hidden layer. These are not interchangeable.
- Exclude BOS/EOS and padding consistently before pooling.
- Compare proteins only when preprocessing, layer, model, and revision match.
- An embedding can drive a fitted downstream model, clustering, or retrieval; it is not itself a function label or phenotype.

## Entropy and mutations

For position `i`, mask the wild-type residue, obtain sequence logits, and retain the exact tokenizer vocabulary mapping. Define the allowed residue-token set before calculating entropy. The default set is exactly the 20 canonical one-letter residue tokens `A,C,D,E,F,G,H,I,K,L,M,N,P,Q,R,S,T,V,W,Y`. Include `B`, `Z`, `U`, `O`, or `X` only when the analysis explicitly requires them, the pinned tokenizer maps each symbol to one residue token, and the alternate set is recorded in provenance. Never include BOS, EOS, padding, mask, chain-break, or other special/control tokens in the residue-token set. Then:

- residue entropy: select only the allowed residue-token logits, set `m = max_{r in allowed} z_r`, and renormalize over that set as `Q(a) = exp(z_a - m) / sum_{r in allowed} exp(z_r - m)`, then compute `-sum_{a in allowed} Q(a) log Q(a)`. A dominant special/control-token logit must not change this residue entropy.
- mutation log-likelihood ratio: `ln P(mut) - ln P(wt)` in the same masked context

Separately apply natural-log `log_softmax` over the complete returned sequence-logit vocabulary when retaining the wild-type and alternate full-vocabulary log probabilities. Compute the same-context mutation LLR directly as `alternate_logit - wild_type_logit`; do not derive residue entropy from those full-vocabulary probabilities. With the pinned tokenizer's single BOS token, one-based residue position `i` maps to zero-based logits index `i`; preserve that alongside the zero-based sequence index `i - 1`. Retain the wild-type and alternate raw logits and full-vocabulary log probabilities.

The official PETase notebook additionally reports `-sum_a P(a) log2 P(a)` over the complete returned sequence-logit vocabulary. When reproducing it, label that value `tutorial_full_vocabulary_entropy_bits`, record the complete token set and base 2, and keep it separate from the default canonical-residue entropy above. A dominant control-token logit may change the tutorial metric but must not change canonical-residue entropy.

For a per-position fraction of negatively scored substitutions, evaluate the 19 genuine canonical alternates and exclude the wild type: its LLR is identically zero and it is not a substitution. State the denominator explicitly. The official notebook divides by all 20 canonical residues; the plugin deliberately corrects that presentation rather than silently copying it. A full landscape retains the `20 × L` canonical-AA score matrix, marks wild-type cells as the zero reference, and binds every row to its token ID.

Low entropy or a negative mutation score can suggest constraint, but neither is experimental fitness. Avoid comparing raw scores across models/revisions without calibration.

## SAE features

SAE activations are learned, sparse directions with generated biological descriptions. Report the base ESMC model, exact SAE model/layer/codebook, normalization, activation magnitude, aggregation rule, threshold, and residue regions. The official interpretation workflow uses `esmc-6b-2024-12` with `esmc-6b-2024-12-sae-layer60-k64-codebook16384`, normalized features, and a top-64 sparse code per token.

Use the canonical SDK/wire form `SAEConfig(models=[...], normalize_features=True)`. Decode `output.sae_outputs[exact_model]`, densify only when the output size is acceptable, and remove the BOS/EOS rows with `[1:-1]` before mapping activations to residues. The pinned ATP-synthase tutorial uses managed `/api/v1/encode` tokenization followed by one managed `/api/v1/logits` request, not local tokenization. Its active-value threshold is strictly `activation > 0.01`; retain the top 10 features by maximum activation and top 10 by prevalence, fetch compatible Atlas descriptions for the top five maximum-activation features, and map the top three maximum-activation features by highlighting the 10 highest-activation residues of each in the Biohub MCP view of the exact analyzed sequence. Take the features in rank order, count only residues with `activation > 0.01`, skip a residue that a higher-ranked feature already highlights, and break a tie by the lower position. Fetch the 2XND chain A FASTA sequence once, fetch five Atlas feature records, call `ui_show_protein_structure` once, and retain separate encode/logits raw responses, decoded SAE features, rankings, Atlas responses, per-residue activations, the structure-view record, and provenance.

Atlas descriptions are dictionary-specific. The official tutorial supports looking up feature indices from the exact 6B layer-60, k64, 16,384-codebook checkpoint above in the Atlas feature catalog. The same integer from a 600M SAE, a 65,536-codebook SAE, a different layer, or another checkpoint is not the same learned feature. Normalization changes activation scaling and ranking rather than feature-index identity, so record it separately. If checkpoint compatibility is not proven, present the activation without an Atlas description.

Show activations on a structure with the Biohub MCP view of the exact sequence that ESMC analyzed. That view numbers chain `A` from 1 to N in that sequence, so it needs no alignment. Before you relate residues to other coordinates, such as an experimental PDB entry, explicitly align the sequence used for ESMC to the coordinate residues with chain IDs, author residue numbers, insertion codes, missing residues, and variants. Never assume sequence index `i` is PDB `resi=i+1`. Never draw a structure image or an activation map yourself. Treat feature labels as interpretive hypotheses and corroborate with sequence, structure, Pfam/taxonomy, or experiments.

## Downstream heads and fine-tuning

An `AutoModelForSequenceClassification` head can be randomly initialized when no fitted checkpoint exists. Never call its logits a biological prediction. Fit on documented labels; split by homology/family where leakage matters; calibrate and evaluate on held-out data; report class balance, uncertainty, and domain shift. Fine-tuning belongs on self-hosted/private or controlled compute, not the managed inference endpoint.

# ESMFold2 inputs and results

## Serialized input entities

```json
{
  "sequences": [
    {"type": "protein", "id": "A", "sequence": "MKT...", "msa": null},
    {
      "type": "dna",
      "id": "B",
      "sequence": "GATAGCGCTATC",
      "modifications": [{"position": 5, "ccd": "C36"}]
    },
    {"type": "rna", "id": "R", "sequence": "ACGU"},
    {"type": "ligand", "id": "L", "ccd": ["SAH"]}
  ]
}
```

- Managed entity IDs may be omitted or null. Local/Hugging Face SDK inputs require IDs. When present, they are unique strings or homomer ID lists. Pocket, distogram, and covalent-bond references require explicit matching IDs; an anonymous entity cannot be referenced by an invented chain name.
- Modification positions are zero-based and must lie inside the entity.
- Ligands use exactly one of SMILES or a non-empty CCD list.
- In the current managed contract, only protein entities can carry a non-null MSA. The pinned SDK may emit `msa:null` for RNA; the plugin accepts that SDK compatibility form and removes the undocumented null field from the managed wire request. The managed MSA contains `sequences`, optional `deletions`, and pinned-SDK `headers`; the ungapped first row must match the chain. Preserve non-empty headers only on all-atom per-chain MSAs because Biohub's official paired-MSA workflow uses `key=<taxonomy_id>` tokens to pair rows across chains; omit headers from top-level single-chain managed requests. Local SDK RNA MSA remains route-specific. Fast ignores MSA, so reject that combination and route every MSA workflow to full ESMFold2.
- The full model can run without an MSA. Do not invent one or claim it was used.
- `/fold_all_atom` accepts either this serialized `all_atom_input` object or a protein `sequence` with optional MSA, never both in one request.
- The pinned SDK also serializes optional `pocket`, `distogram_conditioning`, and `covalent_bonds` root fields. Validate explicit chain references, zero-based residue/atom indices, and exact square distogram dimensions before calling the provider. Reject unknown root/entity fields rather than silently passing typos through as valid requests.
- The packaged validator proves sequence-based residue bounds and nonnegative integer atom-index shape only. It does not prove atom existence, valence, bond chemistry, or that tutorial indices match a separately parsed molecule. Before execution, independently resolve atom indices against parsed residue templates or the parsed ligand molecular graph. SMILES atom indices are not positions in the SMILES text. Keep representative chemistry and engineered tags explicit in provenance instead of silently relabeling the modeled construct as an exact drug complex.

## Artifact selection

- mmCIF: preferred all-atom output, especially for modified residues, ligands, nucleic acids, covalent bonds, or large chain sets.
- PDB: useful for compatibility but can lose identifiers/chemistry. If exported, retain the mmCIF source and conversion provenance.
- Confidence arrays and optional tensors: save as structured numeric files with shape/dtype metadata and checksums.
- Managed CLI artifacts: retain `raw-response.json`, the compact normalized `result.json`, `presentation-request.json`, the PDB or mmCIF referenced by `structure_artifact`, and `provenance.json` together. The raw response is authoritative for returned coordinate/state arrays. The validated `presentation-request.json` is the renderer-neutral Structure Viewer handoff and binds the exact coordinate path, digest, media type, size, requested view, and retained `openIntentId`.

## Confidence interpretation

- pLDDT: local confidence, not experimental B factor, dynamics, or correctness.
- pAE: predicted aligned error between positions; inspect domains/interfaces.
- pTM: global topology confidence.
- iPTM and pair-chain iPTM: interface-level confidence for complexes; not binding affinity or functional validation.
- Distogram/embeddings: optional model outputs, not direct experimental claims.

Managed provenance validates and labels pLDDT, pTM, iPTM, and pair-chain iPTM on the current 0-1 scale, and pAE in angstroms. The pinned SDK's PDB serializer can encode 0-1 pLDDT as 0-100 B-factors; keep the provider-native confidence and label that conversion explicitly.

Structure prediction returns one or more static conformations under model assumptions. It does not establish kinetics, conformational ensembles, thermodynamic stability, binding affinity, catalysis, or clinical utility.

Surface every returned `quality_warnings` item with the result. Do not silently repair coordinates; high pLDDT is a confidence signal, not a chemistry check, and cannot override a connectivity, valence, clash, or geometry warning.

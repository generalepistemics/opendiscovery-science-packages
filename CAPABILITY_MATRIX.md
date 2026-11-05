# Sequence Viewer capability matrix

This matrix describes the formats and operations exposed by the extension. A
listed capability is bounded by the limits below and by the source file's
declared format. It does not claim complete feature parity with a specialist
desktop application.

## Documents and views

| Area | Supported input or behavior | Boundary |
| --- | --- | --- |
| Sequence | FASTA, FASTQ, GenBank, EMBL, and common plain sequence suffixes | Large files use bounded reads and indexed/paged state; source bytes are not sent to the model as ordinary text. |
| Alignment | Aligned FASTA, AFA, CLUSTAL, Stockholm, A2M, A3M, MSF, PHYLIP, NEXUS, and PIR | Ambiguous rectangular FASTA opens in the combined viewer with a Sequence / Alignment choice. |
| Chromatograms | Processed ABIF 1.01 and SCF 2.00/3.00 | Inputs are capped at 8 MiB; trace signals remain in source orientation and are not silently discarded to fit a session. |
| Construct files | Verified-revision SnapGene DNA (`.dna`) | This is a bounded DNA import, not a full native SnapGene document implementation. |
| Evidence tracks | GFF3/GTF/BED, VCF, SAM, and indexed regional BAM/CRAM | BAM/CRAM require their index; CRAM usually needs its matching reference. Indexed windows are capped at 100,000 bases and base-level pileup detail at 200 bases. |

## Analysis and editing

| Capability | Behavior and limits |
| --- | --- |
| Sequence summaries | Record inventory, streaming FASTQ summaries, and bounded quality reports. Detailed FASTQ quality analysis samples at most 1,000 eligible reads and 100,000 bases. Reports are descriptive and are not a full FastQC run or automatic pass/fail assessment. |
| Translation and ORFs | Translation follows an unambiguous source `transl_table`; when multiple or conflicting codes are present, a code must be selected explicitly. |
| Restriction and primer tools | Restriction-site/digest analysis and exploratory primer candidates. Primer results are not genome-wide specificity or experimental validation. |
| Alignment analysis | Pairwise and center-star alignment, distance matrices, and exploratory NJ/UPGMA trees. These are not publication-grade phylogenetic inference. |
| In-memory edits | Sequence insert/delete/replace/reverse-complement/rotation and alignment gap/column/row/group/sort edits. Changes apply to a copy, support undo/redo, and require explicit export. |
| Annotations | Add, update, delete, or import features while preserving qualifiers and coordinate provenance. Duplicate IDs must be resolved explicitly. |
| Sessions and outputs | Save/restore bounded viewer sessions and export sequence/alignment data, annotations, tables, SVG figures, Newick, or JSON. Workspace publication requires a separately authenticated, source-bound capability and explicit confirmation. |

## Data and safety limits

- Sequence and alignment files are opened through server-owned handles, bounded
  reads, and revision checks. File contents are not inlined into model context.
- Binary imports are capped at 8 MiB. Saved sessions are capped at 512 KiB.
- Unsupported binary revisions fail closed. Preserve original files when an
  import does not represent every source datum.
- Imported evidence is tied to its loaded reference. Editing that reference
  invalidates evidence placement; display-only reverse-complement projection
  does not change source-coordinate semantics.
- External search, structure prediction, RNA folding, CRISPR/cloning, and
  publication-grade phylogeny require separately approved tools and traceable
  artifacts; the viewer does not silently run these services.

For supported public-data workflows and pinned reference outputs, see
[Starter examples](STARTER_EXAMPLES.md). Those examples are reproducible
reference cases, not a substitute for interpreting live viewer state.

<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="assets/opendiscovery-dark.svg"><img src="assets/opendiscovery-light.svg" width="96" alt="OpenDiscovery"></picture></p>
<h1 align="center">OpenDiscovery Science</h1>
<p align="center">Scientific skills, service tools and interactive viewers.</p>

## Skills

Open **Settings → Skills catalog** and choose an OpenDiscovery collection. Install individual skills or select several together at user or project scope.

| Collection | Includes |
| --- | --- |
| Life Sciences Databases | 44 skills for genetics, proteins, pathways, chemistry and clinical evidence |
| Scientific Research | Nine workflows for evidence review, study design and scientific writing |
| Adaptyv Workflows | Four companion workflows for the Adaptyv service |
| Boltz Workflows | Eight companion workflows for molecular prediction, ADME and design |
| Inductive Workflows | Three workflows for molecular-property prediction and analog comparison |
| Rowan Workflows | Computational chemistry and biology with workflow references |
| NVIDIA BioNeMo | 31 skills for NIMs, protein design, genomics and molecular learning |
| Biohub ESM | Five protein research and model workflow skills |
| Runpod Workflows | Six compute, deployment and infrastructure skills |
| Monarch Workflows | Nine account, compute and model workflow skills |
| Cerebrium | Deployment guidance and runtime references |
| Modal Setup | Configure the selected engine host and provider account |
| Baseten Setup | Configure the CLI and official workflow guidance |
| Pendar Workflows | Three research survey and citation skills |

For applications that do not yet list these sources, add this GitHub repository with branch `skills` in Skills catalog. Choose `skills/life-sciences-databases`, `skills/scientific-research`, `skills/adaptyv-workflows` `skills/boltz-workflows`, `skills/inductive-workflows` or `skills/rowan-workflows` as the subpath:

`generalepistemics/opendiscovery-science-packages#skills`

Each skill includes its maintained supporting resources. Referenced external runtimes, model repositories and provider documentation remain explicit prerequisites. BioNeMo GPU workflows require their documented hardware, CUDA environments and model inputs; installing guidance does not install model weights. Biohub shared Python helpers require a POSIX engine host; hosted MCP capabilities are separate. Monarch installs its hosted connection with nine companion skills; CLI and other provider API workflows need their documented setup. Database helpers require Python 3.10 or newer. Individual databases and external services may require credentials or impose access limits. Optional numerical scripts and manuscript compilation require their documented runtimes.

### Analysis and model development

The additional collections use the same Skills catalog and user/project installation controls. Each skill includes its own resource tree and upstream notices. Runtime packages and credentials belong to the selected engine host; installing instructions does not provision compute or install GPU libraries.

| Collection | Skills | Includes |
| --- | ---: | --- |
| Molecular Biology & Evolution | 7 | Sequences, phylogenetics, constructs, primers and RNA structure |
| Single-Cell & Spatial Analysis | 8 | Scanpy, Seurat, AnnData, integration, trajectories and spatial analysis |
| Bulk Expression & Functional Analysis | 4 | Differential expression, co-expression, enrichment and motifs |
| Proteomics | 10 | Import, QC, identification, quantification, PTMs and DIA |
| Metabolomics & Lipidomics | 9 | Spectra, preprocessing, annotation, normalization and pathways |
| Microbiome & Metagenomics | 8 | Taxonomy, abundance, resistance, function and strains |
| Cheminformatics & Medicinal Chemistry | 8 | Molecular features, series, filters, docking and pockets |
| Molecular Dynamics | 4 | Preparation, simulation setup and trajectory analysis |
| Cell Analysis & Scientific Imaging | 8 | Segmentation, tracking, cytometry, registration and slide processing |
| Immunoinformatics | 6 | Epitope, MHC, TCR, neoantigen and assay workflows |
| Study Statistics | 12 | Design, inference, sensitivity, multiplicity and reporting |
| Atomistic & Computational Chemistry | 5 | ASE and CP2K task guides, xTB, materials and phonons |
| Scientific Workflows & Reports | 5 | Snakemake, Nextflow, QC and reproducible reports |
| Scientific Figures | 3 | Scientific plots and protein/DNA diagrams |
| Model Training | 14 | Data preparation, adapters, distributed training and interpretation |
| Reinforcement Learning | 5 | GRPO, OpenRLHF, verl, Stable-Baselines3 and PufferLib |
| Model Evaluation & Serving | 10 | Benchmarks, serving, quantization and experiment tracking |
| Software Engineering | 9 | Debugging, reviews, tests, packaging, dependencies and SQL |

## Service connections

Find services in **Discover**, using the Science or Cloud category as appropriate. Manage their connections in **Settings → Extensions → MCP servers**. Provider accounts and credits are separate from OpenDiscovery. Services with companion skills install them together with their MCP connection. Skills-only setup and research collections remain in Skills catalog. Individual companion skills are also available in Skills catalog. Installation does not create a provider account or submit a job.

## Interactive viewers

Choose a viewer in **Discover → Science**, or use **Settings → Extensions → Apps → Add app** with its installation link. Each package includes its interactive App, local MCP tools and companion skill in one installation. Viewers are optional downloads.

| Viewer | Installation link | Use |
| --- | --- | --- |
| Sequence Viewer | `https://github.com/generalepistemics/opendiscovery-science-packages#sequence-viewer` | Inspect and annotate biological sequences |
| Structure Viewer | `https://github.com/generalepistemics/opendiscovery-science-packages#structure-viewer` | Explore molecular structures in 3D |
| Slide Viewer | `https://github.com/generalepistemics/opendiscovery-science-packages#slide-viewer` | Explore supported microscopy, whole-slide DICOM and spatial AnnData sources |

Review the requested capabilities before enabling a viewer. Open a supported workspace file from **Files**, or ask the agent to open it. Manage updates, disabling and removal through **Apps**. Project outputs remain separate from the installed package.

Slide Viewer requires an application with extension host compatibility **2.5.2 or newer**; older applications reject installation with the required host version. File format variants, codecs and optional scientific workflows have their own requirements. Installing a viewer does not install Python environments, download model weights or authorize remote data access. These tools are intended for research, not clinical diagnosis.

## Updates and removal

Refresh a Skills catalog source to read published content. To apply a correction, preserve local edits, remove the installed copy through Skills management and install it from the refreshed source. Existing destination conflicts use the normal confirmation controls. Remove skills through Skills management. Ordinary skills do not use the Apps updater.

Interactive viewers use their own Apps installation and update lifecycle. Installing a skills collection does not install a viewer.

## Notices

Required licenses and source acknowledgements accompany the distributed content. Service names identify their respective providers. The older native skills-only package branches are retained for existing installations; new skills installations use the `skills` branch. Remove an older skills-only App before installing the same skills through Skills catalog to avoid duplicates.

## Workspace Apps

Excalidraw and Resource Monitor are optional OpenDiscovery-compatible Git packages, maintained alongside this content. They retain their original licenses and use OpenDiscovery’s SDK and service runtime.

| App | Installation link | Use |
| --- | --- | --- |
| Excalidraw | `https://github.com/generalepistemics/opendiscovery-science-packages#excalidraw` | Edit Excalidraw and supported Obsidian drawings in Files |
| Resource Monitor | `https://github.com/generalepistemics/opendiscovery-science-packages#resource-monitor` | Inspect actual host, engine and child-process resource use |

Review requested capabilities before enabling an App. Resource Monitor runs a local service with the current user’s process access; stopping a process is a separate deliberate action.

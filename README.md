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

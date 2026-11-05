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
| Boltz Workflows | Seven companion workflows for molecular prediction and design |

For applications that do not yet list these sources, add this GitHub repository with branch `skills` in Skills catalog. Choose `skills/life-sciences-databases`, `skills/scientific-research`, `skills/adaptyv-workflows` or `skills/boltz-workflows` as the subpath:

`generalepistemics/opendiscovery-science-packages#skills`

Each skill includes its required supporting resources. Database helpers require Python 3.10 or newer. Individual databases and external services may require credentials or impose access limits. Optional numerical scripts and manuscript compilation require their documented runtimes.

## Service connections

Find science services in **Discover → Science**. Manage their connections in **Settings → Extensions → MCP servers**. Provider accounts and credits are separate from OpenDiscovery. Adaptyv and Boltz each install their connection and companion workflow skills together. Individual companion skills are also available in Skills catalog. Installation does not create a provider account or submit a job.

## Updates and removal

Refresh a Skills catalog source to read published content. To apply a correction, preserve local edits, remove the installed copy through Skills management and install it from the refreshed source. Existing destination conflicts use the normal confirmation controls. Remove skills through Skills management. Ordinary skills do not use the Apps updater.

Interactive viewers use their own Apps installation and update lifecycle. Installing a skills collection does not install a viewer.

## Notices

Required licenses and source acknowledgements accompany the distributed content. Service names identify their respective providers. The older native skills-only package branches are retained for existing installations; new skills installations use the `skills` branch. Remove an older skills-only App before installing the same skills through Skills catalog to avoid duplicates.

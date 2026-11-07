---
name: ase
description: Unified ASE router skill with a tree of subskills for static/relax/MD/NEB workflows and backend adapters (GPAW, MACE). Use when you need backend-agnostic workflow orchestration while keeping calculator-specific setup isolated in adapter subskills, with reproducible task preparation as output.
compatibility: Requires Python and ASE. Optional backend dependencies are GPAW and/or MACE depending on selected adapter. Prepares tasks/configuration only; run using the chosen calculator on the explicitly authorized engine host when execution is requested.
license: MIT
metadata:
  author: qqgu
  version: 0.1.0
  repository: https://gitlab.com/ase/ase
  distribution-publisher: OpenDiscovery
  distribution-source: https://github.com/vangorade/Enso_latest
  distribution-revision: 2e1984cfeea229b971788cb298da56acc47aced8
  distribution-path: atomistic-workflows/ase
---

## OpenDiscovery runtime

This skill supplies instructions and supporting resources; it does not install a scientific runtime or create a service connection. Run commands in the selected project on the engine host. Check its operating system, dependencies, input paths and available compute before starting. Use a project environment for required packages. Obtain provider credentials through that host’s environment or official CLI; never print tokens. Request approval before paid compute, model uploads or public publication. Report missing prerequisites and failed analysis directly; do not substitute demonstration data or fabricated outputs.

# ASE Top-Level Router

Use this skill as the unified entry point for ASE ecosystem tasks.

## Purpose

This skill routes requests to one branch under the ASE tree:

- `ase/ase-workflows`
- `ase/ase-calculators`

## Scope

This top-level router should:

- decide whether the request is workflow-level or backend-adapter-level
- gather the minimum context required for the selected branch
- delegate details to the corresponding branch router
- keep workflow logic and backend logic separated

This top-level router should not:

- hardcode task-specific or backend-specific parameters directly
- execute calculations directly

## Routing rules

1. task intent is static/relax/md/neb workflow -> `ase/ase-workflows`
1. task intent is backend selection/configuration -> `ase/ase-calculators`
1. if mixed request, route to `ase/ase-workflows` first, then call `ase/ase-calculators` as dependency

## Output from top-level router

Provide:

1. selected ASE branch path
1. reason for branch selection
1. missing minimum inputs
1. explicit next delegation step

## Included task guides

- [ase-calculators](ase-calculators/GUIDE.md)
- [ase-calculators/gpaw](ase-calculators/gpaw/GUIDE.md)
- [ase-calculators/mace](ase-calculators/mace/GUIDE.md)
- [ase-workflows](ase-workflows/GUIDE.md)
- [ase-workflows/md](ase-workflows/md/GUIDE.md)
- [ase-workflows/neb](ase-workflows/neb/GUIDE.md)
- [ase-workflows/relax](ase-workflows/relax/GUIDE.md)
- [ase-workflows/static](ase-workflows/static/GUIDE.md)

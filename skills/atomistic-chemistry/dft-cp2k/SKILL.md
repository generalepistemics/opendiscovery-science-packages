---
name: dft-cp2k
description: Route CP2K requests to task-specific subskills based on user intent. Use when the user asks for CP2K workflows and you must decide between static, relaxation, molecular dynamics, or electronic-analysis preparation. This orchestration skill dispatches to the correct CP2K subskill and enforces consistent handoff to submission skills.
compatibility: Requires a runnable CP2K environment and suitable basis/pseudopotential data for target elements.
license: MIT
metadata:
  author: qqgu
  version: 0.1.0
  repository: https://github.com/cp2k/cp2k
  distribution-publisher: OpenDiscovery
  distribution-source: https://github.com/vangorade/Enso_latest
  distribution-revision: 2e1984cfeea229b971788cb298da56acc47aced8
  distribution-path: quantum-chemistry/dft-cp2k
---

## OpenDiscovery runtime

This skill supplies instructions and supporting resources; it does not install a scientific runtime or create a service connection. Run commands in the selected project on the engine host. Check its operating system, dependencies, input paths and available compute before starting. Use a project environment for required packages. Obtain provider credentials through that host’s environment or official CLI; never print tokens. Request approval before paid compute, model uploads or public publication. Report missing prerequisites and failed analysis directly; do not substitute demonstration data or fabricated outputs.

# CP2K Task Router

Use this skill as the **top-level CP2K orchestration layer**.

## Purpose

This skill routes requests to one task-specific CP2K subskill path:

- `dft-cp2k/static`
- `dft-cp2k/relax`
- `dft-cp2k/md`
- `dft-cp2k/electronic`

## Scope

This router skill should:

- require user-provided structure or prerequisite context
- classify request intent into one CP2K task type
- collect minimal shared context before dispatch
- delegate detailed parameter handling to selected subskill
- enforce consistent output/handoff policy across subskills

This router skill should **not**:

- own detailed templates for all CP2K tasks
- execute or submit calculations
- bypass subskill-specific guardrails

## Hard requirement

The user must provide enough starting context:

- structure input for `static` / `relax` / `md`
- prerequisite converged context for `electronic`

If prerequisites are missing, stop and ask for them.

## Routing rules

1. If user requests single-point SCF/energy: route to `dft-cp2k/static`.
1. If user requests geometry optimization: route to `dft-cp2k/relax`.
1. If user requests molecular dynamics: route to `dft-cp2k/md`.
1. If user requests electronic analysis workflow: route to `dft-cp2k/electronic`.
1. If intent is ambiguous, ask one focused clarification question before routing.

## Shared policy for all subskills

- do not invent missing basis/potential files
- expose assumptions and unresolved scientific choices explicitly
- return handoff-ready task layout
- if execution is requested, use the chosen calculator on the explicitly authorized engine host

## Output from router

Provide:

1. selected subskill path
1. why it was selected
1. minimal missing inputs (if any)
1. explicit next step (invoke selected subskill)

## Included task guides

- [electronic](electronic/GUIDE.md)
- [md](md/GUIDE.md)
- [relax](relax/GUIDE.md)
- [static](static/GUIDE.md)

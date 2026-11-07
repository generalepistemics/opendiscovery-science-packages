# Commands and Workflow

Use this reference for `ase/ase-workflows` routing.

## Router role

`ase/ase-workflows` dispatches to one task subskill path:

- `ase/ase-workflows/static`
- `ase/ase-workflows/relax`
- `ase/ase-workflows/md`
- `ase/ase-workflows/neb`

## Dispatch checklist

1. identify task intent
1. collect workflow-level controls (convergence, trajectory policy, reporting)
1. request backend adapter via `ase/ase-calculators`
1. invoke workflow subskill with selected adapter
1. run on the explicitly authorized engine host when requested, after checking calculator and compute prerequisites

## Intent mapping

- static -> `ase/ase-workflows/static`
- relax -> `ase/ase-workflows/relax`
- md -> `ase/ase-workflows/md`
- neb -> `ase/ase-workflows/neb`

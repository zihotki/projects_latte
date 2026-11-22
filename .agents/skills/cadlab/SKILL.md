---
name: cadlab
description: Use when starting a design project or creating, editing, checking, or exporting CadQuery shapes, parts, or assemblies in this repository's CAD Lab workspace.
---

# CAD Lab

Identify the exact project folder, including any nested project. For a new
design, create a folder under `cadlab/projects/` with a `model.py`. Run
`cadlab/bin/cadlab run --project <folder>` to open the project in SOMA.

## SOMA skills

Read the enabled skills and any others relevant to the task from the shared
SOMA library. Use the commands in the project's skill list, for example:

```sh
./cadlab/bin/cadlab skill 3d-printing --project cadlab/projects/example
```

This uses the project's settings when available and the template defaults
before initialization. `cadlab paths` gives the shared template directory.

- **Modeling** uses `design-workflow.md` and `cadquery.md`. For adjustable
  dimensions, see `parametric.md`.
- **Filament printing** uses `3d-printing.md`, `tolerances.md`, and `analysis.md`.
  See also the [CAD Lab FDM guide](../../../cadlab/FDM-DESIGN.md).
- **Assembly and fit** use `assemblies.md`, `joints.md`, and `tolerances.md`.

The CAD Lab workflow below takes precedence for design acceptance, reporting,
and verification.

## Model and verify

1. Identify the requested changes and the dimensions, interfaces, and functions
   to preserve. For a correction, reproduce the issue in the relevant view or
   section when possible. Ask only when missing information prevents a sound
   design decision.
2. Complete and check the base geometry, dimensions, fit, and function. Add
   chamfers and other finishing features last. After a base geometry change,
   check the intended finish on the rebuilt solid, including affected transitions
   and new edges.
3. Verify the requested change and the features it affects through dependencies.
   Preserve geometry and function outside the requested change. Inspect finished
   parts in assembly and in print orientation where applicable. For printed
   parts, check the rims and corners that run through the layers. Run scoped
   project checks when available.

Complete verification on the digital model yourself. Keep any draft reviews,
progress notes, and check results internal. Leave the model open in SOMA for
the user's visual review.

## Build and export

Use the wrapper from the repository root. See the
[CAD Lab guide](../../../cadlab/README.md) for setup and dependencies.

```sh
project=cadlab/projects/example
./cadlab/bin/cadlab soma build --project "$project" --json
```

For a requested export, use `./cadlab/bin/cadlab soma export --help` to select the
parts and format. The wrapper defaults mesh exports to fine detail. For native
mesh exports, pass `--detail fine`. If you need an image, use `./cadlab/bin/cadlab soma render --project <folder>`
with that project open in the viewer, then inspect the result.

For harness changes, use the
[CAD Lab validation commands](../../../cadlab/README.md#build-export-and-validate).

## Review comments

When the user reports comments, read all pending comments for the project:

```sh
./cadlab/bin/cadlab soma review list --project <folder>
```

Compare references from older builds with the current model. After you fix and
verify a comment, mark its ID as addressed:

```sh
./cadlab/bin/cadlab soma review address --project <folder> <comment IDs ...>
```

Leave comments that are not yet verified pending.

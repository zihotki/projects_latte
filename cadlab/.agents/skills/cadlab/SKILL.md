---
name: cadlab
description: Use when starting a design project or creating, editing, checking, or exporting CadQuery shapes, parts, or assemblies in this repository's CAD Lab workspace.
---

# CAD Lab

Read the [workspace instructions](../../../AGENTS.md) and identify the exact
design folder. A design can have its own project inside another design folder.
Use the [CAD Lab guide](../../../README.md) to set up the harness. For a new
design, create a project folder under `cadlab/projects/` and use SOMA's
**Open folder** to generate its project files.

## Use the project's SOMA skills

Read the target project's `AGENTS.md`. Open each skill it lists under
**Always follow** and the skills under **Read when relevant** that apply to the
task. Read them from that project's `.soma/skills/` to use its current settings.

Use the applicable skills to turn requirements and reference dimensions into
geometry. See SOMA's [Design workflow](../../../vendor/soma/app/resources/skills/design-workflow.md)
and [Clean CadQuery modeling](../../../vendor/soma/app/resources/skills/cadquery.md)
templates for examples of native skills. Check the dimensions, interfaces, and
other properties that matter to the requested design. Run the project's own
checks when available. Follow the repository's Git instructions and the user's
authorization for commits.

## Build and export

From the repository root, set `project` to the design path and use the wrapper. This example builds the starter design.

```sh
project=cadlab/projects/example
./cadlab/bin/cadlab soma build --project "$project" --json
```

The native CLI loads installed packages from the target project's environment.
To install a dependency or run Python directly, use the CAD Lab guide. Read
the project's `.soma/skills/shell-environment.md` when its `AGENTS.md` lists it.

For a requested export, use `./cadlab/bin/cadlab soma export --help` to select the
parts and format. The wrapper defaults mesh exports to fine detail. For native
mesh exports, pass `--detail fine`. If you need an image from `soma render`, open
the same design in the running SOMA app.

Use the guide's [CAD Lab validation commands](../../../README.md#validate-cad-lab-only)
for changes to the harness. Report the checks you ran and the paths to requested
deliverables.

---
name: cadlab
description: Use when starting a design project or creating, editing, checking, or exporting CadQuery shapes, parts, or assemblies in this repository's CAD Lab workspace.
---

# CAD Lab

Read the [workspace instructions](../../../cadlab/AGENTS.md) and identify the exact
design folder. A design can have its own project inside another design folder.
Use the [CAD Lab guide](../../../cadlab/README.md) to set up the harness. For a new
design, create a project folder under `cadlab/projects/` and create its `model.py`.
Run `cadlab/bin/cadlab run --project <folder>` to initialize it and open that
exact folder in SOMA. Keep the viewer available for the user to review edits.

## Use the project's SOMA skills

Read the target project's `AGENTS.md` and its SOMA app skill,
`.soma/skills/soma-app.md` when present. The [fork template](https://github.com/zihotki/SOMA/blob/feat/open-folder/app/resources/skills/soma-app.md)
is a reference; prefer the installed or project copy. Open each skill it lists under
**Always follow** and the skills under **Read when relevant** that apply to the
task. Read them from that project's `.soma/skills/` to use its current settings.

Use the applicable skills to turn requirements and reference dimensions into
geometry. If the project has no SOMA skills yet, run `cadlab/bin/cadlab paths` to find
the shared `skills` directory. Read its `design-workflow.md` and `cadquery.md`
templates; use each template's declared defaults for placeholders. Project
copies take precedence after initialization. Check the dimensions, interfaces, and
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
mesh exports, pass `--detail fine`. If you need an image from `soma render`, use the SOMA terminal in the viewer
for that exact design; each project has its own app profile and connection.

Use the guide's [CAD Lab validation commands](../../../cadlab/README.md#build-export-and-validate)
for changes to the harness. Report the checks you ran and the paths to requested
deliverables.

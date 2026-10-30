# Buratino

Buratino is a local furniture design workspace based on Cabineteer. Each
project is a folder under `projects/` with one `project.py` file. Builds are
explicit. Outputs are drafts, not manufacturing packages.

## Start

Run commands from the repository root. Setup installs the locked CAD runtime
in `buratino/.venv/` and viewing assets in `buratino/vendor/three/`. It keeps
downloads, test files, and runtime identity in `buratino/.cache/`.

```bash
./buratino/bin/buratino setup
./buratino/bin/buratino doctor
./buratino/bin/buratino build projects/spaces-fixed-drawers
./buratino/bin/buratino preview projects/spaces-fixed-drawers
```

Run `./buratino/bin/buratino preview` to open one catalog for the two current
designs and the example projects. It refreshes a missing or stale build for
each design before it starts. The catalog shows examples and tests with their
build state. You can also preview one project by short name, for example
`./buratino/bin/buratino preview two-under-window`. `build` and `export-cutlist`
also accept a short project name.

The [authoring guide](docs/designing.md) explains which model to choose and how
to build a new project. Start from a runnable example:

- [Rectangular cabinet with drawer boxes and applied fronts](projects/spaces-fixed-drawers/project.py)
- [Rectangular cabinet with drawers and an open space](projects/spaces-fixed-open/project.py)
- [Parent door over internal spaces](projects/spaces-covered-drawers/project.py)
- [Cabinet row with doors and a drawer front](projects/space-assembly-fronts/project.py)
- [Nested bare insert and complete cabinet](projects/space-nested-inserts/project.py)
- [Profiled assembly with a sloped roof](projects/profile-row-sloped/project.py)
- [Larger native profile assembly draft](projects/real-assembly-native/project.py)

The [coordinate contract](docs/coordinates.md) describes model axes, local
stock frames, placement, and the CAD-to-viewer boundary.

`preview` prints a loopback URL. Each project page shows one captured build.
After a new build, refresh the page. The preview server can stay running.
Select a part or cut-list row to highlight it. Visibility and drawer pose
controls change display only; they do not change geometry or cutting
quantities. Stop the server with Ctrl-C.

Export a validated build with `./buratino/bin/buratino export-cutlist` for
ZAGENZAGEN or OPMAATZAGEN. See the [cut-service guide](docs/cut-services.md)
for CSV fields, grouping, configuration, and open provider questions.

## Build outputs and limits

Each build writes a new folder under that project's `build/` directory. It
contains `result.json`, `parts.csv`, a 3D preview, review report, assembly guide,
and captured source and provenance. Previous builds stay in place. Failed
exports do not replace the latest completed build. Use `--json` for the full
result and checks.

Space plans are resolved without CAD. Space builds then create CAD shapes and
check shape validity, part overlaps, and declared contacts. These checks do not
confirm fit, fastening, hardware installation, stock, or manufacturing
readiness. Review the report and resolve open assumptions before construction.

`doctor` checks Cabineteer provenance, the editable source location, the local
runtime, and viewing assets. Cabineteer source is tracked in
`vendor/cabineteer`; builds capture the engine source used for each result.

## Checks

```bash
./buratino/bin/buratino check
./buratino/bin/buratino test
./buratino/bin/buratino test-native
```

`check` runs source checks. `test` runs Buratino tests. `test-native` runs the
Cabineteer suite in a separate process. Optional CAD and cut-list packages can
cause upstream tests to skip.

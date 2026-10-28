# Buratino

Buratino is a local furniture design workspace based on Cabineteer. Each
project uses one `project.py` file for measurements, calculations, and its
native Cabineteer assembly. Builds are explicit. All outputs are drafts, not
manufacturing packages.

## Run a project

Run these commands from the repository root. Setup downloads the locked CAD
packages and integrity-checked Three.js assets into `buratino/.local/`.

```bash
./buratino/bin/buratino setup
./buratino/bin/buratino doctor
./buratino/bin/buratino build projects/simple-cabinet
./buratino/bin/buratino preview projects/simple-cabinet
```

The drawer example uses the same commands with `projects/drawer-cabinet`.
The two-cabinet draft uses `projects/real-assembly`.
The native migration uses `projects/real-assembly-native`; the earlier project
remains a working reference. The native design has two lower drawer cabinets,
two frames, and one four-section upper carcass with shared dividers. Its nine
drawers, seven adjustable shelves, roof, fronts, and cut list come from one
resolved assembly. Both projects remain draft designs.
The bare inclined example uses `projects/inclined-cabinet`.
The declarative Space examples use `projects/spaces-fixed-drawers`,
`projects/spaces-fixed-open`, and `projects/spaces-covered-drawers`. Each exports
a native `CabinetProject` with a `SpaceModelSpec`. The assembly examples use
`projects/space-assembly-fronts` and `projects/space-nested-inserts`. They show
weighted cabinet widths, left and right hinge sides, a bare insert, and a
complete cabinet inside a host Space. All examples use 2 mm front gaps and
reveal. Cabineteer resolves each input to one CAD-free plan with allocations,
placements, spaces, fronts, physical stock, and viewer records. Buratino reads
that plan for its report and cut list, then materializes the same parts for the
GLB preview. Build and preview these projects with the same commands above.
Open the loopback URL printed by `preview`. Each page shows one captured build.
After a new build, refresh the page to load it; the server can stay running.
Rotate or zoom the model, or choose a standard view. Drawer controls
change the display pose only. Select a model part or cut-list row to highlight
matching parts. Visibility controls hide cabinets, carcasses, drawers, or
fronts. These display controls do not change geometry or cutting quantities.
Stop the preview with Ctrl-C.

## Edit a project

Edit `projects/<name>/project.py`. Keep reported space in `space_mm`, separate
from selected cabinet dimensions. Keep observations and unverified choices in
`observations` and `assumptions`. The `calculated` map records useful resolved
values. The `project` export is a native `CabinetProject`; optional
`drawer_configs` entries use native `DrawerConfig` values.

Create one folder under `projects/` for each design. Start from an example's
`project.py`, then replace its measurements and assumptions. Keep decisions
in that folder. Build and preview commands accept paths under `projects/`.
Generated builds stay in the corresponding project's `build/` directory.

Cabineteer owns cabinet dimensions, geometry, hardware, and native project
models. Buratino loads the project, builds reports and previews, and records
the source used for each build. The native source is in `vendor/cabineteer`.

### Inclined cabinets

For a bare cabinet, set `roof_angle_deg` on its native `CabinetConfig`. A
positive angle rises from left to right; a negative angle falls. `height` is
the maximum exterior height. The top caps the sides, and its thickness is
measured normal to the slope. Stock dimensions are rectangular blanks that
need trimming to the finished profiles.

The single-cabinet `roof_angle_deg` path supports bare butt carcasses with an
unmachined back. That path does not support openings, drawers, doors, shelves,
columns, edge banding, or machining plans. Separate cabinets in that path need
heights calculated from their positions. Composite `ProfileAssemblySpec`
projects, including `real-assembly-native`, support one shared profiled upper
carcass with drawers, fronts, and adjustable shelves.

The native hardware catalog includes Hettich Quadro V6 EB20 runners in 380,
450, and 480 mm lengths. Mounting details and other open assumptions remain
in the project report and must be checked before construction.

The bare cabinet is 720 × 970 × 500 mm, with 18 mm sides, top and bottom, and a
6 mm back. The drawer example keeps four overlay fronts, 450 mm Quadro V6 EB20
requirements, 16 mm drawer sides, 18 mm inner fronts and backs, and 12 mm
bottoms. Its body is 720 × 970 × 500 mm; closed overall depth is 520 mm.
Measurements, material notes, and open construction questions remain in each
project file.

The `linked-row-fixture` and `shared-column-fixture` projects are synthetic
examples for assembly behavior. Their dimensions are test choices, not user
measurements. They show separate connected cabinets and a native shared
divider. They do not select a final construction for a future cabinet.

## Draft limits

Each build writes a new folder under that project's `build/` directory. It
contains `result.json`, `parts.csv`, the combined 3D preview, review report,
assembly guide, captured source and provenance. Previous builds stay in place.
Failed exports do not replace the latest completed build. The build command
prints the output folder. Add `--json` for the full result and checks.

The package is diagnostic. The 6×40 Domino face and edge plunge depths have
not been selected. Candidate centers are calculated, but jig registration,
depths and settings remain open. The assembly guide is not a machining
instruction. Drawer mounting, fastening, clearances and measured stock also
need confirmation. A successful build does not approve manufacturing.

## Check the project

```bash
./buratino/bin/buratino check
./buratino/bin/buratino test
./buratino/bin/buratino test-native
```

`test` checks the Buratino project and build harness. `test-native` runs the
Cabineteer suite in a separate process. The repository test script runs both.
Some upstream tests skip when optional CAD or cutlist packages are absent.

`doctor` checks Cabineteer provenance, the editable source location, the local
runtime, and viewing assets. Cabineteer source is tracked in `vendor/cabineteer`.
Its lock records the upstream commit and the patch applied before import. Builds
capture the engine source and include its content in their input identity. The
old `.local/cabineteer` checkout is a recovery copy and is not used.

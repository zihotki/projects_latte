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
Open the loopback URL printed by `preview`. The preview shows one captured
build. Rotate or zoom the model, or choose a standard view. Drawer controls
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
Failed exports do not replace the latest completed build.

The package is diagnostic. In particular, the selected 6×40 Domino creates
known panel-thickness errors. Mortise positions, depths, settings, and
quantities remain unverified. The assembly guide gives an order of work, not
drilling instructions. Drawer mounting, fastening, clearances, and measured
stock also need confirmation. A successful build does not approve
manufacturing.

## Check the project

```bash
./buratino/bin/buratino check
./buratino/bin/buratino test
```

Root `./scripts/check.sh` and `./scripts/test.sh` include Buratino. Run
`./scripts/integration.sh` when Docker is available. `doctor` checks the
Cabineteer source pin, local runtime, and viewing assets. Keep the pinned
Cabineteer source clean. Do not edit its ignored checkout.

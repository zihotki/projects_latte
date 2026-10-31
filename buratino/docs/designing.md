# Designing a Buratino project

Start with one runnable `project.py` in `buratino/projects/<name>/`. Copy the
closest current example, then replace its dimensions, materials, hardware, and
assumptions. Keep project code declarative: use Cabineteer inputs to describe
the furniture. Add Python calculations only for values that depend on other
project inputs. Use millimetres for dimensions and gaps.

The [coordinate contract](coordinates.md) defines axes, stock datums, placement,
and export frames. Read it before adding geometry or machining logic.

## Choose a model

| Design | Start from | Model |
| --- | --- | --- |
| Rectangular carcass with clear spaces, drawers, doors, or fronts | [spaces-fixed-drawers](../projects/spaces-fixed-drawers/project.py) | `SpaceModelSpec` |
| Several rectangular cabinets in a row | [space-assembly-fronts](../projects/space-assembly-fronts/project.py) | `space_cabinets` and `Row` |
| An insert or cabinet inside a host space | [space-nested-inserts](../projects/space-nested-inserts/project.py) | `AssemblyModule` and `AssemblyRef` |
| A profiled or sloped assembly | [profile-row-sloped](../projects/profile-row-sloped/project.py) | `ProfileAssemblySpec` |

Use a Space model for rectangular, butt-joined carcasses with an applied back.
It does not define sloped or changing-height clear spaces. Use
`ProfileAssemblySpec` for supported profiled assemblies. See the larger
[attic clothing storage design](../projects/attic-clothing-storage/project.py) for a
complete example.

Space projects can also define explicit local machining and paired Domino
mortises, and component-owned Domino recipes with `Carcass.joinery`,
`DrawerBox.corner_joinery`, and `Divider.joinery`. A structural divider inherits
the carcass recipe by default. Bands select narrow stock faces,
have zero thickness, and leave the solid and cut list unchanged. See
[Space machining and edge banding](operations.md), the runnable [machined
drawer example](../projects/machined-drawer/project.py), and the [two under
window example](../projects/two-under-window/project.py).

## Describe clear spaces

Import `CabinetProject` and `SpaceModelSpec` from `cabineteer.project`, and
`Carcass`, `Space`, `Split`, `Fixed`, and `Fr` from `cabineteer.spaces`. A
`SpaceModelSpec` holds one carcass, one root `Space`, and optional fronts. A
`Space` can be open, contain a `DrawerBox`, contain an `AssemblyRef`, or split
into child spaces. Keep `project.py` focused on these native values and the
project's observations, assumptions, and derived measurements.

Import other input types from `cabineteer.spaces` when used, such as
`DrawerBox`, `Divider`, `Door`, `AppliedDrawerFront`, and `AppliedFaceboard`.

`Carcass.door_gap`, `drawer_front_gap`, and `outer_reveal` each default to
2 mm. The first two set the total gap at a shared door or drawer-front seam;
the two faces each take half. At a mixed door and drawer-front seam, the
larger configured gap applies. `outer_reveal` sets the gap at the outside edge.

For each split child, set a size. `Fixed(mm)` reserves a clear dimension.
`Fr(weight)` divides the remaining whole millimetres by integer weight, after
fixed sizes and divider thicknesses. Cabineteer floors each weighted share to
whole millimetres. For example, 200 mm across three `Fr(1)` spaces gives 66 mm
to each and 2 mm of slack. Each flexible span must receive at least 1 mm. By
default, width slack goes on the right and height slack goes at the top. Set
`Split.allowance_edge` to `left` or `right` on width splits, or `bottom` or
`top` on height splits, to choose the edge that holds the slack.

`Split` makes regions; it does not add stock. Add a `Divider` between spaces
when the design needs a physical panel. Its thickness uses the split axis. A
divider can have the `structural` or `adjustable` role; adjustable dividers are
for height splits. Set `depth` to make a shorter divider, such as a front rail.
Its depth starts at the front after any `recess`; omit it for the full remaining
depth. Give each space, divider, content item, and front a unique name within
its scope.

## Add fronts

Fronts are separate inputs from the spaces and their contents. Put them in the
`fronts` tuple on `SpaceModelSpec`, `SpaceCabinetDefinition`, or
`AssemblyModule`, where they belong. A drawer box does not create a front by
itself.

- Use `Door(name, covers="/root/...", hinge_side="left")` for a left-hinged
  door. The default hinge side is right.
- Use `AppliedDrawerFront` with both `covers` and `attached_to`. `covers` names
  the space region. `attached_to` names the drawer box, such as
  `"/root/lower/box-lower"`. Set `top_reveal` to override its exposed top gap;
  shared seams still use the configured front gap.
- Use `AppliedFaceboard` on a cabinet definition or module for a fixed face. It
  has no motion group.

Use the full path when a name can repeat. Front inputs set geometry and motion
grouping; the example assumptions still need to record unverified hinge,
mounting, reveal, and clearance choices.

`Fixed(mm)` on a height split sets the clear opening height. It does not set
the drawer-box or front height. For `DrawerBox(height="fit")`, Cabineteer
subtracts `bottom_clearance` and `top_clearance` from that opening. If
`top_clearance` is unset, the fit recipe uses its default vertical gap. The
bottom clearance must also meet the selected slide's minimum.

`DrawerBox(depth=544)` sets the box depth independently of runner length.
Omit `depth` to keep the runner-based default. The box and its front gap must
fit the clear opening depth. A side-mounted box must be at least as deep as
its runner; an undermount box must keep the runner-specific depth. A saved
runner travel value sets the preview open distance independently of box depth.

Drawer boxes in Space and profile assemblies use the same stock-panel and cut
recipe. Bottom blanks include the groove depth at both edges in each direction.
The default groove depth is 6 mm; the default 13 mm inset locates the bottom
panel underside. Profile drawer cut records use each part's native stock
length/width/thickness frame. Their face polygons, cut depths and inward axes
are also shown in the `report.html#part-drawings` section. These are draft dimensions, not CNC paths.

Set `runner_relief_depth_mm` on either profile drawer recipe, or
`runner_relief_depth` on `DrawerBox` / `DrawerConfig`, to cut an outer runner
rebate on both sides. It runs the full side length from the lower edge to the
bottom panel underside. The default is zero. Runner limits use the remaining
side thickness; box sizing and stock cutlists still use the full stock thickness.

## Nest modules and arrange cabinets

`AssemblyRef` places a named `AssemblyModule` inside a host space. A module
whose root is a `Space` is a bare insert. A module whose root is a `Row` or
`Stack` can contain `CabinetRef` values and frames, so it can place complete
cabinet definitions. Set `Insets(left=..., right=..., front=..., back=...,
bottom=..., top=...)` to leave a gap inside the host space. Set finite
`size_x`, `size_y`, and `size_z` requests for the module. A `Row` or `Stack`
root can use `Fixed`, `Fr`, or `Natural`. A bare `Space` root cannot infer
`Natural`; use `Fixed` or a `Fr` request from its host budget on each axis.
Insets reduce that budget. The nested example shows both module types.

`AssemblyModule`, `AssemblyRef`, `Insets`, and `SpaceCabinetDefinition` are in
`cabineteer.spaces`. `CabinetRef`, `Row`, and `Stack` are in
`cabineteer.layout`.

An inserted module's structural envelope must fit the inset host volume. Check
occupied bounds because fronts can extend past that envelope. Adjacent cabinet
definitions retain their own carcass sides; the assembly does not add a shared
wall or divider.

`Row` places children along X. `Stack` places them from bottom to top along Z.
Both use `gap_mm`, alignment, and `size_x` and `size_z` requests (`Fixed`,
`Fr`, or `Natural`). A `Stack` can set `depth_mm`. These values define the
group's structural envelope and datum. Children align inside that envelope;
fronts or other occupied geometry can extend beyond it. Review the resolved
structural and occupied bounds and any overhang diagnostics.

Use the assembly examples for rows and nesting. Define each reusable cabinet
once in `space_cabinets`, then place it with `CabinetRef`. Keep framing and
cabinet placement in the `Row` or `Stack` that owns their shared datum.

## Current limits

Enter furniture dimensions and profile points as project inputs. They are not
inferred from a room model. There is no room or ceiling snapping and no
general-purpose constraint solver.
Rectangular Space models size clear regions; use the profile path for supported
slopes. Space machining operations are explicit dimensions on qualified
physical parts. They do not generate CNC toolpaths or specify machine settings.
Profile assemblies do not accept these operations. Preview door and drawer
poses are illustrative. They do not check collisions during movement.
Profile assemblies and legacy cabinet projects do not accept Space edge
banding.

## Resolve, build, and review

First resolve the native project in the locked runtime. For Space projects,
`project.resolved_space_assembly()` returns the CAD-free plan. It checks input
references and resolves allocations, placements, spaces, fronts, and physical
parts without making CAD shapes. Use the result to inspect dimensions and
slack while editing. `plan.spaces` has clear-space bounds; `plan.allowances`
records unused edge space. Assembly plans also have allocation and placement
records.

Run a plan check from the repository root with the locked Python runtime. Set
`<name>` to the project folder:

```bash
buratino/.venv/bin/python - <<'PY'
from runpy import run_path

project = run_path("buratino/projects/<name>/project.py")["project"]
plan = project.resolved_space_assembly()
print("spaces:", [(space["id"], space["size"]) for space in plan.spaces])
print("fronts:", [(front["id"], front["size"]) for front in plan.fronts])
print("physical parts:", len(plan.part_plan.parts))
PY
```

Then run the normal build and preview from the repository root:

```bash
./buratino/bin/buratino build projects/<name>
./buratino/bin/buratino preview projects/<name>
```

After an edit, resolve the project again, build a new draft, then refresh the
preview page.

For a Space build, Buratino materializes the resolved parts as CAD shapes and
checks shape validity, part overlaps, and declared contacts. Profile builds
report native cap contact and overlap checks; they do not run the Space CAD
validation. Review `result.json`, `report.html`, and the preview after each
meaningful edit.
These checks do not confirm site fit, hardware installation, fasteners, or
manufacturing readiness. Keep unverified values in `assumptions` and observed
measurements in `observations`.

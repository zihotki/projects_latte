# Space machining operations

Use these inputs on a `CabinetProject` that uses `SpaceModelSpec`,
`space_cabinets`, or `space_modules`. Put them on the top-level project.
Operation and joint IDs must be unique across both tuples. Part IDs must match
the resolved physical part paths, including instance prefixes.

The resolver records each cut on its part. CAD and the manufacturing report
use these same records. They describe geometry in millimetres. They do not set
cutters, machine settings, feed rates, or toolpaths.

Space projects may also set `edge_banding=(EdgeBand(...), ...)` on the
top-level project. Each `EdgeBand` needs a unique `id`, an exact qualified
`part_id`, one stock face selector (`x-`, `x+`, `y-`, `y+`, `z-`, or `z+`), and
an optional six-digit `#RRGGBB` display color. It selects a narrow face whose
normal is not the stock thickness axis. It colors the full edge length and has
zero thickness. No edge-band dimension or material is inferred. The resolver
rejects unknown parts and duplicate part/edge selections. The viewer reports
an error if machining removes the selected edge face completely. It colors only
surviving finished faces on the original stock plane. This display input does not change the solid or
the cut list, BOM, or CSV fields.

Space projects can record grain for each resolved part with
`part_grain=(PartGrain("side-left", "/cabinet/carcass/side_left", "z"),)`.
The axis is local to the stock part (`x`, `y`, or `z`); `none` records stock
with no directional grain. A part with no record has unknown grain. The
resolver rejects duplicate, unknown, and thickness-axis references. It does
not infer grain from dimensions or change part geometry.
Import `PartGrain` from `cabineteer.part_grain`. The **Grain marks** control in
the main toolbar shows these saved directions. Finish controls change the display;
they do not edit `part_grain`.

See the [coordinate contract](coordinates.md) for stock axes, placement, face
coordinates, and the conversion to viewer coordinates.

## Small runnable project

Save this as `project.py` and run it with the locked Buratino Python runtime.
The pocket uses the local stock frame of the cabinet's left side.

```python
from cabineteer.operations import Groove, Pocket
from cabineteer.project import CabinetProject, EdgeBand, SpaceModelSpec
from cabineteer.spaces import Carcass, Space

project = CabinetProject(
    name="one-machined-side",
    space_model=SpaceModelSpec(
        carcass=Carcass(
            width=300, height=400, depth=280,
            side_thickness=18, bottom_thickness=18, top_thickness=18,
            back_thickness=6, material="maple", back_material="maple",
        ),
        root=Space("root"),
    ),
    operations=(
        Pocket(
            id="shelf-clearance",
            part_id="/cabinet/carcass/side_left",
            face="x-",
            u=20, v=80, size_u=40, size_v=18, depth=6,
        ),
        Groove(
            id="lower-side-groove",
            part_id="/cabinet/carcass/side_left",
            face="x+", edge="z-", offset=80, width=6, depth=3,
        ),
    ),
    edge_banding=(
        EdgeBand(
            id="front-left-side-band",
            part_id="/cabinet/carcass/side_left",
            edge="y-",
            color="#b78b5b",
        ),
    ),
)

plan = project.resolved_space_model()
print(plan.to_dict()["part_plan"]["parts"])
```

For an assembly, resolve `project.resolved_space_assembly()` and copy the full
part path from `part_plan.parts` into each input. A changed instance name can
change that path.

## Inputs

All inputs are frozen data classes in `cabineteer.operations`. Provide explicit
cut dimensions. An edge span can follow its named edge to the end. Faces are
`x-`, `x+`, `y-`, `y+`, `z-`, or `z+`.
Face coordinates `(u, v)` use the remaining local axes in ascending XYZ order.
The local origin is the minimum XYZ corner of the unmachined blank. Depth is
positive inward from the selected face.

```python
Pocket(id, part_id, face, u, v, size_u, size_v, depth)
Rabbet(id, part_id, face, edge, width, depth, start=0, length=None)
Bevel(id, part_id, face, edge, leg_a, leg_b, start=0, length=None)
Groove(id, part_id, face, edge, offset, width, depth, start=0, length=None)
Bore(id, part_id, face, u, v, diameter, depth)
Mortise(id, part_id, face, u, v, axis, length, width, depth)
DominoJoint(
    id, part_a, face_a, part_b, face_b, centre, axis,
    length, width, depth_a, depth_b,
)
```

`Pocket` removes a rectangular prism. `Rabbet` names an adjacent edge; width
and depth enter from their named faces. `Bevel` sweeps a right triangle along
the edge. Their `start` defaults to zero. An omitted or null `length` follows
the edge to its end; set a length for a stopped cut. The resolver recalculates
automatic spans when stock size changes. `Groove` runs parallel to its named
edge. Its `offset` measures inward from that edge to the near groove boundary.
It also follows the edge end when `length` is omitted or null. The resolved
groove uses the canonical pocket record. `Bore` is a round hole normal to a
face. `Mortise` is an obround
slot; its overall length must be at least its width. A `DominoJoint` describes
one paired joint with one world-space centre, one world-space axis, common
length and width, and explicit depth for each part. The resolver creates one
mortise record on each part. It does not choose a Domino size.

Every footprint and depth must fit the unmachined stock. A joint needs
coincident contact faces and a registered pair. The resolver rejects unknown
or ambiguous part IDs, duplicate IDs, non-box profiles, invalid dimensions,
and unsupported transforms.

## Review the result

```bash
./buratino/bin/buratino build projects/machined-drawer
```

Open the revision directory printed by the command. Its `result.json` has the
operation records on each part, and its `report.html` has the per-part
machining table. `blank_mm` reports the original stock. A machined part has no
verified `finished_mm` dimensions. These records do not confirm tooling, fit,
hardware, installation, or manufacturing readiness.

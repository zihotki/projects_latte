# Coordinates and placement

This page defines the coordinate contract used by Buratino and Cabineteer.
Use it when you add a part, operation, export, or viewer feature. Coordinates
always need a frame and a unit. A mesh vertex alone does not give a position
in the assembled cabinet.

## Model axes and units

All design and CAD distances use **millimetres**. The model uses a right-handed
XYZ frame:

| Axis | Positive direction | Cabinet dimension |
| --- | --- | --- |
| X | Left to right, when you face the cabinet | Width |
| Y | Front to back | Depth |
| Z | Bottom to top | Height |

A standalone Space cabinet starts at its outside lower front left corner,
`(0, 0, 0)`. Applied fronts can extend into negative Y. An assembly has its own
datum; a cabinet inside it can have a nonzero origin. “World” in model records
means the assembled furniture frame. It does not mean a measured room frame.

Geometry uses floating-point values. The whole-millimetre Space allocation
rule is a layout rule; it does not justify rounding slopes, frame axes, or
exported vertices. Numerical checks need a stated tolerance. Viewer offsets
used to keep grain marks visible above a face are display values, not added
stock thickness or machining allowances.

## The frames are different contracts

| Frame | Origin and axes | Used for |
| --- | --- | --- |
| Cabinet or module | Placement datum; model XYZ directions | Layout, clear spaces, nested inserts |
| Space stock | Minimum XYZ corner of the **uncut blank**; model XYZ directions | Cuts, grain axes, edge selectors |
| Profile stock | Explicit `LocalFrame`: origin plus length, width, thickness axes | Profile drawings and stock dimensions |
| CAD world | Assembly datum; model XYZ directions | Placed solids, contacts, bounds |
| GLB node local | Defined by the exported node hierarchy | Mesh vertices and viewer overlays |
| Viewer world | CAD basis rotated to Y-up | Camera, picking, display poses |

Do not treat Space stock XYZ and profile stock length/width/thickness as the
same axis order. Do not treat a GLB node's local coordinates as stock-local
coordinates.

## Space parts and nested placement

The resolved physical part plan is the source for rectangular geometry.
`stock.dimensions` and `profile.size` contain **XYZ dimensions**. The local
uncut box runs from zero to those dimensions. `transform.translation` places
it in CAD world. Generated `origin` and `bounds` describe that same placement:

```text
world_point = stock_point + transform.translation
origin = transform.translation
bounds = [origin, origin + size]
```

Nested cabinets and modules compose **translations only**. Each host origin,
layout offset, and inset contributes once. `Row` advances along X; `Stack`
advances along Z. A structural envelope sets the layout datum. Occupied bounds
also include fronts and other overhangs; their minimum is not a replacement
datum for the cabinet.

The current Space plan emits identity `transform.axes`. CAD materialization
and operation validation reject nonidentity axes. Nested rotation and mirror
placement are not supported. An `axes` field is not evidence of a general
matrix-transform API.

CAD creates the box at local zero, applies local cuts, then translates the
finished solid. Moving a cabinet must not change its cut dimensions or stock
face selections. See [Space resolution](../vendor/cabineteer/src/cabineteer/space_assembly.py)
and [CAD materialization](../vendor/cabineteer/src/cabineteer/space_adapter.py).

## Machining, grain, and edges

Machining refers to the uncut Space stock. It does not use the finished solid's
minimum corner or a viewer camera direction. A cut that removes an outside
face does not move the stock datum.

| Selected face | Face plane | U axis | V axis |
| --- | --- | --- | --- |
| `x-`, `x+` | X = 0 or stock X size | +Y | +Z |
| `y-`, `y+` | Y = 0 or stock Y size | +X | +Z |
| `z-`, `z+` | Z = 0 or stock Z size | +X | +Y |

Depth is positive inward: from a minus face it advances along the positive
normal axis; from a plus face it advances along the negative normal axis.
U and V do not reverse on the opposite face. A drawing can reverse a screen
direction without changing these machining coordinates.

An edge selector names an adjacent stock face. Edge spans follow the line
where the two faces meet. `PartGrain.axis` names a stock XYZ axis;
`surface_normal_axis_local` identifies the panel thickness direction.
`EdgeBand.edge` names a narrow stock face. These inputs stay attached to the
stock when machining changes the finished faces.

For example, a right side at world X = 702 with stock thickness 18 has outer
planes X = 702 and 720. A pocket on `x-` at `(u=20, v=100)` starts at world
`(702, origin_y + 20, origin_z + 100)` and cuts towards +X. Its local X plane
is still zero. A pocket floor inside the blank is not an original main face.

A `DominoJoint.centre` is an exception to the local input rule: it is an
assembly-world point. Its `axis` names a world XYZ axis. The resolver subtracts
each part translation and creates the two stock-local mortises. It checks the
contact faces and their common centre. See [operation inputs](operations.md)
and the [operation resolver](../vendor/cabineteer/src/cabineteer/operations.py).

## Native profile frames and world meshes

Native `ProfilePart` panels define their outline with row-local X/Z points in
`profile_xz_mm`. `y_mm` and `extrusion_mm` place and extrude that outline
along +Y. `world_offset_mm` adds row placement. These are native profile
fields; they are not the removed upper-project `profile.points_mm` format.
Outline coordinates are not stock length/thickness coordinates.

Built-in profile panels and native carcass adapters generate an explicit
`LocalFrame`. These generated frames are orthonormal and right-handed. Length
follows the panel, width lies in its plane, and thickness is normal to the
plane. A sloped cap therefore has a sloped length axis. Negative axis
components can be part of a right-handed frame; they do not by themselves
mean the part is mirrored. `LocalFrame` does not validate arbitrary input.

```text
world_point = frame.origin_mm
            + length * frame.length_axis
            + width * frame.width_axis
            + thickness * frame.thickness_axis
```

Native profile report `profile_mm` points and the `extrusion_mm` vector use
this manufacturing frame. Its `stock_mm` uses length, width, thickness order.
A native carcass panel can instead carry `geometry.kind = "world_mesh"`,
`frame = "world"`, and `units = "mm"`. Those vertices are already placed. Do
not apply the local stock frame to them again. That tessellation is display
geometry, not a machining plan. See
[profile frames and records](../vendor/cabineteer/src/cabineteer/profiles.py).

## GLB and the viewer

For supported Space and native assembly outputs, read the vertex **and the
complete node transform chain**. Space solids are placed before export, so
their named part nodes can be identity nodes with CAD-world vertex positions.
Native carcass `world_mesh` vertices also use CAD-world millimetres. Never add
the part origin to these exported vertices a second time. Other exporters may
represent placement in node transforms; a consumer must handle the full chain.

The exported scene root converts CAD Z-up to viewer Y-up with a -90 degree
rotation about X:

```text
CAD (x, y, z) -> viewer (x, z, -y)
```

This changes the basis, not the dimensions. The current viewer uses the same
numeric millimetre values. Apply the basis conversion once. A different
consumer must check units and node transforms at its import boundary.

For Space grain marks, the viewer transforms mesh vertices into the named
part node frame with `inverse(part.matrixWorld) * mesh.matrixWorld`. For a
Space part with profile data, it clips triangles to the original stock main
faces. Inset groove and rebate floors do not receive grain marks. For
world-placed Space meshes, coordinates in the part frame still include CAD
placement. Keep the stock datum when deriving face planes.

CAD assigns edge-band colors to surviving faces on the declared stock planes.
It matches each face normal and center to the plane; the viewer does not infer
edge-band provenance. Drawer and door poses are display transforms. They move
their part in the viewer and do not change resolved coordinates, reports, or
cut quantities.
See [viewer controls](../vendor/cabineteer/src/cabineteer/assets/viewer_controls.js)
and [GLB export](../vendor/cabineteer/src/cabineteer/visualize.py).

## Reports and cutting dimensions

Space report `stock_mm` and `blank_mm` order the two panel dimensions as
length and width. This can differ from stock XYZ order. Keep the stock axis
mapping and grain direction when you map these dimensions to a provider.
Do not recover orientation from the largest dimension alone. When planar
dimensions are equal, the first local axis in X, Y, Z order is the stable
blank-length tie-breaker used for reported grain direction.

Panel drawings project the actual CAD solid into a page. Their screen origin
and view direction are presentation choices. Operation coordinates retain
their stock datum. Drawing grouping removes translation when comparing parts;
it does not silently equate rotated or reflected parts. Buratino's current
build does not export STEP. See [panel views](../src/buratino/panel_views.py).

## Validation and change rules

These implementation checks define the supported cases:

| Rule | Checks |
| --- | --- |
| Nested placement uses translations and insets once | [Space assemblies](../vendor/cabineteer/tests/test_space_assembly.py), [CAD placements](../vendor/cabineteer/tests/test_space_assembly_cad.py) |
| Cuts use the stock datum and positive inward depth | [Operation validation](../vendor/cabineteer/tests/test_operations.py), [CAD cuts on six faces](../vendor/cabineteer/tests/test_space_operations_cad.py) |
| Profile frames reconstruct placed panel geometry | [Profiles](../vendor/cabineteer/tests/test_profiles.py), [profile consumers](../vendor/cabineteer/tests/test_profile_consumers.py) |
| Grain axes retain stock meaning | [Part grain](../vendor/cabineteer/tests/test_space_part_grain.py), [main-face plane regression](../vendor/cabineteer/tests/test_viewer_profile_grain.js) |
| Fresh exports retain placement, units, and the one root basis conversion | [Coordinate integration tests](../tests/test_coordinate_contract.py) |

These checks do not establish support for Space rotations or mirrors.

Run the export boundary checks in the locked runtime:

```sh
./buratino/bin/buratino test tests/test_coordinate_contract.py
node buratino/vendor/cabineteer/tests/test_viewer_profile_grain.js
```

Before changing a coordinate boundary, check a nonzero placement and unequal
dimensions. A symmetric box at the origin can hide an axis swap or a double
translation. Compare plan bounds, CAD bounds, and freshly exported GLB vertices
after node transforms. Include a placed sloped panel. Keep the original stock
frame unchanged.

When you add a geometry representation, define its frame at the producer and
add the corresponding consumer conversion. Do not infer its origin from the
shape's current minimum corner, dimensions, or part name.

The viewer grain regression must keep both original main faces where they
survive and reject inset machining faces. A helper test alone cannot establish
that the CAD exporter and viewer use the same frame. Pixel checks are still
useful for overlay appearance and open poses; numeric bounds checks do not
prove those visual details.

"""Ventilated sharpening kit box. Dimensions in mm; Z is up."""

import cadquery as cq
from soma import add_part, param

STONE_THICKNESS = param(
    6.0, "Stone thickness", min=5, max=7, step=0.5, unit="mm", group="Contents"
)
HOLDER_FEET = param(
    3.0, "Holder feet thickness", min=0, max=4, step=0.5, unit="mm", group="Contents"
)
CLEARANCE = param(
    0.5, "Slot clearance per side", min=0.3, max=1, step=0.1, unit="mm", group="Fit"
)
LID_CLEARANCE = param(
    0.35, "Lid clearance per side", min=0.2, max=0.6, step=0.05, unit="mm", group="Fit"
)
LAYOUT = param("Assembly", "Layout", options=["Assembly", "Print"], group="Display")

WALL = 2.4
BOTTOM = 2.4
DIVIDER = 2.4
EDGE_CHAMFER = 0.5
STONE_HEIGHT = 75.0
HOLDER_HEIGHT = 95.0
REST_HEIGHT = HOLDER_HEIGHT - STONE_HEIGHT
TOP_GAP = 0.5
LID_LIFT = 0.0
SLOT = STONE_THICKNESS + 2 * CLEARANCE
# Holder and leather stand on edge; the last bay holds shared accessories.
BAYS = [SLOT] * 4 + [30 + HOLDER_FEET + 2, 8, 74.4]
LENGTH = 208.0  # accommodates the 200 mm leather with clearance
HEIGHT = 102.0  # accommodates the 95 mm wide holder on edge
INNER_WIDTH = sum(BAYS) + (len(BAYS) - 1) * DIVIDER
WIDTH = INNER_WIDTH + 2 * WALL
assert WIDTH <= 256 and LENGTH <= 256 and HEIGHT <= 256, "Box exceeds A1 build volume"

body = cq.Workplane("XY").box(WIDTH, LENGTH, HEIGHT, centered=(False, False, False))
body = body.edges("|Z").chamfer(EDGE_CHAMFER)
body = body.faces(">Z").edges().chamfer(EDGE_CHAMFER)
body = body.faces("<Z").edges().chamfer(EDGE_CHAMFER)
body = body.cut(
    cq.Workplane("XY", origin=(WALL, WALL, BOTTOM)).box(
        INNER_WIDTH, LENGTH - 2 * WALL, HEIGHT, centered=(False, False, False)
    )
)
x = WALL
starts = []
for i, bay in enumerate(BAYS):
    starts.append(x)
    if i < len(BAYS) - 1:
        divider = cq.Workplane("XY", origin=(x + bay, WALL, BOTTOM)).box(
            DIVIDER,
            LENGTH - 2 * WALL,
            45 if i < 4 else 60,
            centered=(False, False, False),
        )
        divider = divider.faces(">Z").edges("|Y").chamfer(EDGE_CHAMFER)
        body = body.union(divider)
    x += bay + DIVIDER

# Three raised rests bring the stone tops level with the holder top.
# The spaces beneath them remain open to the floor vents.
for x in starts[:4]:
    for y in (25.0, LENGTH / 2, LENGTH - 25.0):
        body = body.union(
            cq.Workplane("XY", origin=(x, y - 2, BOTTOM)).box(
                SLOT, 4, REST_HEIGHT, centered=(False, False, False)
            )
        )
    # Hexagonal holes connect the air gap to the space below the box.
    holes = [
        (x + SLOT / 2, y)
        for y in (30, 40, 50, 60, 70, 80, 90, 115, 125, 135, 145, 155, 165, 175)
    ]
    cutter = (
        cq.Workplane("XY", origin=(0, 0, -0.1))
        .pushPoints(holes)
        .polygon(6, 4.8)
        .extrude(BOTTOM + 0.2)
    )
    body = body.cut(cutter)

# The 75 mm wide leather stands on matching supports beside the holder.
for y in (25.0, LENGTH / 2, LENGTH - 25.0):
    body = body.union(
        cq.Workplane("XY", origin=(starts[5], y - 2, BOTTOM)).box(
            BAYS[5], 4, REST_HEIGHT, centered=(False, False, False)
        )
    )

# Fill both spaces between the stone stops and the end walls. The pocket
# between the filled ends remains 171 mm long for 170 mm stones.
stone_end = starts[3] + SLOT
for y, depth in ((WALL, 18.5 - WALL), (189.5, LENGTH - WALL - 189.5)):
    body = body.union(
        cq.Workplane("XY", origin=(WALL, y, BOTTOM)).box(
            stone_end - WALL, depth, 38, centered=(False, False, False)
        )
    )

# Diamond apertures have 45-degree upper edges for support-free FDM bridging.
points = [(y, z) for y in range(30, 181, 15) for z in range(11, 92, 10)]
holes = (
    cq.Workplane("YZ", origin=(-0.1, 0, 0))
    .pushPoints(points)
    .polygon(4, 5.6)
    .extrude(stone_end + DIVIDER + 0.2)
)
body = body.cut(holes)

# Loose slip-on cover, with vents above the stone rack only. The lid seats on
# the box rim. It is not a watertight closure.
LID_TOP = 2.4
SKIRT = 8.0
outside_w = WIDTH + 2 * (LID_CLEARANCE + WALL)
outside_l = LENGTH + 2 * (LID_CLEARANCE + WALL)
lid = cq.Workplane("XY").box(
    outside_w, outside_l, SKIRT + LID_TOP, centered=(False, False, False)
)
lid = lid.edges("|Z").chamfer(EDGE_CHAMFER)
lid = lid.faces(">Z").edges().chamfer(EDGE_CHAMFER)
lid = lid.cut(
    cq.Workplane("XY", origin=(WALL, WALL, -0.1)).box(
        WIDTH + 2 * LID_CLEARANCE,
        LENGTH + 2 * LID_CLEARANCE,
        SKIRT + 0.1,
        centered=(False, False, False),
    )
)
lid_holes = [
    (WALL + LID_CLEARANCE + xx + SLOT / 2, WALL + LID_CLEARANCE + y)
    for xx in starts[:4]
    for y in (30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180)
]
lid = lid.cut(
    cq.Workplane("XY", origin=(0, 0, SKIRT - 0.1))
    .pushPoints(lid_holes)
    .polygon(6, 4.8)
    .extrude(LID_TOP + 0.2)
)
# Stops on the inside of the lid sit just above the stone, leather and holder.
# They are placed between lid vents so the air holes remain open.
stop_height = HEIGHT + LID_LIFT - (BOTTOM + HOLDER_HEIGHT) - TOP_GAP
assert 0 < stop_height < SKIRT, "Lid stops do not fit within the lid"
stop_x = [x + SLOT / 2 for x in starts[:4]] + [
    starts[4] + BAYS[4] / 2,
    starts[5] + BAYS[5] / 2,
]
for x in stop_x:
    for y in (35, 175):
        lid = lid.union(
            cq.Workplane(
                "XY",
                origin=(
                    WALL + LID_CLEARANCE + x,
                    WALL + LID_CLEARANCE + y,
                    SKIRT - stop_height,
                ),
            ).box(3, 3, stop_height + 0.1, centered=(True, True, False))
        )
if LAYOUT == "Assembly":
    lid = lid.translate(
        (-WALL - LID_CLEARANCE, -WALL - LID_CLEARANCE, HEIGHT - SKIRT + LID_LIFT)
    )
else:
    # Print the cover top face down, beside the box in the viewer.
    lid = lid.rotate((0, 0, 0), (1, 0, 0), 180).translate(
        (WIDTH + 15, outside_l, SKIRT + LID_TOP)
    )
for name, part in [("Storage box", body), ("Ventilated lid", lid)]:
    assert part.val().isValid() and len(part.solids().vals()) == 1, f"{name} is invalid"
    bb = part.val().BoundingBox()
    assert max(bb.xlen, bb.ylen, bb.zlen) <= 256, f"{name} exceeds A1 build volume"
    add_part(name, part)

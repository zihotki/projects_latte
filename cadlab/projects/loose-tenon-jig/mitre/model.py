"""Screw-together mitre mortise jig for 18 mm stock."""

from math import cos, radians, sin, sqrt
from pathlib import Path
import sys

import cadquery as cq
from soma import add_part, param

# Both SOMA projects use the same guide geometry and tooling formulas.
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
try:
    from parts import geometry as g
finally:
    sys.path.pop(1)

bushing_diameter = param(16.0, "Guide bushing outside diameter", min=12, max=30,
                         step=0.05, unit="mm", group="Tooling")
bushing_projection = param(5.0, "Bushing projection below router base", min=3, max=8,
                           step=0.1, unit="mm", group="Tooling")
cutter_diameter = param(6.0, "Mortise cutter diameter", min=5, max=6,
                        step=0.05, unit="mm", group="Tooling")
slot_allowance = param(0.25, "Total slot fit allowance", min=0.15, max=g.MAX_SLOT_ALLOWANCE,
                       step=0.05, unit="mm", group="Fit")
mitre_angle = param(45.0, "Angle between bevel and board face", min=36, max=90,
                    step=0.5, unit="°", group="Geometry")
display = param("Bevel and mortise", "View setup",
                options=["Bevel and mortise", "Jig", "Print jig",
                         "Print guide plate", "Print fence"], group="Display")

DECK_HALF, DECK_FRONT, DECK_BACK = 84.0, -54.0, 57.0
DECK_CORNER = 8.0
FENCE_HALF, FENCE_BACK = 76.0, DECK_FRONT
FENCE_LENGTH = 34.0 * sqrt(2)  # Along the angled workpiece face.
WING_END, WING_THICKNESS = 116.0, 12.0 / sqrt(2)
BOARD_HALF = 115.0
NORMAL_FASTENER_Y = -31.0
PILOT_WALL = 1.5

PLUNGE = g.TENON_LENGTH / 2
ANGLE_SINE, ANGLE_COSINE = sin(radians(mitre_angle)), cos(radians(mitre_angle))
SLOPE = ANGLE_COSINE / ANGLE_SINE
MIN_WOOD = 1.0
MAX_CUT_WIDTH = g.TENON_THICKNESS + g.MAX_SLOT_ALLOWANCE
# With the widest cut, the nearest point at the mouth leaves 1 mm normal to the stock face.
REFERENCE_FACE_Y = -MAX_CUT_WIDTH / 2 - MIN_WOOD / ANGLE_SINE
OPPOSITE_FACE_Y = REFERENCE_FACE_Y + g.STOCK / ANGLE_SINE
# Move the entire screw and locator row together if a shallow bevel needs more pilot wall.
FASTENER_Y = min(NORMAL_FASTENER_Y, REFERENCE_FACE_Y - g.SCREW_PILOT_DEPTH * SLOPE
                 - g.SCREW_PILOT_DIAMETER / 2 - PILOT_WALL / ANGLE_SINE)


def make_guide(width, length):
    # The guide underside is the bevel plane.
    deck = g.outline(((-DECK_HALF + DECK_CORNER, DECK_FRONT), (DECK_HALF - DECK_CORNER, DECK_FRONT),
                      (DECK_HALF, DECK_FRONT + DECK_CORNER), (DECK_HALF, DECK_BACK - DECK_CORNER),
                      (DECK_HALF - DECK_CORNER, DECK_BACK), (-DECK_HALF + DECK_CORNER, DECK_BACK),
                      (-DECK_HALF, DECK_BACK - DECK_CORNER), (-DECK_HALF, DECK_FRONT + DECK_CORNER)))
    deck = deck.cut(g.chamfered_slot(width, length, 0))
    for pocket in g.locating_pockets(FASTENER_Y, locate_x=True):
        deck = deck.cut(pocket)
    for x in g.L_JOINT_X:
        deck = deck.cut(g.screw_clearance(x, FASTENER_Y))

    mark_height = min(g.PLATE / 2, g.PLATE - bushing_projection - g.BARREL_MARK_CLEARANCE)
    marks = g.marking_tools(DECK_FRONT, DECK_BACK, ((DECK_FRONT, 1), (DECK_BACK, -1)),
                            ((0.0, DECK_HALF),), width, length, mark_height)
    return cq.Workplane(obj=deck.val().cut(*marks))


def make_fence(width):
    # In this frame the workpiece face lies on the bed and the end is at Y = -FENCE_LENGTH.
    rear_span = REFERENCE_FACE_Y - FENCE_BACK
    rear_height = rear_span * ANGLE_SINE
    end_height = (rear_span - FENCE_LENGTH * ANGLE_COSINE) / ANGLE_SINE
    section = ((-FENCE_LENGTH, 0), (0, 0), (-rear_span * ANGLE_COSINE, rear_height),
               (-FENCE_LENGTH, end_height))
    fence = cq.Workplane("YZ", origin=(-WING_END, 0, 0)).polyline(section).close().extrude(2 * WING_END)
    wing_cut_width = WING_END - FENCE_HALF + g.CUT_MARGIN
    for side in (-1, 1):
        x = side * (FENCE_HALF + wing_cut_width / 2)
        fence = fence.cut(g.box(wing_cut_width, FENCE_LENGTH + 2 * g.CUT_MARGIN,
                                rear_height - WING_THICKNESS + g.CUT_MARGIN, x, -FENCE_LENGTH / 2, WING_THICKNESS))
    fence = fence.edges().chamfer(g.BED_CHAMFER)

    origin, x_axis = (0, 0, 0), (1, 0, 0)
    face_mark_length = g.PLATE / (2 * ANGLE_SINE)
    face_mark = (g.alignment_groove(face_mark_length + 2 * g.CUT_MARGIN)
                 .rotate(origin, x_axis, 180).translate((0, -face_mark_length / 2, 0)))
    end_mark = (g.alignment_groove(end_height + 2 * g.CUT_MARGIN)
                .rotate(origin, x_axis, 90).translate((0, -FENCE_LENGTH, end_height / 2)))
    fence = (fence.cut(face_mark).cut(end_mark).rotate(origin, x_axis, mitre_angle)
             .translate((0, REFERENCE_FACE_Y, 0)))

    for x in g.LOCATOR_X:
        fence = fence.union(g.locator(x, FASTENER_Y))

    for x in g.L_JOINT_X:
        fence = fence.cut(g.screw_pilot(x, FASTENER_Y))

    # Continue the centerline across the exposed seat and down the rear face.
    mark_start = -width / 2 - g.OPENING_CHAMFER
    mark_end = REFERENCE_FACE_Y + g.CUT_MARGIN
    seat_mark = g.alignment_groove(mark_end - mark_start).translate((0, (mark_start + mark_end) / 2, 0))
    back_height = FENCE_LENGTH * ANGLE_SINE - end_height * ANGLE_COSINE
    back_mark = (g.alignment_groove(back_height + 2 * g.CUT_MARGIN).rotate(origin, x_axis, 90)
                 .translate((0, FENCE_BACK, -back_height / 2)))
    return fence.cut(seat_mark).cut(back_mark)


def reference_stock():
    depth = -55.0
    section = ((REFERENCE_FACE_Y, 0), (OPPOSITE_FACE_Y, 0),
               (OPPOSITE_FACE_Y + depth * SLOPE, depth), (REFERENCE_FACE_Y + depth * SLOPE, depth))
    return (cq.Workplane("YZ", origin=(-BOARD_HALF, 0, 0))
            .polyline(section).close().extrude(2 * BOARD_HALF))


slot_width, slot_length = g.slot_dimensions(bushing_diameter, cutter_diameter, slot_allowance)
cut_width = g.TENON_THICKNESS + slot_allowance
cut_length = g.TENON_WIDTH + slot_allowance
mouth_wall = (-REFERENCE_FACE_Y - cut_width / 2) * ANGLE_SINE
bottom_wall = (OPPOSITE_FACE_Y - PLUNGE * SLOPE - cut_width / 2) * ANGLE_SINE
if min(mouth_wall, bottom_wall) < MIN_WOOD - 1e-9:
    raise ValueError("The mortise must leave at least 1 mm of wood on the bevelled stock.")
if bushing_projection > g.PLATE - g.BARREL_MARK_CLEARANCE:
    raise ValueError("The bushing projection must leave clearance beneath the guide deck.")

guide = make_guide(slot_width, slot_length)
fence = make_fence(slot_width)
printing = display.startswith("Print")
if printing:
    guide = g.position_on_bed(guide, 40, 20)
    fence_y = 143 if display == "Print jig" else 20
    fence = fence.rotate((0, 0, 0), (1, 0, 0), -mitre_angle)
    fence = g.position_on_bed(fence, g.A1 / 2 - WING_END, fence_y)

pieces = [("Mitre guide plate", guide, (0.30, 0.55, 0.72)),
          (f"{mitre_angle:g}° fence with clamp wings", fence, (0.66, 0.55, 0.38))]
if display == "Print guide plate":
    pieces = pieces[:1]
elif display == "Print fence":
    pieces = pieces[1:]

for name, part, color in pieces:
    if len(part.solids().vals()) != 1 or not part.val().isValid():
        raise ValueError(f"{name} must be one valid solid.")
    if printing:
        bounds = part.val().BoundingBox()
        if min(bounds.xmin, bounds.ymin) < g.BRIM or max(bounds.xmax, bounds.ymax) > g.A1 - g.BRIM:
            raise ValueError(f"{name} and its 4 mm brim must fit on the A1 plate.")
    add_part(name, part, color=color)

if not printing:
    for index, screw_x in enumerate(g.L_JOINT_X, 1):
        add_part(f"4 × 30 mm wood screw {index}", g.screw(screw_x, FASTENER_Y),
                 role="hardware", group="Hardware")

if display == "Bevel and mortise":
    cut = g.box(cut_length, cut_width, PLUNGE, 0, 0, -PLUNGE)
    stock = reference_stock()
    add_part("18 mm bevelled board", stock.cut(cut), role="reference", color=(0.77, 0.58, 0.39), alpha=0.55)
    add_part("15 mm mortise envelope", cut, role="reference", color=(0.87, 0.39, 0.17), alpha=0.75)

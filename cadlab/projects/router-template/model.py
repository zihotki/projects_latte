"""Round guide template for routing an internal circular hole. Dimensions are mm."""

import cadquery as cq
from soma import add_part, param

# The workpiece hole and router tooling determine the guide opening.
# The template stays centered on the Z axis, with its bottom on XY.
TARGET_DIAMETER = param(65.0, "Finished hole diameter", min=50, max=80, step=0.5, unit="mm")
BUSHING_DIAMETER = param(16.0, "Bushing outside diameter", min=12, max=20, step=0.5, unit="mm")
BIT_DIAMETER = param(6.0, "Bit diameter", min=4, max=10, step=0.5, unit="mm")
PLATE_DIAMETER = param(200.0, "Plate diameter", min=160, max=220, step=1, unit="mm")
THICKNESS = param(6.0, "Plate thickness", min=4, max=10, step=0.5, unit="mm")
CHAMFER = 0.5
GUIDE_DIAMETER = TARGET_DIAMETER + BUSHING_DIAMETER - BIT_DIAMETER


def make_template():
    plate = (cq.Workplane("XY")
             .circle(PLATE_DIAMETER / 2)
             .circle(GUIDE_DIAMETER / 2)
             .extrude(THICKNESS))
    assert plate.edges("%Circle").size() == 4, "Expected four circular edges"
    plate = plate.edges("%Circle").chamfer(CHAMFER)
    shape = plate.val()
    assert shape.isValid() and len(plate.solids().vals()) == 1, "Template must be one valid solid"
    return plate


add_part("Router template", make_template())

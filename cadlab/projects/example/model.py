"""A small parametric plate for checking the SOMA workspace. Dimensions are mm."""

import cadquery as cq
from soma import add_part, param

width = param(40.0, "Width", min=20, max=100, unit="mm")
depth = param(30.0, "Depth", min=20, max=100, unit="mm")
thickness = param(4.0, "Thickness", min=2, max=10, unit="mm")
hole_diameter = param(6.0, "Hole diameter", min=2, max=12, unit="mm")

result = (
    cq.Workplane("XY")
    .box(width, depth, thickness)
    .faces(">Z")
    .workplane()
    .hole(hole_diameter)
)

add_part("Plate", result)

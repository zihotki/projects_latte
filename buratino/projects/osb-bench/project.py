"""Draft OSB bench using native Space cabinets and a recessed frame."""

from cabineteer.layout import CabinetRef, Frame, Row, Stack
from cabineteer.project import CabinetProject
from cabineteer.spaces import (
    Carcass,
    Divider,
    Fixed,
    Space,
    SpaceCabinetDefinition,
    Split,
)

WIDTH = 2380
UNIT_WIDTH = WIDTH // 2
DEPTH = 500
THICKNESS = 18
BASE_HEIGHT = 70
BOX_HEIGHT = 340
BACK_EXTENSION = 250
TOE_RECESS = 70
MATERIAL = "18 mm OSB"

variables = {
    "preview_finish": "osb",
    "observations": [
        "Bench dimensions are design inputs and have not been checked on site.",
    ],
    "assumptions": [
        "Each unit has a one-piece back applied behind the sides.",
        "The base is a four-rail frame with no intermediate supports in this draft.",
        "Fasteners, stability, load capacity and back attachment are unverified.",
    ],
}
calculated = {}

# Whole-millimetre spaces differ by at most 1 mm and use all available width.
opening_widths = (373, 373, 372)
children = []
for index, width in enumerate(opening_widths, start=1):
    children.append(Space(f"section-{index}", Fixed(width)))
    if index < len(opening_widths):
        children.append(
            Divider(f"divider-{index}", thickness=THICKNESS, material=MATERIAL)
        )

body = SpaceCabinetDefinition(
    "bench-body",
    Carcass(
        width=UNIT_WIDTH,
        height=BOX_HEIGHT,
        depth=DEPTH,
        side_thickness=THICKNESS,
        bottom_thickness=THICKNESS,
        top_thickness=THICKNESS,
        back_thickness=THICKNESS,
        back_height=BOX_HEIGHT + BACK_EXTENSION,
        horizontal_panels_full_width=True,
        material=MATERIAL,
        back_material=MATERIAL,
    ),
    Space("root", split=Split("width", tuple(children))),
)


def unit(name):
    return Stack(
        name,
        (
            Frame(
                "base", UNIT_WIDTH, DEPTH - TOE_RECESS, BASE_HEIGHT, THICKNESS, MATERIAL
            ),
            CabinetRef("body", "bench-body"),
        ),
        size_x=Fixed(UNIT_WIDTH),
        size_z=Fixed(BASE_HEIGHT + BOX_HEIGHT),
        depth_alignment="back",
    )


project = CabinetProject(
    name="osb-bench",
    space_cabinets=(body,),
    layout=Row(
        "bench",
        (unit("left"), unit("right")),
        size_x=Fixed(WIDTH),
        size_z=Fixed(BASE_HEIGHT + BOX_HEIGHT),
        depth_alignment="back",
    ),
)

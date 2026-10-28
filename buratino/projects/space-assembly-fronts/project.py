"""A two-cabinet row with a left-hinged door and a drawer front."""

from cabineteer.hettich_eb20 import EB20_SLIDE_KEYS
from cabineteer.layout import CabinetRef, Row
from cabineteer.project import CabinetProject
from cabineteer.spaces import (
    AppliedDrawerFront,
    Carcass,
    Door,
    DrawerBox,
    Fixed,
    Fr,
    Space,
    SpaceCabinetDefinition,
)

variables = {
    "observations": ["Example dimensions are design inputs, not site measurements."],
    "assumptions": [
        "Both overlay fronts use a 2 mm reveal.",
        "The 380 mm Hettich Quadro V6 EB20 selection is illustrative.",
        "Check hinge mounting and drawer clearances before construction.",
    ],
}
calculated = {}

_drawer_recipe = {
    "bottom_clearance": 30,
    "height": "fit",
    "slide_key": EB20_SLIDE_KEYS[380],
    "side_thickness": 16,
    "front_back_thickness": 18,
    "bottom_thickness": 12,
    "bottom_dado_depth": 6,
    "bottom_dado_inset": 13,
    "material": "plywood",
    "bottom_material": "plywood",
}

space_cabinets = (
    SpaceCabinetDefinition(
        name="left-door-cabinet",
        carcass=Carcass(
            width=240,
            height=600,
            depth=420,
            side_thickness=18,
            bottom_thickness=18,
            top_thickness=18,
            back_thickness=6,
            door_gap=2,
            drawer_front_gap=2,
            outer_reveal=2,
            material="plywood",
            back_material="plywood",
        ),
        root=Space("root"),
        fronts=(Door("left-door", covers="/root", hinge_side="left"),),
    ),
    SpaceCabinetDefinition(
        name="drawer-cabinet",
        carcass=Carcass(
            width=Fr(1),
            height=600,
            depth=420,
            side_thickness=18,
            bottom_thickness=18,
            top_thickness=18,
            back_thickness=6,
            door_gap=2,
            drawer_front_gap=2,
            outer_reveal=2,
            material="plywood",
            back_material="plywood",
        ),
        root=Space("root", content=DrawerBox("box", **_drawer_recipe)),
        fronts=(
            AppliedDrawerFront(
                "drawer-front",
                covers="/root",
                attached_to="/root/box",
                thickness=18,
                material="plywood",
            ),
        ),
    ),
    SpaceCabinetDefinition(
        name="right-door-cabinet",
        carcass=Carcass(
            width=Fr(2),
            height=600,
            depth=420,
            side_thickness=18,
            bottom_thickness=18,
            top_thickness=18,
            back_thickness=6,
            door_gap=2,
            drawer_front_gap=2,
            outer_reveal=2,
            material="plywood",
            back_material="plywood",
        ),
        root=Space("root"),
        fronts=(Door("right-door", covers="/root", hinge_side="right"),),
    ),
)

layout = Row(
    name="main-row",
    children=(
        CabinetRef(name="left", definition="left-door-cabinet"),
        CabinetRef(name="right", definition="drawer-cabinet"),
        CabinetRef(name="far-right", definition="right-door-cabinet"),
    ),
    gap_mm=6,
    size_x=Fixed(953),
    size_z=Fixed(600),
)

project = CabinetProject(
    name="space-assembly-fronts",
    space_cabinets=space_cabinets,
    layout=layout,
)

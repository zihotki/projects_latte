"""Two plywood cabinets with two side-mounted drawers each."""

from cabineteer.layout import CabinetRef, Row
from cabineteer.project import CabinetProject, GrainRule
from cabineteer.spaces import (
    AppliedDrawerFront,
    Carcass,
    Divider,
    DrawerBox,
    Fixed,
    Fr,
    Space,
    SpaceCabinetDefinition,
    Split,
)

variables = {
    "observations": [
        "Each cabinet is 1048 mm wide, 679 mm high, and 590 mm deep including fronts.",
        "Cabinet and drawer parts use 18 mm plywood.",
        "Each cabinet has two drawers using Ferretti HDSC550V90 slides.",
    ],
    "assumptions": [
        "The 572 mm body depth includes the back and excludes the 18 mm fronts.",
        "Cabinets stand side by side with no gap, and drawers have "
        "equal-height openings.",
        "Drawer fronts have 2 mm reveals and a 3 mm top reveal; confirm handles.",
        "A 50 mm deep, 18 mm thick rail spans the cabinet front between drawers; "
        "confirm fastening and support.",
        "Drawer bottoms use 18 mm plywood in 6 mm deep grooves with a 13 mm "
        "bottom inset; confirm joinery.",
        "Slide clearance is modeled as 19.5 mm per side; confirm installation "
        "tolerances, mounting, load conditions and drawer width with the supplier.",
        "The model does not check whether the cabinets fit under the window "
        "or support the intended load.",
        "Grain directions are design choices for the shown plywood parts, "
        "not measurements of purchased sheets. Confirm the cutting layout.",
    ],
}
calculated = {}

_drawer = {
    "height": 270,
    "bottom_clearance": 10,
    "top_clearance": 10,
    "front_gap": 0,
    "slide_key": "ferretti_hdsc550v90",
    "side_thickness": 18,
    "front_back_thickness": 18,
    "bottom_thickness": 18,
    "bottom_dado_depth": 6,
    "bottom_dado_inset": 13,
    "material": "plywood",
    "bottom_material": "plywood",
}

cabinet = SpaceCabinetDefinition(
    name="two-drawer-cabinet",
    carcass=Carcass(
        width=1048,
        height=679,
        depth=572,
        side_thickness=18,
        bottom_thickness=18,
        top_thickness=18,
        back_thickness=18,
        material="plywood",
        back_material="plywood",
    ),
    root=Space(
        "root",
        split=Split(
            axis="height",
            children=(
                Space("lower", Fr(1), content=DrawerBox("box-lower", **_drawer)),
                Divider("front-rail", depth=50, material="plywood"),
                Space("upper", Fr(1), content=DrawerBox("box-upper", **_drawer)),
            ),
        ),
    ),
    fronts=(
        AppliedDrawerFront(
            "lower-front",
            covers="/root/lower",
            attached_to="/root/lower/box-lower",
            thickness=18,
            material="plywood",
        ),
        AppliedDrawerFront(
            "upper-front",
            covers="/root/upper",
            attached_to="/root/upper/box-upper",
            thickness=18,
            material="plywood",
            top_reveal=3,
        ),
    ),
)

project = CabinetProject(
    name="two-under-window",
    space_cabinets=(cabinet,),
    layout=Row(
        name="cabinet-row",
        children=(
            CabinetRef(name="left", definition="two-drawer-cabinet"),
            CabinetRef(name="right", definition="two-drawer-cabinet"),
        ),
        gap_mm=0,
        size_x=Fixed(2096),
        size_z=Fixed(679),
    ),
    part_grain=tuple(
        GrainRule(pattern, pattern, axis)
        for pattern, axis in (
            ("/cabinet-row/*/carcass/side_*", "z"),
            ("/cabinet-row/*/carcass/top", "x"),
            ("/cabinet-row/*/carcass/bottom", "x"),
            ("/cabinet-row/*/carcass/back", "z"),
            ("/cabinet-row/*/root/*/box-*/side_*", "y"),
            ("/cabinet-row/*/root/*/box-*/sub_front", "x"),
            ("/cabinet-row/*/root/*/box-*/back", "x"),
            ("/cabinet-row/*/root/*/box-*/bottom", "x"),
            ("/cabinet-row/*/root/front-rail", "x"),
            ("/cabinet-row/*/front/*", "z"),
        )
    ),
)

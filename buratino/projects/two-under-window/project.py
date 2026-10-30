"""Two melamine cabinets with two side-mounted drawers each."""

from cabineteer.joinery import DominoJoinery
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
        "Carcass parts use 18 mm melamine; drawer walls and fronts use 18 mm plywood.",
        "Each cabinet has two drawers using Ferretti HDSC500V90 slides.",
    ],
    "assumptions": [
        "The 572 mm body depth includes the back and excludes the 18 mm fronts.",
        "Cabinets stand side by side with no gap, and drawers have "
        "equal-height openings.",
        "Drawer fronts have 2 mm reveals and a 3 mm top reveal; confirm handles.",
        "A 50 mm deep, 18 mm thick rail spans the cabinet front between drawers; "
        "Domino joints are modeled at both ends; confirm support.",
        "Drawer bottoms use 12 mm plywood in 8 mm deep grooves with a 13 mm "
        "bottom inset.",
        "Drawer boxes are 544 mm deep, leaving 10 mm behind in the 554 mm clear body. "
        "The 500 mm runner travel leaves the rear 44 mm inside at full travel.",
        "Domino joints use a declared 6 x 40 mm tenon recipe: 20 x 6 mm obround "
        "mortises, 12 mm into the side face and 28 mm into the panel end. "
        "These slot dimensions are design choices, not catalog mortise measurements.",
        "The back is screw-on and applied fronts need separate fastening; "
        "no screw holes are modeled.",
        "Slide clearance is modeled as 19.5 mm per side; confirm installation "
        "tolerances, mounting, load conditions and drawer width with the supplier.",
        "Runner source: https://www.meubelbeslagcenter.nl/"
        "heavy-duty-softclose-ladegeleiders-500mm-zijmontage . "
        "The supplier lists HDSC500V90 as a pair, 500 mm long with 500 mm travel, "
        "19.5 mm thick, 53 mm high, with a 90 kg product rating. "
        "This is not a cabinet load check.",
        "Asymmetric 12/28 mm depths for a 40 mm Domino follow the Festool manual: "
        "https://www.festool.com/-/media/tts/fcp/festool/knowledge/downloads-page/download-brochures/"
        "manual_domino/versions/festool-domino-manual-april-2016-au-imp-en.pdf .",
        "The model does not check whether the cabinets fit under the window "
        "or support the intended load.",
        "Grain directions are design choices for the shown plywood parts, "
        "not measurements of purchased sheets. Confirm the cutting layout.",
    ],
}
calculated = {}

_drawer = {
    "height": 270,
    "depth": 544,
    "bottom_clearance": 10,
    "top_clearance": 10,
    "front_gap": 0,
    "slide_key": "ferretti_hdsc500v90",
    "side_thickness": 18,
    "front_back_thickness": 18,
    "bottom_thickness": 12,
    "bottom_dado_depth": 8,
    "bottom_dado_inset": 13,
    "corner_joinery": DominoJoinery(end_offsets=(60, 60), spacing=90),
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
        material="melamine",
        back_material="melamine",
        joinery=DominoJoinery(end_offsets=(70, 74)),
    ),
    root=Space(
        "root",
        split=Split(
            axis="height",
            children=(
                Space("lower", Fr(1), content=DrawerBox("box-lower", **_drawer)),
                Divider("front-rail", depth=50, material="melamine"),
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

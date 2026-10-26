"""Bare cabinet project. Inputs and assembly stay together in this file."""

from cabineteer.cabinet import CabinetConfig
from cabineteer.joinery import CarcassJoinery, DominoSpec
from cabineteer.project import CabinetProject, ProjectCabinet, SharedDesign

# Measurements, material choices, and unresolved design notes.
variables = {
    "space_mm": {"width": 720, "height": 970, "depth_min": 500, "depth_max": 550},
    "observations": [
        (
            "User-reported space the furniture must fit within; "
            "this is not a measured fit survey."
        ),
        "Depth is reported as 500 to 550 mm. Exact clear depth remains open.",
    ],
    "assumptions": [
        (
            "720 x 970 mm are space limits. This draft has no fitting allowance; "
            "confirm final carcass dimensions before cutting."
        ),
        (
            "500 mm is a draft carcass depth; the later overlay fronts need "
            "additional depth within the verified space."
        ),
        (
            "Top thickness is provisionally 18 mm. Measured thicknesses have "
            "not been supplied."
        ),
        (
            "The 6 mm back, its unmachined pocket beneath the top, and its "
            "fastening are provisional."
        ),
        "Edge treatment, support/plinth, installation and fixing method remain open.",
        (
            "Step 1 is a bare cabinet. Four drawers, overlay fronts, EB20 runners, "
            "and bottom braces are deferred to step 2."
        ),
    ],
    "width_mm": 720,
    "height_mm": 970,
    "depth_mm": 500,
    "side_thickness_mm": 18,
    "top_thickness_mm": 18,
    "bottom_thickness_mm": 18,
    "back_thickness_mm": 6,
    "carcass_material": "Melamine-faced board; core and measured thickness unverified",
    "back_material": "6 mm board; material and fastening unconfirmed",
    "cabinet_gap_mm": 0,
    "connections": [],
    "edge_gap_mm": 2,
    "front_gap_mm": 2,
}


# Native shared settings are defined once. Use the resolved native config for
# calculated interior dimensions.
_shared = SharedDesign(
    side_thickness=variables["side_thickness_mm"],
    top_thickness=variables["top_thickness_mm"],
    bottom_thickness=variables["bottom_thickness_mm"],
    back_thickness=variables["back_thickness_mm"],
    carcass_material=variables["carcass_material"],
    face_top_style="plain",
    face_bottom_style="plain",
    carcass_joinery=CarcassJoinery.FLOATING_TENON,
    back_style="under_top",
    back_capture="pocket",
    domino_spec=DominoSpec(size_key="6x40"),
)
_config = CabinetConfig(
    width=variables["width_mm"],
    height=variables["height_mm"],
    depth=variables["depth_mm"],
    openings=[],
    columns=[],
    leg_count=0,
)
_calculation_project = CabinetProject(
    name="simple-cabinet",
    cabinets=(ProjectCabinet(name="cabinet", config=_config),),
    shared=_shared,
)
_resolved = dict(_calculation_project.resolved())["cabinet"]
calculated = {
    "interior_width_mm": _resolved.interior_width,
    "interior_height_mm": _resolved.interior_height,
    "interior_depth_mm": _resolved.interior_depth,
    "closed_depth_mm": _resolved.depth,
}


# Assembly: one native cabinet with the shared settings above.
project = CabinetProject(
    name="simple-cabinet",
    cabinets=(ProjectCabinet(name="cabinet", config=_config),),
    shared=_shared,
)

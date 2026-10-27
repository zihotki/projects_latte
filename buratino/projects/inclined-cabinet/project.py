"""Synthetic bare cabinet with an inclined top, for preview and stock planning."""

import math

from cabineteer.cabinet import CabinetConfig
from cabineteer.project import CabinetProject, ProjectCabinet, SharedDesign

variables = {
    "width_mm": 720,
    "left_height_mm": 850,
    "right_height_mm": 970,
    "depth_mm": 500,
    "carcass_material": "Example board",
    "back_material": "Example back board",
    "observations": ["Synthetic dimensions; this is not a measured installation."],
    "assumptions": [
        "Roof joints, fasteners, and fabrication details are not selected."
    ],
    "connections": [],
}
calculated = {
    "left_height_mm": variables["left_height_mm"],
    "right_height_mm": variables["right_height_mm"],
}
angle = math.degrees(
    math.atan2(
        variables["right_height_mm"] - variables["left_height_mm"],
        variables["width_mm"],
    )
)
config = CabinetConfig(
    width=variables["width_mm"],
    height=max(variables["left_height_mm"], variables["right_height_mm"]),
    depth=variables["depth_mm"],
    roof_angle_deg=angle,
    openings=[],
    columns=[],
    leg_count=0,
)
project = CabinetProject(
    name="inclined-cabinet",
    cabinets=(ProjectCabinet(name="cabinet", config=config),),
    shared=SharedDesign(
        face_top_style="plain",
        face_bottom_style="plain",
        back_style="under_top",
        back_capture="pocket",
    ),
)

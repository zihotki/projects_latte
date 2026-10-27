"""Synthetic native profile assembly. All measurements are draft inputs."""

from cabineteer.cabinet import CabinetConfig, OpeningConfig
from cabineteer.layout import Frame, LayoutLeaf, Stack
from cabineteer.profiles import (
    ProfileAssemblySpec,
    ProfiledBox,
    ProfileFaceSpec,
    RoofProfile,
)
from cabineteer.project import CabinetProject, ProjectCabinet

variables = {
    "assumptions": [
        "Synthetic dimensions; hardware, joinery and installation are unverified."
    ]
}
calculated = {}
frame = Frame("frame.support", 720, 380, 50, 18, "18 mm plywood")
layout = Stack(
    "assembly",
    (
        LayoutLeaf("lower", 720, 550, 720),
        frame,
        LayoutLeaf("upper", 720, 420, 600),
    ),
)
boxes = (
    ProfiledBox("upper.left", 0, 360, 420, 18, 18, 6, "18 mm plywood", "6 mm board"),
    ProfiledBox("upper.right", 360, 360, 420, 18, 18, 6, "18 mm plywood", "6 mm board"),
)
lower = CabinetConfig(
    width=720,
    height=720,
    depth=550,
    back_thickness=6,
    door_gap_mm=2,
    drawer_front_gap_mm=2,
    openings=[OpeningConfig(240, "drawer"), OpeningConfig(444, "door")],
)
drawer = {
    "opening_width": 684,
    "opening_height": 240,
    "opening_depth": 544,
    "slide_key": "buratino_hettich_quadro_v6_eb20_480",
    "side_thickness": 16,
    "front_back_thickness": 18,
    "bottom_thickness": 12,
    "bottom_dado_depth": 6,
    "bottom_dado_inset": 13,
    "front_gap": 0,
    "vertical_gap": 60,
    "use_standard_height": False,
    "applied_face": False,
    "joinery_style": "butt",
    "face_overlay_top": 3,
    "face_overlay_bottom": 3,
}
profile = ProfileAssemblySpec(
    RoofProfile(((0, 300), (720, 600)), 18),
    boxes,
    "roof",
    ("slope",),
    frame,
    "lower",
    "18 mm plywood",
    ProfileFaceSpec(drawer, 30, material="18 mm plywood"),
    shared_owner="upper",
    roof_joint="level_over_divider",
)
project = CabinetProject(
    "profile-row-sloped",
    (ProjectCabinet("lower", lower),),
    layout=layout,
    profile_assembly=profile,
)

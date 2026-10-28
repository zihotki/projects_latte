"""Native draft of the measured real assembly; joinery remains unverified."""

from cabineteer.cabinet import CabinetConfig
from cabineteer.layout import Frame, LayoutLeaf, Row, Stack
from cabineteer.profiles import (
    ProfileAssemblySpec,
    ProfiledBox,
    ProfileDrawerSpec,
    ProfileFaceSpec,
    ProfileLowerDrawerSpec,
    ProfileShelfSpec,
    RoofProfile,
)
from cabineteer.project import CabinetProject, ProjectCabinet

variables = {
    "space_mm": {},
    "first_compartment_space_mm": {
        "width": 720,
        "height": 970,
        "depth_min": 500,
        "depth_max": 550,
    },
    "observations": [
        "The reported space is not a measured fit survey.",
        "Exact clear depth is unknown within the reported 500 to 550 mm range.",
        "The 720 x 970 mm space applies to the first compartment only.",
        "Width for the second cabinet and the full assembly is unmeasured.",
        "Final fitting allowance is unmeasured.",
    ],
    "assumptions": [
        "Both lower carcasses are selected as 720 x 930 x 506 mm.",
        "The second lower cabinet fit is unverified.",
        "The two lower carcasses are intended to be fastened side-to-side.",
        "The upper projects 46 mm beyond the support frame; support is unverified.",
        "Check ceiling fit before construction.",
        "Hardware, joinery, wall restraint, frames, and shelf supports are unverified.",
        "One shared upper carcass and an applied back are draft choices.",
        "Rear drawer relief and runner mounting are not specified for machining.",
    ],
}
calculated = {}

lower = CabinetConfig(
    width=720,
    height=930,
    depth=506,
    side_thickness=18,
    top_thickness=18,
    bottom_thickness=18,
    back_thickness=6,
    back_capture="overlay",
    back_style="full_height",
    carcass_material="Melamine-faced board",
    face_material="Melamine-faced board",
    face_gap_mm=2,
    door_gap_mm=2,
    drawer_front_gap_mm=2,
    leg_count=0,
)
bottom_frame = Frame("frame.bottom", 1440, 506, 50, 18, "18 mm plywood")
support_frame = Frame("frame.support", 1440, 380, 50, 18, "18 mm plywood")
layout = Stack(
    "assembly",
    (
        bottom_frame,
        Row(
            "lowers",
            (
                LayoutLeaf("left-drawers", 720, 506, 930),
                LayoutLeaf("right-drawers", 720, 506, 930),
            ),
        ),
        support_frame,
        LayoutLeaf("upper", 1440, 426, 1204),
    ),
)
boxes = tuple(
    ProfiledBox(
        name,
        x,
        360,
        426,
        18,
        18,
        6,
        "Melamine-faced board",
        "6 mm board",
    )
    for name, x in (
        ("upper.section-1", 0),
        ("upper.section-2", 360),
        ("upper.section-3", 720),
        ("upper.section-4", 1080),
    )
)
lower_recipe = dict(
    slide_key="buratino_hettich_quadro_v6_eb20_480",
    drawer_count=4,
    box_height_mm=180,
    bottom_clearance_mm=30,
    side_mm=16,
    front_back_mm=18,
    bottom_mm=12,
    bottom_dado_depth_mm=6,
    bottom_dado_inset_mm=13,
    material="Melamine-faced board",
    bottom_material="Melamine-faced board",
)
profile = ProfileAssemblySpec(
    roof=RoofProfile(((0, 235), (1080, 1204), (1440, 1204)), 18),
    boxes=boxes,
    cap_owner="upper.roof",
    cap_names=("slope", "level"),
    frame=support_frame,
    lower="left-drawers",
    lower_back_material="6 mm board",
    frames=(bottom_frame, support_frame),
    cap_material="Melamine-faced board",
    shared_owner="upper",
    continuous_bottom=True,
    roof_joint="level_over_divider",
    faces=ProfileFaceSpec(
        outer_reveal_mm=2,
        roof_reveal_mm=2,
        depth_offset_mm=2,
        thickness_mm=18,
        material="Melamine-faced board",
    ),
    lower_drawers=(
        ProfileLowerDrawerSpec(cabinet="left-drawers", **lower_recipe),
        ProfileLowerDrawerSpec(cabinet="right-drawers", **lower_recipe),
    ),
    upper_drawers=(
        ProfileDrawerSpec(
            section="upper.section-1",
            slide_key="buratino_hettich_quadro_v6_eb20_380",
            box_height_mm=140,
            bottom_clearance_mm=20,
            side_mm=16,
            front_back_mm=18,
            bottom_mm=12,
            bottom_dado_depth_mm=6,
            bottom_dado_inset_mm=13,
            material="Melamine-faced board",
            bottom_material="Melamine-faced board",
        ),
    ),
    adjustable_shelves=(
        ProfileShelfSpec(
            "low", "upper.section-2", 270, material="Melamine-faced board"
        ),
        ProfileShelfSpec(
            "low", "upper.section-3", 270, material="Melamine-faced board"
        ),
        ProfileShelfSpec(
            "mid", "upper.section-3", 550, material="Melamine-faced board"
        ),
        ProfileShelfSpec(
            "high", "upper.section-3", 830, material="Melamine-faced board"
        ),
        ProfileShelfSpec(
            "low", "upper.section-4", 270, material="Melamine-faced board"
        ),
        ProfileShelfSpec(
            "mid", "upper.section-4", 550, material="Melamine-faced board"
        ),
        ProfileShelfSpec(
            "high", "upper.section-4", 830, material="Melamine-faced board"
        ),
    ),
)
project = CabinetProject(
    "real-assembly-native",
    (ProjectCabinet("left-drawers", lower), ProjectCabinet("right-drawers", lower)),
    layout=layout,
    profile_assembly=profile,
)

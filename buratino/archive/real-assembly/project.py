"""Two equal four-drawer cabinets for a draft side-by-side assembly."""

from dataclasses import replace

from cabineteer.cabinet import CabinetConfig, OpeningConfig
from cabineteer.joinery import CarcassJoinery, DominoSpec, DrawerJoineryStyle
from cabineteer.project import CabinetProject, ProjectCabinet, SharedDesign

from buratino.drawers import EB20_SLIDE_KEYS, make_eb20_drawer_config

# A code identifies one group of panels with the same modeled processing.
# If a group changes, review this map and assign new codes where needed.
part_codes = {
    **dict.fromkeys(("left-drawers.carcass.left_side",), "L01"),
    **dict.fromkeys(("left-drawers.carcass.right_side",), "L02"),
    **dict.fromkeys(
        (
            "left-drawers.carcass.bottom",
            "right-drawers.carcass.bottom",
            "left-drawers.carcass.top",
            "right-drawers.carcass.top",
        ),
        "L03",
    ),
    **dict.fromkeys(
        (
            "left-drawers.carcass.back",
            "right-drawers.carcass.back",
        ),
        "L05",
    ),
    **{
        f"{cabinet}.drawer.column-0.opening-{index}.side_left": "L06"
        for cabinet in ("left-drawers", "right-drawers")
        for index in range(4)
    },
    **{
        f"{cabinet}.drawer.column-0.opening-{index}.side_right": "L07"
        for cabinet in ("left-drawers", "right-drawers")
        for index in range(4)
    },
    **{
        f"{cabinet}.drawer.column-0.opening-{index}.inner_front": "L08"
        for cabinet in ("left-drawers", "right-drawers")
        for index in range(4)
    },
    **{
        f"{cabinet}.drawer.column-0.opening-{index}.back": "L09"
        for cabinet in ("left-drawers", "right-drawers")
        for index in range(4)
    },
    **{
        f"{cabinet}.drawer.column-0.opening-{index}.bottom": "L10"
        for cabinet in ("left-drawers", "right-drawers")
        for index in range(4)
    },
    **{
        f"{cabinet}.drawer.column-0.opening-{index}.face": "L11"
        for cabinet in ("left-drawers", "right-drawers")
        for index in range(4)
    },
    **dict.fromkeys(("right-drawers.carcass.left_side",), "L12"),
    **dict.fromkeys(("right-drawers.carcass.right_side",), "L13"),
    **dict.fromkeys(
        (
            "frame.bottom.back",
            "frame.bottom.front",
            "frame.top.back",
            "frame.top.front",
        ),
        "F01",
    ),
    **dict.fromkeys(
        (
            "frame.bottom.left",
            "frame.bottom.right",
        ),
        "F02",
    ),
    **dict.fromkeys(
        (
            "frame.top.left",
            "frame.top.right",
        ),
        "F03",
    ),
    **dict.fromkeys(("upper.left.column-0.opening-0.side_left",), "U01"),
    **dict.fromkeys(("upper.left.column-0.opening-0.side_right",), "U02"),
    **dict.fromkeys(("upper.left.column-0.opening-0.inner_front",), "U03"),
    **dict.fromkeys(("upper.left.column-0.opening-0.back",), "U04"),
    **dict.fromkeys(("upper.left.column-0.opening-0.bottom",), "U05"),
    **dict.fromkeys(("upper.left.left_side",), "U06"),
    **dict.fromkeys(("upper.left.divider",), "U07"),
    **dict.fromkeys(("upper.left.right_side",), "U08"),
    **dict.fromkeys(("upper.left.back",), "U09"),
    **dict.fromkeys(
        (
            "upper.left.bottom_1",
            "upper.left.bottom_2",
            "upper.left.section_2_shelf_1",
            "upper.right.bottom_1",
            "upper.right.bottom_2",
            "upper.right.section_1_shelf_1",
            "upper.right.section_1_shelf_2",
            "upper.right.section_1_shelf_3",
            "upper.right.section_2_shelf_1",
            "upper.right.section_2_shelf_2",
            "upper.right.section_2_shelf_3",
        ),
        "U10",
    ),
    **dict.fromkeys(("upper.right.left_side",), "U11"),
    **dict.fromkeys(("upper.right.divider",), "U12"),
    **dict.fromkeys(("upper.right.right_side",), "U13"),
    **dict.fromkeys(("upper.right.back",), "U14"),
    **dict.fromkeys(("upper.shared.top_sloped",), "U15"),
    **dict.fromkeys(("upper.shared.top_level",), "U16"),
    **dict.fromkeys(("upper.left.column-0.opening-0.face",), "U17"),
    **dict.fromkeys(("upper.left.section-2.door",), "U18"),
    **dict.fromkeys(("upper.right.section-1.door",), "U19"),
    **dict.fromkeys(("upper.right.section-2.door",), "U20"),
}

variables = {
    "part_codes": part_codes,
    "drawer_domino": True,
    "domino_machining": {
        "cutter_diameter_mm": 6,
        "face_depth_mm": {"min": 12, "max": 15},
        "face_reference": "centered",
    },
    # The user confirmed the grain directions shown in this design.
    "grain_direction_confirmed": True,
    # No total installation envelope has been reported for this assembly.
    "space_mm": {},
    "first_compartment_space_mm": {
        "width": 720,
        "height": 970,
        "depth_min": 500,
        "depth_max": 550,
    },
    "observations": [
        (
            "User-reported space the furniture must fit within; "
            "this is not a measured fit survey."
        ),
        "Depth is reported as 500 to 550 mm. Exact clear depth remains open.",
    ],
    "notes": [
        "The reported 720 x 970 mm space belongs to the first compartment only.",
        "Available width for the second cabinet and total assembly is unmeasured.",
        "Final fitting allowance is unmeasured.",
        "The 1440 mm body width is computed from two selected 720 mm cabinets.",
        "The two carcasses are intended to be fastened side-to-side.",
        (
            "The user has a router and suitable jig for the 6x40 Domino mortises. "
            "Slot fit, glue clearance, and reference surfaces remain unverified."
        ),
    ],
    "assumptions": [
        (
            "Both existing drawer cabinets use the same selected 720 x 930 x "
            "506 mm overall carcass dimensions. The second cabinet fit is unverified."
        ),
        (
            "500 mm side depth plus a 6 mm back gives a 506 mm carcass depth. "
            "The 18 mm faces and 2 mm gap make the closed depth 526 mm."
        ),
        ("The full-width rear backs use 6 mm board; back fastening is provisional."),
        "Runner mounting and box-to-face fastening are not specified for machining.",
        (
            "A 180 mm box height and 30 mm base box-bottom clearance are draft "
            "geometry choices, not Hettich manufacturing dimensions. Calculated "
            "opening clearances preserve the earlier box positions with the "
            "native equal-face layout."
        ),
        (
            "The 30 x 13 mm rear back-corner clearances are draft geometry "
            "assumptions, not Hettich manufacturing dimensions."
        ),
        (
            "The 6x40 Domino selection is fixed. The router and suitable jig are "
            "user-provided; slot fit, glue clearance, and reference surfaces "
            "remain unverified."
        ),
        (
            "The carcasses are intended to be fastened side-to-side. Fastener "
            "selection, quantity, capacity, and position remain unverified."
        ),
        (
            "The upper cabinet fastening, wall restraint, shelf support, back, "
            "and top-panel joinery remain unverified."
        ),
    ],
    "frame_height_mm": 50,
    "frame_thickness_mm": 18,
    "frame_material": "18 mm plywood",
    "top_frame_depth_mm": 380,
    "width_mm": 720,
    "height_mm": 930,
    "side_depth_mm": 500,
    "side_thickness_mm": 18,
    "top_thickness_mm": 18,
    "bottom_thickness_mm": 18,
    "back_thickness_mm": 6,
    "carcass_material": "Melamine-faced board",
    "back_material": "6 mm board",
    "cabinet_gap_mm": 0,
    "connections": [
        {"from": "left-drawers", "to": "right-drawers", "type": "side_to_side"}
    ],
    "edge_gap_mm": 2,
    "front_gap_mm": 2,
    "drawer_count": 4,
    # Each cabinet uses one runner length for all its drawers.
    "runner_length_mm": 480,
    "runner_length_by_cabinet_mm": {
        # "left-drawers": 450,
    },
    "drawer_side_thickness_mm": 16,
    "drawer_inner_front_back_thickness_mm": 18,
    "drawer_bottom_thickness_mm": 12,
    "drawer_bottom_recess_mm": 13,
    "drawer_bottom_groove_depth_mm": 6,
    "rear_corner_clearance_width_mm": 30,
    "drawer_box_height_mm": 180,
    "drawer_box_bottom_clearance_mm": 30,
    "drawer_face_thickness_mm": 18,
    "face_to_carcass_gap_mm": 2,
    "drawer_face_overlay_top_mm": 3,
    "drawer_face_overlay_bottom_mm": 3,
    "drawer_material": "Melamine-faced board",
    "upper": {
        "cabinet_width_mm": 720,
        "thickness_mm": 18,
        "back_thickness_mm": 6,
        "back_material": "6 mm board",
        "left_height_mm": 235,
        "right_height_mm": 1204,
        "shelf_levels_mm": [270, 550, 830],
        "runner_length_mm": 380,
        "drawer_side_thickness_mm": 16,
        "drawer_front_back_thickness_mm": 18,
        "drawer_bottom_thickness_mm": 12,
        "drawer_bottom_recess_mm": 13,
        "drawer_rear_corner_clearance_width_mm": 30,
        "drawer_box_height_mm": 140,
        "drawer_bottom_clearance_mm": 20,
        "front_thickness_mm": 18,
        "front_gap_mm": 3,
        "front_bottom_projection_mm": 10,
        "x": 0,
        "y": 0,
        "z": 1030,
        "material": "Melamine-faced board",
    },
}
variables["depth_mm"] = variables["side_depth_mm"] + variables["back_thickness_mm"]
variables["bottom_frame_depth_mm"] = variables["depth_mm"]
variables["upper"]["depth_mm"] = 420 + variables["upper"]["back_thickness_mm"]
variables["upper"]["y"] = variables["depth_mm"] - variables["upper"]["depth_mm"]
variables["upper"]["z"] = variables["height_mm"] + 2 * variables["frame_height_mm"]
variables["assumptions"].extend(
    [
        "The upper cabinets stand on the top frame, flush to the lower backs.",
        "The upper carcass projects 46 mm past the top frame; support is unverified.",
        "Upper shelf levels are draft choices; attachments are unknown.",
        (
            "The sloped top is 18 mm thick normal to its surface and butts "
            "against the right divider and the edge of the flat top above it. "
            "The flat top covers the divider and the right section; their "
            "fastening remains unverified. The divider is centered in the right "
            "cabinet, and the slope transition aligns with its left face. "
            "The four section clear widths are 333 mm."
        ),
        (
            "The upper profile uses the stated endpoint heights and an adjusted "
            "slope for equal sections. Confirm ceiling fit before construction."
        ),
        "Upper 6 mm backs, their stock and fastening are provisional.",
    ]
)
variables["face_material"] = variables["drawer_material"]
# The top frame is flush with the cabinet backs.
variables["cabinet_base_z_mm"] = variables["frame_height_mm"]
variables["frames"] = [
    {
        "id": name,
        "width": 2 * variables["width_mm"],
        "depth": depth,
        "height": variables["frame_height_mm"],
        "thickness": variables["frame_thickness_mm"],
        "material": variables["frame_material"],
        "x": 0,
        "y": variables["depth_mm"] - depth,
        "z": z,
    }
    for name, depth, z in (
        ("bottom", variables["bottom_frame_depth_mm"], 0),
        (
            "top",
            variables["top_frame_depth_mm"],
            variables["frame_height_mm"] + variables["height_mm"],
        ),
    )
]
variables["assumptions"].extend(
    [
        "The top frame is flush with the cabinet backs.",
        "Bottom frame depth is provisionally 506 mm.",
        "Frame butt-joint fastening and attachment to the carcasses are unverified.",
    ]
)


_shared = SharedDesign(
    side_thickness=variables["side_thickness_mm"],
    top_thickness=variables["top_thickness_mm"],
    bottom_thickness=variables["bottom_thickness_mm"],
    back_thickness=variables["back_thickness_mm"],
    carcass_material=variables["carcass_material"],
    face_material=variables["face_material"],
    drawer_box_thickness=variables["drawer_side_thickness_mm"],
    drawer_joinery=DrawerJoineryStyle.BUTT,
    face_gap_mm=variables["front_gap_mm"],
    face_top_style="plain",
    face_bottom_style="plain",
    carcass_joinery=CarcassJoinery.FLOATING_TENON,
    back_style="full_height",
    back_capture="overlay",
    domino_spec=DominoSpec(size_key="6x40"),
)
_base_config = CabinetConfig(
    width=variables["width_mm"],
    height=variables["height_mm"],
    depth=variables["depth_mm"],
    openings=[],
    columns=[],
    leg_count=0,
)
_base_project = CabinetProject(
    name="real-assembly",
    cabinets=(
        ProjectCabinet(name="left-drawers", config=_base_config),
        ProjectCabinet(name="right-drawers", config=_base_config),
    ),
    shared=_shared,
)
_resolved = dict(_base_project.resolved())
_left = _resolved["left-drawers"]

# Use the same native opening and box layout for each cabinet.
calculated = {
    "body_assembly_width_mm": 2 * variables["width_mm"],
    "carcass_assembly_height_mm": variables["upper"]["z"]
    + variables["upper"]["right_height_mm"],
    "closed_depth_mm": (
        variables["depth_mm"]
        + variables["drawer_face_thickness_mm"]
        + variables["face_to_carcass_gap_mm"]
    ),
    "interior_mm": {
        "width": _left.interior_width,
        "height": _left.interior_height,
        "depth": _left.interior_depth,
    },
    "front_height_mm": (
        variables["height_mm"]
        - 2 * variables["edge_gap_mm"]
        - (variables["drawer_count"] - 1) * variables["front_gap_mm"]
    )
    / variables["drawer_count"],
}
_opening_start = _left.bottom_thickness
_opening_boundaries = [
    _opening_start,
    *(
        variables["edge_gap_mm"]
        + index * (calculated["front_height_mm"] + variables["front_gap_mm"])
        - variables["front_gap_mm"] / 2
        for index in range(1, variables["drawer_count"])
    ),
    _left.height - _left.top_thickness,
]
calculated["opening_heights_mm"] = [
    _opening_boundaries[index + 1] - _opening_boundaries[index]
    for index in range(variables["drawer_count"])
]
calculated["box_bottom_clearances_mm"] = [
    _left.bottom_thickness
    + index * calculated["interior_mm"]["height"] / variables["drawer_count"]
    + variables["drawer_box_bottom_clearance_mm"]
    - _opening_boundaries[index]
    for index in range(variables["drawer_count"])
]


def _runner_length_mm(cabinet_name):
    return variables["runner_length_by_cabinet_mm"].get(
        cabinet_name, variables["runner_length_mm"]
    )


def _cabinet(name):
    openings = tuple(
        OpeningConfig(
            height_mm=calculated["opening_heights_mm"][index],
            opening_type="drawer",
            slide_key=EB20_SLIDE_KEYS[_runner_length_mm(name)],
        )
        for index in range(variables["drawer_count"])
    )
    return ProjectCabinet(
        name=name, config=replace(_base_config, openings=list(openings))
    )


project = CabinetProject(
    name="real-assembly",
    cabinets=(_cabinet("left-drawers"), _cabinet("right-drawers")),
    shared=_shared,
)

drawer_configs = {
    f"{cabinet_name}/column-0/opening-{index}": make_eb20_drawer_config(
        opening_width=calculated["interior_mm"]["width"],
        opening_height=calculated["opening_heights_mm"][index],
        opening_depth=calculated["interior_mm"]["depth"],
        side_thickness=variables["drawer_side_thickness_mm"],
        front_back_thickness=variables["drawer_inner_front_back_thickness_mm"],
        bottom_thickness=variables["drawer_bottom_thickness_mm"],
        bottom_dado_depth=variables["drawer_bottom_groove_depth_mm"],
        bottom_dado_inset=variables["drawer_bottom_recess_mm"],
        box_height=variables["drawer_box_height_mm"],
        vertical_gap=calculated["box_bottom_clearances_mm"][index],
        front_gap=0,
        face_thickness=variables["drawer_face_thickness_mm"],
        face_overlay_sides=_left.side_thickness - variables["edge_gap_mm"],
        face_overlay_top=variables["drawer_face_overlay_top_mm"],
        face_overlay_bottom=variables["drawer_face_overlay_bottom_mm"],
        material=variables["drawer_material"],
        joinery_style=DrawerJoineryStyle.BUTT,
        rear_corner_clearance_width_mm=variables["rear_corner_clearance_width_mm"],
        runner_length_mm=_runner_length_mm(cabinet_name),
    )
    for cabinet_name in ("left-drawers", "right-drawers")
    for index in range(variables["drawer_count"])
}

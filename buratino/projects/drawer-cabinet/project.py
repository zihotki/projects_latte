"""Four-drawer cabinet project, authored as one Python module."""

from dataclasses import replace

from cabineteer.cabinet import CabinetConfig, OpeningConfig
from cabineteer.joinery import CarcassJoinery, DominoSpec, DrawerJoineryStyle
from cabineteer.project import CabinetProject, ProjectCabinet, SharedDesign

from buratino.drawers import make_eb20_drawer_config

# The reported envelope is separate from the selected cabinet size.
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
            "500 mm is a draft carcass depth. The 18 mm faces plus a 2 mm "
            "face-to-carcass gap make the overall depth 520 mm."
        ),
        (
            "The 6 mm back, its unmachined pocket beneath the top, and its "
            "fastening are provisional."
        ),
        "Runner mounting and box-to-face fastening are not specified for machining.",
        (
            "A 180 mm box height and 30 mm base box-bottom clearance are draft "
            "geometry choices, not Hettich manufacturing dimensions. Calculated "
            "opening clearances preserve the earlier box positions with the "
            "native equal-face layout."
        ),
        (
            "The 6 mm bottom groove and 30 × 13 mm rear back-corner clearances "
            "are draft geometry assumptions, not Hettich manufacturing dimensions."
        ),
        "The 6x40 Domino selection is fixed, but mortise data remains unverified.",
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
    "drawer_count": 4,
    "drawer_side_thickness_mm": 16,
    "drawer_inner_front_back_thickness_mm": 18,
    "drawer_bottom_thickness_mm": 12,
    "drawer_bottom_recess_mm": 13,
    "drawer_bottom_groove_depth_mm": 6,
    "rear_corner_clearance_width_mm": 30,
    "runner_length_mm": 450,
    "drawer_box_height_mm": 180,
    "drawer_box_bottom_clearance_mm": 30,
    "drawer_face_thickness_mm": 18,
    "face_to_carcass_gap_mm": 2,
    "drawer_face_overlay_top_mm": 3,
    "drawer_face_overlay_bottom_mm": 3,
    "drawer_material": "Melamine-faced board; core and measured thickness unverified",
}
variables["face_material"] = variables["drawer_material"]


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
    back_style="under_top",
    back_capture="pocket",
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
_calculation_project = CabinetProject(
    name="drawer-cabinet",
    cabinets=(ProjectCabinet(name="cabinet", config=_base_config),),
    shared=_shared,
)
_resolved = dict(_calculation_project.resolved())["cabinet"]

# Derived layout values use native resolved cabinet dimensions.
calculated = {
    "interior_width_mm": _resolved.interior_width,
    "interior_height_mm": _resolved.interior_height,
    "interior_depth_mm": _resolved.interior_depth,
    "front_height_mm": (
        _resolved.height
        - 2 * variables["edge_gap_mm"]
        - (variables["drawer_count"] - 1) * variables["front_gap_mm"]
    )
    / variables["drawer_count"],
    "closed_depth_mm": (
        _resolved.depth
        + variables["drawer_face_thickness_mm"]
        + variables["face_to_carcass_gap_mm"]
    ),
}
_opening_start = _resolved.bottom_thickness
_opening_boundaries = [
    _opening_start,
    *(
        variables["edge_gap_mm"]
        + index * (calculated["front_height_mm"] + variables["front_gap_mm"])
        - variables["front_gap_mm"] / 2
        for index in range(1, variables["drawer_count"])
    ),
    _resolved.height - _resolved.top_thickness,
]
calculated["opening_heights_mm"] = [
    _opening_boundaries[index + 1] - _opening_boundaries[index]
    for index in range(variables["drawer_count"])
]
calculated["box_bottom_clearances_mm"] = [
    _resolved.bottom_thickness
    + index * calculated["interior_height_mm"] / variables["drawer_count"]
    + variables["drawer_box_bottom_clearance_mm"]
    - _opening_boundaries[index]
    for index in range(variables["drawer_count"])
]


# Assembly: native openings own the stack; the adapter supplies sourced EB20
# sizing for each drawer while the face layout remains native.
_openings = tuple(
    OpeningConfig(
        height_mm=calculated["opening_heights_mm"][index],
        opening_type="drawer",
        slide_key="buratino_hettich_quadro_v6_eb20",
    )
    for index in range(variables["drawer_count"])
)
_config = replace(_base_config, openings=list(_openings))
project = CabinetProject(
    name="drawer-cabinet",
    cabinets=(ProjectCabinet(name="cabinet", config=_config),),
    shared=_shared,
)
drawer_configs = {
    f"cabinet/column-0/opening-{index}": make_eb20_drawer_config(
        opening_width=calculated["interior_width_mm"],
        opening_height=calculated["opening_heights_mm"][index],
        opening_depth=calculated["interior_depth_mm"],
        side_thickness=variables["drawer_side_thickness_mm"],
        front_back_thickness=variables["drawer_inner_front_back_thickness_mm"],
        bottom_thickness=variables["drawer_bottom_thickness_mm"],
        bottom_dado_depth=variables["drawer_bottom_groove_depth_mm"],
        bottom_dado_inset=variables["drawer_bottom_recess_mm"],
        box_height=variables["drawer_box_height_mm"],
        vertical_gap=calculated["box_bottom_clearances_mm"][index],
        front_gap=0,
        face_thickness=variables["drawer_face_thickness_mm"],
        face_overlay_sides=_resolved.side_thickness - variables["edge_gap_mm"],
        face_overlay_top=variables["drawer_face_overlay_top_mm"],
        face_overlay_bottom=variables["drawer_face_overlay_bottom_mm"],
        material=variables["drawer_material"],
        joinery_style=DrawerJoineryStyle.BUTT,
        rear_corner_clearance_width_mm=variables["rear_corner_clearance_width_mm"],
        runner_length_mm=variables["runner_length_mm"],
    )
    for index in range(variables["drawer_count"])
}

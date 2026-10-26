"""Synthetic two-cabinet row for shared values and explicit connection intent."""

from dataclasses import replace

from cabineteer.cabinet import CabinetConfig, OpeningConfig
from cabineteer.joinery import CarcassJoinery, DominoSpec, DrawerJoineryStyle
from cabineteer.project import CabinetProject, ProjectCabinet, SharedDesign

from buratino.drawers import make_eb20_drawer_config

variables = {
    "space_mm": {"width": 1192, "height": 700, "depth_min": 480, "depth_max": 550},
    "observations": [
        "Synthetic fixture dimensions for assembly tests; not a user survey."
    ],
    "assumptions": ["Side-to-side fastening and capacity are not specified."],
    "width_a_mm": 600,
    "height_mm": 700,
    "unit_b_top_thickness_mm": 22,
    "depth_mm": 480,
    "side_thickness_mm": 18,
    "top_thickness_mm": 18,
    "bottom_thickness_mm": 18,
    "back_thickness_mm": 6,
    "cabinet_gap_mm": 0,
    "connections": [{"from": "unit-a", "to": "unit-b", "type": "side_to_side"}],
    "edge_gap_mm": 2,
    "front_gap_mm": 2,
    "carcass_material": "Synthetic melamine-faced board; unverified",
    "back_material": "Synthetic 6 mm board; unverified",
    "drawer_side_thickness_mm": 16,
    "drawer_inner_front_back_thickness_mm": 18,
    "drawer_bottom_thickness_mm": 12,
    "drawer_box_height_mm": 180,
    "drawer_box_bottom_clearance_mm": 30,
    "drawer_bottom_recess_mm": 12,
    "drawer_bottom_groove_depth_mm": 6,
    "drawer_face_thickness_mm": 18,
    "runner_length_mm": 450,
    "face_to_carcass_gap_mm": 2,
    "drawer_material": "Synthetic melamine-faced board; unverified",
}
variables["face_material"] = variables["drawer_material"]
_width_b_mm = (
    variables["space_mm"]["width"]
    - variables["width_a_mm"]
    - variables["cabinet_gap_mm"]
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
    back_style="under_top",
    back_capture="pocket",
    domino_spec=DominoSpec(size_key="6x40"),
)
_base_a = CabinetConfig(
    width=variables["width_a_mm"],
    height=variables["height_mm"],
    depth=variables["depth_mm"],
    openings=[],
    columns=[],
    leg_count=0,
)
_base_b = CabinetConfig(
    width=_width_b_mm,
    height=variables["height_mm"],
    depth=variables["depth_mm"],
    top_thickness=variables["unit_b_top_thickness_mm"],
    openings=[],
    columns=[],
    leg_count=0,
)
_project_configs = CabinetProject(
    name="linked-row-fixture",
    cabinets=(
        ProjectCabinet(name="unit-a", config=_base_a),
        ProjectCabinet(
            name="unit-b",
            config=_base_b,
            overrides=frozenset({"top_thickness"}),
        ),
    ),
    shared=_shared,
)
_resolved = dict(_project_configs.resolved())

calculated = {
    "width_b_mm": _width_b_mm,
    "run_width_mm": variables["space_mm"]["width"],
    "unit_a_interior_mm": {
        "width": _resolved["unit-a"].interior_width,
        "height": _resolved["unit-a"].interior_height,
        "depth": _resolved["unit-a"].interior_depth,
    },
    "unit_b_interior_mm": {
        "width": _resolved["unit-b"].interior_width,
        "height": _resolved["unit-b"].interior_height,
        "depth": _resolved["unit-b"].interior_depth,
    },
}


_config_a = replace(
    _base_a,
    openings=[
        OpeningConfig(
            height_mm=_resolved["unit-a"].interior_height,
            opening_type="drawer",
            slide_key="buratino_hettich_quadro_v6_eb20",
        )
    ],
)
_config_b = replace(
    _base_b,
    openings=[
        OpeningConfig(
            height_mm=_resolved["unit-b"].interior_height,
            opening_type="drawer",
            slide_key="buratino_hettich_quadro_v6_eb20",
        )
    ],
)
project = CabinetProject(
    name="linked-row-fixture",
    cabinets=(
        ProjectCabinet(name="unit-a", config=_config_a),
        ProjectCabinet(
            name="unit-b",
            config=_config_b,
            overrides=frozenset({"top_thickness"}),
        ),
    ),
    shared=_shared,
)
drawer_configs = {
    "unit-a/column-0/opening-0": make_eb20_drawer_config(
        opening_width=_resolved["unit-a"].interior_width,
        opening_height=_resolved["unit-a"].interior_height,
        opening_depth=_resolved["unit-a"].interior_depth,
        side_thickness=variables["drawer_side_thickness_mm"],
        front_back_thickness=variables["drawer_inner_front_back_thickness_mm"],
        bottom_thickness=variables["drawer_bottom_thickness_mm"],
        bottom_dado_depth=variables["drawer_bottom_groove_depth_mm"],
        bottom_dado_inset=variables["drawer_bottom_recess_mm"],
        box_height=variables["drawer_box_height_mm"],
        vertical_gap=variables["drawer_box_bottom_clearance_mm"],
        front_gap=0,
        face_thickness=variables["drawer_face_thickness_mm"],
        material=variables["drawer_material"],
        joinery_style=DrawerJoineryStyle.BUTT,
        runner_length_mm=variables["runner_length_mm"],
    ),
    "unit-b/column-0/opening-0": make_eb20_drawer_config(
        opening_width=_resolved["unit-b"].interior_width,
        opening_height=_resolved["unit-b"].interior_height,
        opening_depth=_resolved["unit-b"].interior_depth,
        side_thickness=variables["drawer_side_thickness_mm"],
        front_back_thickness=variables["drawer_inner_front_back_thickness_mm"],
        bottom_thickness=variables["drawer_bottom_thickness_mm"],
        bottom_dado_depth=variables["drawer_bottom_groove_depth_mm"],
        bottom_dado_inset=variables["drawer_bottom_recess_mm"],
        box_height=variables["drawer_box_height_mm"],
        vertical_gap=variables["drawer_box_bottom_clearance_mm"],
        front_gap=0,
        face_thickness=variables["drawer_face_thickness_mm"],
        material=variables["drawer_material"],
        joinery_style=DrawerJoineryStyle.BUTT,
        runner_length_mm=variables["runner_length_mm"],
    ),
}

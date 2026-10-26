"""Synthetic native two-column cabinet for continuous-panel checks."""

from dataclasses import replace

from cabineteer.cabinet import CabinetConfig, ColumnConfig, OpeningConfig
from cabineteer.joinery import CarcassJoinery, DominoSpec, DrawerJoineryStyle
from cabineteer.project import CabinetProject, ProjectCabinet, SharedDesign

from buratino.drawers import make_eb20_drawer_config

variables = {
    "space_mm": {"width": 600, "height": 700, "depth_min": 480, "depth_max": 550},
    "observations": [
        "Synthetic fixture dimensions for shared-column tests; not a user survey."
    ],
    "assumptions": [
        "Shared divider is one physical panel. Drawer fastening is unverified."
    ],
    "width_mm": 600,
    "height_mm": 700,
    "depth_mm": 480,
    "side_thickness_mm": 18,
    "top_thickness_mm": 18,
    "bottom_thickness_mm": 18,
    "back_thickness_mm": 6,
    "drawer_side_thickness_mm": 16,
    "drawer_inner_front_back_thickness_mm": 18,
    "drawer_bottom_thickness_mm": 12,
    "drawer_box_height_mm": 180,
    "drawer_bottom_recess_mm": 12,
    "drawer_bottom_groove_depth_mm": 6,
    "drawer_box_bottom_clearance_mm": 30,
    "drawer_face_thickness_mm": 18,
    "runner_length_mm": 450,
    "face_to_carcass_gap_mm": 2,
    "cabinet_gap_mm": 0,
    "connections": [],
    "edge_gap_mm": 2,
    "front_gap_mm": 2,
    "carcass_material": "Synthetic melamine-faced board; unverified",
    "back_material": "Synthetic 6 mm board; unverified",
    "drawer_material": "Synthetic melamine-faced board; unverified",
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
    name="shared-column-fixture",
    cabinets=(ProjectCabinet(name="cabinet", config=_base_config),),
    shared=_shared,
)
_resolved = dict(_calculation_project.resolved())["cabinet"]
calculated = {
    "interior_width_mm": _resolved.interior_width,
    "interior_height_mm": _resolved.interior_height,
    "interior_depth_mm": _resolved.interior_depth,
    "column_width_mm": (_resolved.interior_width - _resolved.side_thickness) / 2,
    "inner_face_overlay_mm": (_resolved.side_thickness - variables["front_gap_mm"]) / 2,
}


# The native column layout owns the shared divider and continuous panels.
_openings = (
    OpeningConfig(
        height_mm=_resolved.interior_height,
        opening_type="drawer",
        slide_key="buratino_hettich_quadro_v6_eb20",
    ),
)
_columns = [
    ColumnConfig(width_mm=calculated["column_width_mm"], openings=_openings),
    ColumnConfig(width_mm=calculated["column_width_mm"], openings=_openings),
]
_config = replace(_base_config, columns=_columns)
project = CabinetProject(
    name="shared-column-fixture",
    cabinets=(ProjectCabinet(name="cabinet", config=_config),),
    shared=_shared,
)
drawer_configs = {
    f"cabinet/column-{index}/opening-0": make_eb20_drawer_config(
        opening_width=calculated["column_width_mm"],
        opening_height=_resolved.interior_height,
        opening_depth=_resolved.interior_depth,
        side_thickness=variables["drawer_side_thickness_mm"],
        front_back_thickness=variables["drawer_inner_front_back_thickness_mm"],
        bottom_thickness=variables["drawer_bottom_thickness_mm"],
        bottom_dado_depth=variables["drawer_bottom_groove_depth_mm"],
        bottom_dado_inset=variables["drawer_bottom_recess_mm"],
        box_height=variables["drawer_box_height_mm"],
        vertical_gap=variables["drawer_box_bottom_clearance_mm"],
        front_gap=0,
        face_thickness=variables["drawer_face_thickness_mm"],
        face_overlay_sides=calculated["inner_face_overlay_mm"],
        face_overlay_top=16,
        face_overlay_bottom=16,
        material=variables["drawer_material"],
        joinery_style=DrawerJoineryStyle.BUTT,
        runner_length_mm=variables["runner_length_mm"],
    )
    for index in range(2)
}

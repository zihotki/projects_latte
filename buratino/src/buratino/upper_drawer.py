"""Draft EB20 drawer for the first upper section."""

import math
from types import SimpleNamespace

from .drawers import drawer_shapes, eb20_profile_for_key, make_eb20_drawer_config

DRAWER_ID = "upper.left.column-0.opening-0"


def make_upper_drawer(spec, face):
    """Return native drawer records and geometry for the left upper opening."""
    width = spec["cabinet_width_mm"]
    thickness = spec["thickness_mm"]
    left = spec["x"] + thickness
    right = spec["x"] + width / 2 - thickness / 2
    opening_width = right - left
    slope = (spec["right_height_mm"] - spec["left_height_mm"]) / (
        1.5 * width - thickness / 2
    )
    underside = (
        spec["z"]
        + spec["left_height_mm"]
        + slope * (left - spec["x"])
        - thickness * math.hypot(1, slope)
    )
    bottom = spec["z"] + thickness
    opening_height = underside - bottom
    cfg = make_eb20_drawer_config(
        opening_width=opening_width,
        opening_height=opening_height,
        opening_depth=spec["depth_mm"] - spec["back_thickness_mm"],
        side_thickness=spec["drawer_side_thickness_mm"],
        front_back_thickness=spec["drawer_front_back_thickness_mm"],
        bottom_thickness=spec["drawer_bottom_thickness_mm"],
        bottom_dado_inset=spec["drawer_bottom_recess_mm"],
        rear_corner_clearance_width_mm=spec["drawer_rear_corner_clearance_width_mm"],
        box_height=spec.get("drawer_box_height_mm", 140),
        vertical_gap=spec.get("drawer_bottom_clearance_mm", 20),
        face_thickness=face["finished_mm"]["thickness"],
        material=spec.get("drawer_material", spec["material"]),
        runner_length_mm=spec["runner_length_mm"],
    )
    shapes, offsets = drawer_shapes(
        cfg, rear_corner_clearance_width_mm=cfg.buratino_rear_corner_clearance_width_mm
    )
    position = {
        "x": left + cfg.side_gap,
        "y": spec["y"] + cfg.front_gap,
        "z": bottom + cfg.buratino_box_bottom_clearance_mm,
    }
    dimensions = {
        "side_left": (cfg.side_panel_length, cfg.box_height, cfg.side_thickness),
        "side_right": (cfg.side_panel_length, cfg.box_height, cfg.side_thickness),
        "inner_front": (
            cfg.front_back_panel_length,
            cfg.box_height,
            cfg.front_back_thickness,
        ),
        "back": (cfg.front_back_panel_length, cfg.box_height, cfg.front_back_thickness),
        "bottom": (
            cfg.bottom_panel_width,
            cfg.bottom_panel_depth,
            cfg.bottom_thickness,
        ),
    }
    prefix = "upper_left_drawer_col1_opening1"
    parts = []
    for component, (length, panel_width, stock) in dimensions.items():
        role = f"{prefix}_{component}"
        parts.append(
            {
                "id": f"{DRAWER_ID}.{component}",
                "role": role,
                "scene_name": role,
                "upper_id": "left",
                "instance_id": DRAWER_ID,
                "component": component,
                "quantity": 1,
                "finished_mm": {
                    "length": length,
                    "width": panel_width,
                    "thickness": stock,
                },
                "material": cfg.buratino_material,
                "edge_treatment": "unconfirmed",
                "grain_direction": "length",
                "grain_status": "assumed",
                "grain_axis_local": "y" if component.startswith("side") else "x",
                "surface_normal_axis_local": "x"
                if component.startswith("side")
                else "z"
                if component == "bottom"
                else "y",
            }
        )
    face_size = face["size_mm"]
    drawer = {
        "instance_id": DRAWER_ID,
        "slide_key": cfg.slide_key,
        "hardware_profile": eb20_profile_for_key(cfg.slide_key),
        "drawer_index": 1,
        "column_index": 0,
        "opening_index": 0,
        "cabinet_id": "upper-left",
        "upper_id": "left",
        "part_ids": [p["id"] for p in parts] + [face["id"]],
        "closed_position_mm": position,
        "face_position_mm": face["position_mm"],
        "face_mm": {
            "width": face_size["x"],
            "height": face_size["z"],
            "thickness": face_size["y"],
        },
        "box_mm": {
            "width": cfg.box_width,
            "height": cfg.box_height,
            "depth": cfg.box_depth,
        },
    }
    instance = {
        "cabinet_id": "upper-left",
        "drawer_id": DRAWER_ID,
        "upper_id": "left",
        "config": cfg,
        "shapes": shapes,
        "offsets": offsets,
        "box_position": position,
        "role_prefix": prefix,
        "face_panel": SimpleNamespace(thickness=face_size["y"]),
    }
    return parts, drawer, instance

"""Draft overlay fronts for the four upper sections.

Profiles use assembly x/z coordinates and are extruded towards the back.
Hinge selection and mounting are not specified by this draft.
"""

import math


def make_upper_front_parts(spec):
    """Return a drawer front and three right-hinged door records.

    The sloped edge is offset normal to the roof; vertical seams and the
    remaining outside edges have the specified nominal clearance.
    """
    if spec is None:
        return []
    if not isinstance(spec, dict):
        raise ValueError("upper must be a mapping")

    def number(key, default=None, *, positive=False):
        value = spec.get(key, default)
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or value < 0
            or (positive and value == 0)
        ):
            requirement = "positive" if positive else "non-negative"
            raise ValueError(f"upper.{key} must be a finite {requirement} number")
        return value

    width = number("cabinet_width_mm", positive=True)
    low = number("left_height_mm", positive=True)
    high = number("right_height_mm", positive=True)
    x0, y0, z0 = (number(key) for key in ("x", "y", "z"))
    thickness = number("front_thickness_mm", spec.get("thickness_mm"), positive=True)
    carcass_thickness = number("thickness_mm", positive=True)
    gap = number("front_gap_mm", 2, positive=True)
    material = spec.get("front_material", spec.get("material"))
    if not isinstance(material, str) or not material:
        raise ValueError("upper front material must be described")
    if high < low:
        raise ValueError("upper heights must form a rising profile")
    section_width = width / 2
    if section_width <= 2 * gap:
        raise ValueError("upper front gaps leave no usable section width")

    slope = (high - low) / (3 * section_width - carcass_thickness / 2)
    slope_drop = gap * math.hypot(1, slope)
    slope_end = x0 + 3 * section_width - carcass_thickness / 2
    # Continue the slope to the seam and align the adjacent flat door there.
    flat_z = z0 + low + slope * (3 * section_width) - slope_drop
    bottom = z0 - number("front_bottom_projection_mm", 10)

    def roof(x):
        return min(z0 + low + slope * (x - x0) - slope_drop, flat_z)

    seams = [
        x0,
        x0 + section_width,
        x0 + width,
        slope_end + carcass_thickness / 2,
        x0 + 2 * width,
    ]
    parts = []
    for index in range(4):
        left = seams[index] + (gap if index == 0 else gap / 2)
        right = seams[index + 1] - (gap if index == 3 else gap / 2)
        if right <= left:
            raise ValueError("upper front gaps leave no usable section width")
        if roof(left) <= z0 + gap or roof(right) <= z0 + gap:
            raise ValueError("upper front gaps leave no usable section height")
        points = [(left, bottom), (right, bottom), (right, roof(right))]
        points.append((left, roof(left)))
        min_z = bottom
        max_z = max(z for _, z in points)
        upper_id = "left" if index < 2 else "right"
        drawer = index == 0
        ident = (
            "upper.left.column-0.opening-0.face"
            if drawer
            else f"upper.{upper_id}.section-{index % 2 + 1}.door"
        )
        role = ident.replace(".", "_").replace("-", "_")
        blank = {"length": max_z - min_z, "width": right - left, "thickness": thickness}
        record = {
            "id": ident,
            "role": role,
            "scene_name": role,
            "upper_id": upper_id,
            "component": "face" if drawer else "door",
            "quantity": 1,
            "finished_mm": blank.copy(),
            "blank_mm": blank,
            "material": material,
            "edge_treatment": "unconfirmed",
            "grain_direction": "length",
            "grain_status": "assumed",
            "grain_axis_local": "z",
            "surface_normal_axis_local": "y",
            "position_mm": {"x": left, "y": y0 - gap - thickness, "z": min_z},
            "size_mm": {"x": right - left, "y": thickness, "z": max_z - min_z},
            "profile": {
                "plane": "xz",
                "points_mm": [[x - left, z - min_z] for x, z in points],
                "extrusion_axis": "y",
                "extrusion_mm": thickness,
            },
        }
        if drawer:
            record["instance_id"] = "upper.left.column-0.opening-0"
        else:
            record.update(hinge_side="right", hinge_status="unverified")
        parts.append(record)
    return parts

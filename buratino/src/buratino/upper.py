"""Draft panel geometry for the upper assembly.

Coordinates are assembly millimetres: x left to right, y front to back,
 and z bottom to top. The top profile describes the outside surface.
"""

import math


def make_upper_parts(spec):
    """Return physical panels and cabinet envelopes for the authored profile."""
    if not spec:
        return [], []
    numeric_keys = (
        "cabinet_width_mm",
        "depth_mm",
        "thickness_mm",
        "back_thickness_mm",
        "left_height_mm",
        "right_height_mm",
        "x",
        "y",
        "z",
    )
    for key in numeric_keys:
        value = spec[key]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"upper.{key} must be a finite non-negative number")
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"upper.{key} must be a finite non-negative number")
    levels = spec["shelf_levels_mm"]
    if (
        not isinstance(levels, list)
        or any(
            isinstance(level, bool)
            or not isinstance(level, int | float)
            or not math.isfinite(level)
            for level in levels
        )
        or any(level <= 0 for level in levels)
        or any(a >= b for a, b in zip(levels, levels[1:], strict=False))
    ):
        raise ValueError(
            "upper.shelf_levels_mm must contain increasing positive numbers"
        )
    if not all(
        isinstance(spec[key], str) and spec[key]
        for key in ("material", "back_material")
    ):
        raise ValueError("Upper panel materials must be described")
    width = spec["cabinet_width_mm"]
    total_depth = spec["depth_mm"]
    back_thickness = spec["back_thickness_mm"]
    depth = total_depth - back_thickness
    thickness = spec["thickness_mm"]
    if thickness <= 0 or width <= 4 * thickness or depth <= 0 or back_thickness <= 0:
        raise ValueError("Upper stock must leave usable width and depth")
    if any(b - a < thickness for a, b in zip(levels, levels[1:], strict=False)):
        raise ValueError("Upper shelf levels must leave room for shelf thickness")
    x0, y0, z0 = (spec[key] for key in ("x", "y", "z"))
    low, high = spec["left_height_mm"], spec["right_height_mm"]
    if high < low or low <= thickness:
        raise ValueError("Upper heights must form a rising profile above the bottom")
    slope_end = x0 + width * 1.5 - thickness / 2
    end = x0 + width * 2
    joint = slope_end

    def top(x):
        return z0 + low + (high - low) * min((x - x0) / (slope_end - x0), 1)

    slope = (high - low) / (slope_end - x0)
    slope_drop = thickness * math.sqrt(1 + slope * slope)

    if low <= thickness + slope_drop:
        raise ValueError("Upper height must accommodate the top and bottom")

    def underside(x):
        if x >= joint:
            return z0 + high - thickness
        return top(x) - slope_drop

    material = spec["material"]
    parts = []

    def panel(part_id, component, points, y, panel_depth, blank, normal, stock=None):
        # The polygon is an x/z section extruded towards the back (+y).
        min_x = min(p[0] for p in points)
        min_z = min(p[1] for p in points)
        max_x = max(p[0] for p in points)
        max_z = max(p[1] for p in points)
        role = part_id.replace(".", "_").replace("-", "_")
        blank_mm = dict(zip(("length", "width", "thickness"), blank, strict=True))
        parts.append(
            {
                "id": part_id,
                "role": role,
                "scene_name": role,
                "upper_id": part_id.split(".")[1],
                "component": component,
                "quantity": 1,
                "finished_mm": blank_mm.copy(),
                "blank_mm": blank_mm,
                "material": stock or material,
                "edge_treatment": "unconfirmed",
                "grain_direction": "length",
                "grain_status": "assumed",
                "grain_axis_local": "z" if normal in {"x", "y"} else "x",
                "surface_normal_axis_local": normal,
                "position_mm": {"x": min_x, "y": y, "z": min_z},
                "size_mm": {"x": max_x - min_x, "y": panel_depth, "z": max_z - min_z},
                "profile": {
                    "plane": "xz",
                    "points_mm": [[x - min_x, z - min_z] for x, z in points],
                    "extrusion_axis": "y",
                    "extrusion_mm": panel_depth,
                },
            }
        )

    def vertical(name, component, left, right):
        points = [(left, z0), (right, z0), (right, underside(right))]
        points.append((left, underside(left)))
        panel(
            name,
            component,
            points,
            y0,
            depth,
            (max(underside(left), underside(right)) - z0, depth, thickness),
            "x",
        )

    for index, start in enumerate((x0, x0 + width)):
        cabinet = ("left", "right")[index]
        for label, a, b in (
            ("left_side", start, start + thickness),
            (
                "divider",
                start + width / 2 - thickness / 2,
                start + width / 2 + thickness / 2,
            ),
            ("right_side", start + width - thickness, start + width),
        ):
            vertical(f"upper.{cabinet}.{label}", label, a, b)
        back_points = [
            (start, z0),
            (start + width, z0),
            (start + width, top(start + width)),
        ]
        if start < slope_end < start + width:
            back_points.append((slope_end, top(slope_end)))
        back_points.append((start, top(start)))
        panel(
            f"upper.{cabinet}.back",
            "back",
            back_points,
            y0 + depth,
            back_thickness,
            (top(start + width) - z0, width, back_thickness),
            "y",
            spec["back_material"],
        )
        # Bottom is split at the divider so it cannot intersect the vertical panels.
        divider_left = start + width / 2 - thickness / 2
        divider_right = divider_left + thickness
        edges = [
            (start + thickness, divider_left),
            (divider_right, start + width - thickness),
        ]
        for section, (left, right) in enumerate(edges):
            panel(
                f"upper.{cabinet}.bottom_{section + 1}",
                "bottom",
                [
                    (left, z0),
                    (right, z0),
                    (right, z0 + thickness),
                    (left, z0 + thickness),
                ],
                y0,
                depth,
                (right - left, depth, thickness),
                "z",
            )
            # The first section is reserved for drawers. Shelf levels are
            # measured from the upper base and shared by the other sections.
            if index == 0 and section == 0:
                continue
            for shelf, level in enumerate(levels, start=1):
                height = z0 + level
                if height < z0 + thickness or height + thickness > underside(left):
                    continue
                panel(
                    f"upper.{cabinet}.section_{section + 1}_shelf_{shelf}",
                    "shelf",
                    [
                        (left, height),
                        (right, height),
                        (right, height + thickness),
                        (left, height + thickness),
                    ],
                    y0,
                    depth,
                    (right - left, depth, thickness),
                    "z",
                )

    # The sloped top butts against the divider and the flat top above it.
    # Stock thickness is measured normal to the sloping face.
    slope_length = math.hypot(joint - x0, slope * (joint - x0))
    panel(
        "upper.shared.top_sloped",
        "top",
        [
            (x0, top(x0) - slope_drop),
            (joint, top(joint) - slope_drop),
            (joint, top(joint)),
            (x0, top(x0)),
        ],
        y0,
        depth,
        (
            slope_length + slope_drop * abs(slope) / math.sqrt(1 + slope * slope),
            depth,
            thickness,
        ),
        "z",
    )
    panel(
        "upper.shared.top_level",
        "top",
        [
            (joint, z0 + high - thickness),
            (end, z0 + high - thickness),
            (end, z0 + high),
            (joint, z0 + high),
        ],
        y0,
        depth,
        (end - joint, depth, thickness),
        "z",
    )
    cabinets = [
        {
            "id": f"upper-{name}",
            "placement_mm": {"x": start, "y": y0, "z": z0},
            "bounds_mm": {
                "min": {"x": start, "y": y0, "z": z0},
                "max": {
                    "x": start + width,
                    "y": y0 + total_depth,
                    "z": top(start + width),
                },
            },
        }
        for name, start in (("left", x0), ("right", x0 + width))
    ]
    return parts, cabinets


def add_upper_geometry(assembly, records):
    """Add the exact x/z profile of each upper panel to the CAD assembly."""
    import cadquery as cq
    from cabineteer.cabinet import PartInfo

    geometry = []
    for record in records:
        if "upper_id" not in record:
            continue
        pos = record["position_mm"]
        profile = record["profile"]
        vertices = [cq.Vector(x, 0, z) for x, z in profile["points_mm"]]
        wire = cq.Wire.makePolygon([*vertices, vertices[0]])
        shape = cq.Workplane("XY").newObject(
            [cq.Solid.extrudeLinear(wire, [], cq.Vector(0, profile["extrusion_mm"], 0))]
        )
        assembly.add(
            shape,
            name=record["role"],
            loc=cq.Location((pos["x"], pos["y"], pos["z"])),
            color=cq.Color(0.75, 0.73, 0.68, 1),
        )
        geometry.append(
            PartInfo(
                name=record["role"],
                shape=shape,
                material_thickness=record["blank_mm"]["thickness"],
                grain_direction="length",
            )
        )
    return geometry

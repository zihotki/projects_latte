"""Groove drawing anchors derived from recorded stock coordinates."""

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class GrooveDimension:
    operation_id: str
    width_mm: float
    inset_mm: float
    depth_mm: float
    thickness_mm: float
    transverse_mm: float
    width_points: tuple
    inset_points: tuple
    profile_points: tuple


def groove_dimensions(part: dict) -> list[GrooveDimension]:
    """Map Space XYZ or native L/W/T groove records into world coordinates."""
    native = part.get("local_frame")
    if native:
        origin = native["origin_mm"]
        axes = [native[key] for key in ("length_axis", "width_axis", "thickness_axis")]
    else:
        transform = part.get("transform", {})
        origin = transform.get("translation", (0, 0, 0))
        axes = transform.get("axes", ((1, 0, 0), (0, 1, 0), (0, 0, 1)))

    def world(point):
        return tuple(
            origin[i] + sum(point[j] * axes[j][i] for j in range(3)) for i in range(3)
        )

    result = []
    for cut in part.get("operations", []):
        bottom = cut.get("role") == "bottom_groove"
        explicit = cut.get("input_type") == "groove"
        if not bottom and not explicit:
            continue
        if native:
            polygon = cut["local_profile_mm"]
            low = [min(p[i] for p in polygon) for i in range(3)]
            high = [max(p[i] for p in polygon) for i in range(3)]
            normal = next(
                i for i, value in enumerate(cut["inward_axis_local"]) if value
            )
            across, along = 1, 0  # Native drawer recipe: L along wall, W above base.
            size = [part["stock_mm"][key] for key in ("length", "width", "thickness")]
            depth = cut["depth_mm"]
            edge_positive = False
        else:
            size = part["profile"]["size"]
            normal = "xyz".index(cut["face"][0])
            uv = [i for i in range(3) if i != normal]
            low = [0.0, 0.0, 0.0]
            low[normal] = size[normal] if cut["face"][1] == "+" else 0.0
            low[uv[0]], low[uv[1]] = cut["u"], cut["v"]
            high = low.copy()
            high[uv[0]] += cut["size_u"]
            high[uv[1]] += cut["size_v"]
            if explicit:
                across = "xyz".index(cut["groove"]["edge"][0])
                edge_positive = cut["groove"]["edge"][1] == "+"
            else:
                across, edge_positive = uv[1], False
            along = next(i for i in uv if i != across)
            polygon = []
            for a, b in ((0, 0), (1, 0), (1, 1), (0, 1)):
                point = low.copy()
                point[along] = (low, high)[a][along]
                point[across] = (low, high)[b][across]
                polygon.append(point)
            depth = cut["depth"]
        width = high[across] - low[across]
        inset = size[across] - high[across] if edge_positive else low[across]
        # Separate stations keep the width and edge-inset dimension lines apart.
        width_a = low.copy()
        width_a[along] += (high[along] - low[along]) * 0.68
        width_b = width_a.copy()
        width_b[across] = high[across]
        inset_a = low.copy()
        inset_a[along] += (high[along] - low[along]) * 0.42
        inset_a[across] = size[across] if edge_positive else 0.0
        inset_b = inset_a.copy()
        inset_b[across] = high[across] if edge_positive else low[across]
        result.append(
            GrooveDimension(
                cut["id"],
                width,
                inset,
                depth,
                size[normal],
                size[across],
                tuple(map(world, (width_a, width_b))),
                tuple(map(world, (inset_a, inset_b))),
                tuple(map(world, polygon)),
            )
        )
    return result


def _path(points):
    return "M" + " L".join(f"{x:.3f} {y:.3f}" for x, y in points)


def groove_callouts(features, project, start_y=260):
    """Attach dimensions to the CAD feature, with a linked depth section below."""
    output = []
    for index, feature in enumerate(features):
        label = f"G{index + 1}"
        row = start_y + index * 110
        output.append(
            '<g class="groove-dimensions" '
            f'data-operation="{escape(feature.operation_id, quote=True)}" '
            'stroke="#17566d" stroke-width="0.8" fill="none">'
        )
        dimensions = []
        for field, points, value in (
            ("width", feature.width_points, feature.width_mm),
            ("inset", feature.inset_points, feature.inset_mm),
        ):
            a, b = map(project, points)
            mid = tuple((p + q) / 2 for p, q in zip(a, b, strict=True))
            dimensions.append((mid, field, a, b, value))
        # Follow the screen order so mirrored/rotated panels do not get crossed
        # leaders. Keep each value attached to its own measurement endpoints.
        for (mid, field, a, b, value), (gutter, x) in zip(
            sorted(dimensions), ((25, 70), (335, 250)), strict=True
        ):
            leader = (mid, (gutter, 195), (gutter, row - 10), (x, row - 10))
            output.append(
                f'<path class="groove-{field}" d="{_path((a, b))}"/>'
                f'<circle cx="{a[0]:.3f}" cy="{a[1]:.3f}" r="1.5"/>'
                f'<circle cx="{b[0]:.3f}" cy="{b[1]:.3f}" r="1.5"/>'
                f'<path class="dimension-leader" d="{_path(leader)}"/>'
                f'<text x="{x}" y="{row}" text-anchor="middle" stroke="none" '
                f'fill="#17566d" font-size="10">{label} {field}: {value:g} mm</text>'
            )
        # This section is a stock/record detail, not a second CAD solid. It shows
        # the opening and its floor in true proportions, cropped after the groove.
        extent = min(feature.transverse_mm, feature.inset_mm + feature.width_mm + 10)
        scale = min(150 / extent, 35 / feature.thickness_mm)
        left, top = 75, row + 22
        near = left + feature.inset_mm * scale
        far = near + feature.width_mm * scale
        right = left + extent * scale
        floor = top + feature.depth_mm * scale
        bottom = top + feature.thickness_mm * scale
        break_edge = (
            (
                (right - 3, top + (bottom - top) * 0.3),
                (right + 3, top + (bottom - top) * 0.5),
                (right - 3, top + (bottom - top) * 0.7),
            )
            if extent < feature.transverse_mm
            else ()
        )
        outline = (
            (left, bottom),
            (left, top),
            (near, top),
            (near, floor),
            (far, floor),
            (far, top),
            (right, top),
            *break_edge,
            (right, bottom),
            (left, bottom),
        )
        dim_x = right + 12
        output.append(
            f'<text x="180" y="{row + 14}" text-anchor="middle" stroke="none" '
            f'fill="#17566d" font-size="9">{label} section detail at groove</text>'
            f'<path class="groove-section" d="{_path(outline)}" fill="#edf3f5"/>'
            f'<path d="{_path(((far, top), (dim_x + 3, top)))} '
            f"{_path(((far, floor), (dim_x + 3, floor)))} "
            f'{_path(((dim_x, top), (dim_x, floor)))}"/>'
            f'<circle cx="{dim_x:.3f}" cy="{top:.3f}" r="1.3"/>'
            f'<circle cx="{dim_x:.3f}" cy="{floor:.3f}" r="1.3"/>'
            f'<text class="groove-depth" x="{dim_x + 7:.3f}" '
            f'y="{(top + floor) / 2 + 3:.3f}" '
            'stroke="none" fill="#17566d" font-size="10">'
            f"{feature.depth_mm:g} mm deep</text>"
            "</g>"
        )
    return "".join(output)

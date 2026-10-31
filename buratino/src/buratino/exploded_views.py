"""Exploded drawings from copies of the placed, machined CAD panels."""

import json
from collections import defaultdict
from html import escape

from .panel_views import _projected_geometry, _svg_projector

_DIRECTION = (1, -1.5, 1.1)
_X_DIRECTION = (1.5, 1, 0)
_FACADE_KINDS = {
    "applied_faceboard",
    "applied_drawer_front",
    "door",
    "drawer_face",
    "drawer_front",
}
_SHELL_COMPONENTS = {
    "back",
    "bottom",
    "cap",
    "carcass",
    "left_side",
    "roof",
    "roof_cap",
    "right_side",
    "side",
    "side_left",
    "side_right",
    "top",
}


def _is_facade(part):
    return any(part.get(key) in _FACADE_KINDS for key in ("component", "kind")) or (
        part.get("component") == "face" and bool(part.get("instance_id"))
    )


def _items(parts):
    groups = defaultdict(list)
    for part in parts:
        if _is_facade(part):
            continue
        drawer = part.get("instance_id") or part.get("motion_group")
        cabinet = part.get("cabinet_id") or part.get("owner") or "cabinet"
        groups[(cabinet, drawer)].append(part)
    return groups


def _bounds(shapes):
    from cadquery import Compound

    return Compound.makeCompound(shapes).BoundingBox()


def _layout(members, assembly, part_codes):
    shapes = [assembly.objects[part["role"]].toCompound() for part in members]
    bounds = _bounds(shapes)
    origin = (bounds.xmin, bounds.ymin, bounds.zmin)
    rows = []
    for part, shape in zip(members, shapes, strict=True):
        box = shape.BoundingBox()
        code = part_codes[part["id"]]
        signature = (
            code,
            *(
                round(v - origin[i % 3], 5)
                for i, v in enumerate(
                    (box.xmin, box.ymin, box.zmin, box.xmax, box.ymax, box.zmax)
                )
            ),
        )
        rows.append((signature, part, shape))
    return sorted(rows, key=lambda row: row[0])


def _axis_vector(value):
    if isinstance(value, str) and value in "xyz" and len(value) == 1:
        return tuple(float(value == axis) for axis in "xyz")
    if isinstance(value, list | tuple) and len(value) == 3:
        vector = tuple(float(v) for v in value)
        if sum(v * v for v in vector) > 1e-12:
            length = sum(v * v for v in vector) ** 0.5
            return tuple(v / length for v in vector)
    return None


def _world_normal(part, shape):
    frame = part.get("local_frame")
    if isinstance(frame, dict):
        normal = _axis_vector(frame.get("thickness_axis"))
        if normal:
            return normal
    stock = part.get("stock")
    transform = part.get("transform")
    if isinstance(stock, dict) and isinstance(transform, dict):
        thickness_axis = stock.get("thickness_axis")
        axes = transform.get("axes")
        if (
            type(thickness_axis) is int
            and 0 <= thickness_axis < 3
            and isinstance(axes, list | tuple)
            and len(axes) == 3
        ):
            normal = _axis_vector(axes[thickness_axis])
            if normal:
                return normal
    normal = _axis_vector(part.get("surface_normal_axis_local"))
    if normal:
        return normal
    # Use the broad planar face normal for records without a usable stock frame.
    faces = sorted(shape.Faces(), key=lambda face: face.Area(), reverse=True)
    if faces:
        return _axis_vector(faces[0].normalAt().toTuple())
    return (0.0, 0.0, 1.0)


def _is_shell_component(part):
    component = part.get("component") or part.get("kind")
    return component in _SHELL_COMPONENTS


def _explode(rows, *, drawer=False):
    bounds = _bounds([row[2] for row in rows])
    center = bounds.center.toTuple()
    gap = max(bounds.xlen, bounds.ylen, bounds.zlen) * 0.08
    panels = []
    for _, part, shape in rows:
        if not drawer and not _is_shell_component(part):
            panels.append((part, shape))
            continue
        normal = _world_normal(part, shape)
        delta = tuple(
            a - b for a, b in zip(shape.Center().toTuple(), center, strict=True)
        )
        direction = (
            1 if sum(a * b for a, b in zip(delta, normal, strict=True)) >= 0 else -1
        )
        offset = tuple(direction * gap * value for value in normal)
        panels.append((part, shape.translate(offset)))
    return panels


def _front_facing(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) < -1e-8


def _drawing(rows, copies, *, drawer=False):
    from cadquery.occ_impl.exporters.svg import makeSVGedge

    panels = _explode(rows, drawer=drawer)
    projections = [
        _projected_geometry(shape, _DIRECTION, _X_DIRECTION) for _, shape in panels
    ]
    bounds = _bounds(projections)
    width = 440
    # The projected centers can put nearly every label on the same side.
    # Count those sides before sizing the viewport; positive scaling preserves them.
    project_unit = _svg_projector(_DIRECTION, bounds, 1, 0, 0, x_direction=_X_DIRECTION)
    right_count = sum(
        project_unit(shape.Center().toTuple())[0] >= bounds.xlen / 2
        for _, shape in panels
    )
    height = max(340, 32 + max(right_count, len(panels) - right_count) * 25)
    scale = min(292 / bounds.xlen, (height - 32) / bounds.ylen)
    left = (width - bounds.xlen * scale) / 2
    top = (height - bounds.ylen * scale) / 2
    project = _svg_projector(
        _DIRECTION, bounds, scale, left, top, x_direction=_X_DIRECTION
    )
    labels = [[], []]
    drawing = []
    # Draw far panels first; all cut edges remain available in the projection.
    order = sorted(
        range(len(panels)),
        key=lambda i: sum(
            a * b
            for a, b in zip(panels[i][1].Center().toTuple(), _DIRECTION, strict=True)
        ),
    )
    for index in order:
        part, shape = panels[index]
        projected = projections[index]
        vertices, triangles = shape.tessellate(1, 0.5)
        points = [project(vertex.toTuple()) for vertex in vertices]
        faces = " ".join(
            "M"
            + " L".join(f"{points[v][0]:.1f},{points[v][1]:.1f}" for v in tri)
            + " Z"
            for tri in triangles
            # Keep camera-facing triangles so opposite solid faces do not
            # cancel their fill winding in the combined SVG path.
            if _front_facing(*(points[v] for v in tri))
        )
        edges = " ".join(makeSVGedge(edge) for edge in projected.Edges())
        ident = escape(part["id"], quote=True)
        code = escape(rows[index][0][0])
        ids = escape(json.dumps([copy[index][1]["id"] for copy in copies]), quote=True)
        drawing.append(
            f'<g data-part-id="{ident}" data-part-ids="{ids}">'
            f'<path d="{faces}" fill="#e4edf4" stroke="none"/>'
            f'<path d="{edges}" transform="translate({left:g} {top:g}) '
            f"scale({scale:g} {-scale:g}) "
            f'translate({-bounds.xmin:g} {-bounds.ymax:g})" '
            f'fill="none" stroke="#33485a" stroke-width="{0.65 / scale:g}"/>'
            "</g>"
        )
        x, y = project(shape.Center().toTuple())
        labels[int(x >= width / 2)].append((y, x, code))
    for side, entries in enumerate(labels):
        entries.sort()
        for index, (anchor_y, anchor_x, code) in enumerate(entries):
            y = height / 2 + (index - (len(entries) - 1) / 2) * 25
            x = width - 12 if side else 12
            end = width - 59 if side else 59
            drawing.append(
                f'<path d="M{anchor_x:.1f},{anchor_y:.1f} L{end},{y:.1f}" '
                'stroke="#566b7b" stroke-width="0.8" fill="none"/>'
                f'<circle cx="{anchor_x:.1f}" cy="{anchor_y:.1f}" r="1.8" '
                'fill="#33485a"/>'
                f'<text x="{x}" y="{y:.1f}" dy=".35em" '
                f'text-anchor="{"end" if side else "start"}" '
                'font-family="sans-serif" font-size="14" fill="#182d3c" '
                'stroke="white" stroke-width="3" paint-order="stroke">'
                f"{code}</text>"
            )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Exploded panels with part codes" '
        'style="display:block;width:100%;height:auto;max-width:640px">'
        + "".join(drawing)
        + "</svg>"
    )


def exploded_views(assembly, parts: list[dict], part_codes: dict[str, str]) -> str:
    """Return item diagrams, with one label per panel and no CAD modifications.

    Equivalent items share a view only when codes and relative placed bounds
    match. Part codes already distinguish panel geometry and machining.
    """
    if assembly is None or not parts:
        return ""
    layouts = {}
    for (_, drawer), members in _items(parts).items():
        rows = _layout(members, assembly, part_codes)
        components = {row[1].get("component") or row[1].get("kind") for row in rows}
        kind = (
            "drawer"
            if drawer
            else "roof"
            if components and components <= {"cap", "roof", "roof_cap"}
            else "body"
        )
        key = (kind, tuple(row[0] for row in rows))
        layouts.setdefault(key, []).append(rows)
    figures = []
    for (kind, _), copies in layouts.items():
        title = {"drawer": "Drawer", "roof": "Cabinet roof", "body": "Cabinet body"}[
            kind
        ]
        if len(copies) > 1:
            title += f" ×{len(copies)}"
        ids = [row[1]["id"] for copy in copies for row in copy]
        figures.append(
            '<figure class="exploded-item" style="margin:1em 0;break-inside:avoid" '
            f'data-part-ids="{escape(json.dumps(ids), quote=True)}">'
            f"<figcaption>{title}</figcaption>"
            + _drawing(copies[0], copies, drawer=kind == "drawer")
            + "</figure>"
        )
    return "".join(figures)

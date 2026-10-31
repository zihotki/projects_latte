"""Exploded drawings from copies of the placed, machined CAD panels."""

import json
import math
from collections import defaultdict
from html import escape

from .grouping import machining_signature
from .panel_views import _svg_projector

_DIRECTION = (1, -1.5, 1.1)
_X_DIRECTION = (1.5, 1, 0)
_FACADE_KINDS = {
    "applied_faceboard",
    "applied_drawer_front",
    "door",
    "drawer_face",
    "drawer_front",
}
_MOVES = {
    "side_left": (-1, 0, 0),
    "side_right": (1, 0, 0),
    "bottom": (0, 0, -1),
    "top": (0, 0, 1),
    "back": (0, 1, 0),
    "front": (0, -1, 0),
    "divider": (0, 0, 0),
    "shelf": (0, 0, 0),
    "rail_left": (-1, 0, 0),
    "rail_right": (1, 0, 0),
    "rail_front": (0, -1, 0),
    "rail_back": (0, 1, 0),
}
_IDENTITY = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def _is_facade(part):
    return any(part.get(key) in _FACADE_KINDS for key in ("component", "kind")) or (
        part.get("component") == "face" and bool(part.get("instance_id"))
    )


def _report(part):
    if "report" in part:
        return part["report"]
    # Preserve the existing legacy adapter's explicit component vocabulary.
    member = part.get("component", part.get("kind"))
    member = {
        "left_side": "side_left",
        "right_side": "side_right",
        "roof": "top",
        "cap": "top",
        "roof_cap": "top",
        "inner_front": "front",
        "subfront": "front",
        "inner_back": "back",
        "adjustable_shelf": "shelf",
    }.get(member, member)
    drawer = part.get("instance_id") or part.get("motion_group")
    return dict(
        item_id=drawer or part.get("cabinet_id") or part.get("owner") or "cabinet",
        member=member,
        recipe="drawer" if drawer else "rectangular",
        axes=_IDENTITY,
    )


def _items(parts):
    groups = defaultdict(list)
    seen = set()
    for part in parts:
        if _is_facade(part):
            continue
        ident = part["id"]
        if ident in seen:
            raise ValueError(f"Exploded view: duplicate physical member {ident}")
        seen.add(ident)
        report = _report(part)
        if report.get("member") not in _MOVES or report.get("recipe") not in {
            "drawer",
            "rectangular",
            "profiled",
            "frame",
        }:
            raise ValueError(f"Exploded view: unknown report member {ident}: {report}")
        groups[report["item_id"]].append(part)
    return groups


def _bounds(shapes):
    from cadquery import Compound

    return Compound.makeCompound(shapes).BoundingBox()


def _placed_shape(assembly, name):
    """toCompound applies the node location; add each ancestor exactly once."""
    node = assembly.objects[name]
    shape = node.toCompound()
    parent = node.parent
    from cadquery import Location

    placement = Location()
    while parent is not None:
        placement = parent.loc * placement
        parent = parent.parent
    return shape.moved(placement)


def _layout(members, assembly, part_codes):
    missing = [
        p["id"]
        for p in members
        if p.get("role") not in assembly.objects or p["id"] not in part_codes
    ]
    if missing:
        raise ValueError(
            "Exploded view: missing shapes or codes: " + ", ".join(missing)
        )
    shapes = [_placed_shape(assembly, p["role"]) for p in members]
    empty = [
        p["id"] for p, shape in zip(members, shapes, strict=True) if not shape.Solids()
    ]
    if empty:
        raise ValueError(
            "Exploded view: members must contain solids: " + ", ".join(empty)
        )
    bounds = _bounds(shapes)
    origin = (bounds.xmin, bounds.ymin, bounds.zmin)
    rows = []
    for part, shape in zip(members, shapes, strict=True):
        box = shape.BoundingBox()
        report = _report(part)
        signature = (
            part_codes[part["id"]],
            report["member"],
            report["recipe"],
            tuple(tuple(axis) for axis in report["axes"]),
            *(
                round(v - origin[i % 3], 5)
                for i, v in enumerate(
                    (box.xmin, box.ymin, box.zmin, box.xmax, box.ymax, box.zmax)
                )
            ),
            round(shape.Volume(), 5),
            round(shape.Area(), 5),
            tuple(
                sorted(
                    (
                        edge.geomType(),
                        round(edge.Length(), 5),
                        tuple(
                            sorted(
                                tuple(
                                    round(v - origin[i], 5)
                                    for i, v in enumerate(edge.positionAt(t).toTuple())
                                )
                                for t in (0, 0.25, 0.5, 0.75, 1)
                            )
                        ),
                    )
                    for edge in shape.Edges()
                )
            ),
            machining_signature(part),
        )
        rows.append((signature, part, shape))
    return sorted(rows, key=lambda row: row[0])


def _item_axes(rows):
    axes = tuple(tuple(float(v) for v in axis) for axis in _report(rows[0][1])["axes"])
    if (
        len(axes) != 3
        or any(
            len(axis) != 3 or any(not math.isfinite(v) for v in axis) for axis in axes
        )
        or any(
            abs(sum(a * b for a, b in zip(axes[i], axes[j], strict=True)) - (i == j))
            > 1e-6
            for i in range(3)
            for j in range(3)
        )
    ):
        raise ValueError(
            "Exploded view: invalid item axes: "
            + ", ".join(row[1]["id"] for row in rows)
        )
    if any(
        tuple(tuple(axis) for axis in _report(row[1])["axes"]) != axes for row in rows
    ):
        raise ValueError(
            "Exploded view: inconsistent item axes: "
            + ", ".join(row[1]["id"] for row in rows)
        )
    return axes


def _world(vector, axes):
    return tuple(sum(vector[j] * axes[j][i] for j in range(3)) for i in range(3))


def _explode(rows):
    """Resolve fixed item-relative recipes to flat world translations."""
    bounds = _bounds([row[2] for row in rows])
    axes = _item_axes(rows)
    gap = max(bounds.xlen, bounds.ylen, bounds.zlen) * 0.16
    panels = []
    for _, part, shape in rows:
        report = _report(part)
        member, recipe = report["member"], report["recipe"]
        move = _MOVES[member]
        if recipe == "frame" and not member.startswith("rail_"):
            raise ValueError(f"Exploded view: invalid frame member {part['id']}")
        if recipe == "profiled" and member == "top":
            # Roof segments move together, preserving the joint and relative pose.
            move = (0, 0, 1.35)
        if recipe == "drawer":
            move = tuple(value * 0.65 for value in move)
        offset = _world(tuple(value * gap for value in move), axes)
        panels.append((part, shape.translate(offset)))
    return panels


def _visible_projections(shapes, direction=_DIRECTION, x_direction=_X_DIRECTION):
    """Remove hidden lines once for the complete scene, retaining part identity."""
    from cadquery import Compound, Shape
    from cadquery.occ_impl.shapes import TOLERANCE
    from OCP.BRepLib import BRepLib
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape

    projection = HLRBRep_Algo()
    # Add each shape separately: selecting children of one added compound does
    # not return their edges in HLRBRep_HLRToShape.
    for shape in shapes:
        projection.Add(shape.wrapped)
    axes = gp_Ax2(gp_Pnt(), gp_Dir(*direction), gp_Dir(*x_direction))
    projection.Projector(HLRAlgo_Projector(axes))
    projection.Update()
    projection.Hide()
    edges = HLRBRep_HLRToShape(projection)
    results = []
    for shape in shapes:
        visible = []
        for extract in (
            edges.VCompound,
            edges.Rg1LineVCompound,
            edges.OutLineVCompound,
        ):
            compound = extract(shape.wrapped)
            if not compound.IsNull():
                BRepLib.BuildCurves3d_s(compound, TOLERANCE)
                visible.append(Shape(compound))
        results.append(Compound.makeCompound(visible))
    return results


def _area(points):
    """Area of the 2D convex hull; a visible line has no readable footprint."""
    points = sorted(set(points))

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    hull = []
    for sequence in (points, list(reversed(points))):
        side = []
        for point in sequence:
            while len(side) > 1 and cross(side[-2], side[-1], point) <= 0:
                side.pop()
            side.append(point)
        hull.extend(side[:-1])
    return (
        abs(
            sum(
                a[0] * b[1] - a[1] * b[0]
                for a, b in zip(hull, hull[1:] + hull[:1], strict=True)
            )
        )
        / 2
    )


def _visible_patch_area(projected):
    """Use one connected visible outline, without bridging hidden gaps."""
    pending = []
    for edge in projected.Edges():
        points = [edge.positionAt(t) for t in (0, 0.5, 1)]
        ends = {tuple(round(v, 6) for v in (p.x, p.y)) for p in (points[0], points[-1])}
        pending.append((ends, [(p.x, p.y) for p in points]))
    areas = [0.0]
    while pending:
        ends, points = pending.pop()
        growing = True
        while growing:
            growing = False
            for index in range(len(pending) - 1, -1, -1):
                other_ends, other_points = pending[index]
                if ends & other_ends:
                    ends.update(other_ends)
                    points.extend(other_points)
                    pending.pop(index)
                    growing = True
        areas.append(_area(points))
    return max(areas)


def _drawing(
    rows, copies, panels, subjects, *, direction=_DIRECTION, x_direction=_X_DIRECTION
):
    from cadquery.occ_impl.exporters.svg import makeSVGedge

    projections = _visible_projections(
        [shape for _, shape in panels], direction, x_direction
    )
    bounds = _bounds(projections)
    width = 440
    # Visible edge anchors can put nearly every label on the same side.
    # Count those sides before sizing the viewport; positive scaling preserves them.
    project_unit = _svg_projector(direction, bounds, 1, 0, 0, x_direction=x_direction)
    anchors = []
    covered = set()
    for (part, shape), projected in zip(panels, projections, strict=True):
        center_x, center_y = project_unit(shape.Center().toTuple())
        candidates = (
            [edge.positionAt(0.5) for edge in projected.Edges()]
            if part["id"] in subjects
            else []
        )
        anchors.append(
            min(
                candidates,
                key=lambda p: (p.x - bounds.xmin - center_x) ** 2
                + (bounds.ymax - p.y - center_y) ** 2,
            )
            if candidates
            else None
        )
    right_count = sum(
        anchor.x - bounds.xmin >= bounds.xlen / 2
        for anchor in anchors
        if anchor is not None
    )
    visible_count = sum(anchor is not None for anchor in anchors)
    height = max(340, 32 + max(right_count, visible_count - right_count) * 25)
    scale = min(292 / max(bounds.xlen, 1e-6), (height - 32) / max(bounds.ylen, 1e-6))
    left = (width - bounds.xlen * scale) / 2
    top = (height - bounds.ylen * scale) / 2
    labels = [[], []]
    drawing = []
    for index, (part, _) in enumerate(panels):
        projected = projections[index]
        edges = " ".join(makeSVGedge(edge) for edge in projected.Edges())
        ident = escape(part["id"], quote=True)
        code = escape(next(row[0][0] for row in rows if row[1]["id"] == part["id"]))
        copy_index = next(i for i, row in enumerate(rows) if row[1]["id"] == part["id"])
        ids = escape(
            json.dumps([copy[copy_index][1]["id"] for copy in copies]), quote=True
        )
        drawing.append(
            f'<g data-part-id="{ident}" data-part-ids="{ids}">'
            f'<path d="{edges}" transform="translate({left:g} {top:g}) '
            f"scale({scale:g} {-scale:g}) "
            f'translate({-bounds.xmin:g} {-bounds.ymax:g})" '
            f'fill="none" stroke="#33485a" stroke-width="{0.65 / scale:g}"/>'
            "</g>"
        )
        anchor = anchors[index]
        if anchor is not None:
            box = projected.BoundingBox()
            # A short visible sliver must not count as readable coverage.
            full_area = _area(
                [
                    project_unit(edge.positionAt(t).toTuple())
                    for edge in panels[index][1].Edges()
                    for t in (0, 0.5, 1)
                ]
            )
            visible_area = _visible_patch_area(projected)
            readable = (
                min(box.xlen, box.ylen) * scale >= 8
                and visible_area * scale**2 >= 64
                and visible_area >= full_area * 0.18
            )
            if not readable:
                continue
            covered.add(part["id"])
            x = left + (anchor.x - bounds.xmin) * scale
            y = top + (bounds.ymax - anchor.y) * scale
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
    ), covered


def exploded_views(assembly, parts: list[dict], part_codes: dict[str, str]) -> str:
    """Draw real solids without changing source placement or manufacturing data."""
    if assembly is None or not parts:
        return ""
    layouts = {}
    for members in _items(parts).values():
        rows = _layout(members, assembly, part_codes)
        key = tuple(row[0] for row in rows)
        layouts.setdefault(key, []).append(rows)
    figures = []
    for copies in layouts.values():
        rows = copies[0]
        axes = _item_axes(rows)
        recipe = _report(rows[0][1])["recipe"]
        if any(_report(row[1])["recipe"] != recipe for row in rows):
            raise ValueError("Exploded view: inconsistent item recipe")
        title = {
            "drawer": "Drawer",
            "rectangular": "Cabinet body",
            "profiled": "Cabinet body",
            "frame": "Frame",
        }[recipe]
        if len(copies) > 1:
            title += f" ×{len(copies)}"
        panels = _explode(rows)
        ids = {part["id"] for part, _ in panels}
        interior = {
            part["id"]
            for part, _ in panels
            if _report(part)["member"] in {"divider", "shelf"}
        }
        direction, x_direction = _world(_DIRECTION, axes), _world(_X_DIRECTION, axes)
        views = []
        svg, covered = _drawing(
            rows,
            copies,
            panels,
            ids - interior,
            direction=direction,
            x_direction=x_direction,
        )
        views.append(("Overview", svg))
        if interior:
            detail = [
                (part, shape)
                for part, shape in panels
                if part["id"] in interior
                or _report(part)["member"] in {"back", "bottom"}
            ]
            svg, visible = _drawing(
                rows,
                copies,
                detail,
                interior,
                direction=direction,
                x_direction=x_direction,
            )
            covered |= visible
            views.append(("Interior", svg))
        # The last fallback shows each remaining whole component on its own.
        for part, shape in panels:
            if part["id"] not in covered:
                svg, visible = _drawing(
                    rows,
                    copies,
                    [(part, shape)],
                    {part["id"]},
                    direction=direction,
                    x_direction=x_direction,
                )
                covered |= visible
                views.append((f"Part {part_codes[part['id']]}", svg))
        if missing := ids - covered:
            raise ValueError(
                "Exploded view: unreadable parts: " + ", ".join(sorted(missing))
            )
        physical_ids = [row[1]["id"] for copy in copies for row in copy]
        figures.append(
            '<figure class="exploded-item" style="margin:1em 0;break-inside:avoid" '
            f'data-part-ids="{escape(json.dumps(physical_ids), quote=True)}">'
            f"<figcaption>{title}</figcaption>"
            + "".join(
                f'<div class="exploded-view" data-view="{caption}">'
                f"<p>{caption}</p>{svg}</div>"
                for caption, svg in views
            )
            + "</figure>"
        )
    return "".join(figures)

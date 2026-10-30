"""Draft panel views projected from the solids in the CAD assembly."""

import json
import math
import re

from .grouping import machining_signature
from .machining_dimensions import groove_callouts, groove_dimensions


def _projected_geometry(shape, direction, x_direction=None):
    """Use the same projected edges and bounds as CadQuery's SVG exporter."""
    from cadquery import Compound, Shape
    from cadquery.occ_impl.shapes import TOLERANCE
    from OCP.BRepLib import BRepLib
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape

    projection = HLRBRep_Algo()
    projection.Add(shape.wrapped)
    axes = gp_Ax2(gp_Pnt(), gp_Dir(*direction))
    if x_direction is not None:
        axes.SetXDirection(gp_Dir(*x_direction))
    projection.Projector(HLRAlgo_Projector(axes))
    projection.Update()
    projection.Hide()
    edges = HLRBRep_HLRToShape(projection)
    projected = []
    for compound in (
        edges.VCompound(),
        edges.Rg1LineVCompound(),
        edges.OutLineVCompound(),
        edges.HCompound(),
        edges.OutLineHCompound(),
    ):
        if not compound.IsNull():
            BRepLib.BuildCurves3d_s(compound, TOLERANCE)
            projected.append(Shape(compound))
    return Compound.makeCompound(projected)


def _svg_projector(
    direction, bounds, scale, left, top, rotation_axis=None, x_direction=None
):
    """Use getSVG's world projector, optional CAD rotation and viewport transform."""
    from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf
    from OCP.HLRAlgo import HLRAlgo_Projector

    axes = gp_Ax2(gp_Pnt(), gp_Dir(*direction))
    if x_direction is not None:
        axes.SetXDirection(gp_Dir(*x_direction))
    projector = HLRAlgo_Projector(axes)
    rotation = gp_Trsf()
    if rotation_axis is not None:
        rotation.SetRotation(gp_Ax1(gp_Pnt(), gp_Dir(*rotation_axis)), math.pi / 2)

    def project(point):
        world = gp_Pnt(*point)
        if rotation_axis is not None:
            world.Transform(rotation)
        x, y, _ = projector.Project(world)
        return left + (x - bounds.xmin) * scale, top + (bounds.ymax - y) * scale

    return project


def panel_views(assembly, parts: list[dict]) -> dict[str, str]:
    """Return one inline SVG per physical part, keyed by its stable ID.

    The largest planar face defines the viewing direction. Hidden edges are
    included because modeled features can be on either face. These views do
    not add machining that is absent from the model.
    """
    from cadquery.occ_impl.exporters.svg import getSVG

    views = {}
    for part in parts:
        shape = assembly.objects[part["role"]].toCompound()
        planar_faces = [face for face in shape.Faces() if face.geomType() == "PLANE"]
        if not planar_faces:
            raise ValueError(f"Panel {part['id']} has no planar face to project")
        face = max(planar_faces, key=lambda item: item.Area())
        normal = face.normalAt()
        projection = _projected_geometry(shape, normal.toTuple())
        bounds = projection.BoundingBox()
        rotation_axis = None
        side_map = ".carcass." in part["id"] and part.get("component") in {
            "left_side",
            "right_side",
        }
        if (side_map and bounds.xlen > bounds.ylen) or (
            not side_map and bounds.ylen > bounds.xlen
        ):
            rotation_axis = normal.toTuple()
            shape = shape.rotate((0, 0, 0), rotation_axis, 90)
            face = max(
                (item for item in shape.Faces() if item.geomType() == "PLANE"),
                key=lambda item: item.Area(),
            )
            normal = face.normalAt()
            projection = _projected_geometry(shape, normal.toTuple())
            bounds = projection.BoundingBox()
        width, height = bounds.xlen, bounds.ylen
        scale = min(360 / width * 0.75, 200 / height * 0.75)
        left = (360 - width * scale) / 2
        top = (200 - height * scale) / 2
        right, bottom = left + width * scale, top + height * scale
        svg = getSVG(
            shape,
            {
                "width": 360,
                "height": 200,
                "marginLeft": left,
                "marginTop": top,
                "projectionDir": normal.toTuple(),
                "showAxes": False,
                "showHidden": True,
            },
        )
        svg = svg[svg.index("<svg") :]
        if any(cut.get("type") == "mortise" for cut in part.get("operations", [])):
            # Emphasize the existing CAD cut edges, including hidden mortises.
            # Set the width in drawing pixels so large panels stay readable.
            svg = re.sub(
                r'<g\s+stroke="[^"]*" fill="none" stroke-dasharray="[^"]*"\s*>',
                f'<g class="machining-outline" stroke="#75400d" fill="none" '
                f'stroke-width="{1.25 / scale:g}" stroke-dasharray="none">',
                svg,
                count=1,
            )
        features = groove_dimensions(part)
        viewport_height = 255 + 110 * len(features)
        svg = svg.replace('height="200.0"', f'height="{viewport_height:.1f}"')
        # Scale the full viewport, including dimensions below the CAD outline.
        svg = svg.replace("<svg", f'<svg viewBox="0 0 360 {viewport_height}"', 1)
        blank = part.get("blank_mm") or part.get("finished_mm", {})
        dim_y, dim_x = top - 13, left - 16
        callouts = (
            f'<g stroke="#333" stroke-width="0.8" fill="none">'
            f'<path d="M{left:.1f} {top:.1f} V{dim_y - 4:.1f} '
            f"M{right:.1f} {top:.1f} V{dim_y - 4:.1f} "
            f"M{left:.1f} {dim_y:.1f} H{right:.1f} "
            f"M{left - 3:.1f} {dim_y + 3:.1f} l6 -6 "
            f"M{right - 3:.1f} {dim_y + 3:.1f} l6 -6 "
            f"M{left:.1f} {top:.1f} H{dim_x - 4:.1f} "
            f"M{left:.1f} {bottom:.1f} H{dim_x - 4:.1f} "
            f"M{dim_x:.1f} {top:.1f} V{bottom:.1f} "
            f"M{dim_x - 3:.1f} {top + 3:.1f} l6 -6 "
            f'M{dim_x - 3:.1f} {bottom + 3:.1f} l6 -6"/></g>'
            f'<text x="{(left + right) / 2:.1f}" y="{dim_y - 3:.1f}" '
            f'text-anchor="middle" font-size="10">{width:.1f} mm</text>'
            f'<text x="{dim_x - 4:.1f}" y="{(top + bottom) / 2:.1f}" '
            'text-anchor="middle" font-size="10" '
            f'transform="rotate(-90 {dim_x - 4:.1f} {(top + bottom) / 2:.1f})">'
            f"{height:.1f} mm</text>"
        )
        # Dimension the longest diagonal straight edge when a profile has one.
        # The projected coordinates use the same scale and origin as getSVG.
        diagonals = []
        outline = _projected_geometry(face.outerWire(), normal.toTuple())
        for edge in outline.Edges():
            vertices = edge.Vertices()
            if edge.geomType() != "LINE" or len(vertices) != 2:
                continue
            a, b = (vertex.Center() for vertex in vertices)
            dx, dy = b.x - a.x, b.y - a.y
            if abs(dx) > 1e-5 and abs(dy) > 1e-5:
                diagonals.append((math.hypot(dx, dy), a, b))
        if diagonals:
            length, a, b = max(diagonals, key=lambda item: item[0])
            angle = math.degrees(math.atan2(abs(b.y - a.y), abs(b.x - a.x)))
            callouts += (
                f'<text x="180" y="243" text-anchor="middle" font-size="10">'
                f"Sloped edge: {length:.1f} mm at {angle:.1f}°</text>"
            )
            # A shortened horizontal edge locates the slope without a vertex
            # table. Dimension it only when it is on the bottom of the view.
            for edge in outline.Edges():
                vertices = edge.Vertices()
                if edge.geomType() != "LINE" or len(vertices) != 2:
                    continue
                a, b = (vertex.Center() for vertex in vertices)
                edge_width = abs(b.x - a.x)
                if (
                    abs(a.y - bounds.ymin) > 1e-5
                    or abs(b.y - bounds.ymin) > 1e-5
                    or edge_width < 1e-5
                    or edge_width >= width - 1e-5
                ):
                    continue
                x1 = left + (min(a.x, b.x) - bounds.xmin) * scale
                x2 = left + (max(a.x, b.x) - bounds.xmin) * scale
                y = bottom + 14
                callouts += (
                    f'<path d="M{x1:.1f} {bottom:.1f} V{y + 4:.1f} '
                    f"M{x2:.1f} {bottom:.1f} V{y + 4:.1f} "
                    f"M{x1:.1f} {y:.1f} H{x2:.1f} "
                    f"M{x1 - 3:.1f} {y + 3:.1f} l6 -6 "
                    f'M{x2 - 3:.1f} {y + 3:.1f} l6 -6" '
                    'stroke="#333" stroke-width="0.8" fill="none"/>'
                    f'<text x="{(x1 + x2) / 2:.1f}" y="{y + 11:.1f}" '
                    f'text-anchor="middle" font-size="10">{edge_width:.1f} mm</text>'
                )
                break
        # Match without relying on the drawing orientation. Keep the full stock
        # envelope when it differs from the projected outline.
        stock_axes = sorted((blank["length"], blank["width"]))
        projected_axes = sorted((width, height))
        same_envelope = all(
            abs(stock - projected) < 1e-5
            for stock, projected in zip(stock_axes, projected_axes, strict=True)
        )
        if same_envelope:
            stock_label = (
                f'<text x="180" y="225" text-anchor="middle" '
                f'font-size="10" fill="#222">Stock thickness: '
                f"{blank['thickness']:g} mm</text>"
            )
        else:
            stock_label = (
                '<text x="180" y="210" text-anchor="middle" '
                'font-size="10" fill="#222">Max stock blank</text>'
                f'<text x="180" y="225" text-anchor="middle" '
                f'font-size="10" fill="#222">{blank["length"]:g} × '
                f"{blank['width']:g} × {blank['thickness']:g} mm</text>"
            )
        project = _svg_projector(
            normal.toTuple(), bounds, scale, left, top, rotation_axis
        )
        machining = groove_callouts(features, project)
        svg = svg.replace("</svg>", callouts + stock_label + machining + "</svg>")
        views[part["id"]] = svg
    return views


def panel_groups(
    assembly, parts: list[dict], joints: list[dict] | None = None
) -> list[list[dict]]:
    """Group translated copies only when their solids and processing agree.

    Rotation and reflection are deliberately not normalized: they can change
    the face or edge on which a modeled feature appears.
    """
    by_id = {part["id"]: part for part in parts}
    groups: list[list[dict]] = []
    representatives = []
    for part in parts:
        shape = assembly.objects[part["role"]].toCompound()
        box = shape.BoundingBox()
        normalized = shape.translate((-box.xmin, -box.ymin, -box.zmin))
        dimensions = (box.xlen, box.ylen, box.zlen)
        component = part.get("component", part["id"].rsplit(".", 1)[-1])
        assigned = []
        for joint in joints or []:
            # Space joints are already modeled and included in machining_signature.
            # Their report graph contains per-instance IDs, not extra processing.
            if joint.get("type") == "space_domino":
                continue
            if part["id"] not in joint.get("parts", []):
                continue
            counterparts = [
                by_id.get(other_id, {}).get("component", other_id)
                for other_id in joint["parts"]
                if other_id != part["id"]
            ]
            details = {
                key: value
                for key, value in joint.items()
                if key not in {"id", "cabinet_id", "drawer_id", "parts"}
            }
            assigned.append(
                (tuple(sorted(counterparts)), json.dumps(details, sort_keys=True))
            )
        # Side registration is not modeled. Preserve handedness. For other
        # jointed components only top/bottom edge joints are comparable.
        if (
            "side" in component
            or (assigned and component not in {"top", "bottom"})
            or assigned
            and any(
                len(counterparts) != 1
                or counterparts[0]
                not in {"left_side", "right_side", "side_left", "side_right"}
                for counterparts, _ in assigned
            )
        ):
            identity = component
        else:
            identity = None
        processing = (
            (identity, tuple(sorted(assigned)))
            + tuple(
                part.get(key)
                for key in (
                    "material",
                    "edge_treatment",
                    "grain_direction",
                    "grain_status",
                    "grain_axis_local",
                    "surface_normal_axis_local",
                    "finished_mm",
                    "blank_mm",
                    "profile",
                    "machining_assumptions",
                    "rear_clearance_mm",
                )
            )
            + (machining_signature(part),)
        )
        for index, (other, other_dimensions, other_processing) in enumerate(
            representatives
        ):
            if processing != other_processing or any(
                abs(a - b) > 1e-6
                for a, b in zip(dimensions, other_dimensions, strict=True)
            ):
                continue
            if abs(normalized.Volume() - other.Volume()) > 1e-5:
                continue
            if (
                normalized.cut(other).Volume() < 1e-5
                and other.cut(normalized).Volume() < 1e-5
            ):
                groups[index].append(part)
                break
        else:
            groups.append([part])
            representatives.append((normalized, dimensions, processing))
    return groups

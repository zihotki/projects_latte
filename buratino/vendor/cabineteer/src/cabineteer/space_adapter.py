"""Downstream records, CAD materialization and static checks for space models."""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations
import hashlib
import json

from .spaces import ResolvedModel


def space_model_records(model: ResolvedModel, cabinet_id: str = "cabinet") -> dict:
    """Convert canonical plan data into stock and viewer records without CAD."""
    parts = []
    groups = {}
    drawer_ids = {c["id"] for c in model.contents if "slide_key" in c}
    instances = [p for p in model.placements if p.get("kind") == "cabinet"]
    hierarchy = [p for p in model.placements if p.get("kind") in ("cabinet", "assembly_ref", "frame")]
    def ancestors(ident):
        return sorted((p["id"] for p in hierarchy if ident.startswith(p["id"] + "/")), key=len)
    for source in model.part_plan.parts:
        item = deepcopy(source)
        owners = [p["id"] for p in instances if item["id"].startswith(p["id"] + "/")]
        owner = max(owners, key=len) if owners else cabinet_id
        dims = list(item["stock"]["dimensions"])
        thickness = item["stock"]["thickness"]
        # Remove one stock thickness axis, preserving the other local axes.
        axis = item["stock"].get("thickness_axis")
        if axis not in (0, 1, 2) or abs(dims[axis] - thickness) >= 1e-8:
            raise ValueError(f"{item['id']}: stock thickness is not a stock dimension")
        planar = [v for i, v in enumerate(dims) if i != axis]
        stock = {"length": max(planar), "width": min(planar), "thickness": thickness}
        motion = item.get("motion_group")
        if item["kind"] == "divider":
            item["divider_role"] = item["role"]
        item.update(cabinet_id=owner, ancestor_ids=ancestors(item["id"]), component=item["kind"], quantity=1,
                    stock_mm=stock, role=item["id"], viewer_role=item["id"],
                    label=item["kind"].replace("_", " ").title(),
                    datum={"origin": "localminXYZ", "axes": "partXYZ"},
                    operations=deepcopy(item.get("operations", [])))
        if item["kind"] == "door":
            item.update(hinge_side=item.get("hinge_side", "right"),
                        preview_pose="illustrative_only")
        if motion in drawer_ids:
            item["instance_id"] = motion
        parts.append(item)
        key = (item["material"], *stock.values())
        groups.setdefault(key, []).append(item)
    cutting_groups = [dict(id="space-group-" + hashlib.sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest()[:16], label=members[0]["label"],
        quantity=len(members), material=members[0]["material"],
        members=[p["id"] for p in members], blank_mm=members[0]["stock_mm"])
        for key, members in sorted(groups.items())]
    drawers = [dict(instance_id=c["id"], box_mm=dict(zip(("width", "depth", "height"), c["size"]))) for c in model.contents if "slide_key" in c]
    return {"parts": parts, "contacts": deepcopy(model.part_plan.contacts),
            "viewer": {"parts": parts, "cutting_groups": cutting_groups,
                       "drawers": drawers, "cabinets": [dict(p, name=p["id"].rsplit("/", 1)[-1], parent_id=(ancestors(p["id"])[-1] if ancestors(p["id"]) else None), ancestor_ids=ancestors(p["id"])) for p in instances] or [{"id": cabinet_id, "name": cabinet_id}],
                       "instances": [dict(p, parent_id=(ancestors(p["id"])[-1] if ancestors(p["id"]) else None), ancestor_ids=ancestors(p["id"])) for p in hierarchy]}}


def materialize_model(model: ResolvedModel) -> dict:
    """Materialize recorded local profiles and operations, keyed by part ID."""
    import cadquery as cq
    shapes = {}
    for part in model.part_plan.parts:
        profile = part["profile"]
        if profile["type"] != "box":
            raise ValueError(f"{part['id']}: unsupported profile {profile['type']!r}")
        x, y, z = profile["size"]
        shape = cq.Workplane("XY").box(x, y, z, centered=False)
        for op in part.get("operations", []):
            try:
                cutter = _operation_cutter(cq, op, (x, y, z), part["id"])
                shape = shape.cut(cutter)
                value = shape.val()
                if not shape.solids().vals() or value.Volume() <= 1e-8:
                    raise ValueError("cut removes all stock")
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(f"{part['id']}: CAD failed for operation {op.get('id', '<unknown>')!r}: {exc}") from exc
        try:
            solids = shape.solids().vals()
            if not solids or shape.val().Volume() <= 1e-8:
                raise ValueError("operations remove all stock")
            if any(not solid.isValid() for solid in solids):
                raise ValueError("operations produce invalid solid geometry")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"{part['id']}: CAD materialization failed: {exc}") from exc
        transform = part["transform"]
        if transform["axes"] != [[1,0,0],[0,1,0],[0,0,1]]:
            raise ValueError(f"{part['id']}: unsupported transform axes")
        shapes[part["id"]] = shape.translate(tuple(transform["translation"]))
    return shapes


def _operation_cutter(cq, op: dict, dims: tuple[float, float, float], part_id: str):
    """Build one axis-aligned cutter in the unmachined local XYZ frame."""
    kind = op.get("type")
    label = f"{part_id}: operation {op.get('id', '<unknown>')!r}"
    faces = ("x-", "x+", "y-", "y+", "z-", "z+")
    face = op.get("face")
    if face not in faces:
        raise ValueError(f"{label}: invalid face {face!r}")
    normal_axis = "xyz".index(face[0])
    face_positive = face[1] == "+"
    uv_axes = [axis for axis in range(3) if axis != normal_axis]

    def face_depth_box(depth: float) -> list[list[float]]:
        bounds = [[0.0, dims[i]] for i in range(3)]
        bounds[normal_axis] = ([dims[normal_axis] - depth, dims[normal_axis]]
                               if face_positive else [0.0, depth])
        return bounds

    def box(bounds):
        lengths = tuple(max(0.0, high - low) for low, high in bounds)
        if any(length <= 0 for length in lengths):
            raise ValueError(f"{label}: cut has an empty extent")
        return cq.Solid.makeBox(*lengths, pnt=cq.Vector(*(low for low, _ in bounds)))

    if kind == "pocket":
        bounds = face_depth_box(op["depth"])
        bounds[uv_axes[0]] = [op["u"], op["u"] + op["size_u"]]
        bounds[uv_axes[1]] = [op["v"], op["v"] + op["size_v"]]
        return box(bounds)

    if kind == "rabbet":
        edge = op.get("edge")
        if edge not in faces or edge[0] == face[0]:
            raise ValueError(f"{label}: invalid adjacent edge {edge!r}")
        edge_axis = "xyz".index(edge[0])
        along_axis = next(i for i in range(3) if i not in (normal_axis, edge_axis))
        bounds = face_depth_box(op["depth"])
        edge_extent = dims[edge_axis]
        bounds[edge_axis] = ([0.0, op["width"]] if edge[1] == "-"
                             else [edge_extent - op["width"], edge_extent])
        bounds[along_axis] = [op["start"], op["start"] + op["length"]]
        return box(bounds)

    if kind == "bevel":
        edge = op.get("edge")
        if edge not in faces or edge[0] == face[0]:
            raise ValueError(f"{label}: invalid adjacent edge {edge!r}")
        edge_axis = "xyz".index(edge[0])
        along_axis = next(i for i in range(3) if i not in (normal_axis, edge_axis))
        # The cut triangle starts at the selected edge and extends inward on
        # both adjacent faces, then sweeps along the common axis.
        n0 = dims[normal_axis] if face_positive else 0.0
        e0 = dims[edge_axis] if edge[1] == "+" else 0.0
        n_in = -1.0 if face_positive else 1.0
        e_in = -1.0 if edge[1] == "+" else 1.0
        points = []
        for n, e in ((n0, e0),
                     (n0, e0 + e_in * op["leg_a"]),
                     (n0 + n_in * op["leg_b"], e0)):
            p = [0.0, 0.0, 0.0]
            p[normal_axis], p[edge_axis], p[along_axis] = n, e, op["start"]
            points.append(cq.Vector(*p))
        wire = cq.Wire.makePolygon(points, close=True)
        sweep = [0.0, 0.0, 0.0]
        sweep[along_axis] = op["length"]
        return cq.Solid.extrudeLinear(wire, [], cq.Vector(*sweep))

    if kind in ("bore", "mortise"):
        centre = [0.0, 0.0, 0.0]
        centre[normal_axis] = dims[normal_axis] if face_positive else 0.0
        centre[uv_axes[0]], centre[uv_axes[1]] = op["u"], op["v"]
        inward = [0.0, 0.0, 0.0]
        inward[normal_axis] = -1.0 if face_positive else 1.0
        if kind == "bore":
            return cq.Solid.makeCylinder(op["diameter"] / 2, op["depth"],
                                         cq.Vector(*centre), cq.Vector(*inward))
        if op.get("axis") not in ("u", "v"):
            raise ValueError(f"{label}: invalid mortise axis {op.get('axis')!r}")
        long_axis = uv_axes[0 if op["axis"] == "u" else 1]
        cross_axis = uv_axes[1 if op["axis"] == "u" else 0]
        radius = op["width"] / 2
        half_straight = (op["length"] - op["width"]) / 2
        cutters = []
        if half_straight > 0:
            bounds = [[0.0, dims[i]] for i in range(3)]
            bounds[normal_axis] = ([dims[normal_axis] - op["depth"], dims[normal_axis]]
                                  if face_positive else [0.0, op["depth"]])
            bounds[long_axis] = [centre[long_axis] - half_straight,
                                 centre[long_axis] + half_straight]
            bounds[cross_axis] = [centre[cross_axis] - radius,
                                  centre[cross_axis] + radius]
            cutters.append(box(bounds))
        for offset in (-half_straight, half_straight):
            cap = list(centre)
            cap[long_axis] += offset
            cutters.append(cq.Solid.makeCylinder(radius, op["depth"],
                cq.Vector(*cap), cq.Vector(*inward)))
        cutter = cutters[0]
        for extra in cutters[1:]:
            cutter = cutter.fuse(extra)
        return cutter

    raise ValueError(f"{label}: unsupported operation {kind!r}")


def validate_model(model: ResolvedModel, tolerance: float = 1e-5, shapes: dict | None = None) -> dict:
    """Check shapes, declared contacts and solid intersections without changing the model.

    Callers that already materialized the model may supply the complete shape map.
    """
    if shapes is None:
        try:
            shapes = materialize_model(model)
        except ImportError:
            return {"status": "unavailable", "diagnostics": []}
    expected = {part["id"] for part in model.part_plan.parts}
    if set(shapes) != expected:
        raise ValueError("shape IDs must match the complete physical part plan")
    diagnostics = []
    for ident, shape in shapes.items():
        solids = shape.solids().vals()
        if not solids or not shape.val().isValid():
            diagnostics.append(dict(code="invalid_shape", part_ids=[ident]))
        elif len(solids) > 1:
            diagnostics.append(dict(code="disconnected_solids", part_ids=[ident], solid_count=len(solids)))
    contacts = {tuple(sorted((c["part_a"], c["part_b"]))): c for c in model.part_plan.contacts}
    for a, b in combinations(shapes, 2):
        left, right = shapes[a].val(), shapes[b].val()
        overlap = left.intersect(right).Volume()
        if overlap > tolerance:
            diagnostics.append(dict(code="overlap", part_ids=[a, b], volume_mm3=overlap))
        if (a, b) in contacts or (b, a) in contacts:
            if left.distance(right) > tolerance:
                diagnostics.append(dict(code="missing_contact", part_ids=[a, b], relationship=contacts[tuple(sorted((a, b)))]["type"]))
    return {"status": "failed" if diagnostics else "passed", "diagnostics": diagnostics}

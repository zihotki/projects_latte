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
                    label=item["kind"].replace("_", " ").title())
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
    from .joinery import (DrawerJoinerySpec, DrawerJoineryStyle,
                          apply_drawer_joinery_to_side, apply_drawer_joinery_to_front_back)
    shapes = {}
    for part in model.part_plan.parts:
        profile = part["profile"]
        if profile["type"] != "box":
            raise ValueError(f"{part['id']}: unsupported profile {profile['type']!r}")
        x, y, z = profile["size"]
        shape = cq.Workplane("XY").box(x, y, z, centered=False)
        for op in part["operations"]:
            side = op["side"]
            if op["type"] == "bottom_dado":
                depth, inset, width = op["depth"], op["inset"], op["width"]
                if side in ("side_L", "side_R"):
                    offset = (x-depth if side == "side_L" else 0, 0, inset)
                    size = (depth, y, width)
                else:
                    offset = (0, y-depth if side == "sub_front" else 0, inset)
                    size = (x, depth, width)
                shape = shape.cut(cq.Workplane("XY").transformed(offset=offset).box(*size, centered=False))
            elif op["type"] == "drawer_corner":
                params = dict(op["parameters"])
                params["style"] = DrawerJoineryStyle(params["style"])
                spec = DrawerJoinerySpec(**params)
                if side in ("side_L", "side_R"):
                    shape = apply_drawer_joinery_to_side(shape, spec, y, z, side="left" if side == "side_L" else "right")
                else:
                    shape = apply_drawer_joinery_to_front_back(shape, spec, x, z, position="front" if side == "sub_front" else "back")
            else:
                raise ValueError(f"{part['id']}: unsupported operation {op['type']!r}")
        transform = part["transform"]
        if transform["axes"] != [[1,0,0],[0,1,0],[0,0,1]]:
            raise ValueError(f"{part['id']}: unsupported transform axes")
        shapes[part["id"]] = shape.translate(tuple(transform["translation"]))
    return shapes


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
        if not shape.val().isValid():
            diagnostics.append(dict(code="invalid_shape", part_ids=[ident]))
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

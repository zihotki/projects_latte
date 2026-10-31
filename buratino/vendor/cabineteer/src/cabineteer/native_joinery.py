"""Domino cuts on owned, axis-aligned contacts of existing native solids."""

from dataclasses import asdict, dataclass, replace
from itertools import combinations

from .joinery import component_domino_rows
from .operations import resolve_operations
from .profiles import ProfilePart

TOLERANCE = 1e-5


@dataclass(frozen=True)
class NativeMortise:
    id: str
    part_id: str
    face: str
    u: float
    v: float
    axis: str
    length: float
    width: float
    depth: float
    joint_id: str
    joint_side: str
    type: str = "mortise"
    source: str = "joint"
    coordinate_frame: str = "stock_lwt"
    status: str = "unverified"


def _axis_aligned(part):
    frame = part.local_frame
    return all(
        sum(abs(value) > TOLERANCE for value in axis) == 1
        and abs(sum(value * value for value in axis) - 1) < TOLERANCE
        for axis in (frame.length_axis, frame.width_axis, frame.thickness_axis)
    )


def _stock_record(part):
    box = part.solid().val().BoundingBox()
    low = [getattr(box, axis + "min") for axis in "xyz"]
    high = [getattr(box, axis + "max") for axis in "xyz"]
    # OCC can add tiny numerical tolerances to otherwise exact stock planes.
    low = [round(value, 6) for value in low]
    high = [round(value, 6) for value in high]
    size = [b - a for a, b in zip(low, high)]
    thickness = next(
        i for i, v in enumerate(part.local_frame.thickness_axis) if abs(v) > 0.5
    )
    return {
        "id": part.id,
        "bounds": (low, high),
        "stock": {"dimensions": size, "thickness_axis": thickness},
        "profile": {"type": "box", "size": size},
        "transform": {"translation": low, "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
    }


def _contact(a, b):
    low = [max(x, y) for x, y in zip(a["bounds"][0], b["bounds"][0])]
    high = [min(x, y) for x, y in zip(a["bounds"][1], b["bounds"][1])]
    return any(
        abs(high[i] - low[i]) < TOLERANCE
        and all(high[j] - low[j] > TOLERANCE for j in range(3) if j != i)
        for i in range(3)
    )


def _recipe_for(a, b, spec):
    drawer_a, _, _ = a.id.partition(".drawer.")
    drawer_b, _, _ = b.id.partition(".drawer.")
    sides = {"side_left", "side_right"}
    if ".drawer." in a.id or ".drawer." in b.id:
        if ".drawer." in a.id and ".drawer." in b.id and drawer_a == drawer_b:
            if (
                a.component in sides and b.component in {"inner_front", "inner_back"}
            ) or (
                b.component in sides and a.component in {"inner_front", "inner_back"}
            ):
                return spec.corner_joinery
        return None
    walls = sides | {"divider"}
    panels = {"top", "bottom", "floor"}
    if a.owner == b.owner and (
        a.component in walls
        and b.component in panels
        or b.component in walls
        and a.component in panels
    ):
        return spec.joinery
    # Caps belong to the roof, rather than the upper carcass owner.
    if (
        a.component == "cap" and isinstance(b, ProfilePart) and b.component in walls
    ) or (b.component == "cap" and isinstance(a, ProfilePart) and a.component in walls):
        return spec.joinery
    return None


def _native_operation(op, part, record):
    normal = "xyz".index(op["face"][0])
    uv = [i for i in range(3) if i != normal]
    center = list(record["transform"]["translation"])
    center[normal] += record["profile"]["size"][normal] if op["face"][1] == "+" else 0
    center[uv[0]] += op["u"]
    center[uv[1]] += op["v"]
    frame = part.local_frame
    axes = (frame.length_axis, frame.width_axis, frame.thickness_axis)
    local = [
        round(sum((center[i] - frame.origin_mm[i]) * axis[i] for i in range(3)), 6)
        for axis in axes
    ]
    local_normal = next(i for i, axis in enumerate(axes) if abs(axis[normal]) > 0.5)
    outward = 1 if op["face"][1] == "+" else -1
    face = "xyz"[local_normal] + (
        "+" if axes[local_normal][normal] * outward > 0 else "-"
    )
    long_world = uv[0 if op["axis"] == "u" else 1]
    local_uv = [i for i in range(3) if i != local_normal]
    long_local = next(i for i, axis in enumerate(axes) if abs(axis[long_world]) > 0.5)
    return NativeMortise(
        op["id"],
        part.id,
        face,
        local[local_uv[0]],
        local[local_uv[1]],
        "u" if long_local == local_uv[0] else "v",
        op["length"],
        op["width"],
        op["depth"],
        op["joint_id"],
        op["joint_side"],
    ), tuple(center)


def apply_native_joinery(assembly, spec):
    """Cut only declared contact families; keep stock and native placement data."""
    if spec.joinery is None and spec.corner_joinery is None:
        return assembly
    import cadquery as cq
    from .space_adapter import _operation_cutter

    parts = assembly.parts
    eligible = [p for p in parts if _axis_aligned(p)]
    records = {p.id: _stock_record(p) for p in eligible}
    contacts = []
    for a, b in combinations(eligible, 2):
        recipe = _recipe_for(a, b, spec)
        if recipe is not None and _contact(records[a.id], records[b.id]):
            contacts.append({"part_a": a.id, "part_b": b.id, "joinery": asdict(recipe)})
    rows = component_domino_rows(list(records.values()), contacts)
    operations = resolve_operations(list(records.values()), (), rows)
    by_part = {}
    for op in operations:
        by_part.setdefault(op["part_id"], []).append(op)
    machined = []
    joints = {}
    for part in parts:
        cuts = by_part.get(part.id, ())
        if not cuts:
            machined.append(part)
            continue
        record = records[part.id]
        original = part.solid()
        shape = original
        native_cuts = []
        for op in cuts:
            cutter = _operation_cutter(cq, op, record["profile"]["size"], part.id)
            cutter = cutter.translate(tuple(record["transform"]["translation"]))
            # A stock bounding box alone cannot prove fit in a profiled panel.
            missing = (
                cutter.Volume()
                - original.intersect(cq.Workplane(obj=cutter)).val().Volume()
            )
            if missing > max(0.001, cutter.Volume() * 1e-7):
                raise ValueError(
                    f"{part.id}: Domino {op['joint_id']} does not fit the finished profile"
                )
            shape = shape.cut(cutter)
            native, center = _native_operation(op, part, record)
            native_cuts.append(native)
            joint = joints.setdefault(
                native.joint_id,
                {
                    "id": native.joint_id,
                    "type": "native_domino",
                    "center_mm": center,
                    "length_mm": native.length,
                    "width_mm": native.width,
                    "status": "unverified",
                    "parts": [],
                    "mortises": [],
                },
            )
            joint["parts"].append(part.id)
            joint["mortises"].append(
                {
                    "part_id": part.id,
                    "operation_id": native.id,
                    "depth_mm": native.depth,
                }
            )
        solids = shape.solids().vals()
        if len(solids) != 1 or not solids[0].isValid():
            raise ValueError(
                f"{part.id}: Domino cuts produce invalid or separated stock"
            )
        updates = {"operations": part.operations + tuple(native_cuts)}
        updates["machined_shape" if isinstance(part, ProfilePart) else "shape"] = shape
        machined.append(replace(part, **updates))
    checks = ()
    if spec.joinery is not None and any(
        p.component == "cap" and not _axis_aligned(p) for p in parts
    ):
        checks = (
            {
                "severity": "unknown",
                "code": "joinery.sloped_cap_unverified",
                "message": "Sloped cap joints are not modeled. They require a verified oblique mating frame and paired mortise centers.",
            },
        )
    return replace(
        assembly,
        parts=tuple(machined),
        joints=tuple(joints.values()),
        joinery_checks=checks,
    )

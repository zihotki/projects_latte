"""CAD-independent subtractive cuts in unmachined part coordinates."""

from dataclasses import asdict, dataclass
import math

TOLERANCE = 1e-6


@dataclass(frozen=True)
class Pocket:
    id: str
    part_id: str
    face: str
    u: float
    v: float
    size_u: float
    size_v: float
    depth: float


@dataclass(frozen=True)
class Rabbet:
    id: str
    part_id: str
    face: str
    edge: str
    start: float
    length: float
    width: float
    depth: float


@dataclass(frozen=True)
class Bevel:
    id: str
    part_id: str
    face: str
    edge: str
    start: float
    length: float
    leg_a: float
    leg_b: float


@dataclass(frozen=True)
class Bore:
    id: str
    part_id: str
    face: str
    u: float
    v: float
    diameter: float
    depth: float


@dataclass(frozen=True)
class Mortise:
    id: str
    part_id: str
    face: str
    u: float
    v: float
    axis: str
    length: float
    width: float
    depth: float


@dataclass(frozen=True)
class DominoJoint:
    id: str
    part_a: str
    face_a: str
    part_b: str
    face_b: str
    centre: tuple[float, float, float]
    axis: str
    length: float
    width: float
    depth_a: float
    depth_b: float


OPERATIONS = (Pocket, Rabbet, Bevel, Bore, Mortise)


def _number(value, label, *, positive=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or (value <= 0 if positive else value < 0)
    ):
        raise ValueError(
            f"{label}: expected {'positive' if positive else 'nonnegative'} finite number"
        )
    return value


def _face(face):
    if not isinstance(face, str) or face not in ("x-", "x+", "y-", "y+", "z-", "z+"):
        raise ValueError(f"invalid face {face!r}")
    return "xyz".index(face[0])


def _validate(part, op):
    if part.get("profile", {}).get("type") != "box":
        raise ValueError(f"{part['id']}: only box profiles are supported")
    transform = part["transform"]
    if transform["axes"] != [[1, 0, 0], [0, 1, 0], [0, 0, 1]]:
        raise ValueError(f"{part['id']}: unsupported transform")
    dims = part["profile"]["size"]
    try:
        n = _face(op.face)
    except ValueError as exc:
        raise ValueError(f"face: {exc}") from exc
    uv = [i for i in range(3) if i != n]
    for name in (
        "depth",
        "size_u",
        "size_v",
        "diameter",
        "length",
        "width",
        "leg_a",
        "leg_b",
    ):
        if hasattr(op, name):
            _number(getattr(op, name), name, positive=True)
    for name in ("u", "v", "start"):
        if hasattr(op, name):
            _number(getattr(op, name), name)

    def fits(start, span, bound):
        return start >= -TOLERANCE and start + span <= bound + TOLERANCE

    if hasattr(op, "depth") and op.depth > dims[n] + TOLERANCE:
        raise ValueError(f"{op.id}: depth exceeds stock")
    if isinstance(op, Pocket):
        valid = fits(op.u, op.size_u, dims[uv[0]]) and fits(
            op.v, op.size_v, dims[uv[1]]
        )
    elif isinstance(op, (Bore, Mortise)):
        if isinstance(op, Bore):
            du = dv = op.diameter
        else:
            if op.axis not in ("u", "v") or op.length < op.width:
                raise ValueError(f"{op.id}: invalid mortise axis or dimensions")
            du, dv = (op.length, op.width) if op.axis == "u" else (op.width, op.length)
        valid = fits(op.u - du / 2, du, dims[uv[0]]) and fits(
            op.v - dv / 2, dv, dims[uv[1]]
        )
    else:
        try:
            e = _face(op.edge)
        except ValueError as exc:
            raise ValueError(f"edge: {exc}") from exc
        if e == n:
            raise ValueError(f"{op.id}: edge must be adjacent to face")
        along = next(i for i in range(3) if i not in (n, e))
        valid = fits(op.start, op.length, dims[along])
        if isinstance(op, Rabbet):
            valid &= op.width <= dims[e] + TOLERANCE
        else:
            valid &= op.leg_a <= dims[e] + TOLERANCE and op.leg_b <= dims[n] + TOLERANCE
    if not valid:
        raise ValueError(f"{op.id}: cut exceeds stock")


def resolve_operations(parts, operations, joints):
    """Return validated cuts; XYZ is stock-local, with depth inward from face."""
    by_id = {p["id"]: p for p in parts}
    if len(by_id) != len(parts):
        raise ValueError("duplicate part IDs")
    ids = set()
    result = []

    def add(op, source, ident, **extra):
        part = by_id.get(op.part_id)
        if part is None:
            raise ValueError(f"{op.id}: unknown part {op.part_id!r}")
        try:
            _validate(part, op)
        except ValueError as exc:
            detail = str(exc)
            if source == "joint" and detail.startswith("depth:"):
                detail = f"depth_{extra['joint_side']}:" + detail[len("depth:") :]
            raise ValueError(f"{source} {op.id} part {op.part_id}: {detail}") from exc
        data = asdict(op)
        data.update(id=ident, type=type(op).__name__.lower(), source=source, **extra)
        result.append(data)

    for item in (*operations, *joints):
        if not isinstance(item, (*OPERATIONS, DominoJoint)):
            raise ValueError("unknown operation or joint type")
        if (
            not isinstance(item.id, str)
            or not item.id
            or "/" in item.id
            or item.id in ids
        ):
            raise ValueError(f"invalid or duplicate operation ID {item.id!r}")
        ids.add(item.id)
        if isinstance(item, OPERATIONS):
            if item not in operations:
                raise ValueError("joint list contains an operation")
            add(item, "user", "user/" + item.id)
            continue
        if item not in joints:
            raise ValueError("operation list contains a joint")
        if (
            item.part_a == item.part_b
            or item.part_a not in by_id
            or item.part_b not in by_id
        ):
            raise ValueError(f"{item.id}: joint requires two existing distinct parts")
        if (
            not isinstance(item.axis, str)
            or item.axis not in ("x", "y", "z")
            or not isinstance(item.centre, (tuple, list))
            or len(item.centre) != 3
        ):
            raise ValueError(f"{item.id}: invalid centre or axis")
        if any(
            isinstance(x, bool)
            or not isinstance(x, (int, float))
            or not math.isfinite(x)
            for x in item.centre
        ):
            raise ValueError(f"{item.id}: invalid centre")
        try:
            na = _face(item.face_a)
        except ValueError as exc:
            raise ValueError(
                f"joint {item.id} part {item.part_a} face_a: {exc}"
            ) from exc
        try:
            nb = _face(item.face_b)
        except ValueError as exc:
            raise ValueError(
                f"joint {item.id} part {item.part_b} face_b: {exc}"
            ) from exc
        if na != nb or item.face_a[1] == item.face_b[1] or item.axis == item.face_a[0]:
            raise ValueError(f"{item.id}: incompatible joint faces or axis")
        for side in ("a", "b"):
            part_id, face = getattr(item, "part_" + side), getattr(item, "face_" + side)
            part = by_id[part_id]
            trans = part["transform"]["translation"]
            n = _face(face)
            local = [a - b for a, b in zip(item.centre, trans)]
            if (
                abs(local[n] - (part["profile"]["size"][n] if face[1] == "+" else 0))
                > TOLERANCE
            ):
                raise ValueError(f"{item.id}: joint centre is not on both faces")
            uv = [i for i in range(3) if i != n]
            axis = "u" if "xyz".index(item.axis) == uv[0] else "v"
            op = Mortise(
                item.id,
                part_id,
                face,
                local[uv[0]],
                local[uv[1]],
                axis,
                item.length,
                item.width,
                getattr(item, "depth_" + side),
            )
            add(
                op,
                "joint",
                f"joint/{item.id}/{side}",
                joint_id=item.id,
                joint_side=side,
            )
    return sorted(result, key=lambda x: (x["part_id"], x["id"]))


def drawer_pockets(part_id, side, size, dado_inset, dado_width, dado_depth, joinery):
    """Convert the existing drawer recipe's rectangular cuts to pocket records."""
    x, y, z = size
    result = []

    def pocket(role, face, u, v, su, sv, depth):
        result.append(
            dict(
                id=f"drawer/{part_id}/{role}",
                part_id=part_id,
                type="pocket",
                source="drawer",
                role=role,
                face=face,
                u=u,
                v=v,
                size_u=su,
                size_v=sv,
                depth=depth,
            )
        )

    inner = {"side_L": "x+", "side_R": "x-", "sub_front": "y+", "back": "y-"}[side]
    pocket(
        "bottom_groove",
        inner,
        0,
        dado_inset,
        y if side.startswith("side") else x,
        dado_width,
        dado_depth,
    )
    if side.startswith("side"):
        if joinery.style.value == "butt" or joinery.laps_front:
            return result
        dy = (
            joinery.side_dado_depth_y
            if joinery.style.value == "qqq"
            else joinery.front_back_thickness
        )
        inset = dy if joinery.style.value == "qqq" else 0
        for role, start in (("corner_front", inset), ("corner_back", y - dy - inset)):
            pocket(role, inner, start, 0, dy, z, joinery.engagement_x)
    elif joinery.laps_front:
        for role, start in (
            ("corner_left", 0),
            ("corner_right", x - joinery.side_thickness),
        ):
            pocket(
                role, inner, start, 0, joinery.side_thickness, z, joinery.socket_depth
            )
    elif joinery.style.value == "qqq":
        outer = "y-" if side == "sub_front" else "y+"
        for role, start in (
            ("corner_left", 0),
            ("corner_right", x - joinery.fb_channel_depth_x),
        ):
            pocket(
                role,
                outer,
                start,
                0,
                joinery.fb_channel_depth_x,
                z,
                joinery.front_back_thickness - joinery.fb_channel_depth_y,
            )
    return result

"""CAD-independent subtractive cuts in unmachined part coordinates."""

from dataclasses import asdict, dataclass, replace
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
    width: float
    depth: float
    start: float = 0
    length: float | None = None


@dataclass(frozen=True)
class Bevel:
    id: str
    part_id: str
    face: str
    edge: str
    leg_a: float
    leg_b: float
    start: float = 0
    length: float | None = None


@dataclass(frozen=True)
class Groove:
    id: str
    part_id: str
    face: str
    edge: str
    offset: float
    width: float
    depth: float
    start: float = 0
    length: float | None = None


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


@dataclass(frozen=True)
class DominoRow:
    """Explicit mortise row on the overlap of two opposed contact faces.

    Positions are offsets along ``axis`` from the contact overlap minimum.
    The other in-plane coordinate is the overlap midpoint. Each position
    expands to a DominoJoint with the stable ID ``<row id>-<position>``.
    """
    id: str
    part_a: str
    face_a: str
    part_b: str
    face_b: str
    positions: tuple[float, ...]
    axis: str
    length: float
    width: float
    depth_a: float
    depth_b: float


OPERATIONS = (Pocket, Rabbet, Bevel, Groove, Bore, Mortise)


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


def _validate_input_fields(part, op):
    if part.get("profile", {}).get("type") != "box":
        raise ValueError(f"{part['id']}: only box profiles are supported")
    transform = part["transform"]
    if transform["axes"] != [[1, 0, 0], [0, 1, 0], [0, 0, 1]]:
        raise ValueError(f"{part['id']}: unsupported transform")
    for name in ("depth", "size_u", "size_v", "diameter", "width", "leg_a", "leg_b"):
        if hasattr(op, name):
            _number(getattr(op, name), name, positive=True)
    for name in ("u", "v", "start"):
        if hasattr(op, name):
            _number(getattr(op, name), name)
    if hasattr(op, "length"):
        if op.length is None and not isinstance(op, (Rabbet, Bevel, Groove)):
            raise ValueError("length: expected positive finite number")
        if op.length is not None:
            _number(op.length, "length", positive=True)
    if isinstance(op, Groove):
        _number(op.offset, "offset")
    try:
        _face(op.face)
    except ValueError as exc:
        raise ValueError(f"face: {exc}") from exc
    if hasattr(op, "edge"):
        try:
            _face(op.edge)
        except ValueError as exc:
            raise ValueError(f"edge: {exc}") from exc


def _validate(part, op):
    _validate_input_fields(part, op)
    dims = part["profile"]["size"]
    try:
        n = _face(op.face)
    except ValueError as exc:
        raise ValueError(f"face: {exc}") from exc
    uv = [i for i in range(3) if i != n]

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


def _resolve_edge_span(part, op):
    """Resolve an automatic edge span against the current stock dimensions."""
    normal_axis = _face(op.face)
    edge_axis = _face(op.edge)
    if normal_axis == edge_axis:
        return op
    along_axis = next(i for i in range(3) if i not in (normal_axis, edge_axis))
    start = op.start
    length = (
        part["profile"]["size"][along_axis] - start if op.length is None else op.length
    )
    if length <= 0:
        raise ValueError(f"{op.id}: length must be positive and fit the remaining edge")
    return replace(op, length=length)


def _groove_pocket(part, op):
    """Map an edge groove input to the existing face-pocket representation."""
    normal_axis = _face(op.face)
    edge_axis = _face(op.edge)
    if normal_axis == edge_axis:
        return None
    along_axis = next(i for i in range(3) if i not in (normal_axis, edge_axis))
    dims = part["profile"]["size"]
    length = dims[along_axis] - op.start if op.length is None else op.length
    if length <= 0:
        raise ValueError(f"{op.id}: length must be positive and fit the remaining edge")
    uv_axes = [i for i in range(3) if i != normal_axis]
    edge_extent = dims[edge_axis]
    low = op.offset if op.edge[1] == "-" else edge_extent - op.offset - op.width
    positions = {along_axis: op.start, edge_axis: low}
    spans = {along_axis: length, edge_axis: op.width}
    return Pocket(
        op.id,
        op.part_id,
        op.face,
        positions[uv_axes[0]],
        positions[uv_axes[1]],
        spans[uv_axes[0]],
        spans[uv_axes[1]],
        op.depth,
    )


def _expand_domino_row(row, by_id):
    if not isinstance(row.id, str) or not row.id or "/" in row.id:
        raise ValueError(f"invalid row ID {row.id!r}")
    if row.part_a == row.part_b or row.part_a not in by_id or row.part_b not in by_id:
        raise ValueError(f"{row.id}: row requires two existing distinct parts")
    normal = _face(row.face_a)
    if _face(row.face_b) != normal or row.face_a[1] == row.face_b[1]:
        raise ValueError(f"{row.id}: row requires opposed faces")
    if row.axis not in ("x", "y", "z") or row.axis == row.face_a[0]:
        raise ValueError(f"{row.id}: incompatible row axis")
    a, b = by_id[row.part_a], by_id[row.part_b]
    origins = [part["transform"]["translation"] for part in (a, b)]
    sizes = [part["profile"]["size"] for part in (a, b)]
    planes = [origin[normal] + (size[normal] if face[1] == "+" else 0)
              for origin, size, face in zip(origins, sizes, (row.face_a, row.face_b))]
    if abs(planes[0] - planes[1]) > TOLERANCE:
        raise ValueError(f"{row.id}: row faces must be coincident")
    in_plane = [i for i in range(3) if i != normal]
    low = [max(origin[i] for origin in origins) for i in range(3)]
    high = [min(origin[i] + size[i] for origin, size in zip(origins, sizes)) for i in range(3)]
    if any(high[i] - low[i] <= TOLERANCE for i in in_plane):
        raise ValueError(f"{row.id}: row faces have no contact overlap")
    if not isinstance(row.positions, (tuple, list)) or not row.positions:
        raise ValueError(f"{row.id}: row requires positions")
    axis = "xyz".index(row.axis)
    cross = next(i for i in in_plane if i != axis)
    for position in row.positions:
        _number(position, f"{row.id} position")
        if position > high[axis] - low[axis]:
            raise ValueError(f"{row.id}: row position outside contact overlap")
        centre = [0.0, 0.0, 0.0]
        centre[normal] = planes[0]
        centre[axis] = low[axis] + position
        centre[cross] = (low[cross] + high[cross]) / 2
        yield DominoJoint(f"{row.id}-{position:g}", row.part_a, row.face_a,
                          row.part_b, row.face_b, tuple(centre), row.axis,
                          row.length, row.width, row.depth_a, row.depth_b)


def resolve_operations(parts, operations, joints):
    """Return validated cuts; XYZ is stock-local, with depth inward from face."""
    by_id = {p["id"]: p for p in parts}
    if len(by_id) != len(parts):
        raise ValueError("duplicate part IDs")
    row_ids = set()
    expanded = []
    for joint in joints:
        if isinstance(joint, DominoRow):
            if not isinstance(joint.id, str) or not joint.id or "/" in joint.id:
                raise ValueError(f"invalid row ID {joint.id!r}")
            if joint.id in row_ids:
                raise ValueError(f"duplicate row ID {joint.id!r}")
            row_ids.add(joint.id)
            expanded.extend(_expand_domino_row(joint, by_id))
        else:
            expanded.append(joint)
    joints = tuple(expanded)
    ids = set()
    result = []

    def add(op, source, ident, *, input_op=None, **extra):
        part = by_id.get(op.part_id)
        if part is None:
            raise ValueError(f"{op.id}: unknown part {op.part_id!r}")
        input_op = op if input_op is None else input_op
        try:
            _validate_input_fields(part, input_op)
            if isinstance(op, (Rabbet, Bevel)):
                op = _resolve_edge_span(part, op)
            elif isinstance(op, Groove):
                op = _groove_pocket(part, op)
                if op is None:
                    raise ValueError(f"{input_op.id}: edge must be adjacent to face")
            _validate(part, op)
        except ValueError as exc:
            detail = str(exc)
            if source == "joint" and detail.startswith("depth:"):
                detail = f"depth_{extra['joint_side']}:" + detail[len("depth:") :]
            raise ValueError(
                f"{source} {input_op.id} part {input_op.part_id}: {detail}"
            ) from exc
        data = asdict(op)
        data.update(id=ident, type=type(op).__name__.lower(), source=source, **extra)
        if isinstance(input_op, Groove):
            along_axis = next(
                i
                for i in range(3)
                if i not in (_face(input_op.face), _face(input_op.edge))
            )
            data["groove"] = {
                "edge": input_op.edge,
                "offset": input_op.offset,
                "width": input_op.width,
                "start": input_op.start,
                "length": (
                    input_op.length
                    if input_op.length is not None
                    else part["profile"]["size"][along_axis] - input_op.start
                ),
            }
            data["input_type"] = "groove"
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

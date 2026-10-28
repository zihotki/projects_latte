"""Geometry-independent cabinet layout values and placement resolution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TypeAlias

from .allocation import Fixed, Fr, Natural, allocate_tracks


@dataclass(frozen=True)
class Bounds3D:
    """Axis-aligned bounds in millimetres."""

    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @property
    def width_mm(self) -> float:
        return self.max_x - self.min_x

    @property
    def depth_mm(self) -> float:
        return self.max_y - self.min_y

    @property
    def height_mm(self) -> float:
        return self.max_z - self.min_z


Width: TypeAlias = float | int | Fr  # noqa: UP040 - Python 3.10 support
Alignment: TypeAlias = str  # noqa: UP040 - Python 3.10 support


@dataclass(frozen=True)
class LayoutLeaf:
    """A rectangular carcass envelope for a cabinet or other layout item."""

    name: str
    width_mm: Width
    depth_mm: float
    height_mm: float
    occupied_bounds_mm: Bounds3D | None = None


@dataclass(frozen=True)
class Frame:
    """A four-rail support frame with a rectangular carcass envelope."""

    name: str
    width_mm: float
    depth_mm: float
    height_mm: float
    stock_mm: float
    material: str = ""

    def rails(self) -> tuple[FrameRail, ...]:
        _validate_size(self.width_mm, "frame width")
        _validate_size(self.depth_mm, "frame depth")
        _validate_size(self.height_mm, "frame height")
        _validate_size(self.stock_mm, "frame stock")
        if self.stock_mm <= 0 or 2 * self.stock_mm > min(self.width_mm, self.depth_mm):
            raise ValueError("frame stock must fit within its width and depth")
        return (
            FrameRail(
                "front", (0.0, 0.0, 0.0), self.width_mm, self.stock_mm, self.height_mm
            ),
            FrameRail(
                "back",
                (0.0, self.depth_mm - self.stock_mm, 0.0),
                self.width_mm,
                self.stock_mm,
                self.height_mm,
            ),
            FrameRail(
                "left",
                (0.0, self.stock_mm, 0.0),
                self.stock_mm,
                self.depth_mm - 2 * self.stock_mm,
                self.height_mm,
            ),
            FrameRail(
                "right",
                (self.width_mm - self.stock_mm, self.stock_mm, 0.0),
                self.stock_mm,
                self.depth_mm - 2 * self.stock_mm,
                self.height_mm,
            ),
        )


@dataclass(frozen=True)
class FrameRail:
    name: str
    origin_mm: tuple[float, float, float]
    width_mm: float
    depth_mm: float
    height_mm: float


@dataclass(frozen=True)
class CabinetRef:
    name: str
    definition: str


@dataclass(frozen=True)
class Row:
    """An ordered group of layout items placed along X."""

    name: str
    children: tuple[LayoutNode, ...]
    gap_mm: float = 0.0
    alignment: Alignment = "left"
    depth_alignment: Alignment = "back"
    size_x: Fixed | Fr | Natural = Natural()
    size_z: Fixed | Fr | Natural = Natural()


@dataclass(frozen=True)
class Stack:
    """An ordered group of layout items placed from bottom to top."""

    name: str
    children: tuple[LayoutNode, ...]
    gap_mm: float = 0.0
    depth_mm: float | None = None
    alignment: Alignment = "left"
    depth_alignment: Alignment = "back"
    size_x: Fixed | Fr | Natural = Natural()
    size_z: Fixed | Fr | Natural = Natural()


LayoutNode: TypeAlias = LayoutLeaf | Frame | CabinetRef | Row | Stack  # noqa: UP040 - Python 3.10 support


@dataclass(frozen=True)
class ResolvedPlacement:
    name: str
    origin_mm: tuple[float, float, float]
    carcass_bounds_mm: Bounds3D
    occupied_world_bounds_mm: Bounds3D
    path: str = ""
    node: object = None


@dataclass(frozen=True)
class GroupAllocation:
    path: str
    bounds: Bounds3D
    used_span: float
    slack: float


@dataclass(frozen=True)
class ResolvedLayout:
    placements: tuple[ResolvedPlacement, ...]
    carcass_bounds_mm: Bounds3D
    occupied_world_bounds_mm: Bounds3D
    allocations: tuple[GroupAllocation, ...] = ()


def resolve_layout(
    node: LayoutNode, origin_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
    *, definitions=None, available_size_mm=None,
) -> ResolvedLayout:
    """Resolve structural boxes and placements without CAD or changing inputs."""
    if len(origin_mm) != 3:
        raise ValueError("origin must contain X, Y, and Z")
    origin = tuple(_finite(v, "origin") for v in origin_mm)
    if available_size_mm is not None and len(available_size_mm) != 3:
        raise ValueError("available size must contain width, depth, and height")
    budget = tuple(None if v is None else _size(v, "available size") for v in
                   (available_size_mm or (None, None, None)))
    registry = definitions or {}
    if not hasattr(registry, "get"):
        registry = {item.name: item for item in registry}
    active = set()

    def request(item, axis):
        if isinstance(item, CabinetRef):
            definition = registry.get(item.definition)
            if definition is None:
                raise ValueError(f"{item.name}: unknown cabinet definition {item.definition!r}")
            return (definition.carcass.width, definition.carcass.depth, definition.carcass.height)[axis]
        if isinstance(item, (LayoutLeaf, Frame)):
            return (item.width_mm, item.depth_mm, item.height_mm)[axis]
        if isinstance(item, (Row, Stack)):
            if axis == 1:
                return item.depth_mm if isinstance(item, Stack) and item.depth_mm is not None else Natural()
            return item.size_x if axis == 0 else item.size_z
        raise TypeError(f"unsupported layout node: {type(item).__name__}")

    def intrinsic(item, axis, path, seen):
        key = id(item)
        if key in seen:
            raise ValueError(f"{path}: layout contains a cycle")
        value = request(item, axis)
        if isinstance(value, Fr):
            raise ValueError(f"{path}: Natural size depends on unresolved Fr")
        if not isinstance(value, Natural):
            return _size(value.mm if isinstance(value, Fixed) else value, f"{path} size")
        if not isinstance(item, (Row, Stack)) or not item.children:
            raise ValueError(f"{path}: Natural size has no children")
        seen.add(key)
        try:
            values = [intrinsic(c, axis, f"{path}/{c.name}", seen) for c in item.children]
            own_axis = 0 if isinstance(item, Row) else 2
            return _finite(sum(values) + _size(item.gap_mm, f"{path} gap") * (len(values)-1), f"{path} size") if axis == own_axis else max(values)
        finally:
            seen.remove(key)

    def resolve(item, pos, dimensions, path, parent_axis=None):
        if id(item) in active:
            raise ValueError(f"{path}: layout contains a cycle")
        if not isinstance(item.name, str) or not item.name or "/" in item.name:
            raise ValueError(f"{path}: invalid name")
        active.add(id(item))
        try:
            if isinstance(item, (LayoutLeaf, Frame, CabinetRef)):
                if isinstance(item, Frame):
                    item.rails()
                if any(v <= 0 for v in dimensions):
                    raise ValueError(f"{path}: dimensions must be positive")
                box = _bounds(pos, dimensions)
                occupied = item.occupied_bounds_mm if isinstance(item, LayoutLeaf) else None
                if occupied is not None:
                    _validate_bounds(occupied)
                world = _union([box, _translate(occupied, pos)] if occupied else [box])
                return ResolvedLayout((ResolvedPlacement(item.name, pos, box, world, path, item),), box, world)
            if not isinstance(item, (Row, Stack)):
                raise TypeError(f"unsupported layout node: {type(item).__name__}")
            if not item.children:
                raise ValueError(f"{path}: group must contain children")
            names = [c.name for c in item.children]
            if len(set(names)) != len(names):
                raise ValueError(f"{path}: duplicate child names")
            axis = 0 if isinstance(item, Row) else 2
            _alignment(item.alignment, ("left", "center", "right", "bottom", "top"), "alignment")
            _alignment(item.depth_alignment, ("front", "center", "back"), "depth alignment")
            gap = _size(item.gap_mm, f"{path} gap")
            tracks = []
            for child in item.children:
                value = request(child, axis)
                tracks.append(value if isinstance(value, Fr) else Fixed(intrinsic(child, axis, f"{path}/{child.name}", set())))
            result = allocate_tracks(dimensions[axis], tracks, gap * (len(tracks)-1))
            used = dimensions[axis] - result.slack
            offset = _align_offset(dimensions[axis], used, item.alignment)
            cursor = pos[axis] + offset
            resolved = []
            for child, length in zip(item.children, result.lengths):
                child_path = f"{path}/{child.name}"
                sizes = []
                for i in range(3):
                    if i == axis:
                        sizes.append(length)
                        continue
                    value = request(child, i)
                    if isinstance(value, Fr):
                        raise ValueError(f"{child_path}: Fr is only valid on the parent allocation axis")
                    size = intrinsic(child, i, child_path, set())
                    if size > dimensions[i] + 1e-9:
                        raise ValueError(f"{child_path}: child exceeds group bounds")
                    sizes.append(size)
                child_pos = list(pos)
                child_pos[axis] = cursor
                if axis != 0:
                    child_pos[0] += _align_offset(dimensions[0], sizes[0], item.alignment)
                child_pos[1] += _align_offset(dimensions[1], sizes[1], item.depth_alignment)
                resolved.append(resolve(child, tuple(child_pos), tuple(sizes), child_path, axis))
                cursor = _finite(cursor + length + gap, f"{path} position")
            box = _bounds(pos, dimensions)
            occupied = _union([r.occupied_world_bounds_mm for r in resolved])
            allocations = (GroupAllocation(path, box, used, result.slack),) + tuple(a for r in resolved for a in r.allocations)
            return ResolvedLayout(tuple(p for r in resolved for p in r.placements), box, occupied, allocations)
        finally:
            active.remove(id(item))

    dimensions = []
    for axis in range(3):
        value = request(node, axis)
        if isinstance(value, Fr):
            if budget[axis] is None:
                raise ValueError(f"{node.name}: Fr requires a finite budget")
            size = budget[axis]
        else:
            size = intrinsic(node, axis, node.name, set())
        if budget[axis] is not None and size > budget[axis] + 1e-9:
            raise ValueError(f"{node.name}: size exceeds available budget")
        dimensions.append(size)
    return resolve(node, origin, tuple(dimensions), node.name)


def _union(bounds: list[Bounds3D]) -> Bounds3D:
    result = Bounds3D(
        min(b.min_x for b in bounds),
        min(b.min_y for b in bounds),
        min(b.min_z for b in bounds),
        max(b.max_x for b in bounds),
        max(b.max_y for b in bounds),
        max(b.max_z for b in bounds),
    )
    _validate_bounds(result)
    return result


def _bounds(
    origin: tuple[float, float, float], size: tuple[float, float, float]
) -> Bounds3D:
    x, y, z = origin
    width, depth, height = size
    return Bounds3D(
        x,
        y,
        z,
        _finite(x + width, "maximum X"),
        _finite(y + depth, "maximum Y"),
        _finite(z + height, "maximum Z"),
    )


def _translate(bounds: Bounds3D, origin: tuple[float, float, float]) -> Bounds3D:
    x, y, z = origin
    return Bounds3D(
        _finite(bounds.min_x + x, "occupied minimum X"),
        _finite(bounds.min_y + y, "occupied minimum Y"),
        _finite(bounds.min_z + z, "occupied minimum Z"),
        _finite(bounds.max_x + x, "occupied maximum X"),
        _finite(bounds.max_y + y, "occupied maximum Y"),
        _finite(bounds.max_z + z, "occupied maximum Z"),
    )


def _validate_bounds(bounds: Bounds3D) -> None:
    tuple(
        _finite(value, "occupied bound")
        for value in (
            bounds.min_x,
            bounds.min_y,
            bounds.min_z,
            bounds.max_x,
            bounds.max_y,
            bounds.max_z,
        )
    )
    if (
        bounds.max_x < bounds.min_x
        or bounds.max_y < bounds.min_y
        or bounds.max_z < bounds.min_z
    ):
        raise ValueError("occupied bounds must have non-negative sizes")
    _finite(bounds.max_x - bounds.min_x, "occupied width")
    _finite(bounds.max_y - bounds.min_y, "occupied depth")
    _finite(bounds.max_z - bounds.min_z, "occupied height")


def layout_to_dict(node: LayoutNode) -> dict:
    """Encode a layout with the canonical tagged project representation."""
    from .project import _encode_input
    return _encode_input(node)


def layout_from_dict(data: dict) -> LayoutNode:
    """Decode a layout with the canonical tagged project reader."""
    from .project import _read_input
    node = _read_input(data)
    if not isinstance(node, (LayoutLeaf, CabinetRef, Frame, Row, Stack)):
        raise ValueError("expected a layout node")
    return node


def _align_offset(container: float, child: float, alignment: str) -> float:
    if child > container + 1e-9:
        raise ValueError("child exceeds its parent span")
    if alignment in ("left", "front", "bottom"):
        return 0.0
    if alignment == "center":
        return _finite((container - child) / 2, "alignment offset")
    if alignment in ("right", "back", "top"):
        return _finite(container - child, "alignment offset")
    raise ValueError(f"invalid alignment: {alignment}")


def _alignment(value: str, allowed: tuple[str, ...], name: str) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}")
    return value


def _size(value: float | int | None, name: str) -> float:
    result = _finite(value, name)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _validate_size(value: float | int, name: str) -> None:
    _size(value, name)


def _finite(value: float | int, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be finite")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result

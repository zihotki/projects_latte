"""Geometry-independent cabinet layout values and placement resolution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True)
class Fill:
    """A width that uses an equal share of the parent row's free span."""


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


Width: TypeAlias = float | int | Fill  # noqa: UP040 - Python 3.10 support
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
class Row:
    """An ordered group of layout items placed along X."""

    name: str
    children: tuple[LayoutNode, ...]
    gap_mm: float = 0.0
    span_mm: float | None = None
    alignment: Alignment = "left"
    depth_alignment: Alignment = "back"


@dataclass(frozen=True)
class Stack:
    """An ordered group of layout items placed from bottom to top."""

    name: str
    children: tuple[LayoutNode, ...]
    gap_mm: float = 0.0
    width_mm: float | None = None
    depth_mm: float | None = None
    alignment: Alignment = "left"
    depth_alignment: Alignment = "back"


LayoutNode: TypeAlias = LayoutLeaf | Frame | Row | Stack  # noqa: UP040 - Python 3.10 support


@dataclass(frozen=True)
class ResolvedPlacement:
    name: str
    origin_mm: tuple[float, float, float]
    carcass_bounds_mm: Bounds3D
    occupied_world_bounds_mm: Bounds3D


@dataclass(frozen=True)
class ResolvedLayout:
    placements: tuple[ResolvedPlacement, ...]
    carcass_bounds_mm: Bounds3D
    occupied_world_bounds_mm: Bounds3D


def resolve_layout(
    node: LayoutNode, origin_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
) -> ResolvedLayout:
    """Resolve leaf placements and bounds without creating panel geometry."""
    if len(origin_mm) != 3:
        raise ValueError("origin must contain X, Y, and Z")
    origin = tuple(_finite(value, "origin") for value in origin_mm)
    return _resolve(node, origin, set())


def _resolve(
    node: LayoutNode, origin: tuple[float, float, float], active: set[int]
) -> ResolvedLayout:
    key = id(node)
    if key in active:
        raise ValueError("layout contains a cycle")
    active.add(key)
    try:
        if isinstance(node, LayoutLeaf | Frame):
            width = _width(node.width_mm)
            depth = _size(node.depth_mm, "depth")
            height = _size(node.height_mm, "height")
            if isinstance(width, Fill):
                raise ValueError("fill width requires a parent row span")
            if isinstance(node, Frame):
                node.rails()
            carcass = _bounds(origin, (width, depth, height))
            occupied = node.occupied_bounds_mm if isinstance(node, LayoutLeaf) else None
            if occupied is not None:
                _validate_bounds(occupied)
            world = _translate(occupied, origin) if occupied else carcass
            placement = ResolvedPlacement(node.name, origin, carcass, world)
            return ResolvedLayout((placement,), carcass, world)
        if isinstance(node, Row):
            return _resolve_row(node, origin, active)
        if isinstance(node, Stack):
            return _resolve_stack(node, origin, active)
        raise TypeError(f"unsupported layout node: {type(node).__name__}")
    finally:
        active.remove(key)


def _resolve_row(
    node: Row, origin: tuple[float, float, float], active: set[int]
) -> ResolvedLayout:
    _alignment(node.alignment, ("left", "center", "right"), "row alignment")
    _alignment(node.depth_alignment, ("front", "center", "back"), "depth alignment")
    gap = _size(node.gap_mm, "row gap")
    if not node.children:
        raise ValueError("row must contain at least one child")
    fixed = 0.0
    fill_count = 0
    widths = []
    for child in node.children:
        width = _node_width(child, active)
        widths.append(width)
        if isinstance(width, Fill):
            fill_count += 1
        else:
            fixed += width
    gaps = gap * (len(node.children) - 1)
    span = _size(node.span_mm, "row span") if node.span_mm is not None else None
    if fill_count and span is None:
        raise ValueError("fill width requires a finite parent row span")
    if span is None:
        span = fixed + gaps
    remainder = span - fixed - gaps
    if remainder < -1e-9:
        raise ValueError("row fixed widths and gaps exceed the available span")
    fill_width = max(0.0, remainder) / fill_count if fill_count else 0.0
    used = fixed + gaps + fill_count * fill_width
    offset = _align_offset(span, used, node.alignment)
    depths = [_node_depth(child, active) for child in node.children]
    row_depth = max(depths)
    children = []
    cursor = origin[0] + offset
    for child, child_width, child_depth in zip(
        node.children, widths, depths, strict=True
    ):
        width = fill_width if isinstance(child_width, Fill) else child_width
        y = origin[1] + _align_offset(row_depth, child_depth, node.depth_alignment)
        z = origin[2] - _occupied_min_z(child, active)
        children.append(_resolve_with_width(child, (cursor, y, z), width, active))
        cursor += width + gap
    return _combine(children)


def _resolve_stack(
    node: Stack, origin: tuple[float, float, float], active: set[int]
) -> ResolvedLayout:
    _alignment(node.alignment, ("left", "center", "right"), "stack alignment")
    _alignment(node.depth_alignment, ("front", "center", "back"), "depth alignment")
    gap = _size(node.gap_mm, "stack gap")
    if not node.children:
        raise ValueError("stack must contain at least one child")
    widths = [_node_width(child, active) for child in node.children]
    if any(isinstance(width, Fill) for width in widths):
        raise ValueError("fill width is only valid in a row")
    depths = [_node_depth(child, active) for child in node.children]
    stack_width = (
        _size(node.width_mm, "stack width")
        if node.width_mm is not None
        else max(widths)
    )
    stack_depth = (
        _size(node.depth_mm, "stack depth")
        if node.depth_mm is not None
        else max(depths)
    )
    if any(width > stack_width for width in widths) or any(
        depth > stack_depth for depth in depths
    ):
        raise ValueError("stack child exceeds its constrained bounds")
    children = []
    cursor = origin[2]
    for child, width, depth in zip(node.children, widths, depths, strict=True):
        x = origin[0] + _align_offset(stack_width, width, node.alignment)
        y = origin[1] + _align_offset(stack_depth, depth, node.depth_alignment)
        z = cursor - _occupied_min_z(child, active)
        resolved = _resolve_with_width(child, (x, y, z), width, active)
        children.append(resolved)
        cursor += resolved.occupied_world_bounds_mm.max_z - cursor + gap
    return _combine(children)


def _resolve_with_width(
    node: LayoutNode, origin: tuple[float, float, float], width: float, active: set[int]
) -> ResolvedLayout:
    if isinstance(node, LayoutLeaf) and isinstance(node.width_mm, Fill):
        bounds = _bounds(
            origin,
            (width, _size(node.depth_mm, "depth"), _size(node.height_mm, "height")),
        )
        world = (
            _translate(node.occupied_bounds_mm, origin)
            if node.occupied_bounds_mm
            else bounds
        )
        if node.occupied_bounds_mm is not None:
            _validate_bounds(node.occupied_bounds_mm)
        return ResolvedLayout(
            (ResolvedPlacement(node.name, origin, bounds, world),), bounds, world
        )
    if isinstance(node, Frame) and width != node.width_mm:
        raise ValueError("frame width cannot use row fill")
    return _resolve(node, origin, active)


def _node_width(node: LayoutNode, active: set[int]) -> Width:
    if isinstance(node, LayoutLeaf | Frame):
        return _width(node.width_mm)
    if id(node) in active:
        raise ValueError("layout contains a cycle")
    active.add(id(node))
    try:
        if isinstance(node, Row):
            sizes = [_node_width(child, active) for child in node.children]
            fills = sum(isinstance(size, Fill) for size in sizes)
            fixed = sum(size for size in sizes if not isinstance(size, Fill))
            span = _size(node.span_mm, "row span") if node.span_mm is not None else None
            if fills and span is None:
                raise ValueError("fill width requires a finite parent row span")
            return (
                span
                if span is not None
                else fixed + node.gap_mm * max(0, len(sizes) - 1)
            )
        return (
            _size(node.width_mm, "stack width")
            if node.width_mm is not None
            else max(_resolved_width(child, active) for child in node.children)
        )
    finally:
        active.remove(id(node))


def _resolved_width(node: LayoutNode, active: set[int]) -> float:
    value = _node_width(node, active)
    if isinstance(value, Fill):
        raise ValueError("fill width requires a finite parent row span")
    return value


def _node_depth(node: LayoutNode, active: set[int]) -> float:
    if isinstance(node, LayoutLeaf | Frame):
        return _size(node.depth_mm, "depth")
    if id(node) in active:
        raise ValueError("layout contains a cycle")
    active.add(id(node))
    try:
        if isinstance(node, Stack) and node.depth_mm is not None:
            return _size(node.depth_mm, "stack depth")
        return max(_node_depth(child, active) for child in node.children)
    finally:
        active.remove(id(node))


def _occupied_min_z(node: LayoutNode, active: set[int]) -> float:
    if isinstance(node, LayoutLeaf) and node.occupied_bounds_mm:
        return node.occupied_bounds_mm.min_z
    return 0.0


def _combine(children: list[ResolvedLayout]) -> ResolvedLayout:
    carcass = _union([child.carcass_bounds_mm for child in children])
    occupied = _union([child.occupied_world_bounds_mm for child in children])
    return ResolvedLayout(
        tuple(p for child in children for p in child.placements), carcass, occupied
    )


def _union(bounds: list[Bounds3D]) -> Bounds3D:
    return Bounds3D(
        min(b.min_x for b in bounds),
        min(b.min_y for b in bounds),
        min(b.min_z for b in bounds),
        max(b.max_x for b in bounds),
        max(b.max_y for b in bounds),
        max(b.max_z for b in bounds),
    )


def _bounds(
    origin: tuple[float, float, float], size: tuple[float, float, float]
) -> Bounds3D:
    x, y, z = origin
    width, depth, height = size
    return Bounds3D(x, y, z, x + width, y + depth, z + height)


def _translate(bounds: Bounds3D, origin: tuple[float, float, float]) -> Bounds3D:
    x, y, z = origin
    return Bounds3D(
        bounds.min_x + x,
        bounds.min_y + y,
        bounds.min_z + z,
        bounds.max_x + x,
        bounds.max_y + y,
        bounds.max_z + z,
    )


def _validate_bounds(bounds: Bounds3D) -> None:
    values = (
        bounds.min_x,
        bounds.min_y,
        bounds.min_z,
        bounds.max_x,
        bounds.max_y,
        bounds.max_z,
    )
    if any(not math.isfinite(value) for value in values):
        raise ValueError("occupied bounds must be finite")
    if (
        bounds.max_x < bounds.min_x
        or bounds.max_y < bounds.min_y
        or bounds.max_z < bounds.min_z
    ):
        raise ValueError("occupied bounds must have non-negative sizes")


def layout_to_dict(node: LayoutNode) -> dict:
    """Return the JSON form used by native project snapshots."""
    if isinstance(node, LayoutLeaf):
        return {
            "type": "leaf",
            "name": node.name,
            "width_mm": _width_to_dict(node.width_mm),
            "depth_mm": node.depth_mm,
            "height_mm": node.height_mm,
            "occupied_bounds_mm": _bounds_to_dict(node.occupied_bounds_mm),
        }
    if isinstance(node, Frame):
        return {
            "type": "frame",
            "name": node.name,
            "width_mm": node.width_mm,
            "depth_mm": node.depth_mm,
            "height_mm": node.height_mm,
            "stock_mm": node.stock_mm,
            "material": node.material,
        }
    if isinstance(node, Row | Stack):
        data = {
            "type": "row" if isinstance(node, Row) else "stack",
            "name": node.name,
            "children": [layout_to_dict(child) for child in node.children],
            "gap_mm": node.gap_mm,
            "alignment": node.alignment,
            "depth_alignment": node.depth_alignment,
        }
        if isinstance(node, Row):
            data["span_mm"] = node.span_mm
        else:
            data["width_mm"] = node.width_mm
            data["depth_mm"] = node.depth_mm
        return data
    raise TypeError(f"unsupported layout node: {type(node).__name__}")


def layout_from_dict(data: dict) -> LayoutNode:
    """Build a native layout value from a project snapshot record."""
    if not isinstance(data, dict):
        raise ValueError("layout value must be an object")
    kind = data.get("type")
    if kind == "leaf":
        return LayoutLeaf(
            name=str(data["name"]),
            width_mm=_width_from_dict(data["width_mm"]),
            depth_mm=float(data["depth_mm"]),
            height_mm=float(data["height_mm"]),
            occupied_bounds_mm=_bounds_from_dict(data.get("occupied_bounds_mm")),
        )
    if kind == "frame":
        return Frame(
            name=str(data["name"]),
            width_mm=float(data["width_mm"]),
            depth_mm=float(data["depth_mm"]),
            height_mm=float(data["height_mm"]),
            stock_mm=float(data["stock_mm"]),
            material=str(data.get("material", "")),
        )
    children = tuple(layout_from_dict(child) for child in data.get("children", ()))
    common = {
        "name": str(data["name"]),
        "children": children,
        "gap_mm": float(data.get("gap_mm", 0)),
        "alignment": str(data.get("alignment", "left")),
        "depth_alignment": str(data.get("depth_alignment", "back")),
    }
    if kind == "row":
        span = data.get("span_mm")
        return Row(**common, span_mm=float(span) if span is not None else None)
    if kind == "stack":
        width, depth = data.get("width_mm"), data.get("depth_mm")
        return Stack(
            **common,
            width_mm=float(width) if width is not None else None,
            depth_mm=float(depth) if depth is not None else None,
        )
    raise ValueError(f"unsupported layout type: {kind!r}")


def _width_to_dict(width: Width) -> dict | float:
    return {"fill": True} if isinstance(width, Fill) else width


def _width_from_dict(value: dict | float | int) -> Width:
    if value == {"fill": True}:
        return Fill()
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("width must be a number or fill marker")
    return float(value)


def _bounds_to_dict(bounds: Bounds3D | None) -> dict | None:
    if bounds is None:
        return None
    return {
        "min_x": bounds.min_x,
        "min_y": bounds.min_y,
        "min_z": bounds.min_z,
        "max_x": bounds.max_x,
        "max_y": bounds.max_y,
        "max_z": bounds.max_z,
    }


def _bounds_from_dict(data: dict | None) -> Bounds3D | None:
    if data is None:
        return None
    return Bounds3D(
        *(
            float(data[key])
            for key in ("min_x", "min_y", "min_z", "max_x", "max_y", "max_z")
        )
    )


def _align_offset(container: float, child: float, alignment: str) -> float:
    if child > container + 1e-9:
        raise ValueError("child exceeds its parent span")
    if alignment in ("left", "front"):
        return 0.0
    if alignment == "center":
        return (container - child) / 2
    if alignment in ("right", "back"):
        return container - child
    raise ValueError(f"invalid alignment: {alignment}")


def _alignment(value: str, allowed: tuple[str, ...], name: str) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}")
    return value


def _width(value: Width) -> Width:
    if isinstance(value, Fill):
        return value
    return _size(value, "width")


def _size(value: float | int | None, name: str) -> float:
    result = _finite(value, name)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _validate_size(value: float | int, name: str) -> None:
    _size(value, name)


def _finite(value: float | int, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be finite")
    return float(value)

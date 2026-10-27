"""Native planar roofs and top-open carcass panels.

Coordinates are row-local, with X along the row, Y front to back and Z up.
Profile vertices are the outer top; each segment is a separate cap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .inclined import prism
from .layout import (
    Bounds3D,
    Frame,
    LayoutLeaf,
    LayoutNode,
    ResolvedLayout,
    Row,
    Stack,
    resolve_layout,
)


@dataclass(frozen=True)
class RoofProfile:
    points: tuple[tuple[float, float], ...]
    thickness_mm: float

    def __post_init__(self):
        if (
            len(self.points) < 2
            or not math.isfinite(self.thickness_mm)
            or self.thickness_mm <= 0
        ):
            raise ValueError("roof requires positive thickness and at least two points")
        if any(not math.isfinite(v) for point in self.points for v in point):
            raise ValueError("roof points must be finite")
        if any(
            b[0] <= a[0] for a, b in zip(self.points, self.points[1:], strict=False)
        ):
            raise ValueError("roof X coordinates must increase")

    def segments(self):
        for a, b in zip(self.points, self.points[1:], strict=False):
            slope = (b[1] - a[1]) / (b[0] - a[0])
            drop = self.thickness_mm * math.hypot(1, slope)
            yield a, b, slope, drop


@dataclass(frozen=True)
class ProfiledBox:
    name: str
    x_mm: float
    width_mm: float
    depth_mm: float
    side_mm: float
    bottom_mm: float
    back_mm: float
    material: str = ""
    back_material: str = ""


@dataclass(frozen=True)
class LocalFrame:
    origin_mm: tuple[float, float, float]
    length_axis: tuple[float, float, float]
    width_axis: tuple[float, float, float]
    thickness_axis: tuple[float, float, float]


@dataclass(frozen=True)
class ProfilePart:
    """A panel profile in row X/Z, extruded towards positive Y.

    Stock length and width are dimensions in the panel plane; thickness is
    normal to that plane. The solid is generated from the same profile.
    """

    id: str
    owner: str
    component: str
    material: str
    profile_xz_mm: tuple[tuple[float, float], ...]
    y_mm: float
    extrusion_mm: float
    stock_mm: tuple[float, float, float]
    quantity: int = 1
    orientation: str = ""
    world_offset_mm: tuple[float, float, float] = (0, 0, 0)
    operations: tuple = ()

    @property
    def local_frame(self) -> LocalFrame:
        if self.orientation == "cap":
            a, b = self.profile_xz_mm[:2]
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            axis = ((b[0] - a[0]) / length, 0, (b[1] - a[1]) / length)
            width = (0, 1, 0)
            thickness = (-axis[2], 0, axis[0])
        elif self.orientation == "side":
            axis, width, thickness = (0, 0, 1), (0, 1, 0), (-1, 0, 0)
        elif self.orientation in ("back", "rail_x"):
            axis, width, thickness = (1, 0, 0), (0, 0, 1), (0, -1, 0)
        elif self.orientation == "rail_y":
            axis, width, thickness = (0, 1, 0), (0, 0, 1), (1, 0, 0)
        elif self.orientation == "bottom":
            axis, width, thickness = (1, 0, 0), (0, 1, 0), (0, 0, 1)
        else:
            raise ValueError("part orientation is required")
        vertices = [
            (x, y, z)
            for x, z in self.profile_xz_mm
            for y in (self.y_mm, self.y_mm + self.extrusion_mm)
        ]
        axes = (axis, width, thickness)
        minima = [
            min(sum(a * b for a, b in zip(v, direction, strict=True)) for v in vertices)
            for direction in axes
        ]
        origin = tuple(
            sum(minima[j] * axes[j][i] for j in range(3)) + self.world_offset_mm[i]
            for i in range(3)
        )
        return LocalFrame(origin, axis, width, thickness)

    @property
    def local_profile_mm(self) -> tuple[tuple[float, float, float], ...]:
        frame = self.local_frame
        axes = (frame.length_axis, frame.width_axis, frame.thickness_axis)
        result = []
        for x, z in self.profile_xz_mm:
            vertex = (
                x + self.world_offset_mm[0],
                self.y_mm + self.world_offset_mm[1],
                z + self.world_offset_mm[2],
            )
            relative = tuple(
                v - o for v, o in zip(vertex, frame.origin_mm, strict=True)
            )
            result.append(
                tuple(
                    sum(v * a for v, a in zip(relative, axis, strict=True))
                    for axis in axes
                )
            )
        return tuple(result)

    @property
    def local_extrusion_mm(self) -> tuple[float, float, float]:
        frame = self.local_frame
        return tuple(
            self.extrusion_mm * axis[1]
            for axis in (frame.length_axis, frame.width_axis, frame.thickness_axis)
        )

    def placed(self, offset_mm: tuple[float, float, float]) -> ProfilePart:
        return replace(self, world_offset_mm=offset_mm)

    def solid(self):
        x, y, z = self.world_offset_mm
        return prism(self.profile_xz_mm, self.extrusion_mm).translate(
            (x, y + self.y_mm, z)
        )


def _clip(profile: RoofProfile, x0: float, x1: float, *, underside: bool):
    points = []
    for a, b, slope, drop in profile.segments():
        lo, hi = max(x0, a[0]), min(x1, b[0])
        if hi <= lo:
            continue
        segment = [
            (x, a[1] + slope * (x - a[0]) - (drop if underside else 0))
            for x in (lo, hi)
        ]
        for point in segment:
            if not points or point != points[-1]:
                points.append(point)
    return points


def roof_parts(
    profile: RoofProfile,
    depth_mm: float,
    owner: str,
    names: tuple[str, ...],
    material: str = "",
) -> tuple[ProfilePart, ...]:
    segments = tuple(profile.segments())
    if len(names) != len(segments) or len(set(names)) != len(names):
        raise ValueError("one distinct cap name is required for each roof segment")
    if not math.isfinite(depth_mm) or depth_mm <= 0:
        raise ValueError("cap depth must be positive and finite")
    result = []
    for name, (a, b, slope, drop) in zip(names, segments, strict=False):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        # The vertical end cuts extend the projected blank along the slope.
        length += profile.thickness_mm * abs(slope)
        result.append(
            ProfilePart(
                f"{owner}.cap.{name}",
                owner,
                "cap",
                material,
                (a, b, (b[0], b[1] - drop), (a[0], a[1] - drop)),
                0,
                depth_mm,
                (length, depth_mm, profile.thickness_mm),
                orientation="cap",
            )
        )
    return tuple(result)


def box_parts(box: ProfiledBox, profile: RoofProfile) -> tuple[ProfilePart, ...]:
    values = (
        box.x_mm,
        box.width_mm,
        box.depth_mm,
        box.side_mm,
        box.bottom_mm,
        box.back_mm,
    )
    if any(not math.isfinite(v) for v in values) or min(values[1:]) <= 0:
        raise ValueError("box dimensions must be positive and finite")
    x0, x1 = box.x_mm, box.x_mm + box.width_mm
    if (
        x0 < profile.points[0][0]
        or x1 > profile.points[-1][0]
        or box.width_mm <= 2 * box.side_mm
        or box.depth_mm <= box.back_mm
    ):
        raise ValueError("box must fit the roof and its stock")
    depth = box.depth_mm - box.back_mm
    parts = []
    for name, left, right in (
        ("side_left", x0, x0 + box.side_mm),
        ("side_right", x1 - box.side_mm, x1),
    ):
        top = _clip(profile, left, right, underside=True)
        if min(z for _, z in top) <= box.bottom_mm:
            raise ValueError("roof leaves no usable box interior")
        points = ((left, 0), (right, 0), *reversed(top))
        parts.append(
            ProfilePart(
                f"{box.name}.{name}",
                box.name,
                name,
                box.material,
                points,
                0,
                depth,
                (max(z for _, z in top), depth, box.side_mm),
                orientation="side",
            )
        )
    points = (
        (x0 + box.side_mm, 0),
        (x1 - box.side_mm, 0),
        (x1 - box.side_mm, box.bottom_mm),
        (x0 + box.side_mm, box.bottom_mm),
    )
    parts.append(
        ProfilePart(
            f"{box.name}.bottom",
            box.name,
            "bottom",
            box.material,
            points,
            0,
            depth,
            (box.width_mm - 2 * box.side_mm, depth, box.bottom_mm),
            orientation="bottom",
        )
    )
    top = _clip(profile, x0, x1, underside=False)
    points = ((x0, 0), (x1, 0), *reversed(top))
    parts.append(
        ProfilePart(
            f"{box.name}.back",
            box.name,
            "back",
            box.back_material,
            points,
            depth,
            box.back_mm,
            (box.width_mm, max(z for _, z in top), box.back_mm),
            orientation="back",
        )
    )
    return tuple(parts)


def frame_parts(frame: Frame) -> tuple[ProfilePart, ...]:
    parts = []
    for rail in frame.rails():
        x, y, z = rail.origin_mm
        points = (
            (x, z),
            (x + rail.width_mm, z),
            (x + rail.width_mm, z + rail.height_mm),
            (x, z + rail.height_mm),
        )
        length = rail.width_mm if rail.name in ("front", "back") else rail.depth_mm
        parts.append(
            ProfilePart(
                f"{frame.name}.{rail.name}",
                frame.name,
                rail.name,
                frame.material,
                points,
                y,
                rail.depth_mm,
                (length, rail.height_mm, frame.stock_mm),
                orientation="rail_x" if rail.name in ("front", "back") else "rail_y",
            )
        )
    return tuple(parts)


@dataclass(frozen=True)
class ProfileAssembly:
    layout: ResolvedLayout
    parts: tuple[ProfilePart | NativeCarcassPart, ...]


def _layout_with_profile_heights(
    node: LayoutNode,
    heights: dict[str, float],
    cap_anchor: str,
    cap_bounds: Bounds3D,
    active: set[int] | None = None,
) -> LayoutNode:
    """Derive profiled leaf heights before resolving stack positions."""
    if active is None:
        active = set()
    key = id(node)
    if key in active:
        raise ValueError("layout contains a cycle")
    if isinstance(node, LayoutLeaf):
        updates = {}
        if node.name in heights:
            updates["height_mm"] = heights[node.name]
        if node.name == cap_anchor:
            old = node.occupied_bounds_mm
            updates["occupied_bounds_mm"] = (
                cap_bounds
                if old is None
                else Bounds3D(
                    min(old.min_x, cap_bounds.min_x),
                    min(old.min_y, cap_bounds.min_y),
                    min(old.min_z, cap_bounds.min_z),
                    max(old.max_x, cap_bounds.max_x),
                    max(old.max_y, cap_bounds.max_y),
                    max(old.max_z, cap_bounds.max_z),
                )
            )
        return replace(node, **updates) if updates else node
    if isinstance(node, Frame):
        return node
    if isinstance(node, Row | Stack):
        active.add(key)
        try:
            children = tuple(
                _layout_with_profile_heights(
                    child, heights, cap_anchor, cap_bounds, active
                )
                for child in node.children
            )
        finally:
            active.remove(key)
        return replace(node, children=children)
    raise TypeError(f"unsupported layout node: {type(node).__name__}")


def resolve_profile_assembly(
    layout: LayoutNode,
    roof: RoofProfile,
    boxes: tuple[ProfiledBox, ...],
    cap_owner: str,
    cap_names: tuple[str, ...],
    frame: Frame,
    cap_material: str = "",
) -> ProfileAssembly:
    """Place row-owned caps, their boxes and a support frame on a native layout."""
    if not boxes or len({box.name for box in boxes}) != len(boxes):
        raise ValueError("assembly needs distinct profiled boxes")
    panels = {box.name: box_parts(box, roof) for box in boxes}
    heights = {
        box.name: max(z for _, z in panels[box.name][-1].profile_xz_mm) for box in boxes
    }
    anchor = boxes[0]
    cap_bounds = Bounds3D(
        roof.points[0][0] - anchor.x_mm,
        0,
        0,
        roof.points[-1][0] - anchor.x_mm,
        anchor.depth_mm - anchor.back_mm,
        max(z for _, z in roof.points),
    )
    resolved = resolve_layout(
        _layout_with_profile_heights(layout, heights, anchor.name, cap_bounds)
    )
    placements = {p.name: p for p in resolved.placements}
    if len(placements) != len(resolved.placements) or not boxes:
        raise ValueError("assembly needs distinct placement names and boxes")
    frame_placement = placements[frame.name]
    bounds = frame_placement.carcass_bounds_mm
    if (bounds.width_mm, bounds.depth_mm, bounds.height_mm) != (
        frame.width_mm,
        frame.depth_mm,
        frame.height_mm,
    ):
        raise ValueError("frame dimensions differ from its layout")
    row_origins = []
    parts = []
    for box in boxes:
        p = placements[box.name]
        if (
            abs(p.carcass_bounds_mm.width_mm - box.width_mm) > 1e-9
            or abs(p.carcass_bounds_mm.depth_mm - box.depth_mm) > 1e-9
        ):
            raise ValueError("box dimensions differ from its layout")
        x, y, z = p.origin_mm
        row_origins.append((x - box.x_mm, y, z))
    if any(origin != row_origins[0] for origin in row_origins):
        raise ValueError("profiled boxes must share a row datum")
    if any(
        box.depth_mm - box.back_mm != boxes[0].depth_mm - boxes[0].back_mm
        for box in boxes
    ):
        raise ValueError("profiled boxes must share a cap depth")
    origin = row_origins[0]
    for box in boxes:
        parts.extend(part.placed(origin) for part in panels[box.name])
    parts.extend(
        part.placed(origin)
        for part in roof_parts(
            roof,
            boxes[0].depth_mm - boxes[0].back_mm,
            cap_owner,
            cap_names,
            cap_material,
        )
    )
    parts.extend(
        part.placed(placements[frame.name].origin_mm) for part in frame_parts(frame)
    )
    return ProfileAssembly(resolved, tuple(parts))


@dataclass(frozen=True)
class NativeCarcassPart:
    """An existing native carcass part placed in the composite assembly."""

    id: str
    owner: str
    component: str
    material: str
    shape: object
    local_frame: LocalFrame
    stock_mm: tuple[float, float, float]
    quantity: int = 1
    operations: tuple = ()
    local_profile_mm: None = None
    local_extrusion_mm: None = None

    def solid(self):
        return self.shape


def native_carcass_parts(name, cfg, placement):
    """Adapt the existing single-bay builder without rebuilding its geometry."""
    from .cabinet import build_multi_bay_cabinet

    bounds = placement.carcass_bounds_mm
    if (bounds.width_mm, bounds.depth_mm, bounds.height_mm) != (
        cfg.width,
        cfg.depth,
        cfg.height,
    ):
        raise ValueError("cabinet dimensions differ from its layout")
    assembly, parts = build_multi_bay_cabinet(
        [cfg],
        include_drawers=False,
        include_faces=False,
        include_feet=False,
        face_top_style="plain",
    )
    names = {
        "bay0_left_side": ("side_left", "bay_0/left_side"),
        "bay0_right_side": ("side_right", "bay_0/right_side"),
        "bottom": ("bottom", "bottom"),
        "top": ("top", "top"),
        "back": ("back", "back"),
        "floor_0": ("floor", "floor_0"),
    }
    if set(p.name for p in parts) != set(names):
        raise ValueError("profile assembly lower cabinet must have six carcass parts")
    result = []
    for part in parts:
        component, node = names[part.name]
        offset = assembly.objects[node].loc.toTuple()[0]
        position = tuple(
            a + b for a, b in zip(offset, placement.origin_mm, strict=True)
        )
        shape = part.shape.translate(position)
        bounds = shape.val().BoundingBox()
        if component.startswith("side"):
            axes = ((0, 0, 1), (0, 1, 0), (-1, 0, 0))
            origin = (bounds.xmax, bounds.ymin, bounds.zmin)
            stock = (bounds.zlen, bounds.ylen, bounds.xlen)
        elif component == "back":
            axes = ((1, 0, 0), (0, 0, 1), (0, -1, 0))
            origin = (bounds.xmin, bounds.ymax, bounds.zmin)
            stock = (bounds.xlen, bounds.zlen, bounds.ylen)
        else:
            axes = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
            origin = (bounds.xmin, bounds.ymin, bounds.zmin)
            stock = (bounds.xlen, bounds.ylen, bounds.zlen)
        material = cfg.carcass_material
        result.append(
            NativeCarcassPart(
                f"{name}.carcass.{component}",
                name,
                component,
                material,
                shape,
                LocalFrame(origin, *axes),
                stock,
            )
        )
    return tuple(result)


@dataclass(frozen=True)
class ProfileAssemblySpec:
    roof: RoofProfile
    boxes: tuple[ProfiledBox, ...]
    cap_owner: str
    cap_names: tuple[str, ...]
    frame: Frame
    lower: str
    cap_material: str = ""


def profile_spec_to_dict(spec: ProfileAssemblySpec) -> dict:
    from dataclasses import asdict

    return asdict(spec)


def profile_spec_from_dict(data: dict) -> ProfileAssemblySpec:
    roof = data["roof"]
    return ProfileAssemblySpec(
        roof=RoofProfile(tuple(tuple(p) for p in roof["points"]), roof["thickness_mm"]),
        boxes=tuple(ProfiledBox(**box) for box in data["boxes"]),
        cap_owner=data["cap_owner"],
        cap_names=tuple(data["cap_names"]),
        frame=Frame(**data["frame"]),
        lower=data["lower"],
        cap_material=data.get("cap_material", ""),
    )

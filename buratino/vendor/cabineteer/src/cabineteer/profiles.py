"""Native planar roofs and top-open carcass panels.

Coordinates are row-local, with X along the row, Y front to back and Z up.
Profile vertices are the outer top; each segment is a separate cap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

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
    mounting: str = ""

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
    hardware_status: str = "unverified"
    hardware: tuple[dict, ...] = ()


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
    shared_owner: str | None = None,
    frames: tuple[Frame, ...] | None = None,
) -> ProfileAssembly:
    """Place row-owned caps, their boxes and a support frame on a native layout."""
    if not boxes or len({box.name for box in boxes}) != len(boxes):
        raise ValueError("assembly needs distinct profiled boxes")
    panels = {box.name: box_parts(box, roof) for box in boxes}
    if shared_owner is not None:
        if len(boxes) < 2 or any(
            left.x_mm + left.width_mm != right.x_mm
            for left, right in zip(boxes, boxes[1:])
        ):
            raise ValueError("shared carcass requires contiguous sections")
        stock = lambda box: (
            box.depth_mm,
            box.side_mm,
            box.bottom_mm,
            box.back_mm,
            box.material,
            box.back_material,
        )
        if any(stock(box) != stock(boxes[0]) for box in boxes[1:]):
            raise ValueError("shared sections must use the same stock")
    frames = (frame,) if frames is None else frames
    if not frames or len({item.name for item in frames}) != len(frames):
        raise ValueError("assembly requires distinct frames")
    heights = {
        box.name: max(z for _, z in panels[box.name][-1].profile_xz_mm) for box in boxes
    }
    anchor = boxes[0]
    if shared_owner is not None:
        heights = {shared_owner: max(heights.values())}
    caps = roof_parts(
        roof, anchor.depth_mm - anchor.back_mm, cap_owner, cap_names, cap_material
    )
    cap_bounds = Bounds3D(
        roof.points[0][0] - anchor.x_mm,
        0,
        min(0, *(z for cap in caps for _, z in cap.profile_xz_mm)),
        roof.points[-1][0] - anchor.x_mm,
        anchor.depth_mm - anchor.back_mm,
        max(0, *(z for cap in caps for _, z in cap.profile_xz_mm)),
    )
    resolved = resolve_layout(
        _layout_with_profile_heights(
            layout, heights, shared_owner or anchor.name, cap_bounds
        )
    )
    placements = {p.name: p for p in resolved.placements}
    if len(placements) != len(resolved.placements) or not boxes:
        raise ValueError("assembly needs distinct placement names and boxes")
    for item in frames:
        frame_placement = placements[item.name]
        bounds = frame_placement.carcass_bounds_mm
        if (bounds.width_mm, bounds.depth_mm, bounds.height_mm) != (
            item.width_mm,
            item.depth_mm,
            item.height_mm,
        ):
            raise ValueError("frame dimensions differ from its layout")
    row_origins = []
    parts = []
    for box in boxes:
        if shared_owner is not None:
            break
        p = placements[box.name]
        if (
            abs(p.carcass_bounds_mm.width_mm - box.width_mm) > 1e-9
            or abs(p.carcass_bounds_mm.depth_mm - box.depth_mm) > 1e-9
        ):
            raise ValueError("box dimensions differ from its layout")
        x, y, z = p.origin_mm
        row_origins.append((x - box.x_mm, y, z))
    if shared_owner is not None:
        p = placements[shared_owner]
        if (p.carcass_bounds_mm.width_mm, p.carcass_bounds_mm.depth_mm) != (
            boxes[-1].x_mm + boxes[-1].width_mm - anchor.x_mm,
            anchor.depth_mm,
        ):
            raise ValueError("shared carcass dimensions differ from its layout")
        x, y, z = p.origin_mm
        row_origins.append((x - anchor.x_mm, y, z))
    if any(origin != row_origins[0] for origin in row_origins):
        raise ValueError("profiled boxes must share a row datum")
    if any(
        box.depth_mm - box.back_mm != boxes[0].depth_mm - boxes[0].back_mm
        for box in boxes
    ):
        raise ValueError("profiled boxes must share a cap depth")
    origin = row_origins[0]
    if shared_owner is None:
        for box in boxes:
            parts.extend(part.placed(origin) for part in panels[box.name])
    else:
        first, last = boxes[0], boxes[-1]
        depth = first.depth_mm - first.back_mm
        shared_parts = [panels[first.name][0]]
        for index, box in enumerate(boxes[1:], 1):
            seam = box.x_mm
            half = box.side_mm / 2
            if (
                len(roof.points) == 3
                and seam - half == roof.points[1][0]
                and roof.points[1][1] == roof.points[2][1]
            ):
                level_under = roof.points[1][1] - roof.thickness_mm
                top = [(seam - half, level_under), (seam + half, level_under)]
            else:
                top = _clip(roof, seam - half, seam + half, underside=True)
            shared_parts.append(
                ProfilePart(
                    f"{shared_owner}.divider"
                    if len(boxes) == 2
                    else f"{shared_owner}.divider.{index}",
                    shared_owner,
                    "divider",
                    first.material,
                    ((seam - half, 0), (seam + half, 0), *reversed(top)),
                    0,
                    depth,
                    (max(z for _, z in top), depth, box.side_mm),
                    orientation="side",
                )
            )
        shared_parts.append(panels[last.name][1])
        for i, box in enumerate(boxes):
            x0 = box.x_mm + (box.side_mm if i == 0 else box.side_mm / 2)
            x1 = (
                box.x_mm
                + box.width_mm
                - (box.side_mm / 2 if i < len(boxes) - 1 else box.side_mm)
            )
            if x1 <= x0:
                raise ValueError("shared section has no usable width")
            bottom = panels[box.name][2]
            shared_parts.append(
                replace(
                    bottom,
                    profile_xz_mm=(
                        (x0, 0),
                        (x1, 0),
                        (x1, box.bottom_mm),
                        (x0, box.bottom_mm),
                    ),
                    stock_mm=(x1 - x0, depth, box.bottom_mm),
                )
            )
        back = box_parts(
            replace(
                first,
                name=shared_owner,
                width_mm=last.x_mm + last.width_mm - first.x_mm,
            ),
            roof,
        )[3]
        shared_parts.append(back)
        parts.extend(
            replace(
                part,
                id=(
                    f"{shared_owner}.{part.component}"
                    if part.component.startswith("side_")
                    else part.id
                ),
                owner=shared_owner,
            ).placed(origin)
            for part in shared_parts
        )
    parts.extend(part.placed(origin) for part in caps)
    for item in frames:
        parts.extend(
            part.placed(placements[item.name].origin_mm) for part in frame_parts(item)
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


def native_carcass_parts(name, cfg, placement, back_material=""):
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
    actual = {p.name for p in parts}
    if actual not in (set(names), set(names) - {"floor_0"}):
        raise ValueError("profile assembly lower cabinet has unsupported carcass parts")
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
        material = back_material if component == "back" and back_material else cfg.carcass_material
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
class ProfileFaceSpec:
    """Explicit face and drawer inputs for the composite assembly."""

    drawer: dict = field(default_factory=dict)
    drawer_box_bottom_clearance_mm: float = 0
    outer_reveal_mm: float = 2
    roof_reveal_mm: float = 2
    depth_offset_mm: float = 2
    thickness_mm: float = 18
    material: str = ""

    def __post_init__(self):
        values = (
            self.drawer_box_bottom_clearance_mm,
            self.outer_reveal_mm,
            self.roof_reveal_mm,
            self.depth_offset_mm,
        )
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("face clearances must be finite and nonnegative")
        if not math.isfinite(self.thickness_mm) or self.thickness_mm <= 0:
            raise ValueError("face thickness must be positive and finite")
        if self.drawer and not self.drawer.get("slide_key"):
            raise ValueError("drawer slide must be selected explicitly")


@dataclass(frozen=True)
class ProfileDrawerSpec:
    """One rectangular drawer in a named profiled upper section."""

    section: str
    slide_key: str
    box_height_mm: float
    bottom_clearance_mm: float
    side_mm: float = 16
    front_back_mm: float = 18
    bottom_mm: float = 12
    bottom_dado_depth_mm: float = 6
    bottom_dado_inset_mm: float | None = None
    front_gap_mm: float = 0
    joinery_style: str = "butt"
    material: str = ""
    bottom_material: str = ""

    def __post_init__(self):
        if not self.section or not self.slide_key:
            raise ValueError("drawer section and slide key are required")
        positive = (
            self.box_height_mm,
            self.side_mm,
            self.front_back_mm,
            self.bottom_mm,
            self.bottom_dado_depth_mm,
        )
        optional = (self.bottom_clearance_mm, self.front_gap_mm)
        if any(not math.isfinite(v) or v <= 0 for v in positive):
            raise ValueError("drawer stock and height must be positive and finite")
        if any(not math.isfinite(v) or v < 0 for v in optional):
            raise ValueError("drawer clearances must be finite and nonnegative")
        if self.bottom_dado_inset_mm is not None and (
            not math.isfinite(self.bottom_dado_inset_mm)
            or self.bottom_dado_inset_mm < 0
        ):
            raise ValueError("drawer bottom dado inset must be finite and nonnegative")


@dataclass(frozen=True)
class ProfileShelfSpec:
    """Adjustable shelf with its bottom height from the target cabinet base."""

    name: str
    target: str
    height_mm: float
    thickness_mm: float = 18
    front_recess_mm: float = 3
    material: str = ""

    def __post_init__(self):
        if not self.name or not self.target or "." in self.name:
            raise ValueError("shelf name and target are required; name cannot contain a dot")
        if any(
            not math.isfinite(value) or value <= 0
            for value in (self.height_mm, self.thickness_mm)
        ) or not math.isfinite(self.front_recess_mm) or self.front_recess_mm < 0:
            raise ValueError("shelf dimensions must be finite and valid")


@dataclass(frozen=True)
class ProfileLowerDrawerSpec:
    """One recipe for every drawer opening in a named lower cabinet."""

    cabinet: str
    slide_key: str
    box_height_mm: float
    bottom_clearance_mm: float
    side_mm: float = 16
    front_back_mm: float = 18
    bottom_mm: float = 12
    bottom_dado_depth_mm: float = 6
    bottom_dado_inset_mm: float | None = None
    front_gap_mm: float = 0
    material: str = ""
    bottom_material: str = ""
    drawer_count: int = 0

    def __post_init__(self):
        if not self.cabinet or not self.slide_key:
            raise ValueError("lower drawer cabinet and slide key are required")
        if type(self.drawer_count) is not int or self.drawer_count < 0:
            raise ValueError("drawer count must be a nonnegative integer")
        if any(
            not math.isfinite(value) or value <= 0
            for value in (
                self.box_height_mm,
                self.side_mm,
                self.front_back_mm,
                self.bottom_mm,
                self.bottom_dado_depth_mm,
            )
        ) or any(
            not math.isfinite(value) or value < 0
            for value in (
                self.bottom_clearance_mm,
                self.front_gap_mm,
            )
        ):
            raise ValueError("lower drawer dimensions must be finite and valid")


def lower_slide_keys(config, recipe: ProfileLowerDrawerSpec) -> tuple[str, ...]:
    """Return the runner selected for each lower opening."""
    if config.openings:
        return tuple(item.slide_key or recipe.slide_key for item in config.openings)
    return (recipe.slide_key,) * recipe.drawer_count


@dataclass(frozen=True)
class ProfileAssemblySpec:
    roof: RoofProfile
    boxes: tuple[ProfiledBox, ...]
    cap_owner: str
    cap_names: tuple[str, ...]
    frame: Frame
    lower: str
    cap_material: str = ""
    faces: ProfileFaceSpec | None = None
    shared_owner: str | None = None
    roof_joint: str | None = None
    upper_drawers: tuple[ProfileDrawerSpec, ...] = ()
    adjustable_shelves: tuple[ProfileShelfSpec, ...] = ()
    frames: tuple[Frame, ...] = ()
    lower_drawers: tuple[ProfileLowerDrawerSpec, ...] = ()
    lower_back_material: str = ""


def resolved_profile_spec(spec: ProfileAssemblySpec) -> ProfileAssemblySpec:
    """Place a transition joint on the shared divider's left face.

    A single slope has no transition and is unchanged. The authored kink must
    be at the section boundary, with a level segment to its right.
    """
    if spec.roof_joint is None:
        return spec
    if spec.roof_joint != "level_over_divider" or spec.shared_owner is None:
        raise ValueError("roof joint requires a shared carcass")
    if len(spec.roof.points) == 2:
        return spec
    if len(spec.boxes) < 2 or len(spec.roof.points) != 3:
        raise ValueError("roof joint requires sections and one transition")
    start, kink, end = spec.roof.points
    matches = [box for box in spec.boxes[1:] if box.x_mm == kink[0]]
    if len(matches) != 1 or kink[1] != end[1]:
        raise ValueError(
            "roof joint requires a level right segment at the section boundary"
        )
    joint_x = matches[0].x_mm - matches[0].side_mm / 2
    if not start[0] < joint_x < end[0]:
        raise ValueError("roof joint must fit the roof")
    return replace(
        spec, roof=RoofProfile((start, (joint_x, kink[1]), end), spec.roof.thickness_mm)
    )


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
        faces=ProfileFaceSpec(**data["faces"]) if data.get("faces") else None,
        shared_owner=data.get("shared_owner"),
        roof_joint=data.get("roof_joint"),
        upper_drawers=tuple(
            ProfileDrawerSpec(**drawer) for drawer in data.get("upper_drawers", ())
        ),
        adjustable_shelves=tuple(
            ProfileShelfSpec(**shelf) for shelf in data.get("adjustable_shelves", ())
        ),
        frames=tuple(Frame(**frame) for frame in data.get("frames", ())),
        lower_drawers=tuple(
            ProfileLowerDrawerSpec(**recipe) for recipe in data.get("lower_drawers", ())
        ),
        lower_back_material=data.get("lower_back_material", ""),
    )


def _profile_face(
    roof: RoofProfile,
    *,
    name: str,
    owner: str,
    face_type: str,
    x0: float,
    x1: float,
    bottom: float,
    thickness: float,
    outer_reveal: float,
    depth_offset: float,
    material: str = "",
    top_line: tuple[float, float] | None = None,
) -> ProfilePart:
    """Build a front from the lower envelope of normal-offset roof lines.

    Adjacent roof segments must form a convex upper outline.  Their offset
    lines intersect away from the original kink, so clipping the unshifted
    vertices would give the wrong face profile.
    """
    if face_type not in ("door", "drawer_front", "applied_faceboard"):
        raise ValueError("unsupported face type")
    values = (x0, x1, bottom, thickness, outer_reveal, depth_offset)
    if any(not math.isfinite(v) for v in values) or (
        x0 >= x1 or thickness <= 0 or outer_reveal < 0 or depth_offset < 0
    ):
        raise ValueError("invalid face dimensions")
    if top_line is not None and any(not math.isfinite(v) for v in top_line):
        raise ValueError("face top line must be finite")
    if x0 < roof.points[0][0] or x1 > roof.points[-1][0]:
        raise ValueError("face must fit the roof")
    segments = list(roof.segments())
    lines = [
        (slope, a[1] - slope * a[0] - outer_reveal * math.hypot(1, slope))
        for a, _, slope, _ in segments
    ]
    breaks = []
    for (m1, c1), (m2, c2) in zip(lines, lines[1:], strict=False):
        if m1 <= m2:
            raise ValueError("face roof must have strictly convex kinks")
        breaks.append((c2 - c1) / (m1 - m2))
    if any(a >= b for a, b in zip(breaks, breaks[1:], strict=False)):
        raise ValueError("offset roof has unsupported intersections")

    def top(x):
        return min(m * x + c for m, c in lines)

    if top_line is None:
        top_points = [(x0, top(x0))]
        top_points.extend((x, top(x)) for x in breaks if x0 < x < x1)
        top_points.append((x1, top(x1)))
    else:
        slope, intercept = top_line
        top_points = [(x0, slope * x0 + intercept), (x1, slope * x1 + intercept)]
    if min(z for _, z in top_points) <= bottom:
        raise ValueError("roof leaves no face height")
    points = ((x0, bottom), (x1, bottom), *reversed(top_points))
    return ProfilePart(
        name,
        owner,
        face_type,
        material,
        points,
        -depth_offset - thickness,
        thickness,
        (x1 - x0, max(z for _, z in top_points) - bottom, thickness),
        orientation="back",
        mounting={
            "door": "hinged",
            "drawer_front": "drawer-mounted",
            "applied_faceboard": "fixed",
        }[face_type],
    )


def profile_face(
    roof: RoofProfile,
    *,
    name: str,
    owner: str,
    face_type: str,
    x0: float,
    x1: float,
    bottom: float,
    thickness: float,
    outer_reveal: float,
    depth_offset: float,
    material: str = "",
) -> ProfilePart:
    """Build a front from the roof's normal-offset envelope."""
    return _profile_face(
        roof,
        name=name,
        owner=owner,
        face_type=face_type,
        x0=x0,
        x1=x1,
        bottom=bottom,
        thickness=thickness,
        outer_reveal=outer_reveal,
        depth_offset=depth_offset,
        material=material,
    )


def _placed_drawer_parts(drawer, origin, section, owner, material, bottom_material=""):
    """Place the native drawer box in a profile assembly."""
    from .drawer import build_drawer, drawer_part_offsets

    _, drawer_parts = build_drawer(drawer)
    offsets = drawer_part_offsets(drawer)
    names = {
        "drawer_side_L": ("side_left", "side_L"),
        "drawer_side_R": ("side_right", "side_R"),
        "drawer_sub_front": ("inner_front", "sub_front"),
        "drawer_back": ("inner_back", "back"),
        "drawer_bottom": ("bottom", "bottom"),
    }
    parts = []
    for part in drawer_parts:
        component, key = names[part.name]
        pos = tuple(a + b for a, b in zip(origin, offsets[key], strict=True))
        shape = part.shape.translate(pos)
        bounds = shape.val().BoundingBox()
        if component.startswith("side"):
            axes = ((0, 1, 0), (0, 0, 1), (1, 0, 0))
            local_origin = (bounds.xmin, bounds.ymin, bounds.zmin)
            stock = (bounds.ylen, bounds.zlen, bounds.xlen)
        elif component == "bottom":
            axes = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
            local_origin = (bounds.xmin, bounds.ymin, bounds.zmin)
            stock = (bounds.xlen, bounds.ylen, bounds.zlen)
        else:
            axes = ((1, 0, 0), (0, 0, 1), (0, -1, 0))
            local_origin = (bounds.xmin, bounds.ymax, bounds.zmin)
            stock = (bounds.xlen, bounds.zlen, bounds.ylen)
        parts.append(
            NativeCarcassPart(
                f"{section}.drawer.{component}",
                owner,
                component,
                bottom_material
                if component == "bottom" and bottom_material
                else material,
                shape,
                LocalFrame(local_origin, *axes),
                stock,
            )
        )
    return tuple(parts)


def upper_drawer_configs(spec: ProfileAssemblySpec):
    """Derive each upper opening from the carcass and its lowest roof underside."""
    from .drawer import DrawerConfig
    from .hardware import get_slide
    from .joinery import DrawerJoineryStyle

    names = {box.name for box in spec.boxes}
    if len({item.section for item in spec.upper_drawers}) != len(spec.upper_drawers):
        raise ValueError("upper drawer sections must be distinct")
    result = {}
    for item in spec.upper_drawers:
        if item.section not in names:
            raise ValueError(f"unknown upper drawer section: {item.section}")
        i, box = next(
            (i, box) for i, box in enumerate(spec.boxes) if box.name == item.section
        )
        half = box.side_mm / 2 if spec.shared_owner is not None else box.side_mm
        x0 = box.x_mm + (half if i else box.side_mm)
        x1 = (
            box.x_mm + box.width_mm - (half if i < len(spec.boxes) - 1 else box.side_mm)
        )
        # A rectangular box must clear the roof at every X in its footprint.
        underside = _clip(spec.roof, x0, x1, underside=True)
        opening_height = min(z for _, z in underside) - box.bottom_mm
        opening_depth = box.depth_mm - box.back_mm
        slide = get_slide(item.slide_key)
        if item.bottom_clearance_mm < slide.min_bottom_clearance:
            raise ValueError(
                f"upper drawer {item.section} lacks runner bottom clearance"
            )
        if item.box_height_mm + item.bottom_clearance_mm > opening_height:
            raise ValueError(f"upper drawer {item.section} exceeds roof underside")
        drawer = DrawerConfig(
            opening_width=x1 - x0,
            opening_height=opening_height,
            opening_depth=opening_depth,
            slide_key=item.slide_key,
            side_thickness=item.side_mm,
            front_back_thickness=item.front_back_mm,
            bottom_thickness=item.bottom_mm,
            bottom_dado_depth=item.bottom_dado_depth_mm,
            bottom_dado_inset=item.bottom_dado_inset_mm,
            front_gap=item.front_gap_mm,
            vertical_gap=opening_height
            - slide.min_bottom_clearance
            - item.box_height_mm,
            use_standard_height=False,
            applied_face=False,
            joinery_style=DrawerJoineryStyle(item.joinery_style),
        )
        if drawer.box_height != item.box_height_mm or drawer.box_depth > opening_depth:
            raise ValueError(f"upper drawer {item.section} does not fit opening")
        result[item.section] = (item, drawer, x0, box.bottom_mm)
    return result


def adjustable_shelf_parts(spec, lower_parts, other_parts, placements):
    """Resolve declared shelves in the clear carcass spans, without machining."""
    targets = {box.name: (index, box) for index, box in enumerate(spec.boxes)}
    targets[spec.lower] = None
    ids = [f"{item.target}.shelf.{item.name}" for item in spec.adjustable_shelves]
    if len(ids) != len(set(ids)):
        raise ValueError("adjustable shelf IDs must be distinct")

    lower_by_component = {part.component: part for part in lower_parts}
    lower_left = lower_by_component["side_left"].solid().val().BoundingBox()
    lower_right = lower_by_component["side_right"].solid().val().BoundingBox()
    lower_back = lower_by_component["back"].solid().val().BoundingBox()
    lower_origin = placements[spec.lower].origin_mm
    anchor = spec.boxes[0]
    upper_origin = placements[spec.shared_owner or anchor.name].origin_mm
    upper_origin = (upper_origin[0] - anchor.x_mm, *upper_origin[1:])
    result = []
    occupied = []
    for item, part_id in zip(spec.adjustable_shelves, ids, strict=True):
        if item.target not in targets:
            raise ValueError(f"unknown adjustable shelf target: {item.target}")
        if item.target == spec.lower:
            x0 = lower_left.xmax
            x1 = lower_right.xmin
            y0 = lower_left.ymin + item.front_recess_mm
            y1 = lower_back.ymin
            z0 = lower_origin[2] + item.height_mm
            origin = lower_origin
            owner = spec.lower
            material = item.material or lower_by_component["bottom"].material
            roof_limit = lower_by_component["top"].solid().val().BoundingBox().zmin
        else:
            index, box = targets[item.target]
            half = box.side_mm / 2 if spec.shared_owner else box.side_mm
            local_x0 = box.x_mm + (box.side_mm if index == 0 else half)
            local_x1 = box.x_mm + box.width_mm - (
                box.side_mm if index == len(spec.boxes) - 1 else half
            )
            x0, x1 = upper_origin[0] + local_x0, upper_origin[0] + local_x1
            y0 = upper_origin[1] + item.front_recess_mm
            y1 = upper_origin[1] + box.depth_mm - box.back_mm
            z0 = upper_origin[2] + item.height_mm
            origin = upper_origin
            owner = spec.shared_owner or box.name
            material = item.material or box.material
            roof_limit = upper_origin[2] + min(
                z for _, z in _clip(spec.roof, local_x0, local_x1, underside=True)
            )
            if item.height_mm < box.bottom_mm - 1e-9:
                raise ValueError(f"adjustable shelf {part_id} overlaps fixed bottom")
        z1 = z0 + item.thickness_mm
        if x1 <= x0 or y1 <= y0 or z1 > roof_limit + 1e-9:
            raise ValueError(f"adjustable shelf {part_id} does not fit its opening")
        bounds = (x0, x1, y0, y1, z0, z1)
        for other_id, other_bounds in occupied:
            if _bounds_overlap(bounds, other_bounds):
                raise ValueError(f"adjustable shelves {part_id} and {other_id} overlap")
        # Structural lower panels and drawer boxes are checked in world space.
        # Upper roof and sides use their actual clear spans and underside above.
        blockers = (
            tuple(lower_parts) + tuple(other_parts)
            if item.target == spec.lower
            else tuple(
                part for part in other_parts
                if part.id.startswith(f"{item.target}.drawer.")
            )
        )
        for blocker in blockers:
            if item.target == spec.lower and blocker.component in (
                "side_left", "side_right", "back"
            ):
                continue
            bb = blocker.solid().val().BoundingBox()
            if _bounds_overlap(bounds, (bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax)):
                raise ValueError(f"adjustable shelf {part_id} overlaps {blocker.id}")
        occupied.append((part_id, bounds))
        local_x0, local_x1 = x0 - origin[0], x1 - origin[0]
        local_z0, local_z1 = z0 - origin[2], z1 - origin[2]
        result.append(
            ProfilePart(
                part_id, owner, "adjustable_shelf", material,
                ((local_x0, local_z0), (local_x1, local_z0),
                 (local_x1, local_z1), (local_x0, local_z1)),
                y0 - origin[1], y1 - y0,
                (x1 - x0, y1 - y0, item.thickness_mm),
                orientation="bottom", mounting="adjustable",
            ).placed(origin)
        )
    return tuple(result)


def _bounds_overlap(a, b):
    return all(a[low] < b[high] - 1e-9 and b[low] < a[high] - 1e-9
               for low, high in ((0, 1), (2, 3), (4, 5)))


def lower_drawer_parts(spec, configs, placements):
    """Resolve all lower drawer openings from one recipe per cabinet."""
    from .cabinet import OpeningConfig, opening_stack
    from .drawer import DrawerConfig
    from .hardware import get_slide
    from .joinery import DrawerJoineryStyle
    from types import SimpleNamespace

    recipes = {item.cabinet: item for item in spec.lower_drawers}
    if len(recipes) != len(spec.lower_drawers):
        raise ValueError("lower drawer recipes must have distinct cabinets")
    if set(recipes) != set(configs):
        raise ValueError("each lower cabinet needs one drawer recipe")
    face = spec.faces
    if face is None:
        raise ValueError("lower drawers require a profile face specification")

    def drawer_gap(config):
        return (
            config.face_gap_mm
            if config.drawer_front_gap_mm is None
            else config.drawer_front_gap_mm
        )

    parts, hardware = [], []
    for name, cfg in configs.items():
        recipe = recipes[name]
        if cfg.columns or any(item.opening_type != "drawer" for item in cfg.openings):
            raise ValueError(
                f"lower cabinet {name} requires a drawer-only opening stack"
            )
        if not cfg.openings and recipe.drawer_count == 0:
            raise ValueError(
                f"lower cabinet {name} requires drawer openings or a count"
            )
        if cfg.openings and recipe.drawer_count not in (0, len(cfg.openings)):
            raise ValueError(f"lower cabinet {name} drawer count differs from openings")
        placement = placements[name]
        if cfg.openings:
            slots = opening_stack(cfg)
        else:
            height = cfg.interior_height / recipe.drawer_count
            slots = [
                SimpleNamespace(
                    index=i,
                    z=cfg.bottom_thickness + i * height,
                    opening=OpeningConfig(height, "drawer", slide_key=recipe.slide_key),
                )
                for i in range(recipe.drawer_count)
            ]
        gap = drawer_gap(cfg)
        reveal = face.outer_reveal_mm
        face_height = (cfg.height - 2 * reveal - (len(slots) - 1) * gap) / len(slots)
        if face_height <= 0:
            raise ValueError(f"lower cabinet {name} has no usable drawer face height")
        left_reveal = right_reveal = reveal
        for other_name, other_cfg in configs.items():
            if other_name == name:
                continue
            other = placements[other_name]
            if not math.isclose(other.origin_mm[1], placement.origin_mm[1], abs_tol=1e-9):
                continue
            seam_reveal = max(gap, drawer_gap(other_cfg)) / 2
            if math.isclose(
                other.origin_mm[0] + other_cfg.width, placement.origin_mm[0],
                abs_tol=1e-9,
            ):
                left_reveal = seam_reveal
            if math.isclose(
                placement.origin_mm[0] + cfg.width, other.origin_mm[0],
                abs_tol=1e-9,
            ):
                right_reveal = seam_reveal
        if left_reveal + right_reveal >= cfg.width:
            raise ValueError(f"lower cabinet {name} has no usable drawer face width")
        selected_slides = lower_slide_keys(cfg, recipe)
        for slot in slots:
            opening = slot.opening
            slide_key = selected_slides[slot.index]
            slide = get_slide(slide_key)
            if recipe.bottom_clearance_mm < slide.min_bottom_clearance:
                raise ValueError(
                    f"lower drawer {name}/{slot.index} lacks runner clearance"
                )
            if recipe.box_height_mm + recipe.bottom_clearance_mm > opening.height_mm:
                raise ValueError(
                    f"lower drawer {name}/{slot.index} exceeds its opening"
                )
            drawer = DrawerConfig(
                opening_width=cfg.interior_width,
                opening_height=opening.height_mm,
                opening_depth=cfg.interior_depth,
                slide_key=slide_key,
                side_thickness=recipe.side_mm,
                front_back_thickness=recipe.front_back_mm,
                bottom_thickness=recipe.bottom_mm,
                bottom_dado_depth=recipe.bottom_dado_depth_mm,
                bottom_dado_inset=recipe.bottom_dado_inset_mm,
                front_gap=recipe.front_gap_mm,
                vertical_gap=opening.height_mm
                - slide.min_bottom_clearance
                - recipe.box_height_mm,
                use_standard_height=False,
                applied_face=False,
                joinery_style=DrawerJoineryStyle.BUTT,
            )
            if (
                drawer.box_height != recipe.box_height_mm
                or drawer.box_depth > cfg.interior_depth
            ):
                raise ValueError(f"lower drawer {name}/{slot.index} does not fit")
            section = f"{name}.opening.{slot.index}"
            origin = (
                placement.origin_mm[0] + cfg.side_thickness + drawer.side_gap,
                placement.origin_mm[1] + drawer.front_gap,
                placement.origin_mm[2] + slot.z + recipe.bottom_clearance_mm,
            )
            parts.extend(
                _placed_drawer_parts(
                    drawer,
                    origin,
                    section,
                    name,
                    recipe.material or cfg.carcass_material,
                    recipe.bottom_material,
                )
            )
            bottom = reveal + slot.index * (face_height + gap)
            x0, x1 = left_reveal, cfg.width - right_reveal
            parts.append(
                ProfilePart(
                    f"{section}.drawer_front",
                    name,
                    "drawer_front",
                    cfg.face_material,
                    (
                        (x0, bottom),
                        (x1, bottom),
                        (x1, bottom + face_height),
                        (x0, bottom + face_height),
                    ),
                    -face.depth_offset_mm - face.thickness_mm,
                    face.thickness_mm,
                    (x1 - x0, face_height, face.thickness_mm),
                    orientation="back",
                    world_offset_mm=placement.origin_mm,
                    mounting="drawer-mounted",
                )
            )
            hardware.append(
                {
                    "type": "drawer_runner",
                    "slide_key": slide_key,
                    "instance_id": f"{section}.drawer",
                    "quantity": 2,
                    "status": "unverified",
                    "box_bottom_clearance_mm": recipe.bottom_clearance_mm,
                }
            )
    return tuple(parts), tuple(hardware)


def assembly_faces(spec: ProfileAssemblySpec, cfg, placement, row_origin):
    """Resolve upper fronts and all drawer boxes with native builders."""
    from .cabinet import face_layout
    from .drawer import DrawerConfig
    from .joinery import DrawerJoineryStyle

    face = spec.faces
    if face is None:
        if spec.upper_drawers:
            raise ValueError("upper drawers require a profile face specification")
        return ()
    parts = []
    if not spec.lower_drawers:
        if len(cfg.openings) != 2 or [o.opening_type for o in cfg.openings] != [
            "drawer",
            "door",
        ]:
            raise ValueError("profile lower cabinet requires a drawer below one door")
        inputs = dict(face.drawer)
        if "joinery_style" in inputs:
            inputs["joinery_style"] = DrawerJoineryStyle(inputs["joinery_style"])
        drawer = DrawerConfig(**inputs)
        if (drawer.opening_width, drawer.opening_height, drawer.opening_depth) != (
            cfg.interior_width,
            cfg.openings[0].height_mm,
            cfg.interior_depth,
        ):
            raise ValueError("drawer opening differs from lower cabinet")
        if drawer.applied_face:
            raise ValueError("drawer face must be resolved by the cabinet")
        if (
            drawer.box_height <= 0
            or drawer.box_height + face.drawer_box_bottom_clearance_mm
            > drawer.opening_height
        ):
            raise ValueError("drawer box does not fit its opening")
        _ = drawer.box_depth  # Apply native slide depth and stock constraints.
        origin = (
            placement.origin_mm[0] + cfg.side_thickness + drawer.side_gap,
            placement.origin_mm[1] + drawer.front_gap,
            placement.origin_mm[2]
            + cfg.bottom_thickness
            + face.drawer_box_bottom_clearance_mm,
        )
        parts = list(
            _placed_drawer_parts(
                drawer, origin, spec.lower, spec.lower, cfg.carcass_material
            )
        )
    upper_drawers = upper_drawer_configs(spec)
    for box in spec.boxes:
        selected = upper_drawers.get(box.name)
        if selected is None:
            continue
        item, upper, x0, bottom = selected
        upper_origin = (
            row_origin[0] + x0 + upper.side_gap,
            row_origin[1] + upper.front_gap,
            row_origin[2] + bottom + item.bottom_clearance_mm,
        )
        parts.extend(
            _placed_drawer_parts(
                upper,
                upper_origin,
                box.name,
                spec.shared_owner or box.name,
                item.material or box.material,
                item.bottom_material,
            )
        )
    if not spec.lower_drawers:
        panels = face_layout(
            [cfg], face_thickness=face.thickness_mm, face_top_style="plain"
        )
        door_panels = sorted(
            (panel for panel in panels if panel.kind == "door"),
            key=lambda panel: panel.x,
        )
        door_left = door_panels[0].x if door_panels else None
        door_right = door_panels[-1].x + door_panels[-1].width if door_panels else None
        drawer_bottom = cfg.bottom_thickness - drawer.face_overlay_bottom
        drawer_top = (
            cfg.bottom_thickness + drawer.opening_height + drawer.face_overlay_top
        )
        door_gap = cfg.face_gap_mm if cfg.door_gap_mm is None else cfg.door_gap_mm
        drawer_gap = (
            cfg.face_gap_mm
            if cfg.drawer_front_gap_mm is None
            else cfg.drawer_front_gap_mm
        )
        mixed_gap = max(door_gap, drawer_gap)
        for panel in panels:
            if panel.kind not in ("door", "drawer_face"):
                continue
            component = "door" if panel.kind == "door" else "face"
            prefix = "face" if component == "door" else "drawer"
            # The profile assembly uses one declared outer reveal for the lower
            # fronts. Native drawer faces run flush to the cabinet sides, while
            # door width comes from its hinge overlay. Adjust only the outer edge
            # of each end leaf so a paired door keeps its center seam.
            panel_x = panel.x
            panel_width = panel.width
            if component == "face":
                panel_x = face.outer_reveal_mm
                panel_width = cfg.width - 2 * face.outer_reveal_mm
            else:
                if panel.x == door_left:
                    right = panel.x + panel.width
                    panel_x = face.outer_reveal_mm
                    panel_width = right - panel_x
                if panel.x + panel.width == door_right:
                    panel_width = cfg.width - face.outer_reveal_mm - panel_x
            bottom = drawer_top + mixed_gap if component == "door" else drawer_bottom
            top = panel.z + panel.height if component == "door" else drawer_top
            if top <= bottom:
                raise ValueError("drawer overlay leaves no usable face height")
            points = (
                (panel_x, bottom),
                (panel_x + panel_width, bottom),
                (panel_x + panel_width, top),
                (panel_x, top),
            )
            parts.append(
                ProfilePart(
                    f"{spec.lower}.{prefix}.{component}",
                    spec.lower,
                    component,
                    cfg.face_material,
                    points,
                    -face.thickness_mm,
                    face.thickness_mm,
                    (panel_width, top - bottom, face.thickness_mm),
                    orientation="back",
                    world_offset_mm=placement.origin_mm,
                )
            )
        door_gap = cfg.face_gap_mm if cfg.door_gap_mm is None else cfg.door_gap_mm
    else:
        door_gap = cfg.face_gap_mm if cfg.door_gap_mm is None else cfg.door_gap_mm
        drawer_gap = (
            cfg.face_gap_mm
            if cfg.drawer_front_gap_mm is None
            else cfg.drawer_front_gap_mm
        )
    level_transition = (
        spec.roof_joint == "level_over_divider"
        and len(spec.roof.points) == 3
        and len(spec.boxes) >= 2
    )
    transition_index = (
        next(
            (
                i
                for i, box in enumerate(spec.boxes[1:], 1)
                if box.x_mm - box.side_mm / 2 == spec.roof.points[1][0]
            ),
            None,
        )
        if level_transition
        else None
    )
    roof_lines = [
        (slope, a[1] - slope * a[0] - face.roof_reveal_mm * math.hypot(1, slope))
        for a, _, slope, _ in spec.roof.segments()
    ]
    previous_top = None
    for i, box in enumerate(spec.boxes):
        kind = "drawer_front" if box.name in upper_drawers else "door"
        previous_kind = (
            ("drawer_front" if spec.boxes[i - 1].name in upper_drawers else "door")
            if i
            else None
        )
        next_kind = (
            ("drawer_front" if spec.boxes[i + 1].name in upper_drawers else "door")
            if i + 1 < len(spec.boxes)
            else None
        )
        left_gap = (
            face_boundary_gap(
                previous_kind,
                kind,
                door_gap_mm=door_gap,
                drawer_front_gap_mm=drawer_gap,
            )
            if previous_kind
            else 0
        )
        right_gap = (
            face_boundary_gap(
                kind, next_kind, door_gap_mm=door_gap, drawer_front_gap_mm=drawer_gap
            )
            if next_kind
            else 0
        )
        x0 = box.x_mm + (face.outer_reveal_mm if i == 0 else left_gap / 2)
        x1 = (
            box.x_mm
            + box.width_mm
            - (face.outer_reveal_mm if i == len(spec.boxes) - 1 else right_gap / 2)
        )
        top_line = None
        if level_transition:
            # Extend the left section slope across its door, then level the
            # right door to the same top height.
            if i < transition_index:
                top_line = roof_lines[0]
            else:
                top_line = (0, previous_top)
        face_args = dict(
            name=f"{box.name}.{kind}",
            owner=spec.shared_owner or box.name,
            face_type=kind,
            x0=x0,
            x1=x1,
            bottom=face.outer_reveal_mm,
            thickness=face.thickness_mm,
            outer_reveal=face.roof_reveal_mm,
            depth_offset=face.depth_offset_mm,
            material=face.material,
        )
        if top_line is None:
            part = profile_face(spec.roof, **face_args)
        else:
            part = _profile_face(spec.roof, **face_args, top_line=top_line)
        part = part.placed(row_origin)
        parts.append(part)
        if level_transition:
            previous_top = top_line[0] * x1 + top_line[1]
    return tuple(parts)


@dataclass(frozen=True)
class ProfileOperation:
    kind: str
    target: str
    local_profile_mm: tuple[tuple[float, float, float], ...]
    status: str = "unverified"
    angle_deg: float | None = None


def with_profile_operations(part: ProfilePart) -> ProfilePart:
    """Record only cuts represented by the finished profile."""
    profile = part.local_profile_mm
    if part.orientation == "side":
        top = profile[2:]
        if max(p[0] for p in top) - min(p[0] for p in top) <= 1e-9:
            return part
        if len(top) > 2:
            return replace(
                part, operations=(ProfileOperation("profile_trim", "top", top),)
            )
        a, b = sorted((top[0], top[-1]), key=lambda p: p[2])
        angle = math.degrees(math.atan2(b[0] - a[0], b[2] - a[2]))
        operation = ProfileOperation("edge_bevel", "top", top, angle_deg=angle)
    elif part.component in ("back", "door", "drawer_front", "applied_faceboard"):
        if len(profile) == 4 and abs(profile[2][1] - profile[3][1]) <= 1e-9:
            return part
        operation = ProfileOperation("profile_trim", "broad_face", profile)
    else:
        return part
    return replace(part, operations=(operation,))


def face_boundary_gap(
    kind: str,
    neighbor: str,
    *,
    door_gap_mm: float,
    drawer_front_gap_mm: float,
    explicit_gap_mm: float | None = None,
) -> float:
    """Resolve one total gap, including a fixed faceboard boundary."""
    kinds = {"door", "drawer_front", "applied_faceboard"}
    if kind not in kinds or neighbor not in kinds:
        raise ValueError("unsupported face kind")
    values = (door_gap_mm, drawer_front_gap_mm)
    if explicit_gap_mm is not None:
        values += (explicit_gap_mm,)
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("face gaps must be finite and nonnegative")
    if explicit_gap_mm is not None:
        return explicit_gap_mm
    gaps = {"door": door_gap_mm, "drawer_front": drawer_front_gap_mm}
    named = [gaps[k] for k in (kind, neighbor) if k in gaps]
    if not named:
        raise ValueError(
            "a fixed faceboard boundary needs a named face neighbor or gap"
        )
    return max(named)


def layout_with_face_occupancy(layout: LayoutNode, spec: ProfileAssemblySpec, cfg):
    """Include front envelopes before layout resolves stack positions."""
    if spec.faces is None:
        return layout
    from types import SimpleNamespace

    configs = cfg if isinstance(cfg, dict) else {spec.lower: cfg}
    generated = assembly_faces(
        spec, configs[spec.lower], SimpleNamespace(origin_mm=(0, 0, 0)), (0, 0, 0)
    )
    box_x = {box.name: box.x_mm for box in spec.boxes}
    if spec.shared_owner is not None:
        box_x[spec.shared_owner] = spec.boxes[0].x_mm
    envelopes = (
        {
            name: Bounds3D(
                0,
                -spec.faces.depth_offset_mm - spec.faces.thickness_mm,
                0,
                cabinet.width,
                cabinet.depth,
                cabinet.height,
            )
            for name, cabinet in configs.items()
        }
        if spec.lower_drawers
        else {}
    )
    for part in generated:
        if not isinstance(part, ProfilePart):
            continue
        owner = (
            spec.shared_owner
            if spec.shared_owner is not None
            and part.owner in box_x
            and part.owner != spec.shared_owner
            else part.owner
        )
        shift = box_x.get(owner, 0)
        xs = [x - shift for x, _ in part.profile_xz_mm]
        zs = [z for _, z in part.profile_xz_mm]
        envelopes[owner] = (
            Bounds3D(
                min(xs),
                part.y_mm,
                min(zs),
                max(xs),
                part.y_mm + part.extrusion_mm,
                max(zs),
            )
            if owner not in envelopes
            else _bounds_union(
                envelopes[owner],
                Bounds3D(
                    min(xs),
                    part.y_mm,
                    min(zs),
                    max(xs),
                    part.y_mm + part.extrusion_mm,
                    max(zs),
                ),
            )
        )

    def include(node, active):
        if isinstance(node, LayoutLeaf):
            bounds = envelopes.get(node.name)
            if bounds is None:
                return node
            if node.occupied_bounds_mm is not None:
                bounds = _bounds_union(node.occupied_bounds_mm, bounds)
            return replace(node, occupied_bounds_mm=bounds)
        if isinstance(node, Frame):
            return node
        if id(node) in active:
            raise ValueError("layout contains a cycle")
        if isinstance(node, Row | Stack):
            active.add(id(node))
            try:
                return replace(
                    node,
                    children=tuple(include(child, active) for child in node.children),
                )
            finally:
                active.remove(id(node))
        raise TypeError(f"unsupported layout node: {type(node).__name__}")

    return include(layout, set())


def _bounds_union(a: Bounds3D, b: Bounds3D) -> Bounds3D:
    return Bounds3D(
        min(a.min_x, b.min_x),
        min(a.min_y, b.min_y),
        min(a.min_z, b.min_z),
        max(a.max_x, b.max_x),
        max(a.max_y, b.max_y),
        max(a.max_z, b.max_z),
    )


def assembly_records(assembly: ProfileAssembly) -> dict:
    """Return the durable, JSON-ready description used by assembly consumers."""
    from dataclasses import asdict

    parts = []
    viewer_parts = {}
    for part in assembly.parts:
        geometry = None
        if isinstance(part, NativeCarcassPart):
            vertices, triangles = part.solid().val().tessellate(0.01)
            geometry = {
                "kind": "world_mesh",
                "chord_tolerance_mm": 0.01,
                "units": "mm",
                "frame": "world",
                "status": "approximation_not_machining_instruction",
                "vertices_mm": [v.toTuple() for v in vertices],
                "triangles": triangles,
            }
        record = {
            "id": part.id,
            "owner": part.owner,
            "component": part.component,
            "material": part.material,
            "quantity": part.quantity,
            "stock_mm": dict(
                zip(("length", "width", "thickness"), part.stock_mm, strict=True)
            ),
            "local_frame": asdict(part.local_frame),
            "geometry": geometry,
            "profile_mm": part.local_profile_mm,
            "extrusion_mm": part.local_extrusion_mm,
            "operations": [asdict(operation) for operation in part.operations],
            "mounting": getattr(part, "mounting", ""),
        }
        viewer = {"role": part.id, "cabinet_id": part.owner}
        if part.component == "adjustable_shelf":
            viewer["label"] = "Adjustable shelf"
        if part.component in ("door", "drawer_front"):
            viewer["hinge_side"] = "right" if part.component == "door" else None
            viewer["hinge_side_status"] = (
                "assumed_for_preview" if part.component == "door" else "not_applicable"
            )
            viewer["preview_pose"] = "illustrative_only"
            if part.component == "door":
                origin = part.local_frame.origin_mm
                axis = part.local_frame.length_axis
                thickness_axis = part.local_frame.thickness_axis
                viewer["hinge_pivot_mm"] = tuple(
                    origin[i]
                    + axis[i] * part.stock_mm[0]
                    + thickness_axis[i] * part.stock_mm[2] / 2
                    for i in range(3)
                )
        if ".drawer." in part.id or part.component == "drawer_front":
            section = (
                part.id.rpartition(".drawer.")[0]
                if ".drawer." in part.id
                else part.id.removesuffix(".drawer_front")
            )
            instance_id = f"{section}.drawer"
            viewer["instance_id"] = instance_id
            viewer["display_open_distance_mm"] = (
                part.stock_mm[0] if part.component.startswith("side_") else 0
            )
        viewer_parts[part.id] = viewer
        parts.append(record)
    groups_by_signature = {}
    for part in parts:
        signature = (
            part["material"],
            tuple(part["stock_mm"][key] for key in ("length", "width", "thickness")),
        )
        groups_by_signature.setdefault(signature, []).append(part)
    cutting_groups = []
    for index, (signature, members) in enumerate(
        sorted(groups_by_signature.items()), 1
    ):
        material, dimensions = signature
        label = members[0]["component"].replace("_", " ").title()
        cutting_groups.append(
            {
                "id": f"profile-group-{index}",
                "label": label,
                "quantity": sum(member["quantity"] for member in members),
                "material": material,
                "members": [member["id"] for member in members],
                "blank_mm": dict(
                    zip(("length", "width", "thickness"), dimensions, strict=True)
                ),
            }
        )
    drawers = {}
    hardware_by_drawer = {
        item["instance_id"]: item
        for item in assembly.hardware
        if item.get("type") == "drawer_runner" and item.get("instance_id")
    }
    for part in parts:
        viewer = viewer_parts[part["id"]]
        if viewer.get("instance_id"):
            drawer = drawers.setdefault(
                viewer["instance_id"],
                {
                    "instance_id": viewer["instance_id"],
                    "cabinet_id": part["owner"],
                    "box_mm": {"depth": viewer.get("display_open_distance_mm", 0)},
                    "part_ids": [],
                },
            )
            drawer["part_ids"].append(part["id"])
            if viewer.get("display_open_distance_mm"):
                drawer["box_mm"]["depth"] = viewer["display_open_distance_mm"]
    by_id = {part.id: part for part in assembly.parts}
    for instance_id, drawer in drawers.items():
        number = instance_id.rsplit(".", 2)[-2]
        drawer["drawer_index"] = int(number) + 1 if number.isdigit() else 1
        selected = hardware_by_drawer.get(instance_id, {})
        drawer["slide_key"] = selected.get("slide_key")
        box_parts = [
            by_id[part_id]
            for part_id in drawer["part_ids"]
            if by_id[part_id].component not in ("drawer_front", "face")
        ]
        if box_parts:
            bounds = [part.solid().val().BoundingBox() for part in box_parts]
            x0, y0, z0 = (
                min(getattr(b, axis + "min") for b in bounds)
                for axis in ("x", "y", "z")
            )
            x1, y1, z1 = (
                max(getattr(b, axis + "max") for b in bounds)
                for axis in ("x", "y", "z")
            )
            side = next(
                (part for part in box_parts if part.component == "side_left"), None
            )
            drawer["box_mm"] = {
                "width": round(x1 - x0, 6),
                "depth": side.stock_mm[0] if side else round(y1 - y0, 6),
                "height": side.stock_mm[1] if side else round(z1 - z0, 6),
            }
            drawer["closed_position_mm"] = {"x": x0, "y": y0, "z": z0}
        front = next(
            (
                by_id[part_id]
                for part_id in drawer["part_ids"]
                if by_id[part_id].component in ("drawer_front", "face")
            ),
            None,
        )
        if front is not None:
            bounds = front.solid().val().BoundingBox()
            drawer["face_position_mm"] = {
                "x": bounds.xmin,
                "y": bounds.ymin,
                "z": bounds.zmin,
            }
            drawer["face_mm"] = {
                "width": bounds.xlen,
                "height": bounds.zlen,
                "thickness": bounds.ylen,
            }
    return {
        "layout": asdict(assembly.layout),
        "parts": parts,
        "drawers": list(drawers.values()),
        "viewer": {
            "parts": viewer_parts,
            "cutting_groups": cutting_groups,
            "drawers": list(drawers.values()),
        },
        "hardware_status": assembly.hardware_status,
        "hardware": assembly.hardware,
        "status": "draft",
        "manufacturing_ready": False,
    }


def evaluate_assembly(assembly: ProfileAssembly) -> list[dict]:
    """Check cap contact and interference with profiled box panels."""
    caps = [p for p in assembly.parts if p.component == "cap"]
    boxes = [
        p
        for p in assembly.parts
        if isinstance(p, ProfilePart)
        and p.component in ("side_left", "side_right", "divider", "bottom", "back")
    ]
    issues = []
    for panel in boxes:
        shape = panel.solid()
        if panel.component in ("side_left", "side_right", "divider") and caps:
            distance = min(cap.solid().val().distance(shape.val()) for cap in caps)
            if distance > 0.01:
                issues.append(
                    {
                        "severity": "error",
                        "code": "cap.contact",
                        "part": panel.id,
                        "distance_mm": distance,
                    }
                )
        for cap in caps:
            volume = cap.solid().intersect(shape).val().Volume()
            if volume > 0.01:
                issues.append(
                    {
                        "severity": "error",
                        "code": "cap.overlap",
                        "part": panel.id,
                        "cap": cap.id,
                        "volume_mm3": volume,
                    }
                )
    return issues

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
) -> ProfileAssembly:
    """Place row-owned caps, their boxes and a support frame on a native layout."""
    if not boxes or len({box.name for box in boxes}) != len(boxes):
        raise ValueError("assembly needs distinct profiled boxes")
    panels = {box.name: box_parts(box, roof) for box in boxes}
    heights = {
        box.name: max(z for _, z in panels[box.name][-1].profile_xz_mm) for box in boxes
    }
    anchor = boxes[0]
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
    parts.extend(part.placed(origin) for part in caps)
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
class ProfileFaceSpec:
    """Explicit face and drawer inputs for the composite assembly."""

    drawer: dict
    drawer_box_bottom_clearance_mm: float
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
        if not self.drawer.get("slide_key"):
            raise ValueError("drawer slide must be selected explicitly")


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

    top_points = [(x0, top(x0))]
    top_points.extend((x, top(x)) for x in breaks if x0 < x < x1)
    top_points.append((x1, top(x1)))
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


def assembly_faces(spec: ProfileAssemblySpec, cfg, placement, row_origin):
    """Resolve upper fronts and lower drawer using existing native builders."""
    from .cabinet import face_layout
    from .drawer import DrawerConfig, build_drawer, drawer_part_offsets
    from .joinery import DrawerJoineryStyle

    face = spec.faces
    if face is None:
        return ()
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
    _, drawer_parts = build_drawer(drawer)
    offsets = drawer_part_offsets(drawer)
    names = {
        "drawer_side_L": ("side_left", "side_L"),
        "drawer_side_R": ("side_right", "side_R"),
        "drawer_sub_front": ("inner_front", "sub_front"),
        "drawer_back": ("inner_back", "back"),
        "drawer_bottom": ("bottom", "bottom"),
    }
    origin = (
        placement.origin_mm[0] + cfg.side_thickness + drawer.side_gap,
        placement.origin_mm[1] + drawer.front_gap,
        placement.origin_mm[2]
        + cfg.bottom_thickness
        + face.drawer_box_bottom_clearance_mm,
    )
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
                f"{spec.lower}.drawer.{component}",
                spec.lower,
                component,
                cfg.carcass_material,
                shape,
                LocalFrame(local_origin, *axes),
                stock,
            )
        )
    panels = face_layout(
        [cfg], face_thickness=face.thickness_mm, face_top_style="plain"
    )
    drawer_bottom = cfg.bottom_thickness - drawer.face_overlay_bottom
    drawer_top = cfg.bottom_thickness + drawer.opening_height + drawer.face_overlay_top
    door_gap = cfg.face_gap_mm if cfg.door_gap_mm is None else cfg.door_gap_mm
    drawer_gap = (
        cfg.face_gap_mm if cfg.drawer_front_gap_mm is None else cfg.drawer_front_gap_mm
    )
    mixed_gap = max(door_gap, drawer_gap)
    for panel in panels:
        if panel.kind not in ("door", "drawer_face"):
            continue
        component = "door" if panel.kind == "door" else "face"
        prefix = "face" if component == "door" else "drawer"
        bottom = drawer_top + mixed_gap if component == "door" else drawer_bottom
        top = panel.z + panel.height if component == "door" else drawer_top
        if top <= bottom:
            raise ValueError("drawer overlay leaves no usable face height")
        points = (
            (panel.x, bottom),
            (panel.x + panel.width, bottom),
            (panel.x + panel.width, top),
            (panel.x, top),
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
                (panel.width, top - bottom, face.thickness_mm),
                orientation="back",
                world_offset_mm=placement.origin_mm,
            )
        )
    door_gap = cfg.face_gap_mm if cfg.door_gap_mm is None else cfg.door_gap_mm
    for i, box in enumerate(spec.boxes):
        x0 = box.x_mm + (face.outer_reveal_mm if i == 0 else door_gap / 2)
        x1 = (
            box.x_mm
            + box.width_mm
            - (face.outer_reveal_mm if i == len(spec.boxes) - 1 else door_gap / 2)
        )
        parts.append(
            profile_face(
                spec.roof,
                name=f"{box.name}.door",
                owner=box.name,
                face_type="door",
                x0=x0,
                x1=x1,
                bottom=face.outer_reveal_mm,
                thickness=face.thickness_mm,
                outer_reveal=face.roof_reveal_mm,
                depth_offset=face.depth_offset_mm,
                material=face.material,
            ).placed(row_origin)
        )
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

    generated = assembly_faces(
        spec, cfg, SimpleNamespace(origin_mm=(0, 0, 0)), (0, 0, 0)
    )
    box_x = {box.name: box.x_mm for box in spec.boxes}
    envelopes = {}
    for part in generated:
        if not isinstance(part, ProfilePart):
            continue
        shift = box_x.get(part.owner, 0)
        xs = [x - shift for x, _ in part.profile_xz_mm]
        zs = [z for _, z in part.profile_xz_mm]
        envelopes[part.owner] = (
            Bounds3D(
                min(xs),
                part.y_mm,
                min(zs),
                max(xs),
                part.y_mm + part.extrusion_mm,
                max(zs),
            )
            if part.owner not in envelopes
            else _bounds_union(
                envelopes[part.owner],
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
            instance_id = f"{part.owner}.drawer"
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
    for index, (signature, members) in enumerate(sorted(groups_by_signature.items()), 1):
        material, dimensions = signature
        label = members[0]["component"].replace("_", " ").title()
        cutting_groups.append({
            "id": f"profile-group-{index}",
            "label": label,
            "quantity": sum(member["quantity"] for member in members),
            "material": material,
            "members": [member["id"] for member in members],
            "blank_mm": dict(zip(("length", "width", "thickness"), dimensions, strict=True)),
        })
    drawers = {}
    for part in parts:
        viewer = viewer_parts[part["id"]]
        if viewer.get("instance_id"):
            drawer = drawers.setdefault(viewer["instance_id"], {
                "instance_id": viewer["instance_id"],
                "drawer_index": 1,
                "cabinet_id": part["owner"],
                "box_mm": {"depth": viewer.get("display_open_distance_mm", 0)},
            })
            if viewer.get("display_open_distance_mm"):
                drawer["box_mm"]["depth"] = viewer["display_open_distance_mm"]
    return {
        "layout": asdict(assembly.layout),
        "parts": parts,
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
        and p.component in ("side_left", "side_right", "bottom", "back")
    ]
    issues = []
    for panel in boxes:
        shape = panel.solid()
        if panel.component in ("side_left", "side_right") and caps:
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

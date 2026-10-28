"""Rectangular clear-space resolution and CAD-independent physical part plans.

Coordinates are millimetres, with X left-to-right, Y front-to-back, and Z up.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any

from .cabinet import CabinetConfig, back_capture_geometry, carcass_panel
from .drawer import DEFAULT_VERTICAL_GAP, DrawerConfig, drawer_part_offsets
from .door import DoorConfig
from .hardware import OverlayType, get_slide
from .joinery import DrawerJoineryStyle


@dataclass(frozen=True)
class Fixed:
    mm: float


@dataclass(frozen=True)
class Fr:
    weight: int = 1


@dataclass(frozen=True)
class DrawerBox:
    name: str
    bottom_clearance: float
    height: float | str = "fit"
    top_clearance: float | None = None
    slide_key: str = "blum_tandem_550h"
    side_thickness: float = 15
    front_back_thickness: float = 15
    bottom_thickness: float | None = None
    bottom_dado_depth: float = 6
    bottom_dado_inset: float | None = None
    front_gap: float = 2
    joinery_style: str = "butt"
    material: str = "baltic_birch"
    bottom_material: str = "baltic_birch"


@dataclass(frozen=True)
class Divider:
    name: str
    thickness: float = 18
    role: str = "structural"
    material: str = "baltic_birch"
    recess: float | None = None


@dataclass(frozen=True)
class Split:
    axis: str
    children: tuple[Space | Divider, ...] | list[Space | Divider]
    allowance_edge: str | None = None


@dataclass(frozen=True)
class Space:
    name: str
    size: Fixed | Fr | None = None
    split: Split | None = None
    content: DrawerBox | None = None


@dataclass(frozen=True)
class Door:
    name: str
    covers: str
    hinge_key: str = "blum_clip_top_blumotion_110_full"
    thickness: float = 18
    material: str = "finished_wood"


@dataclass(frozen=True)
class AppliedDrawerFront:
    name: str
    covers: str
    attached_to: str
    thickness: float = 18
    material: str = "finished_wood"


@dataclass(frozen=True)
class Carcass:
    width: float
    height: float
    depth: float
    side_thickness: float = 18
    bottom_thickness: float = 18
    top_thickness: float = 18
    back_thickness: float = 6
    material: str = "baltic_birch"
    back_material: str = "plywood"
    face_gap: float = 2


@dataclass(frozen=True)
class PhysicalPartPlan:
    parts: list[dict[str, Any]]
    contacts: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class ResolvedModel:
    spaces: list[dict[str, Any]]
    dividers: list[dict[str, Any]]
    allowances: list[dict[str, Any]]
    contents: list[dict[str, Any]]
    fronts: list[dict[str, Any]]
    part_plan: PhysicalPartPlan
    inputs: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResolvedModel:
        data = dict(data)
        data["part_plan"] = PhysicalPartPlan(**data["part_plan"])
        return cls(**data)


def _number(value: float, label: str, *, zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (value < 0 if zero else value <= 0):
        raise ValueError(f"{label}: expected a {'nonnegative' if zero else 'positive'} finite number")
    return value


def _integer(value: float, label: str, *, zero: bool = False) -> int:
    value = _number(value, label, zero=zero)
    if value != int(value):
        raise ValueError(f"{label}: incompatible fractional millimetre value {value:g}")
    return int(value)


def _name(name: str, path: str) -> None:
    if not isinstance(name, str) or not name or "/" in name or name in (".", ".."):
        raise ValueError(f"{path}: invalid name {name!r}")


def _input(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {"type": type(value).__name__, **{k: _input(getattr(value, k)) for k in value.__dataclass_fields__}}
    if isinstance(value, (list, tuple)):
        return [_input(v) for v in value]
    return value


def resolve_model(carcass: Carcass, root: Space, fronts: tuple[Door | AppliedDrawerFront, ...] | list[Door | AppliedDrawerFront] = ()) -> ResolvedModel:
    """Resolve an applied-back, butt carcass and its rectangular clear spaces."""
    for k in ("width", "height", "depth", "side_thickness", "bottom_thickness", "top_thickness", "back_thickness"):
        _number(getattr(carcass, k), f"carcass.{k}")
    _number(carcass.face_gap, "carcass.face_gap", zero=True)
    cfg = CabinetConfig(width=carcass.width, height=carcass.height, depth=carcass.depth,
                        side_thickness=carcass.side_thickness, bottom_thickness=carcass.bottom_thickness,
                        top_thickness=carcass.top_thickness, back_thickness=carcass.back_thickness,
                        back_capture="overlay")
    dims = tuple(_integer(v, f"root {a}") for a, v in zip(("width", "depth", "height"), (cfg.interior_width, cfg.interior_depth, cfg.interior_height)))
    spaces, dividers, allowances, contents, faces, parts = [], [], [], [], [], []
    active: set[int] = set()
    contacts: list[dict[str, str]] = []
    contact_keys: set[tuple[str, str, str]] = set()
    part_ids: set[str] = set()

    def contact(a: str | None, b: str | None, kind: str) -> None:
        if a is None or b is None or a == b:
            return
        a, b = sorted((a, b))
        key = (a, b, kind)
        if key not in contact_keys:
            contact_keys.add(key)
            contacts.append(dict(part_a=a, part_b=b, type=kind))

    def part(id: str, kind: str, origin: tuple, size: tuple, material: str, thickness: float, **extra: Any) -> None:
        if id in part_ids:
            raise ValueError(f"duplicate part ID {id}: choose different space or part names")
        part_ids.add(id)
        if any(v <= 0 for v in size):
            raise ValueError(f"{id}: invalid part dimensions {size}")
        parts.append(dict(id=id, kind=kind, origin=list(origin), size=list(size), bounds=[list(origin), [a+b for a,b in zip(origin,size)]], material=material, thickness=thickness, profile={"type": "box", "size": list(size)}, stock={"dimensions": list(size), "thickness": thickness}, transform={"translation": list(origin), "axes": [[1,0,0],[0,1,0],[0,0,1]]}, operations=[], **extra))

    # Existing panel dimension helpers are the source of butt carcass stock.
    side = carcass_panel(cfg, "side")
    bottom = carcass_panel(cfg, "bottom")
    top = carcass_panel(cfg, "top")
    back = back_capture_geometry(cfg)
    part("/carcass/side_left", "carcass", (0,0,0), (carcass.side_thickness,side.width,carcass.height), carcass.material, carcass.side_thickness)
    part("/carcass/side_right", "carcass", (carcass.width-carcass.side_thickness,0,0), (carcass.side_thickness,side.width,carcass.height), carcass.material, carcass.side_thickness)
    part("/carcass/bottom", "carcass", (carcass.side_thickness,0,0), (bottom.length,bottom.width,carcass.bottom_thickness), carcass.material, carcass.bottom_thickness)
    part("/carcass/top", "carcass", (carcass.side_thickness,0,carcass.height-carcass.top_thickness), (top.length,top.width,carcass.top_thickness), carcass.material, carcass.top_thickness)
    part("/carcass/back", "carcass", (0,carcass.depth-carcass.back_thickness,0), (back.width,carcass.back_thickness,back.height), carcass.back_material, carcass.back_thickness)

    for member in ("side_left", "side_right", "bottom", "top"):
        contact("/carcass/back", "/carcass/" + member, "butt")
    for side_name in ("side_left", "side_right"):
        for panel_name in ("bottom", "top"):
            contact("/carcass/" + side_name, "/carcass/" + panel_name, "butt")

    def visit(space: Space, path: str, origin: tuple, size: tuple, boundaries: dict[str, str | None]) -> None:
        if id(space) in active:
            raise ValueError(f"{path}: cyclic space tree")
        active.add(id(space))
        spaces.append(dict(id=path, origin=list(origin), size=list(size), boundaries=dict(boundaries)))
        if space.split and space.content:
            raise ValueError(f"{path}: a space cannot contain both a split and content")
        if space.content:
            box = space.content
            _name(box.name, path)
            cid = path + "/" + box.name
            bottom_clear = _number(box.bottom_clearance, cid + " bottom clearance", zero=True)
            top_clear = _number(box.top_clearance, cid + " top clearance", zero=True) if box.top_clearance is not None else (DEFAULT_VERTICAL_GAP if box.height == "fit" else 0)
            height = size[2] - bottom_clear - top_clear if box.height == "fit" else _number(box.height, cid + " height")
            if height <= 0 or height + bottom_clear + top_clear > size[2]:
                raise ValueError(f"{cid}: drawer box does not fit its allocated space")
            for key in ("side_thickness", "front_back_thickness", "bottom_dado_depth"):
                _number(getattr(box, key), cid + " " + key)
            for key in ("front_gap", "bottom_dado_inset"):
                if getattr(box, key) is not None:
                    _number(getattr(box, key), cid + " " + key, zero=True)
            if box.bottom_thickness is not None:
                _number(box.bottom_thickness, cid + " bottom_thickness")
            try:
                d = DrawerConfig(opening_width=size[0], opening_height=size[2], opening_depth=size[1], slide_key=box.slide_key,
                    side_thickness=box.side_thickness, front_back_thickness=box.front_back_thickness, bottom_thickness=box.bottom_thickness,
                    bottom_dado_depth=box.bottom_dado_depth, bottom_dado_inset=box.bottom_dado_inset, front_gap=box.front_gap,
                    vertical_gap=size[2] - height - get_slide(box.slide_key).min_bottom_clearance,
                    use_standard_height=False, applied_face=False, joinery_style=DrawerJoineryStyle(box.joinery_style))
                if bottom_clear < d.slide.min_bottom_clearance or d.box_width <= 2*d.side_thickness or d.box_depth > size[1] or d.box_depth <= 2*d.front_back_thickness or d.bottom_dado_depth <= 0 or d.bottom_dado_depth > min(d.side_thickness, d.front_back_thickness) or d.bottom_dado_inset + d.bottom_thickness > height:
                    raise ValueError("drawer recipe does not fit")
                offsets = drawer_part_offsets(d)
                box_origin = (origin[0]+d.side_gap, origin[1]+d.front_gap, origin[2]+bottom_clear)
                box_size = (d.box_width, d.box_depth, height)
                if any(start < low or start + length > low + span for start, length, low, span in zip(box_origin, box_size, origin, size)):
                    raise ValueError("drawer box extends outside its allocated space")
                sizes = {"side_L": (d.side_thickness,d.side_panel_length,height), "side_R": (d.side_thickness,d.side_panel_length,height), "sub_front": (d.front_back_panel_length,d.front_back_thickness,height), "back": (d.front_back_panel_length,d.front_back_thickness,height), "bottom": (d.bottom_panel_width,d.bottom_panel_depth,d.bottom_thickness)}
                for name, sz in sizes.items():
                    p = tuple(a+b for a,b in zip(box_origin, offsets[name]))
                    part(cid+"/"+name, "drawer_"+name, p, sz, box.bottom_material if name == "bottom" else box.material, d.bottom_thickness if name == "bottom" else (d.side_thickness if name.startswith("side") else d.front_back_thickness), owner=cid, motion_group=cid)
                    if name != "bottom":
                        parts[-1]["operations"].append(dict(type="bottom_dado", inset=d.bottom_dado_inset, depth=d.bottom_dado_depth, width=d.bottom_thickness, side=name))
                        parts[-1]["operations"].append(dict(type="drawer_corner", style=box.joinery_style, side=name, parameters=asdict(d.joinery) | {"style": box.joinery_style}))
                for wall in ("side_L", "side_R", "sub_front", "back"):
                    contact(cid + "/bottom", cid + "/" + wall, "bottom_groove")
                for side_name in ("side_L", "side_R"):
                    for end_name in ("sub_front", "back"):
                        contact(cid + "/" + side_name, cid + "/" + end_name, "drawer_corner")
                contents.append(dict(id=cid, space=path, origin=list(box_origin), size=[d.box_width,d.box_depth,height], bottom_clearance=bottom_clear, top_clearance=top_clear, slide_key=box.slide_key))
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"{cid}: {exc}") from exc
        if space.split:
            split = space.split
            if split.axis not in ("width", "height"):
                raise ValueError(f"{path}: invalid split axis {split.axis!r}")
            axis = 0 if split.axis == "width" else 2
            edges = ("left", "right") if axis == 0 else ("bottom", "top")
            edge = split.allowance_edge or edges[1]
            if edge not in edges:
                raise ValueError(f"{path}: invalid allowance edge {edge!r}")
            children = split.children
            if not children or not isinstance(children[0], Space) or not isinstance(children[-1], Space):
                raise ValueError(f"{path}: split must start and end with a space")
            names = set()
            fixed = 0
            weighted = []
            for i, child in enumerate(children):
                if not isinstance(child, (Space, Divider)):
                    raise ValueError(f"{path}: invalid split child")
                _name(child.name, path)
                if child.name in names:
                    raise ValueError(f"{path}: duplicate child name {child.name!r}")
                names.add(child.name)
                if isinstance(child, Divider):
                    if not isinstance(children[i-1], Space) or not isinstance(children[i+1], Space):
                        raise ValueError(f"{path}/{child.name}: divider must separate spaces")
                    fixed += _integer(child.thickness, path + "/" + child.name + " thickness")
                elif isinstance(child.size, Fixed):
                    fixed += _integer(child.size.mm, path + "/" + child.name + " size")
                elif isinstance(child.size, Fr):
                    if isinstance(child.size.weight, bool) or not isinstance(child.size.weight, int) or child.size.weight <= 0:
                        raise ValueError(f"{path}/{child.name}: fr weight must be a positive integer")
                    weighted.append(child)
                else:
                    raise ValueError(f"{path}/{child.name}: split child needs Fixed or Fr size")
            budget = size[axis] - fixed
            if budget < 0:
                raise ValueError(f"{path}: split overfills by {-budget} mm")
            if not weighted and budget:
                raise ValueError(f"{path}: split has {budget} mm unallocated; add a flexible space")
            weight = sum(c.size.weight for c in weighted)
            allocation = {id(c): budget*c.size.weight//weight for c in weighted} if weighted else {}
            slack = budget - sum(allocation.values()) if weighted else 0
            if any(n <= 0 for n in allocation.values()):
                raise ValueError(f"{path}: flexible space resolves to zero")
            cursor = origin[axis] + (slack if edge == edges[0] else 0)
            if slack:
                ao = list(origin); ao[axis] = origin[axis] if edge == edges[0] else origin[axis]+size[axis]-slack
                az = list(size); az[axis] = slack
                allowances.append(dict(owner=path, edge=edge, origin=ao, size=az))
            for index, child in enumerate(children):
                length = _integer(child.thickness, path) if isinstance(child, Divider) else (_integer(child.size.mm, path) if isinstance(child.size, Fixed) else allocation[id(child)])
                co = list(origin); co[axis] = cursor
                cs = list(size); cs[axis] = length
                child_path = path + "/" + child.name
                if isinstance(child, Divider):
                    if child.role not in ("structural", "adjustable") or (child.role == "adjustable" and axis != 2):
                        raise ValueError(f"{child_path}: adjustable dividers must be horizontal")
                    recess = child.recess if child.recess is not None else (3 if child.role == "adjustable" else 0)
                    _number(recess, child_path + " recess", zero=True)
                    if recess >= cs[1]: raise ValueError(f"{child_path}: recess exceeds depth")
                    co[1] += recess; cs[1] -= recess
                    dividers.append(dict(id=child_path, owner=path, axis=split.axis, role=child.role, origin=co, size=cs, recess=recess))
                    part(child_path, "divider", tuple(co), tuple(cs), child.material, length, owner=path, role=child.role)
                    # The panel spans the parent in the perpendicular direction.
                    ends = ("bottom", "top") if axis == 0 else ("left", "right")
                    for boundary in (*ends, "back"):
                        contact(child_path, boundaries[boundary], "butt")
                else:
                    cb = dict(boundaries)
                    low, high = (("left", "right") if axis == 0 else ("bottom", "top"))
                    before = children[index-1] if index else None
                    after = children[index+1] if index+1 < len(children) else None
                    cb[low] = (path + "/" + before.name if isinstance(before, Divider) else boundaries[low] if before is None and not (slack and edge == edges[0]) else None)
                    cb[high] = (path + "/" + after.name if isinstance(after, Divider) else boundaries[high] if after is None and not (slack and edge == edges[1]) else None)
                    visit(child, child_path, tuple(co), tuple(cs), cb)
                cursor += length
        active.remove(id(space))

    _name(root.name, "root")
    if root.size is not None: raise ValueError("root: size comes from carcass")
    visit(root, "/"+root.name, (carcass.side_thickness,0,carcass.bottom_thickness), dims,
          dict(left="/carcass/side_left", right="/carcass/side_right", bottom="/carcass/bottom", top="/carcass/top", back="/carcass/back"))
    def reference(ref: str, records: list[dict], kind: str) -> dict:
        matches = [r for r in records if r["id"] == ref or (not ref.startswith("/") and r["id"].rsplit("/",1)[-1] == ref)]
        if len(matches) != 1:
            raise ValueError(f"{kind} reference {ref!r} is {'ambiguous' if matches else 'unknown'}")
        return matches[0]

    selected = []
    seen = set()
    for front in fronts:
        _name(front.name, "front")
        if front.name in seen: raise ValueError(f"front: duplicate name {front.name!r}")
        seen.add(front.name)
        if not isinstance(front, (Door, AppliedDrawerFront)): raise ValueError("invalid front")
        _number(front.thickness, f"front/{front.name} thickness")
        region = reference(front.covers, spaces, "coverage")
        attachment = None
        if isinstance(front, AppliedDrawerFront):
            attachment = reference(front.attached_to, contents, "drawer attachment")
            if not (attachment["space"] == region["id"] or attachment["space"].startswith(region["id"] + "/")):
                raise ValueError(f"front/{front.name}: attachment is outside coverage {region['id']}")
        selected.append((front, region, attachment))

    for front, region, attachment in selected:
        x,y,z = region["origin"]; w,depth,h = region["size"]
        bounds = [x, x+w, z, z+h]
        inset = False
        if isinstance(front, Door):
            door = DoorConfig(opening_width=w, opening_height=h, hinge_key=front.hinge_key, door_thickness=front.thickness)
            inset = door.hinge.overlay_type == OverlayType.INSET
            if inset:
                bounds = [x+door.gap_side, x+w-door.gap_side, z+door.gap_bottom, z+h-door.gap_top]
            else:
                bounds[0], bounds[1] = x-door.hinge.overlay, x+w+door.hinge.overlay
        else:
            if x == carcass.side_thickness: bounds[0] = 0
            if x+w == carcass.width-carcass.side_thickness: bounds[1] = carcass.width
        # Boundaries shared by declared faces use the middle of any physical
        # divider and one half-reveal each. They do not change the spaces.
        for other, other_region, _ in selected:
            if other is front or inset: continue
            ox,_,oz = other_region["origin"]; ow,_,oh = other_region["size"]
            if max(x,ox) < min(x+w,ox+ow):
                for idx, a, b in ((2, oz+oh, z), (3, z+h, oz)):
                    if a > b: continue
                    between = [d for d in dividers if d["axis"] == "height" and d["origin"][2] == a and d["origin"][2]+d["size"][2] == b and d["origin"][0] <= x and d["origin"][0]+d["size"][0] >= x+w]
                    if a == b or between:
                        bounds[idx] = (a+b)/2 + (carcass.face_gap/2 if idx == 2 else -carcass.face_gap/2)
            if max(z,oz) < min(z+h,oz+oh):
                for idx, a, b in ((0, ox+ow, x), (1, x+w, ox)):
                    if a > b: continue
                    between = [d for d in dividers if d["axis"] == "width" and d["origin"][0] == a and d["origin"][0]+d["size"][0] == b and d["origin"][2] <= z and d["origin"][2]+d["size"][2] >= z+h]
                    if a == b or between:
                        bounds[idx] = (a+b)/2 + (carcass.face_gap/2 if idx == 0 else -carcass.face_gap/2)
        fid = "/front/"+front.name
        pos = (bounds[0], -front.thickness, bounds[2]); sz = (bounds[1]-bounds[0], front.thickness, bounds[3]-bounds[2])
        motion = attachment["id"] if attachment else fid
        part(fid, "door" if isinstance(front, Door) else "drawer_front", pos, sz, front.material, front.thickness, owner=region["id"], motion_group=motion)
        faces.append(dict(id=fid, covers=region["id"], attached_to=attachment["id"] if attachment else None, motion_group=motion, origin=list(pos), size=list(sz)))
    return ResolvedModel(spaces, dividers, allowances, contents, faces, PhysicalPartPlan(parts, contacts), dict(carcass=_input(carcass), root=_input(root), fronts=_input(fronts)))

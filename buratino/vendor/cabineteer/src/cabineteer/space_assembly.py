"""Resolve Space assemblies into one CAD-independent physical plan."""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations
import hashlib
from dataclasses import asdict, replace

from .allocation import Fixed, Fr, Natural
from .front_boundaries import resolve_front_boundaries
from .hardware import get_hinge, get_slide
from .joinery import DominoJoinery, DrawerJoineryStyle, component_domino_rows, validate_domino_joinery
from .layout import CabinetRef, Frame, Row, Stack, resolve_layout
from .spaces import (AppliedDrawerFront, AppliedFaceboard, AssemblyRef, Carcass,
                     Divider, Door, DrawerBox, Insets, PhysicalPartPlan, ResolvedModel, Space, Split, _input, _integer,
                     _name, _number, resolve_model)
from .space_parts import box_part, check_box_part, update_box_part


def _bounds(origin, size):
    return dict(zip(("min_x", "min_y", "min_z", "max_x", "max_y", "max_z"),
                    (*origin, *(a + b for a, b in zip(origin, size)))))


def _bounds_dict(bounds):
    return asdict(bounds)


def _part_bounds(parts):
    """Return physical bounds, or None when the plan contains no parts."""
    if not parts:
        return None
    return ({"min_" + axis: min(part["bounds"][0][i] for part in parts)
             for i, axis in enumerate("xyz")} |
            {"max_" + axis: max(part["bounds"][1][i] for part in parts)
             for i, axis in enumerate("xyz")})


def _validate_size_request(value, path, *, natural=False, integer=False):
    if isinstance(value, Fr):
        if isinstance(value.weight, bool) or not isinstance(value.weight, int) or value.weight <= 0:
            raise ValueError(f"{path}: Fr weight must be a positive integer")
    elif isinstance(value, Natural) and natural:
        return
    else:
        number = value.mm if isinstance(value, Fixed) else value
        (_integer if integer else _number)(number, path)


def _validate_carcass(carcass, path):
    if not isinstance(carcass, Carcass):
        raise ValueError(f"{path}: expected Carcass")
    validate_domino_joinery(carcass.joinery, path + ".joinery")
    for axis in ("width", "height"):
        _validate_size_request(getattr(carcass, axis), f"{path}.{axis}")
    _number(carcass.depth, path + ".depth")
    for field in ("side_thickness", "bottom_thickness", "top_thickness", "back_thickness"):
        _number(getattr(carcass, field), f"{path}.{field}")
    for field in ("door_gap", "drawer_front_gap", "outer_reveal"):
        _number(getattr(carcass, field), f"{path}.{field}", zero=True)
    for field, stock in (("width", 2 * carcass.side_thickness),
                         ("height", carcass.bottom_thickness + carcass.top_thickness),
                         ("depth", carcass.back_thickness)):
        value = getattr(carcass, field)
        if isinstance(value, Fixed):
            value = value.mm
        if not isinstance(value, Fr):
            _integer(value - stock, f"{path} clear {field}")


def _validate_space_inputs(space, path, *, root=False):
    """Validate authored Space recipes without needing an allocated host box."""
    _name(space.name, path)
    if root and space.size is not None:
        raise ValueError(f"{path}: root size comes from its host")
    if not root:
        if not isinstance(space.size, (Fixed, Fr)):
            raise ValueError(f"{path}: split child needs Fixed or Fr size")
        _validate_size_request(space.size, path + " size", integer=True)
    if space.split is not None and space.content is not None:
        raise ValueError(f"{path}: a space cannot contain both a split and content")
    content = space.content
    if isinstance(content, AssemblyRef):
        _name(content.name, path)
        if not isinstance(content.insets, Insets):
            raise ValueError(f"{path}: expected Insets")
        for edge in ("left", "right", "front", "back", "bottom", "top"):
            _integer(getattr(content.insets, edge), f"{path}/{content.name} inset {edge}", zero=True)
    elif isinstance(content, DrawerBox):
        _name(content.name, path)
        validate_domino_joinery(content.corner_joinery, path + ".corner_joinery")
        if content.corner_joinery is not None and content.joinery_style != "butt":
            raise ValueError(f"{path}: corner_joinery requires butt drawer geometry")
        label = f"{path}/{content.name}"
        _number(content.bottom_clearance, label + " bottom_clearance", zero=True)
        if content.height != "fit":
            _number(content.height, label + " height")
        for field in ("top_clearance", "bottom_dado_inset"):
            if getattr(content, field) is not None:
                _number(getattr(content, field), f"{label} {field}", zero=True)
        _number(content.front_gap, label + " front_gap", zero=True)
        for field in ("side_thickness", "front_back_thickness", "bottom_dado_depth"):
            _number(getattr(content, field), f"{label} {field}")
        if content.bottom_thickness is not None:
            _number(content.bottom_thickness, label + " bottom_thickness")
        try:
            get_slide(content.slide_key)
            DrawerJoineryStyle(content.joinery_style)
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"{label}: {exc}") from exc
    elif content is not None:
        raise ValueError(f"{path}: invalid space content")
    split = space.split
    if split is None:
        return
    if not isinstance(split, Split) or split.axis not in ("width", "height"):
        raise ValueError(f"{path}: invalid split")
    edges = ("left", "right") if split.axis == "width" else ("bottom", "top")
    if split.allowance_edge is not None and split.allowance_edge not in edges:
        raise ValueError(f"{path}: invalid allowance edge {split.allowance_edge!r}")
    children = split.children
    if not children or not isinstance(children[0], Space) or not isinstance(children[-1], Space):
        raise ValueError(f"{path}: split must start and end with a space")
    names = set()
    for index, child in enumerate(children):
        if not isinstance(child, (Space, Divider)):
            raise ValueError(f"{path}: invalid split child")
        _name(child.name, path)
        if child.name in names:
            raise ValueError(f"{path}: duplicate child name {child.name!r}")
        names.add(child.name)
        if isinstance(child, Divider):
            if not isinstance(children[index-1], Space) or not isinstance(children[index+1], Space):
                raise ValueError(f"{path}/{child.name}: divider must separate spaces")
            validate_domino_joinery(child.joinery, f"{path}/{child.name}.joinery", inherit=True)
            if child.role == "adjustable" and isinstance(child.joinery, DominoJoinery):
                raise ValueError(f"{path}/{child.name}: adjustable divider cannot have fixed joinery")
            _integer(child.thickness, f"{path}/{child.name} thickness")
            if child.role not in ("structural", "adjustable") or (child.role == "adjustable" and split.axis != "height"):
                raise ValueError(f"{path}/{child.name}: invalid divider role")
            if child.recess is not None:
                _number(child.recess, f"{path}/{child.name} recess", zero=True)
            if child.depth is not None:
                _number(child.depth, f"{path}/{child.name} depth")


def _validate_front_references(root, fronts, path):
    """Validate local front references without allocating or building a model."""
    if not isinstance(root, Space):
        if fronts:
            raise ValueError(f"{path}: fronts require a bare Space root")
        return
    spaces, drawers = [], []
    active = set()

    def collect(space, local):
        if id(space) in active:
            raise ValueError(f"{path}{local}: cyclic space tree")
        active.add(id(space))
        _name(space.name, path + local)
        spaces.append(local)
        if space.split and space.content:
            raise ValueError(f"{path}{local}: a space cannot contain both a split and content")
        if isinstance(space.content, DrawerBox):
            _name(space.content.name, path + local)
            drawers.append((local + "/" + space.content.name, local))
        if space.split:
            names = [child.name for child in space.split.children]
            if len(names) != len(set(names)):
                raise ValueError(f"{path}{local}: duplicate child name")
            for child in space.split.children:
                if isinstance(child, Space):
                    collect(child, local + "/" + child.name)
        active.remove(id(space))

    collect(root, "/" + root.name)

    def reference(value, candidates, kind):
        if not isinstance(value, str):
            raise ValueError(f"{path}: invalid {kind} reference {value!r}")
        matches = [candidate for candidate in candidates
                   if candidate == value or (not value.startswith("/") and candidate.rsplit("/", 1)[-1] == value)]
        if len(matches) != 1:
            raise ValueError(f"{path}: {kind} reference {value!r} is {'ambiguous' if matches else 'unknown'}")
        return matches[0]

    names = set()
    for front in fronts:
        if not isinstance(front, (Door, AppliedDrawerFront, AppliedFaceboard)):
            raise ValueError(f"{path}: invalid front")
        _name(front.name, path + "/front")
        if front.name in names:
            raise ValueError(f"{path}: duplicate front name {front.name!r}")
        names.add(front.name)
        _number(front.thickness, path + "/front/" + front.name + " thickness")
        if isinstance(front, Door) and front.hinge_side not in ("left", "right"):
            raise ValueError(f"{path}/front/{front.name}: invalid hinge side")
        if isinstance(front, Door):
            try:
                get_hinge(front.hinge_key)
            except (KeyError, TypeError) as exc:
                raise ValueError(f"{path}/front/{front.name}: {exc}") from exc
        if isinstance(front, AppliedFaceboard) and front.boundary_gap is not None:
            _number(front.boundary_gap, path + "/front/" + front.name + " boundary gap", zero=True)
        if isinstance(front, AppliedDrawerFront) and front.top_reveal is not None:
            _number(front.top_reveal, path + "/front/" + front.name + " top reveal", zero=True)
        coverage = reference(front.covers, spaces, "coverage")
        if isinstance(front, AppliedDrawerFront):
            attachment = reference(front.attached_to, [ident for ident, _ in drawers], "drawer attachment")
            owner = next(owner for ident, owner in drawers if ident == attachment)
            if not (owner == coverage or owner.startswith(coverage + "/")):
                raise ValueError(f"{path}/front/{front.name}: attachment is outside coverage {coverage}")


def _validate_graph(project, definitions, modules):
    """Check all definitions, including unused entries, before building parts."""
    active = set()
    done = set()

    def definition(kind, name, path):
        registry = definitions if kind == "cabinet" else modules
        if name not in registry:
            raise ValueError(f"{path}: unknown {kind} {name!r}")
        key = (kind, name)
        if key in active:
            raise ValueError(f"{path}: cyclic {kind} reference {name!r}")
        if key in done:
            return
        active.add(key)
        item = registry[name]
        item_path = path + "/" + name
        if kind == "cabinet":
            _validate_carcass(item.carcass, item_path + "/carcass")
            if not isinstance(item.root, Space):
                raise ValueError(f"{item_path}: cabinet root must be a Space")
        else:
            if not isinstance(item.root, (Space, Row, Stack)):
                raise ValueError(f"{item_path}: module root must be a Space, Row or Stack")
            for axis in ("size_x", "size_y", "size_z"):
                value = getattr(item, axis)
                if not isinstance(value, (Fixed, Fr, Natural)):
                    raise ValueError(f"{item_path}: invalid {axis} request")
                _validate_size_request(value, item_path + "/" + axis, natural=True)
        visit(item.root, item_path, set())
        _validate_front_references(item.root, item.fronts, item_path)
        active.remove(key)
        done.add(key)

    def visit(node, path, objects, *, space_root=True):
        key = id(node)
        if key in objects:
            raise ValueError(f"{path}: cyclic input tree")
        if isinstance(node, CabinetRef):
            _name(node.name, path)
            definition("cabinet", node.definition, path)
        elif isinstance(node, Space):
            objects.add(key)
            _validate_space_inputs(node, path, root=space_root)
            if node.split:
                for child in node.split.children:
                    if isinstance(child, Space):
                        visit(child, path + "/" + child.name, objects, space_root=False)
            if isinstance(node.content, AssemblyRef):
                definition("module", node.content.module, path + "/" + node.content.name)
            objects.remove(key)
        elif isinstance(node, (Row, Stack)):
            objects.add(key)
            _name(node.name, path)
            for axis in ("size_x", "size_z"):
                request = getattr(node, axis)
                if not isinstance(request, (Fixed, Fr, Natural)):
                    raise ValueError(f"{path}: invalid {axis} request")
                _validate_size_request(request, path + "/" + axis, natural=True)
            _number(node.gap_mm, path + " gap", zero=True)
            if isinstance(node, Stack) and node.depth_mm is not None:
                _number(node.depth_mm, path + " depth")
            if not node.children or any(not isinstance(child, (CabinetRef, Frame, Row, Stack)) for child in node.children):
                raise ValueError(f"{path}: invalid layout child")
            if len({child.name for child in node.children}) != len(node.children):
                raise ValueError(f"{path}: layout children must have distinct names")
            if node.alignment not in ("left", "center", "right", "bottom", "top") or node.depth_alignment not in ("front", "center", "back"):
                raise ValueError(f"{path}: invalid alignment")
            for child in node.children:
                visit(child, path + "/" + child.name, objects)
            objects.remove(key)
        elif isinstance(node, Frame):
            _name(node.name, path)
            node.rails()
        else:
            raise ValueError(f"{path}: invalid assembly node {type(node).__name__}")

    for name in definitions:
        definition("cabinet", name, "/definitions")
    for name in modules:
        definition("module", name, "/modules")
    if project.layout is not None:
        visit(project.layout, "/layout", set())
    if project.space_model is not None:
        _validate_carcass(project.space_model.carcass, "/host/carcass")
        visit(project.space_model.root, "/host", set())
        _validate_front_references(project.space_model.root, project.space_model.fronts, "/host")


def _intrinsic(node, axis, definitions, path):
    if isinstance(node, CabinetRef):
        carcass = definitions[node.definition].carcass
        request = (carcass.width, carcass.depth, carcass.height)[axis]
    elif isinstance(node, Frame):
        request = (node.width_mm, node.depth_mm, node.height_mm)[axis]
    elif isinstance(node, (Row, Stack)):
        request = (node.size_x, Natural(), node.size_z)[axis]
        if axis == 1 and isinstance(node, Stack) and node.depth_mm is not None:
            request = Fixed(node.depth_mm)
    else:
        raise ValueError(f"{path}: no intrinsic size")
    if isinstance(request, Fr):
        raise ValueError(f"{path}: Natural size depends on unresolved Fr")
    if isinstance(request, Fixed):
        return request.mm
    if isinstance(request, Natural):
        values = [_intrinsic(c, axis, definitions, path + "/" + c.name) for c in node.children]
        own_axis = 0 if isinstance(node, Row) else 2
        return sum(values) + node.gap_mm * (len(values)-1) if axis == own_axis else max(values)
    return request


def resolve_space_assembly(project):
    """Resolve layouts and recursively hosted modules using the Space builder."""
    definitions = {item.name: item for item in project.space_cabinets}
    modules = {item.name: item for item in project.space_modules}
    if len(definitions) != len(project.space_cabinets) or len(modules) != len(project.space_modules):
        raise ValueError("duplicate cabinet definition or module name")
    for name in (*definitions, *modules):
        _name(name, "registry")
    _validate_graph(project, definitions, modules)
    parts, contacts, spaces, dividers, allowances, contents, fronts = ([] for _ in range(7))
    placements, allocations, diagnostics = [], [], []
    active = []
    part_hosts = {}

    def add_model(model, prefix, offset, host=None, inherited=None):
        def qualify(value):
            return prefix + value if isinstance(value, str) and value.startswith("/") else value

        def shift(record):
            item = deepcopy(record)
            for key in ("id", "space", "owner", "covers", "attached_to", "motion_group", "part_a", "part_b"):
                if key in item and item[key] is not None:
                    item[key] = qualify(item[key])
            if "boundaries" in item:
                item["boundaries"] = {k: qualify(v) for k, v in item["boundaries"].items()}
            stock = item.get("stock")
            transform = item.get("transform")
            if isinstance(stock, dict) and "dimensions" in stock and isinstance(transform, dict) and "translation" in transform:
                update_box_part(item, translation=[a+b for a,b in zip(transform["translation"], offset)])
            else:
                if "origin" in item:
                    item["origin"] = [a+b for a,b in zip(item["origin"], offset)]
                if "bounds" in item:
                    item["bounds"] = [[a+b for a,b in zip(point, offset)] for point in item["bounds"]]
                if "transform" in item:
                    item["transform"]["translation"] = [a+b for a,b in zip(item["transform"]["translation"], offset)]
            for op in item.get("operations", []):
                op["part_id"] = qualify(op["part_id"])
                op["id"] = f"drawer/{op['part_id']}/{op['role']}"
            if "coverage" in item:
                item["coverage"] = [item["coverage"][0]+offset[0], item["coverage"][1]+offset[0], item["coverage"][2]+offset[2], item["coverage"][3]+offset[2]]
            if "boundary_policy" in item:
                policy = item["boundary_policy"]
                policy.update(id=item["id"], coverage=item["coverage"], plane=policy["plane"]+offset[1], instance=prefix)
            return item

        new_parts = [shift(p) for p in model.part_plan.parts]
        if host is not None:
            for part in new_parts:
                lo, hi = part["bounds"]
                if any(a < b - 1e-6 or c > d + 1e-6 for a,b,c,d in zip(lo, host[0], hi, host[1])):
                    raise ValueError(f"{part['id']}: part protrudes outside host clear space")
        if host is not None:
            part_hosts.update({part["id"]: host for part in new_parts})
        parts.extend(new_parts)
        contacts.extend(shift(c) for c in model.part_plan.contacts)
        new_spaces = [shift(s) for s in model.spaces]
        if inherited is not None:
            host_bounds, owners = inherited
            for space in new_spaces:
                for edge, axis, high in (("left", 0, False), ("right", 0, True), ("bottom", 2, False), ("top", 2, True), ("back", 1, True)):
                    coordinate = space["origin"][axis] + (space["size"][axis] if high else 0)
                    target = host_bounds[1 if high else 0][axis]
                    if space["boundaries"][edge] is None and abs(coordinate-target) < 1e-6:
                        space["boundaries"][edge] = owners.get(edge)
            for divider in model.dividers:
                part = next(p for p in new_parts if p["id"] == prefix + divider["id"])
                for edge, axis, high in (("left", 0, False), ("right", 0, True), ("bottom", 2, False), ("top", 2, True), ("back", 1, True)):
                    owner = owners.get(edge)
                    coordinate = part["bounds"][1 if high else 0][axis]
                    if owner and abs(coordinate - host_bounds[1 if high else 0][axis]) < 1e-6:
                        a, b = sorted((part["id"], owner))
                        contacts.append(dict(part_a=a, part_b=b, type="butt"))
        spaces.extend(new_spaces)
        dividers.extend(shift(s) for s in model.dividers)
        allowances.extend(shift(s) for s in model.allowances)
        new_contents = [shift(c) for c in model.contents]
        for content in new_contents:
            if "assembly_ref" in content:
                content["front_policy"] = {key: model.inputs["carcass"][key] for key in ("door_gap", "drawer_front_gap", "outer_reveal")}
        contents.extend(new_contents)
        fronts.extend(shift(f) for f in model.fronts)
        for content in new_contents:
            if "assembly_ref" in content:
                module_ref(content)

    def module_ref(content):
        ref = content["assembly_ref"]
        path = content["id"]
        name = ref["module"]
        if name not in modules:
            raise ValueError(f"{path}: unknown module {name!r}")
        key = ("module", name)
        if key in active:
            raise ValueError(f"{path}: cyclic module reference {name!r}")
        module = modules[name]
        ins = ref["insets"]
        values = [_integer(ins[k], f"{path} inset {k}", zero=True) for k in ("left", "right", "front", "back", "bottom", "top")]
        left, right, front, back, bottom, top = values
        host_origin, host_size = content["origin"], content["size"]
        available = [host_size[0]-left-right, host_size[1]-front-back, host_size[2]-bottom-top]
        if any(v <= 0 for v in available):
            raise ValueError(f"{path}: insets leave no available volume")
        origin = [host_origin[0]+left, host_origin[1]+front, host_origin[2]+bottom]
        host = (host_origin, [a+b for a,b in zip(host_origin, host_size)])
        active.append(key)
        try:
            root = module.root
            # A bare Space has no intrinsic finite size of its own.
            size = []
            for i, request in enumerate((module.size_x, module.size_y, module.size_z)):
                if isinstance(request, Fixed): value = request.mm
                elif isinstance(request, Fr):
                    if isinstance(request.weight, bool) or not isinstance(request.weight, int) or request.weight <= 0:
                        raise ValueError(f"{path}: Fr weight must be a positive integer")
                    value = available[i]
                elif isinstance(request, Natural) and not isinstance(root, Space): value = _intrinsic(root, i, definitions, path)
                else: raise ValueError(f"{path}: Natural module size depends on unresolved Fr")
                if value <= 0 or value > available[i]:
                    raise ValueError(f"{path}: module size exceeds host budget")
                size.append(value)
            wrapper_bounds = _bounds(origin, size)
            placements.append(dict(id=path, kind="assembly_ref", definition=name, origin=origin, size=size, structural_bounds=wrapper_bounds))
            for axis, budget, used in zip("xyz", available, size):
                allocations.append(dict(path=path, axis=axis, bounds=wrapper_bounds, used_span=used, slack=budget-used, scope="module_wrapper"))
            if isinstance(root, Space):
                shell = Carcass(width=size[0], depth=size[1], height=size[2], **content["front_policy"])
                add_model(resolve_model(shell, root, module.fronts, _bare=True, _defer_joinery=True), path, origin, host, (host, content["boundaries"]))
            else:
                layout(root, path, origin, size, host)
        finally:
            active.pop()

    def cabinet(definition, path, origin, size, host):
        key = ("cabinet", definition.name)
        if key in active:
            raise ValueError(f"{path}: cyclic cabinet reference {definition.name!r}")
        active.append(key)
        try:
            carcass = replace(definition.carcass, width=size[0], depth=size[1], height=size[2])
            placements.append(dict(id=path, kind="cabinet", definition=definition.name, origin=list(origin), size=list(size), structural_bounds=_bounds(origin, size)))
            add_model(resolve_model(carcass, definition.root, definition.fronts, _defer_joinery=True), path, origin, host)
        finally:
            active.pop()

    def layout(root, prefix, origin, available=None, host=None):
        resolved = resolve_layout(root, tuple(origin), definitions=definitions, available_size_mm=available)
        if available is not None:
            box = resolved.carcass_bounds_mm
            for axis, budget, used in zip("xyz", available, (box.width_mm, box.depth_mm, box.height_mm)):
                allocations.append(dict(path=prefix + "/" + root.name, axis=axis, bounds=_bounds_dict(box), used_span=used, slack=budget-used, scope="module_root"))
        for alloc in resolved.allocations:
            allocations.append(dict(path=prefix + "/" + alloc.path.lstrip("/"), bounds=_bounds_dict(alloc.bounds), used_span=alloc.used_span, slack=alloc.slack))
        for placement in resolved.placements:
            node, box = placement.node, placement.carcass_bounds_mm
            path = prefix + "/" + placement.path.lstrip("/")
            size = (box.width_mm, box.depth_mm, box.height_mm)
            if isinstance(node, CabinetRef):
                cabinet(definitions[node.definition], path, placement.origin_mm, size, host)
            elif isinstance(node, Frame):
                placements.append(dict(id=path, kind="frame", origin=list(placement.origin_mm), size=list(size), structural_bounds=_bounds_dict(box)))
                for rail in node.rails():
                    pos = [a+b for a,b in zip(placement.origin_mm, rail.origin_mm)]
                    sz = [rail.width_mm, rail.depth_mm, rail.height_mm]
                    axis = 1 if rail.name in ("front", "back") else 0
                    part = box_part(path+"/"+rail.name, "frame", sz, pos, node.material, node.stock_mm, axis)
                    if host and any(a < b-1e-6 or c > d+1e-6 for a,b,c,d in zip(part["bounds"][0], host[0], part["bounds"][1], host[1])):
                        raise ValueError(f"{part['id']}: part protrudes outside host clear space")
                    parts.append(part)
                for long_rail in ("front", "back"):
                    for side_rail in ("left", "right"):
                        a, b = sorted((path+"/"+long_rail, path+"/"+side_rail))
                        contacts.append(dict(part_a=a, part_b=b, type="butt"))
        return resolved.carcass_bounds_mm

    if project.space_model is not None:
        spec = project.space_model
        dims = (spec.carcass.width, spec.carcass.depth, spec.carcass.height)
        placements.append(dict(id="/cabinet", kind="cabinet", definition=None, origin=[0,0,0], size=list(dims), structural_bounds=_bounds((0,0,0), dims)))
        add_model(resolve_model(spec.carcass, spec.root, spec.fronts, _defer_joinery=True), "/cabinet", (0,0,0))
        structural = _bounds((0,0,0), dims)
    else:
        if project.layout is None:
            raise ValueError("Space assembly requires a layout")
        structural = _bounds_dict(layout(project.layout, "", (0,0,0)))

    # Resolve seams once more in world coordinates, including adjacent cabinets.
    overlays = [f["boundary_policy"] for f in fronts if not f["inset"]]
    resolved_fronts = resolve_front_boundaries(overlays)
    by_id = {p["id"]: p for p in parts}
    for face in fronts:
        if face["inset"]: continue
        x0, x1, z0, z1 = resolved_fronts[face["id"]]
        part = by_id[face["id"]]
        translation = list(part["transform"]["translation"])
        dimensions = list(part["stock"]["dimensions"])
        translation[0], translation[2] = x0, z0
        dimensions[0], dimensions[2] = x1-x0, z1-z0
        update_box_part(part, translation=translation, dimensions=dimensions)
        face["origin"], face["size"] = list(part["origin"]), list(part["size"])
        host = part_hosts.get(part["id"])
        if host and any(a < b-1e-6 or c > d+1e-6 for a,b,c,d in zip(part["bounds"][0], host[0], part["bounds"][1], host[1])):
            raise ValueError(f"{part['id']}: part protrudes outside host clear space")
    for left, right in combinations((by_id[f["id"]] for f in fronts), 2):
        if all(min(left["bounds"][1][i], right["bounds"][1][i]) - max(left["bounds"][0][i], right["bounds"][0][i]) > 1e-6 for i in range(3)):
            raise ValueError(f"overlapping closed fronts: {left['id']} and {right['id']}")
    for contact in contacts:
        signature = "\0".join((contact["part_a"], contact["part_b"], contact["type"]))
        contact["id"] = "contact-" + hashlib.sha256(signature.encode()).hexdigest()[:16]
    from .operations import resolve_operations
    operations, joints = getattr(project, "operations", ()), getattr(project, "joints", ())
    generated = component_domino_rows(parts, contacts, joints)
    for op in resolve_operations(parts, operations, (*joints, *generated)):
        by_id[op["part_id"]]["operations"].append(op)
    for part in parts:
        part["operations"].sort(key=lambda op: op["id"])
    from .edge_banding import resolve_edge_bands
    resolve_edge_bands(parts, getattr(project, "edge_banding", ()))
    from .part_grain import resolve_part_grain
    resolve_part_grain(parts, getattr(project, "part_grain", ()))
    invalid = [part["id"] for part in parts if not check_box_part(part)]
    if invalid:
        raise ValueError(f"inconsistent Space physical part geometry: {', '.join(invalid)}")
    occupied = _part_bounds(parts)
    if occupied and any(occupied["min_"+axis] < structural["min_"+axis] - 1e-6 or occupied["max_"+axis] > structural["max_"+axis] + 1e-6 for axis in "xyz"):
        diagnostics.append(dict(code="occupied_overhang", structural_bounds=structural, occupied_bounds=occupied))
    return ResolvedModel(spaces, dividers, allowances, contents, fronts, PhysicalPartPlan(parts, contacts),
                         dict(space_model=_input(project.space_model), layout=_input(project.layout), space_cabinets=_input(project.space_cabinets), space_modules=_input(project.space_modules), operations=_input(operations), joints=_input(joints), edge_banding=_input(getattr(project, "edge_banding", ())), part_grain=_input(getattr(project, "part_grain", ()))),
                         placements, allocations, structural, occupied, diagnostics)

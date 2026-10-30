"""Native Cabineteer construction and ordered cabinet assemblies."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .drawers import (
    drawer_shapes,
    eb20_profile_for_key,
    register_eb20_profile,
    validate_drawer_config,
)
from .grouping import group_cutting_blanks
from .project import InputError, ProjectInputs

register_eb20_profile()
register_eb20_profile(480)


@dataclass
class Calculation:
    configs: list
    result: dict
    drawer_instances: list
    native_assembly: object = None
    space_model: object = None
    space_shapes: dict | None = None


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")


def _drawer_key(cabinet_id: str, column_index: int, opening_index: int) -> str:
    return f"{cabinet_id}/column-{column_index}/opening-{opening_index}"


def _rear_relief_width(config):
    return getattr(config, "buratino_rear_corner_clearance_width_mm", 0)


def _require_nonnegative_mm(value, key):
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value < 0
    ):
        raise InputError(
            "invalid_clearance", f"{key} must be a finite non-negative length.", key
        )


def _native_world_location(assembly, name, fallback):
    """Return an object's accumulated local transform from a native assembly."""
    obj = assembly.objects.get(name)
    if obj is None:
        return fallback
    location = obj.loc
    parent = obj.parent
    while parent is not None:
        location = parent.loc * location
        parent = parent.parent
    return location


def _build_native_carcass(config):
    """Build carcass solids through Cabineteer's matching native constructor."""
    from cabineteer.cabinet import (
        bays_from_config,
        dispatch_cabinet_geometry,
    )

    return dispatch_cabinet_geometry(
        config,
        bay_configs=bays_from_config(config) if config.columns else None,
        multi_bay_options={
            "include_drawers": False,
            "include_faces": False,
            "include_feet": False,
        },
    )


def _local_columns(config):
    from cabineteer.cabinet import bays_from_config

    return bays_from_config(config)


def _part_dimensions(part, config):
    """Return the native finished dimensions for this carcass member."""
    from cabineteer.cabinet import carcass_panel_dims

    name = part.name.lower()
    panels = carcass_panel_dims(config)
    if "side" in name and "divider" not in name:
        panel = next(
            (
                p
                for p in panels
                if p.kind == "side" and (p.name == name or p.name == "side")
            ),
            None,
        )
    elif "divider" in name:
        panel = next((p for p in panels if p.kind == "divider"), None)
    elif "bottom" in name:
        panel = next((p for p in panels if p.kind == "bottom"), None)
    elif "top" in name:
        panel = next((p for p in panels if p.kind == "top"), None)
    elif "back" in name:
        panel = next((p for p in panels if p.kind == "back"), None)
    elif "shelf" in name:
        panel = next((p for p in panels if p.kind == "shelf" and p.name in name), None)
    else:
        panel = None
    if panel is not None:
        return {
            "length": panel.length,
            "width": panel.width,
            "thickness": panel.thickness,
        }
    bounds = part.shape.val().BoundingBox()
    dims = sorted((bounds.xlen, bounds.ylen, bounds.zlen), reverse=True)
    thickness = part.material_thickness
    dims.remove(min(dims, key=lambda n: abs(n - thickness)))
    return {"length": dims[0], "width": dims[1], "thickness": thickness}


def _qualified_cabinet_affected(issue, cabinet_id, cabinet_parts):
    """Map native issue labels to stable physical part IDs when possible."""
    source = [value for value in (issue.part_a, issue.part_b) if value]
    affected = []
    components = {part["component"] for part in cabinet_parts}
    for value in source:
        if value in {part["id"] for part in cabinet_parts}:
            affected.append(value)
            continue
        tokens = set(re.split(r"[-_ ]+", value.lower()))
        candidates = set()
        if "side" in tokens:
            candidates.update({"left_side", "right_side"} & components)
        for component in ("top", "bottom", "back", "divider"):
            if component in tokens and component in components:
                candidates.add(component)
        if "shelf" in tokens:
            candidates.update(
                part["component"]
                for part in cabinet_parts
                if part["component"].startswith("shelf")
            )
        for component in sorted(candidates):
            affected.extend(
                part["id"] for part in cabinet_parts if part["component"] == component
            )
    return sorted(set(affected)), source


def _cabinet_face_thicknesses(project, cabinet_id, config):
    """Resolve overlay thickness from each native drawer or door opening."""
    from cabineteer.cabinet import opening_stack

    fallback = project.variables.get("drawer_face_thickness_mm", 18)
    thicknesses = {}
    for column_index, bay in enumerate(_local_columns(config)):
        for opening_index, slot in enumerate(opening_stack(bay)):
            opening = slot.opening
            if opening.opening_type == "drawer":
                drawer = project.drawer_configs.get(
                    _drawer_key(cabinet_id, column_index, opening_index)
                )
                thickness = drawer.face_thickness if drawer else fallback
            elif opening.opening_type in {"door", "door_pair"}:
                thickness = opening.door_thickness or fallback
            else:
                continue
            thicknesses[(column_index, opening_index)] = thickness
    return thicknesses


def _native_drawer_config(
    project, cabinet_id, column_index, opening_index, cabinet, bay, opening
):
    key = _drawer_key(cabinet_id, column_index, opening_index)
    cfg = project.drawer_configs.get(key)
    if cfg is None:
        from cabineteer.drawer import box_config_for_opening

        cfg = box_config_for_opening(
            cabinet,
            bay.interior_width,
            opening.height_mm,
            cabinet.interior_depth,
            opening,
        )
        cfg.applied_face = False
        cfg.buratino_rear_corner_clearance_width_mm = 0
        cfg.buratino_material = project.variables.get(
            "drawer_material", "drawer_stock_unverified"
        )
    try:
        profile = eb20_profile_for_key(cfg.slide_key)
    except ValueError as exc:
        raise InputError("unsupported_drawer_profile", str(exc), key) from exc
    if opening.slide_key is not None and cfg.slide_key != opening.slide_key:
        raise InputError(
            "drawer_config_slide_mismatch",
            "DrawerConfig slide_key must match the opening slide_key.",
            key,
        )
    if not hasattr(cfg, "buratino_box_bottom_clearance_mm"):
        cfg.buratino_box_bottom_clearance_mm = cfg.slide.min_bottom_clearance
    if (
        cfg.opening_width != bay.interior_width
        or cfg.opening_height != opening.height_mm
        or cfg.opening_depth != cabinet.interior_depth
    ):
        raise InputError(
            "drawer_config_opening_mismatch",
            "DrawerConfig must match its native opening width, height, and "
            "cavity depth.",
            key,
        )
    try:
        validate_drawer_config(cfg)
    except (ValueError, TypeError) as exc:
        raise InputError("invalid_drawer_config", str(exc), key) from exc
    if cfg.box_depth != profile["runner_length_mm"]:
        raise InputError(
            "unsupported_runner_length",
            "Drawer box depth must match the selected runner length.",
            key,
        )
    return cfg


def _domino_machining(variables: dict, resolved: list) -> dict | None:
    """Calculate nominal paired depths from the project router inputs."""
    data = variables.get("domino_machining")
    if data is None:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("face_depth_mm"), dict):
        raise InputError(
            "invalid_domino_machining", "Provide cutter diameter and face depth range."
        )
    cutter = data.get("cutter_diameter_mm")
    reference = data.get("face_reference")
    if reference not in (None, "centered"):
        raise InputError("invalid_domino_machining", "Unsupported face reference.")
    low = data["face_depth_mm"].get("min")
    high = data["face_depth_mm"].get("max")
    if (
        any(
            isinstance(v, bool)
            or not isinstance(v, int | float)
            or not math.isfinite(v)
            for v in (cutter, low, high)
        )
        or cutter <= 0
        or low <= 0
        or low > high
        or high >= 40
    ):
        raise InputError(
            "invalid_domino_machining",
            "Cutter and face depths must be positive; "
            "the ordered face range must be below 40 mm.",
        )
    walls = {}
    for cabinet_id, cfg in resolved:
        if cfg.domino_spec.size_key != "6x40":
            raise InputError(
                "invalid_domino_machining",
                "Router depth inputs require a 6x40 Domino.",
                cabinet_id,
            )
        thickness = cfg.side_thickness
        if high >= thickness:
            raise InputError(
                "invalid_domino_machining",
                "Face depth must be less than the side thickness.",
                cabinet_id,
            )
        walls[cabinet_id] = {"min": thickness - high, "max": thickness - low}
    return {
        "cutter_diameter_mm": cutter,
        "face_depth_mm": {"min": low, "max": high},
        "edge_depth_mm": {"min": 40 - high, "max": 40 - low},
        "tenon_length_mm": 40,
        "face_reference": reference,
        "face_wall_mm_by_cabinet": walls,
    }


def _calculate_native_assembly(project: ProjectInputs) -> Calculation:
    from cabineteer.profiles import assembly_records, evaluate_assembly

    native = project.native_project.resolved_assembly()
    data = assembly_records(native)
    geometry_issues = evaluate_assembly(native)
    spec = project.native_project.profile_assembly
    placements = {item.name: item for item in native.layout.placements}

    def point(values):
        return dict(zip(("x", "y", "z"), values, strict=True))

    def bounds(placement):
        box = placement.occupied_world_bounds_mm
        return {
            "min": point((box.min_x, box.min_y, box.min_z)),
            "max": point((box.max_x, box.max_y, box.max_z)),
        }

    cabinets = []
    for name, config in project.native_project.resolved():
        placement = placements[name]
        selected = sorted(
            {
                item["slide_key"]
                for item in native.hardware
                if item.get("instance_id", "").startswith(f"{name}.")
            }
        )
        single_slide = selected[0] if len(selected) == 1 else None
        cabinets.append(
            {
                "id": name,
                "name": name,
                "placement_mm": point(placement.origin_mm),
                "dimensions_mm": {
                    "width": config.width,
                    "height": config.height,
                    "depth": config.depth,
                },
                "bounds_mm": bounds(placement),
                "slide_key": single_slide,
                "slide_keys": selected,
                "hardware_profile": eb20_profile_for_key(single_slide)
                if single_slide
                else None,
            }
        )
    frames = [
        {
            "id": item.name,
            "width": item.width_mm,
            "depth": item.depth_mm,
            "height": item.height_mm,
            "thickness": item.stock_mm,
            "material": item.material,
            **point(placements[item.name].origin_mm),
        }
        for item in (spec.frames or (spec.frame,))
    ]
    upper_names = (
        (spec.shared_owner,)
        if spec.shared_owner
        else tuple(box.name for box in spec.boxes)
    )
    upper_cabinets = [
        {
            "id": name,
            "placement_mm": point(placements[name].origin_mm),
            "bounds_mm": bounds(placements[name]),
        }
        for name in upper_names
    ]
    drawers = [
        {
            **item,
            "hardware_profile": eb20_profile_for_key(item["slide_key"])
            if item.get("slide_key")
            else None,
        }
        for item in data["drawers"]
    ]
    bounds = native.layout.occupied_world_bounds_mm
    dimensions = {
        "width": bounds.width_mm,
        "height": bounds.height_mm,
        "depth": bounds.depth_mm,
    }
    parts = []
    for record in data["parts"]:
        part = dict(record)
        part.update(
            role=record["id"],
            finished_mm=record["stock_mm"],
            blank_mm=record["stock_mm"],
            grain_direction="unknown",
            grain_status="unverified",
            edge_treatment="unverified",
        )
        parts.append(part)
    result = {
        "schema_version": 2,
        "name": project.native_project.name,
        "input_identity": project.identity,
        "status": "draft",
        "validation_status": "blocked",
        "manufacturing_ready": False,
        "dimensions_mm": dimensions,
        "overall_dimensions_mm": dimensions,
        "variables": project.variables,
        "calculated": project.calculated,
        "cabinets": cabinets,
        "frames": frames,
        "upper_cabinets": upper_cabinets,
        "parts": parts,
        "drawers": drawers,
        "joints": [],
        "hardware": data["hardware"],
        "checks": [
            *[
                {**issue, "message": "Native cap contact or overlap check failed."}
                for issue in geometry_issues
            ],
            {
                "severity": "unknown",
                "code": "assembly.unverified",
                "message": (
                    "Hardware, joinery, support and installation remain unverified."
                ),
            },
        ],
        "explanations": {"assembly": "Native resolved assembly and part profiles."},
        "assembly": data,
        "cutting_groups": group_cutting_blanks(parts),
    }
    return Calculation([], result, [], native)


def _space_point(value):
    """Return a plan point as a named report coordinate map."""
    if isinstance(value, dict):
        return {axis: value[axis] for axis in ("x", "y", "z")}
    return dict(zip(("x", "y", "z"), value, strict=True))


def _space_dimensions(value):
    point = _space_point(value)
    return {"width": point["x"], "depth": point["y"], "height": point["z"]}


def _space_bounds_size(bounds):
    """Project native bounds to width, height and depth."""
    return {
        "width": bounds["max_x"] - bounds["min_x"],
        "height": bounds["max_z"] - bounds["min_z"],
        "depth": bounds["max_y"] - bounds["min_y"],
    }


def _calculate_space_model(project: ProjectInputs) -> Calculation:
    """Format a resolved native Space plan for Buratino reports and cut lists."""
    from cabineteer.space_adapter import space_model_records

    native_project = project.native_project
    is_assembly = native_project.layout is not None
    plan = (
        native_project.resolved_space_assembly()
        if is_assembly
        else native_project.resolved_space_model()
    )
    plan_data = plan.to_dict()
    records = space_model_records(plan)
    parts = []
    for source in records["parts"]:
        part = dict(source)
        stock = part.get("stock_mm") or part.get("stock")
        if isinstance(stock, dict) and {"length", "width", "thickness"} <= set(stock):
            part["blank_mm"] = dict(stock)
            if part.get("operations"):
                part.pop("finished_mm", None)
                part["finished_status"] = "unverified_after_machining"
            else:
                part["finished_mm"] = dict(stock)
        part.setdefault("scene_name", part.get("role", part["id"]))
        part.setdefault("grain_direction", "unknown")
        part.setdefault("grain_status", "unverified")
        part.setdefault("edge_treatment", "unverified")
        part.setdefault(
            "local_datum",
            {
                "origin": "unmachined_stock_min_xyz",
                "face_uv": "remaining_axes_ascending_xyz",
                "depth": "inward_from_selected_face",
            },
        )
        parts.append(part)

    contents = plan.contents
    hardware = []
    slide_counts: dict[str, int] = {}
    for content in contents:
        key = content.get("slide_key")
        if key:
            slide_counts[key] = slide_counts.get(key, 0) + 2
    hardware.extend(
        {"type": "drawer_runner", "slide_key": key, "quantity": count}
        for key, count in sorted(slide_counts.items())
    )
    hardware.extend(
        {
            "type": "concealed_door_hinge",
            "name": front["hinge_key"],
            "quantity": None,
        }
        for front in plan.fronts
        if front.get("hinge_key")
    )
    drawer_records = records["viewer"].get("drawers", [])
    dimensions = _space_bounds_size(plan_data["structural_bounds"])
    occupied_dimensions = _space_bounds_size(plan_data["occupied_bounds"])
    cabinet_records = records["viewer"].get("cabinets", [])
    placements = {
        placement["id"]: placement for placement in plan_data.get("placements", [])
    }
    cabinets = []
    for source in cabinet_records:
        cabinet = dict(source)
        placement = placements.get(cabinet.get("id"))
        if placement is not None:
            cabinet["placement_mm"] = _space_point(placement["origin"])
            cabinet["dimensions_mm"] = _space_dimensions(placement["size"])
            cabinet["bounds_mm"] = placement["structural_bounds"]
        cabinets.append(cabinet)
    diagnostics = []
    for item in plan_data.get("diagnostics", []):
        if {"severity", "code", "message"} <= set(item):
            diagnostics.append(item)
        else:
            diagnostics.append(
                {
                    "severity": "unknown",
                    "code": item.get("code", "space.diagnostic"),
                    "message": item.get("message", str(item)),
                }
            )
    result = {
        "schema_version": 2,
        "plan_version": plan.plan_version,
        "name": project.native_project.name,
        "input_identity": project.identity,
        "status": "draft",
        "validation_status": "blocked",
        "manufacturing_ready": False,
        "dimensions_mm": dimensions,
        "overall_dimensions_mm": occupied_dimensions,
        "variables": project.variables,
        "calculated": project.calculated,
        "cabinets": cabinets,
        "frames": [],
        "upper_cabinets": [],
        "parts": parts,
        "drawers": drawer_records,
        "joints": [],
        "hardware": hardware,
        "checks": [
            {
                "severity": "unknown",
                "code": "space_assembly.unverified",
                "message": (
                    "Hardware, joinery, support and installation remain unverified."
                ),
            },
            *diagnostics,
        ],
        "explanations": {
            "assembly": "Native resolved Space plan and physical part plan."
        },
        "assembly": {
            "contacts": records["contacts"],
            "viewer": records["viewer"],
            "plan_version": plan.plan_version,
            "placements": plan_data.get("placements", []),
            "allocations": plan_data.get("allocations", []),
            "structural_bounds": plan_data["structural_bounds"],
            "occupied_bounds": plan_data["occupied_bounds"],
            "spaces": plan_data.get("spaces", []),
            "contents": plan_data.get("contents", []),
            "fronts": plan_data.get("fronts", []),
            "diagnostics": plan_data.get("diagnostics", []),
        },
        "space_model": plan_data,
        "space_plan": plan_data,
        "cutting_groups": group_cutting_blanks(parts),
    }
    return Calculation([], result, [], None, plan)


def calculate(project: ProjectInputs) -> Calculation:
    """Resolve native project configs into draft parts, checks, and placements."""
    if (
        project.native_project.space_model is not None
        or project.native_project.space_cabinets
        or project.native_project.space_modules
    ):
        return _calculate_space_model(project)
    if (
        project.native_project.layout is not None
        or project.native_project.profile_assembly is not None
    ):
        return _calculate_native_assembly(project)

    from cabineteer.cabinet import (
        bay_x_offsets,
        face_layout,
        opening_stack,
    )
    from cabineteer.evaluation import (
        check_drawer_hardware_clearances,
        check_drawer_in_opening,
        check_drawer_joinery,
        evaluate_cabinet,
    )

    resolved = list(project.native_project.resolved())
    if not resolved:
        raise InputError(
            "empty_project", "A project must contain at least one cabinet."
        )
    domino_machining = _domino_machining(project.variables, resolved)
    cabinet_gap = project.variables.get("cabinet_gap_mm", 0)
    cabinet_z = project.variables.get("cabinet_base_z_mm", 0)
    _require_nonnegative_mm(cabinet_z, "cabinet_base_z_mm")
    face_gap = project.variables.get("front_gap_mm", 2)
    edge_gap = project.variables.get("edge_gap_mm", 2)
    front_projection = project.variables.get("face_to_carcass_gap_mm", 0)
    for key, value in (
        ("cabinet_gap_mm", cabinet_gap),
        ("front_gap_mm", face_gap),
        ("edge_gap_mm", edge_gap),
        ("face_to_carcass_gap_mm", front_projection),
    ):
        _require_nonnegative_mm(value, key)

    # Resolve and validate every actual drawer before any native CAD build.

    drawer_configs = {}
    cabinet_slide_keys = {}
    for cabinet_id, config in resolved:
        for ci, bay in enumerate(_local_columns(config)):
            for oi, slot in enumerate(opening_stack(bay)):
                if slot.opening.opening_type == "drawer":
                    drawer_key = _drawer_key(cabinet_id, ci, oi)
                    drawer = _native_drawer_config(
                        project, cabinet_id, ci, oi, config, bay, slot.opening
                    )
                    if (
                        cabinet_id in cabinet_slide_keys
                        and cabinet_slide_keys[cabinet_id] != drawer.slide_key
                    ):
                        raise InputError(
                            "cabinet_runner_profile_mismatch",
                            "All drawers in a cabinet must use the same "
                            "runner profile.",
                            cabinet_id,
                        )
                    cabinet_slide_keys[cabinet_id] = drawer.slide_key
                    drawer_configs[drawer_key] = drawer

    parts: list[dict] = []
    drawers: list[dict] = []
    joints: list[dict] = []
    hardware = [{"type": "domino", "size": "6x40", "quantity": None}]
    issues: list[dict] = []
    cabinet_entries = []
    native_cabinets = []
    drawer_instances = []
    x_run = 0.0
    global_front_plane = 0.0
    face_offsets = []

    # Align each cabinet's completed face plane. Face depth is a native
    # project choice; carcass depth remains independent.
    face_thickness_by_cabinet = []
    for cabinet_id, config in resolved:
        front_projection = project.variables.get("face_to_carcass_gap_mm", 0)
        thicknesses = _cabinet_face_thicknesses(project, cabinet_id, config)
        face_thickness_by_cabinet.append(thicknesses)
        face_depth = max(thicknesses.values()) + front_projection if thicknesses else 0
        face_offsets.append(face_depth)
        global_front_plane = max(global_front_plane, face_depth)
    for (cabinet_id, config), face_depth, face_thicknesses in zip(
        resolved, face_offsets, face_thickness_by_cabinet, strict=True
    ):
        x0 = x_run
        y0 = face_depth - global_front_plane
        slug = _slug(cabinet_id)
        bays = _local_columns(config)
        bay_xs, _ = bay_x_offsets(bays)
        try:
            native_assy, native_parts = _build_native_carcass(config)
        except Exception as exc:
            raise InputError(
                "native_carcass_build_failed", str(exc), cabinet_id
            ) from exc
        cabinet_records = []
        for part in native_parts:
            raw_name = part.name
            if raw_name.startswith("drawer"):
                continue
            semantic = re.sub(r"^bay\d+_", "", raw_name.lower())
            if semantic == "side":
                side_records = ["side_left", "side_right"]
            elif semantic.startswith("side_"):
                side_records = [semantic]
            else:
                side_records = [semantic]
            for role_part in side_records:
                scene_name = f"cabinet_{slug}_{_slug(role_part)}"
                if any(r["role"] == scene_name for r in parts):
                    scene_name = f"{scene_name}_{len(cabinet_records) + 1}"
                dim = _part_dimensions(part, config)
                material = (
                    project.variables.get("back_material", "back_stock_unverified")
                    if "back" in role_part
                    else config.carcass_material
                )
                component = "divider" if role_part.startswith("divider") else role_part
                grain_axis = (
                    "x"
                    if role_part in {"top", "bottom"} or role_part.startswith("shelf")
                    else "z"
                )
                normal_axis = (
                    "x"
                    if role_part.startswith(("side", "divider"))
                    else "y"
                    if role_part == "back"
                    else "z"
                )
                record = {
                    "id": f"{cabinet_id}.carcass.{role_part}",
                    "role": scene_name,
                    "scene_name": scene_name,
                    "cabinet_id": cabinet_id,
                    "component": component,
                    "native_name": raw_name,
                    "quantity": 1,
                    "finished_mm": dim,
                    "material": material,
                    "edge_treatment": "unconfirmed",
                    "grain_direction": "length",
                    "grain_axis_local": grain_axis,
                    "surface_normal_axis_local": normal_axis,
                    "grain_status": "assumed",
                }
                parts.append(record)
                cabinet_records.append((part, role_part, record))
        cabinet_issues = evaluate_cabinet(config)
        for issue in cabinet_issues:
            if issue.check in {
                "hardware_clearance",
                "drawer_bottom_recess",
                "drawer_joinery",
                "drawer_fit",
                "drawer_stack_order",
            }:
                continue
            affected, source_affected = _qualified_cabinet_affected(
                issue, cabinet_id, [record for _, _, record in cabinet_records]
            )
            issues.append(
                {
                    "code": f"cabineteer.{issue.check}",
                    "severity": issue.severity.value,
                    "message": (
                        "Slot fit, glue clearance and jig reference "
                        "surfaces remain unconfirmed."
                        if domino_machining
                        and issue.check == "domino_machining_unknown"
                        else issue.message
                    ),
                    "cabinet_id": cabinet_id,
                    "affected": affected,
                    "source_affected": source_affected,
                }
            )
        native_cabinets.append(
            {
                "id": cabinet_id,
                "config": config,
                "assembly": native_assy,
                "parts": cabinet_records,
                "x": x0,
                "y": y0,
            }
        )
        face_panels = face_layout(
            bays,
            face_thickness=max(face_thicknesses.values(), default=18),
            outer_overlay=config.side_thickness - edge_gap,
            inner_overlay=(config.side_thickness - face_gap) / 2,
            face_gap=face_gap,
            face_bottom_overhang=config.bottom_thickness - edge_gap,
            face_top_overhang=config.top_thickness - edge_gap,
        )
        # Narrow placement adapter for the row: native face_layout owns every
        # panel size, while this applies outside reveals and closes the selected
        # total gap across separate carcasses.
        row_index = len(cabinet_entries)
        seam_adjust = (cabinet_gap + 2 * edge_gap - face_gap) / 2
        from dataclasses import replace as dc_replace

        positioned_faces = []
        for panel in face_panels:
            px, pw = panel.x, panel.width
            if panel.bay == 0:
                px += edge_gap
                if row_index > 0:
                    px -= seam_adjust
                    pw += seam_adjust
            if panel.bay == len(bays) - 1 and row_index < len(resolved) - 1:
                pw += seam_adjust
            positioned_faces.append(dc_replace(panel, x=px, width=pw))
        faces = {
            (panel.bay, panel.slot): panel
            for panel in positioned_faces
            if panel.kind == "drawer_face"
        }
        local_index = 0
        for ci, bay in enumerate(bays):
            slots = opening_stack(bay)
            for oi, slot in enumerate(slots):
                opening = slot.opening
                if opening.opening_type != "drawer":
                    continue
                local_index += 1
                face = faces.get((ci, oi))
                if face is None:
                    raise InputError(
                        "drawer_face_unresolved",
                        "Native face_layout did not produce a drawer front.",
                        _drawer_key(cabinet_id, ci, oi),
                    )
                drawer_cfg = drawer_configs[_drawer_key(cabinet_id, ci, oi)]
                face = dc_replace(face, thickness=drawer_cfg.face_thickness)
                faces[(ci, oi)] = face
                for check in (
                    check_drawer_hardware_clearances(drawer_cfg),
                    check_drawer_joinery(drawer_cfg),
                ):
                    for issue in check:
                        issues.append(
                            {
                                "code": f"cabineteer.{issue.check}",
                                "severity": issue.severity.value,
                                "message": issue.message,
                                "cabinet_id": cabinet_id,
                                "affected": [
                                    drawer_id
                                    := f"{cabinet_id}.drawer.column-{ci}.opening-{oi}"
                                ],
                            }
                        )
                drawer_id = f"{cabinet_id}.drawer.column-{ci}.opening-{oi}"
                role_prefix = f"cabinet_{slug}_drawer_col{ci + 1}_opening{oi + 1}"
                bx = bay_xs[ci] + bay.side_thickness + drawer_cfg.side_gap
                bz = slot.z + getattr(drawer_cfg, "buratino_box_bottom_clearance_mm", 0)
                drawer_position = {"x": bx, "y": drawer_cfg.front_gap, "z": bz}
                face_position = {
                    "x": face.x,
                    "y": -drawer_cfg.face_thickness - front_projection,
                    "z": face.z,
                }
                shape_map, offsets = drawer_shapes(
                    drawer_cfg,
                    rear_corner_clearance_width_mm=getattr(
                        drawer_cfg, "buratino_rear_corner_clearance_width_mm", 0
                    ),
                )
                # The native fit check receives the actual per-opening config.
                # Its local assembly has box origin at zero; placement clearance
                # is recorded separately in the result.
                from cabineteer.drawer import build_drawer

                native_drawer_assy, _ = build_drawer(drawer_cfg)
                for issue in check_drawer_in_opening(
                    native_drawer_assy,
                    drawer_cfg.opening_width,
                    drawer_cfg.opening_height,
                    drawer_cfg.opening_depth,
                    drawer_cfg.slide,
                    drawer_cfg.side_thickness,
                ):
                    issues.append(
                        {
                            "code": f"cabineteer.{issue.check}",
                            "severity": issue.severity.value,
                            "message": issue.message,
                            "cabinet_id": cabinet_id,
                            "affected": [drawer_id],
                        }
                    )
                part_ids = []
                specs = {
                    "side_left": (
                        drawer_cfg.side_panel_length,
                        drawer_cfg.box_height,
                        drawer_cfg.side_thickness,
                    ),
                    "side_right": (
                        drawer_cfg.side_panel_length,
                        drawer_cfg.box_height,
                        drawer_cfg.side_thickness,
                    ),
                    "inner_front": (
                        drawer_cfg.front_back_panel_length,
                        drawer_cfg.box_height,
                        drawer_cfg.front_back_thickness,
                    ),
                    "back": (
                        drawer_cfg.front_back_panel_length,
                        drawer_cfg.box_height,
                        drawer_cfg.front_back_thickness,
                    ),
                    "bottom": (
                        drawer_cfg.bottom_panel_width,
                        drawer_cfg.bottom_panel_depth,
                        drawer_cfg.bottom_thickness,
                    ),
                }
                for component, _shape in shape_map.items():
                    if component == "face":
                        continue
                    ident = f"{drawer_id}.{component}"
                    role = f"{role_prefix}_{component}"
                    part_ids.append(ident)
                    length, width, thickness = specs[component]
                    part_record = {
                        "id": ident,
                        "role": role,
                        "scene_name": role,
                        "cabinet_id": cabinet_id,
                        "instance_id": drawer_id,
                        "drawer_index": local_index,
                        "column_index": ci,
                        "opening_index": oi,
                        "component": component,
                        "quantity": 1,
                        "finished_mm": {
                            "length": length,
                            "width": width,
                            "thickness": thickness,
                        },
                        "material": getattr(
                            drawer_cfg,
                            "buratino_material",
                            "drawer_stock_unverified",
                        ),
                        "edge_treatment": "unconfirmed",
                        "grain_direction": "length",
                        "grain_axis_local": "y"
                        if component.startswith("side")
                        else "x",
                        "surface_normal_axis_local": "x"
                        if component.startswith("side")
                        else "z"
                        if component == "bottom"
                        else "y",
                        "grain_status": "assumed",
                    }
                    if component == "back":
                        relief_width = getattr(
                            drawer_cfg,
                            "buratino_rear_corner_clearance_width_mm",
                            0,
                        )
                        if relief_width:
                            part_record["rear_clearance_mm"] = {
                                "width": relief_width,
                                "height": drawer_cfg.bottom_dado_inset,
                            }
                            part_record["machining_assumptions"] = [
                                {
                                    "operation": "rear_corner_relief",
                                    "dimensions_mm": {
                                        "width": relief_width,
                                        "height": drawer_cfg.bottom_dado_inset,
                                        "depth": drawer_cfg.front_back_thickness,
                                    },
                                    "status": "unverified_draft_interpretation",
                                    "basis": (
                                        "Hettich EB20 sketch; confirm before machining"
                                    ),
                                }
                            ]
                    parts.append(part_record)
                face_id = f"{drawer_id}.face"
                face_role = f"{role_prefix}_face"
                part_ids.append(face_id)
                parts.append(
                    {
                        "id": face_id,
                        "role": face_role,
                        "scene_name": face_role,
                        "cabinet_id": cabinet_id,
                        "instance_id": drawer_id,
                        "drawer_index": local_index,
                        "column_index": ci,
                        "opening_index": oi,
                        "component": "face",
                        "quantity": 1,
                        "finished_mm": {
                            "length": face.width,
                            "width": face.height,
                            "thickness": face.thickness,
                        },
                        "material": config.face_material
                        or project.variables.get(
                            "face_material", "face_stock_unverified"
                        ),
                        "edge_treatment": "unconfirmed",
                        "grain_direction": "length",
                        "grain_axis_local": "x",
                        "surface_normal_axis_local": "y",
                        "grain_status": "assumed",
                    }
                )
                drawers.append(
                    {
                        "instance_id": drawer_id,
                        "slide_key": drawer_cfg.slide_key,
                        "hardware_profile": eb20_profile_for_key(drawer_cfg.slide_key),
                        "drawer_index": local_index,
                        "column_index": ci,
                        "opening_index": oi,
                        "cabinet_id": cabinet_id,
                        "part_ids": part_ids,
                        "closed_position_mm": drawer_position,
                        "face_position_mm": face_position,
                        "face_mm": {
                            "width": face.width,
                            "height": face.height,
                            "thickness": face.thickness,
                        },
                        "box_mm": {
                            "width": drawer_cfg.box_width,
                            "height": drawer_cfg.box_height,
                            "depth": drawer_cfg.box_depth,
                        },
                    }
                )
                drawer_instances.append(
                    {
                        "cabinet_id": cabinet_id,
                        "drawer_id": drawer_id,
                        "config": drawer_cfg,
                        "shapes": shape_map,
                        "offsets": offsets,
                        "box_position": drawer_position,
                        "face_position": face_position,
                        "face_panel": face,
                        "role_prefix": role_prefix,
                    }
                )
        # Carcass joinery is fixed at 6x40; positions and depths remain unverified.
        for panel in () if config.roof_angle_deg else ("bottom", "top"):
            for side in ("left", "right"):
                joints.append(
                    {
                        "id": f"{cabinet_id}.joint.{panel}.{side}",
                        "cabinet_id": cabinet_id,
                        "type": "domino",
                        "tenon": "6x40",
                        "parts": [
                            f"{cabinet_id}.carcass.{panel}",
                            f"{cabinet_id}.carcass.{side}_side",
                        ],
                        "positions_mm": None,
                        "depths_mm": None,
                        "quantity": None,
                        "status": "unverified",
                    }
                )
        cabinet_entries.append(
            {
                "id": cabinet_id,
                "name": cabinet_id,
                "slide_key": cabinet_slide_keys.get(cabinet_id),
                "hardware_profile": (
                    eb20_profile_for_key(cabinet_slide_keys[cabinet_id])
                    if cabinet_id in cabinet_slide_keys
                    else None
                ),
                "placement_mm": {"x": x0, "y": y0, "z": cabinet_z},
                "dimensions_mm": {
                    "width": config.width,
                    "height": config.height,
                    "depth": config.depth,
                },
                "bounds_mm": {
                    "min": {"x": x0, "y": y0 - face_depth, "z": cabinet_z},
                    "max": {
                        "x": x0 + config.width,
                        "y": y0 + config.depth,
                        "z": cabinet_z + config.height,
                    },
                },
            }
        )
        x_run += config.width + cabinet_gap

    # Frames are authored separately from native cabinets. Each is four butt rails.
    frames = project.variables.get("frames", [])
    if not isinstance(frames, list):
        raise InputError("invalid_frames", "frames must be a list.", "frames")
    seen_frames = set()
    for frame in frames:
        if not isinstance(frame, dict):
            raise InputError("invalid_frames", "Each frame must be a map.", "frames")
        frame_id = frame.get("id")
        if (
            not isinstance(frame_id, str)
            or not frame_id
            or _slug(frame_id) != frame_id
            or frame_id in seen_frames
        ):
            raise InputError(
                "invalid_frames", "Frame IDs must be unique simple names.", "frames"
            )
        seen_frames.add(frame_id)
        for key in ("width", "depth", "height", "thickness", "x", "y", "z"):
            _require_nonnegative_mm(frame.get(key), f"frames.{frame_id}.{key}")
        width, depth, height, thickness = (
            frame[k] for k in ("width", "depth", "height", "thickness")
        )
        if (
            height <= 0
            or thickness <= 0
            or width <= 2 * thickness
            or depth <= 2 * thickness
        ):
            raise InputError(
                "invalid_frames",
                "Frame dimensions must leave an open center.",
                f"frames.{frame_id}",
            )
        material = frame.get("material")
        if not isinstance(material, str) or not material:
            raise InputError(
                "invalid_frames",
                "Frame material must be described.",
                f"frames.{frame_id}.material",
            )
        x, y, z = (frame[k] for k in ("x", "y", "z"))
        for rail, length, position, size, axis, normal in (
            ("front", width, (x, y, z), (width, thickness, height), "x", "y"),
            (
                "back",
                width,
                (x, y + depth - thickness, z),
                (width, thickness, height),
                "x",
                "y",
            ),
            (
                "left",
                depth - 2 * thickness,
                (x, y + thickness, z),
                (thickness, depth - 2 * thickness, height),
                "y",
                "x",
            ),
            (
                "right",
                depth - 2 * thickness,
                (x + width - thickness, y + thickness, z),
                (thickness, depth - 2 * thickness, height),
                "y",
                "x",
            ),
        ):
            role = f"frame_{frame_id}_{rail}"
            parts.append(
                {
                    "id": f"frame.{frame_id}.{rail}",
                    "role": role,
                    "scene_name": role,
                    "frame_id": frame_id,
                    "component": "frame_rail",
                    "quantity": 1,
                    "finished_mm": {
                        "length": length,
                        "width": height,
                        "thickness": thickness,
                    },
                    "material": material,
                    "edge_treatment": "unconfirmed",
                    "grain_direction": "length",
                    "grain_axis_local": axis,
                    "surface_normal_axis_local": normal,
                    "grain_status": "assumed",
                    "position_mm": dict(zip(("x", "y", "z"), position, strict=True)),
                    "size_mm": dict(zip(("x", "y", "z"), size, strict=True)),
                }
            )
        issues.append(
            {
                "code": "frame.construction_unverified",
                "severity": "unknown",
                "message": (
                    "Frame butt-joint fastening and attachment are not "
                    "specified or modeled."
                ),
                "affected": [
                    f"frame.{frame_id}.{rail}"
                    for rail in ("front", "back", "left", "right")
                ],
            }
        )

    if project.variables.get("drawer_domino"):
        for item in drawer_instances:
            cfg = item["config"]
            height = cfg.box_height
            # 50 mm centers leave 40.1 mm beyond the nominal 19.8 mm tenon.
            # Actual slot width and the catch positions are not established.
            centers = [50.0, height - 50.0]
            nominal_half_width = 19.8 / 2
            valid = (
                centers[1] - centers[0] >= 19.8
                and centers[0] - nominal_half_width
                > cfg.bottom_dado_inset + cfg.bottom_thickness
            )
            for end in ("inner_front", "back"):
                for side in ("side_left", "side_right"):
                    drawer_id = item["drawer_id"]
                    joints.append(
                        {
                            "id": f"{drawer_id}.joint.{end}.{side}",
                            "cabinet_id": item["cabinet_id"],
                            "drawer_id": drawer_id,
                            "type": "drawer_domino",
                            "tenon": "6x40",
                            "parts": [f"{drawer_id}.{end}", f"{drawer_id}.{side}"],
                            "candidate_centers_from_bottom_mm": centers
                            if valid
                            else None,
                            "quantity": len(centers) if valid else None,
                            "status": "unverified",
                            "limitations": (
                                "Candidate centers use nominal tenon width; "
                                "slot geometry and runner catch positions "
                                "are unverified."
                            ),
                        }
                    )
    # Record named physical connections without claiming verified fasteners.
    connections = project.variables.get("connections", [])
    for connection in connections:
        if isinstance(connection, dict):
            left, right = connection.get("from"), connection.get("to")
        elif isinstance(connection, list | tuple) and len(connection) == 2:
            left, right = connection
        else:
            raise InputError(
                "invalid_connection", "Connections must name two cabinets."
            )
        ids = [name for name, _ in resolved]
        if left not in ids or right not in ids or left == right:
            raise InputError(
                "invalid_connection_target",
                "Connection target must name two different project cabinets.",
            )
        left_index, right_index = ids.index(left), ids.index(right)
        if abs(left_index - right_index) != 1:
            raise InputError(
                "invalid_connection_target",
                "A side-to-side connection must join adjacent cabinets.",
            )
        if left_index < right_index:
            left_id, right_id = left, right
        else:
            left_id, right_id = right, left
        joints.append(
            {
                "id": f"connection.{left_id}.{right_id}",
                "cabinet_id": left_id,
                "cabinet_ids": [left_id, right_id],
                "type": "cabinet_connection",
                "parts": [
                    f"{left_id}.carcass.right_side",
                    f"{right_id}.carcass.left_side",
                ],
                "quantity": None,
                "status": "unverified",
            }
        )
        issues.append(
            {
                "code": "assembly.connection_unverified",
                "severity": "unknown",
                "message": (
                    f"Fastening details for the connection between {left} and "
                    f"{right}, and its capacity, are unverified."
                ),
                "cabinet_id": left,
                "affected": [left, right],
            }
        )

    selected_profiles = {
        item["config"].slide_key: eb20_profile_for_key(item["config"].slide_key)
        for item in drawer_instances
    }
    hardware_profile = (
        next(iter(selected_profiles.values())) if len(selected_profiles) == 1 else None
    )
    if drawer_instances:
        for slide_key, profile in selected_profiles.items():
            count = sum(
                item["config"].slide_key == slide_key for item in drawer_instances
            )
            hardware.append(
                {
                    "type": "drawer_runner",
                    "model": profile["model"],
                    "length_mm": profile["runner_length_mm"],
                    "quantity": count * 2,
                    "quantity_by_part_number": {
                        profile["left_runner_sku"]: count,
                        profile["right_runner_sku"]: count,
                    },
                    "part_numbers": [
                        profile["left_runner_sku"],
                        profile["right_runner_sku"],
                    ],
                    "sources": profile["sources"],
                }
            )
        hardware.extend(
            [
                {
                    "type": "compatible_grooved_bottom_catch_pair",
                    "model": "Hettich Quadro V6 grooved-bottom catch pair",
                    "quantity": len(drawer_instances),
                    "part_numbers": ["9144830", "9144841"],
                    "quantity_by_part_number": {
                        "9144830": len(drawer_instances),
                        "9144841": len(drawer_instances),
                    },
                    "sources": [
                        "https://shop.hettich.com/in_EN/-/Catches-for-Quadro-drawer-runners/bp/variant93961068929464",
                        "https://shop.hettich.com/es_ES/Sistemas-de-correderas/Correderas-ocultas/Correderas-Quadro/Accesorios/Gatillos/Gatillos-para-cajones-de-madera-con-fondo-acanalado-%28Quadro-25-y-Quadro-V6%29-a-la-izquierda/p/9144830",
                        "https://shop.hettich.com/es_ES/Sistemas-de-correderas/Correderas-ocultas/Correderas-Quadro/Accesorios/Gatillos/Gatillos-para-cajones-de-madera-con-fondo-acanalado-%28Quadro-25-y-Quadro-V6%29-a-la-derecha/p/9144841",
                    ],
                },
            ]
        )
        issues.extend(
            [
                {
                    "code": "drawer.rear_corner_clearance_assumption",
                    "severity": "unknown",
                    "message": (
                        f"Draft rear-corner relief is "
                        f"{_rear_relief_width(x['config'])} "
                        f"mm wide by {x['config'].bottom_dado_inset} mm high, "
                        f"through {x['config'].front_back_thickness} mm back stock. "
                        "This is an unverified reading of the Hettich sketch; "
                        "confirm before machining."
                    ),
                    "cabinet_id": x["cabinet_id"],
                    "affected": [f"{x['drawer_id']}.back"],
                }
                for x in drawer_instances
                if getattr(x["config"], "buratino_rear_corner_clearance_width_mm", 0)
            ]
        )
        issues.extend(
            [
                {
                    "code": "drawer.fastening_unverified",
                    "severity": "unknown",
                    "message": (
                        "Butt-corner fastening and face attachment are not "
                        "selected or modeled."
                    ),
                    "cabinet_id": x["cabinet_id"],
                    "affected": [x["drawer_id"]],
                }
                for x in drawer_instances
            ]
        )
        issues.extend(
            [
                {
                    "code": "drawer.bracing_unmodeled",
                    "severity": "unknown",
                    "message": (
                        "Planned manual bottom bracing is not modeled. Fit and "
                        "load path are unverified."
                    ),
                    "cabinet_id": x["cabinet_id"],
                    "affected": [f"{x['drawer_id']}.bottom"],
                }
                for x in drawer_instances
            ]
        )
        issues.extend(
            [
                {
                    "code": "drawer.vertical_recipe_unverified",
                    "severity": "unknown",
                    "message": (
                        "Box height and opening clearances are project choices. "
                        "Confirm runner fit and catch adjustment."
                    ),
                    "cabinet_id": x["cabinet_id"],
                    "affected": [x["drawer_id"]],
                }
                for x in drawer_instances
            ]
        )
        issues.extend(
            [
                {
                    "code": "drawer.runner_mounting_unverified",
                    "severity": "unknown",
                    "message": (
                        "Runner mounting, screws and catch machining are not "
                        "modeled or approved."
                    ),
                    "cabinet_id": x["cabinet_id"],
                    "affected": [x["drawer_id"]],
                }
                for x in drawer_instances
            ]
        )
        issues.extend(
            [
                {
                    "code": "drawer.load_capacity_unverified",
                    "severity": "unknown",
                    "message": "No assembled-drawer load capacity is established.",
                    "cabinet_id": x["cabinet_id"],
                    "affected": [x["drawer_id"]],
                }
                for x in drawer_instances
            ]
        )
        issues.append(
            {
                "code": "drawer.hardware_limits_unverified",
                "severity": "unknown",
                "message": (
                    "The selected 20 mm width is recorded. Minimum and maximum "
                    "clearance limits are unresolved."
                ),
                "affected": [x["drawer_id"] for x in drawer_instances],
            }
        )
        issues.append(
            {
                "code": "drawer.hardware_pack_unverified",
                "severity": "unknown",
                "message": "Runner pack sizes and included catches are not confirmed.",
                "affected": [],
            }
        )

    assumptions = project.variables.get("assumptions", [])
    for assumption in assumptions:
        issues.append(
            {
                "code": "draft.assumption",
                "severity": "unknown",
                "message": str(assumption),
                "affected": [],
            }
        )
    issues.append(
        {
            "code": "machining.unverified",
            "severity": "unknown",
            "message": (
                "Confirm jig registration and cutter settings before machining."
            ),
            "affected": [
                p["id"]
                for p in parts
                if p.get("cabinet_id") and p["component"] != "back"
            ],
        }
    )
    if project.variables.get("grain_direction_confirmed") is True:
        for part in parts:
            if part.get("grain_status") == "assumed":
                part["grain_status"] = "confirmed"
    assumed_grain = [p["id"] for p in parts if p.get("grain_status") == "assumed"]
    if assumed_grain:
        issues.append(
            {
                "code": "grain.direction_assumed",
                "severity": "unknown",
                "message": "Grain direction is an unverified draft choice.",
                "affected": assumed_grain,
            }
        )

    space = project.variables.get("space_mm", {})
    max_width = space.get("width") if isinstance(space, dict) else None
    max_height = space.get("height") if isinstance(space, dict) else None
    min_depth = space.get("depth_min") if isinstance(space, dict) else None
    max_depth = space.get("depth_max") if isinstance(space, dict) else None
    overall_width = max(
        [entry["bounds_mm"]["max"]["x"] for entry in cabinet_entries]
        + [frame["x"] + frame["width"] for frame in frames]
    ) - min(
        [entry["bounds_mm"]["min"]["x"] for entry in cabinet_entries]
        + [frame["x"] for frame in frames]
    )
    carcass_height = max(
        [entry["bounds_mm"]["max"]["z"] for entry in cabinet_entries]
        + [f["z"] + f["height"] for f in frames]
    ) - min(
        [entry["bounds_mm"]["min"]["z"] for entry in cabinet_entries]
        + [f["z"] for f in frames]
    )
    overall_height = max(
        [entry["bounds_mm"]["max"]["z"] for entry in cabinet_entries]
        + [f["z"] + f["height"] for f in frames]
    ) - min(
        [entry["bounds_mm"]["min"]["z"] for entry in cabinet_entries]
        + [f["z"] for f in frames]
    )
    carcass_depth = max(cfg.depth for _, cfg in resolved)
    overall_depth = max(
        [entry["bounds_mm"]["max"]["y"] for entry in cabinet_entries]
        + [f["y"] + f["depth"] for f in frames]
    ) - min(
        [entry["bounds_mm"]["min"]["y"] for entry in cabinet_entries]
        + [f["y"] for f in frames]
    )
    if max_width is not None and overall_width > max_width:
        issues.append(
            {
                "code": "survey.width_exceeded",
                "severity": "error",
                "message": "Cabinet row exceeds the reported available width.",
                "affected": ["overall_dimensions_mm.width"],
            }
        )
    if max_height is not None and overall_height > max_height:
        issues.append(
            {
                "code": "survey.height_exceeded",
                "severity": "error",
                "message": "Cabinet row exceeds the reported available height.",
                "affected": ["overall_dimensions_mm.height"],
            }
        )
    overall_closed_depth = overall_depth
    if min_depth is not None and overall_closed_depth > min_depth:
        issues.append(
            {
                "code": "survey.depth_unconfirmed",
                "severity": "unknown",
                "message": (
                    "Closed overall depth exceeds the reported minimum. Confirm "
                    "available space."
                ),
                "affected": ["overall_dimensions_mm.depth"],
            }
        )
    if max_depth is not None and overall_closed_depth > max_depth:
        issues.append(
            {
                "code": "survey.depth_exceeded",
                "severity": "error",
                "message": (
                    "Closed overall depth exceeds the maximum reported available depth."
                ),
                "affected": ["overall_dimensions_mm.depth"],
            }
        )

    for item in drawer_instances:
        profile = eb20_profile_for_key(item["config"].slide_key)
        if item["config"].opening_depth < profile["minimum_body_depth_mm"]:
            issues.append(
                {
                    "code": "drawer.runner_depth_does_not_fit",
                    "severity": "error",
                    "message": (
                        "The usable cavity is shorter than the "
                        f"{profile['runner_length_mm']} mm runner "
                        "requirement."
                    ),
                    "cabinet_id": item["cabinet_id"],
                    "affected": [item["drawer_id"]],
                }
            )

    grouped = group_cutting_blanks(parts)
    return Calculation(
        [cfg for _, cfg in resolved],
        {
            "schema_version": 2,
            "name": project.native_project.name,
            "input_identity": project.identity,
            "status": "draft",
            "validation_status": "blocked",
            "manufacturing_ready": False,
            "dimensions_mm": {
                "width": overall_width,
                "height": carcass_height,
                "depth": carcass_depth,
            },
            "overall_dimensions_mm": {
                "width": overall_width,
                "height": overall_height,
                "depth": overall_depth,
            },
            "internal_mm": (
                {
                    "width": resolved[0][1].interior_width,
                    "height": resolved[0][1].interior_height,
                    "depth": resolved[0][1].interior_depth,
                }
                if len(resolved) == 1
                else None
            ),
            "domino_machining": domino_machining,
            "variables": project.variables,
            "calculated": project.calculated,
            "cabinets": cabinet_entries,
            "frames": frames,
            "upper_cabinets": [],
            "parts": parts,
            "drawers": drawers,
            "drawer_layout": {
                "display_open_distance_mm": (
                    hardware_profile["box_length_mm"] if hardware_profile else None
                ),
                "face_gap_mm": face_gap,
                "face_thickness_mm": max(
                    (
                        panel.thickness
                        for item in drawer_instances
                        for panel in [item["face_panel"]]
                    ),
                    default=18,
                ),
                "face_thickness_by_cabinet_mm": {
                    cabinet_id: max(thicknesses.values(), default=0)
                    for (cabinet_id, _), thicknesses in zip(
                        resolved, face_thickness_by_cabinet, strict=True
                    )
                },
                "face_to_carcass_gap_mm": front_projection,
            }
            if drawers
            else None,
            "hardware_profile": hardware_profile,
            "hardware_profiles": selected_profiles,
            "drawer_inputs": None,
            "grouping_scope": "cutting_blank",
            "cutting_groups": grouped,
            "joints": joints,
            "hardware": hardware,
            "checks": issues,
            "explanations": {
                "carcass_panels": (
                    "cabineteer.cabinet.carcass_panel_dims and build_cabinet"
                ),
                "drawer_dimensions": (
                    "cabineteer.drawer.DrawerConfig and native part makers"
                ),
                "face_dimensions": "cabineteer.cabinet.face_layout",
            },
        },
        drawer_instances,
    )


def make_geometry(calculation: Calculation):
    """Assemble native cabinet and drawer solids under the stable viewer root."""
    from dataclasses import replace

    import cadquery as cq
    from cabineteer.drawer import make_drawer_face

    assembly = cq.Assembly(name="base_cabinet")
    if calculation.space_model is not None:
        from cabineteer.edge_banding import make_view_assembly
        from cabineteer.space_adapter import materialize_model

        shapes = materialize_model(calculation.space_model)
        calculation.space_shapes = shapes
        assembly = make_view_assembly(calculation.space_model, shapes, "base_cabinet")
        geometry = []
        for part in calculation.result["parts"]:
            ident = part["id"]
            from cabineteer.cabinet import PartInfo

            thickness = part.get("stock_mm", {}).get("thickness", 0)
            geometry.append(
                PartInfo(
                    name=part["role"],
                    shape=shapes[ident],
                    material_thickness=thickness,
                    grain_direction="unknown",
                )
            )
        return assembly, geometry
    if calculation.native_assembly is not None:
        for part in calculation.native_assembly.parts:
            assembly.add(part.solid(), name=part.id)
        return assembly, list(calculation.native_assembly.parts)
    geometry = []
    cabinet_x = {
        entry["id"]: entry["placement_mm"]["x"]
        for entry in calculation.result["cabinets"]
    }
    cabinet_y = {
        entry["id"]: entry["placement_mm"]["y"]
        for entry in calculation.result["cabinets"]
    }
    cabinet_z = {
        entry["id"]: entry["placement_mm"]["z"]
        for entry in calculation.result["cabinets"]
    }
    # Calculate configs are in project order; cabinet records preserve that order.
    for cfg, cabinet in zip(
        calculation.configs, calculation.result["cabinets"], strict=True
    ):
        cabinet_id = cabinet["id"]
        native_assembly, native_parts = _build_native_carcass(cfg)
        for native_part in native_parts:
            raw = native_part.name
            if raw.startswith("drawer"):
                continue
            candidates = [
                p
                for p in calculation.result["parts"]
                if p.get("cabinet_id") == cabinet_id and p.get("native_name") == raw
            ]
            selected = candidates
            if not selected:
                selected = [
                    p
                    for p in calculation.result["parts"]
                    if p.get("cabinet_id") == cabinet_id
                    and p["role"].endswith("_" + _slug(raw))
                ]
            for record in selected[:2]:
                obj_name = raw if raw in native_assembly.objects else None
                if obj_name is None and raw.startswith("bay"):
                    match = __import__("re").fullmatch(
                        r"bay(\d+)_(left_side|right_side)", raw
                    )
                    if match:
                        obj_name = f"bay_{match.group(1)}/{match.group(2)}"
                loc = _native_world_location(native_assembly, obj_name, cq.Location())
                loc = (
                    cq.Location(
                        (
                            cabinet_x[cabinet_id],
                            cabinet_y[cabinet_id],
                            cabinet_z[cabinet_id],
                        )
                    )
                    * loc
                )
                assembly.add(
                    native_part.shape,
                    name=record["role"],
                    loc=loc,
                    color=cq.Color(0.91, 0.92, 0.90, 1),
                )
                geometry.append(native_part)
    for item in calculation.drawer_instances:
        cfg = item["config"]
        cabinet_id = item["cabinet_id"]
        root = (cabinet_x[cabinet_id], cabinet_y[cabinet_id], cabinet_z[cabinet_id])
        for component, shape in item["shapes"].items():
            if component == "face":
                continue
            role = f"{item['role_prefix']}_{component}"
            offset = item["offsets"][component]
            position = tuple(
                root[i] + item["box_position"][axis] + offset[i]
                for i, axis in enumerate(("x", "y", "z"))
            )
            record = next(p for p in calculation.result["parts"] if p["role"] == role)
            assembly.add(
                shape,
                name=role,
                loc=cq.Location(position),
                color=cq.Color(0.87, 0.72, 0.53, 1),
            )
            from cabineteer.cabinet import PartInfo

            geometry.append(
                PartInfo(
                    name=role,
                    shape=shape,
                    material_thickness=record["finished_mm"]["thickness"],
                    grain_direction="length",
                )
            )
        face = item["face_panel"]
        overlay_x = max(0, (face.width - cfg.opening_width) / 2)
        overlay_top = calculation.result["variables"].get(
            "drawer_face_overlay_top_mm", 3
        )
        overlay_bottom = calculation.result["variables"].get(
            "drawer_face_overlay_bottom_mm", 3
        )
        face_cfg = replace(
            cfg,
            opening_height=face.height - overlay_top - overlay_bottom,
            face_overlay_sides=overlay_x,
            face_overlay_top=overlay_top,
            face_overlay_bottom=overlay_bottom,
            applied_face=True,
        )
        face_shape = make_drawer_face(face_cfg)
        face_role = f"{item['role_prefix']}_face"
        face_position = (
            root[0] + item["face_position"]["x"],
            root[1] + item["face_position"]["y"],
            root[2] + item["face_position"]["z"],
        )
        assembly.add(
            face_shape,
            name=face_role,
            loc=cq.Location(face_position),
            color=cq.Color(0.87, 0.72, 0.53, 1),
        )
        from cabineteer.cabinet import PartInfo

        record = next(p for p in calculation.result["parts"] if p["role"] == face_role)
        geometry.append(
            PartInfo(
                name=face_role,
                shape=face_shape,
                material_thickness=record["finished_mm"]["thickness"],
                grain_direction="width",
            )
        )
    from cabineteer.cabinet import PartInfo

    for record in calculation.result["parts"]:
        if "frame_id" not in record:
            continue
        size = record["size_mm"]
        pos = record["position_mm"]
        shape = cq.Workplane("XY").box(size["x"], size["y"], size["z"], centered=False)
        assembly.add(
            shape,
            name=record["role"],
            loc=cq.Location((pos["x"], pos["y"], pos["z"])),
            color=cq.Color(0.65, 0.65, 0.65, 1),
        )
        geometry.append(
            PartInfo(
                name=record["role"],
                shape=shape,
                material_thickness=record["finished_mm"]["thickness"],
                grain_direction="length",
            )
        )
    return assembly, geometry

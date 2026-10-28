"""Draft packages. Each build is staged before it becomes the latest result."""

import csv
import html
import io
import json
import os
import shutil
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .engine import calculate, make_geometry
from .environment import doctor, file_hash, read_json
from .grouping import group_cutting_blanks
from .project import (
    InputError,
    input_identity,
    load_project,
    native_snapshot,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def _coded_groups(
    groups: list[list[dict]], mapping: dict | None
) -> list[tuple[str, list[dict]]]:
    """Assign project codes to matching machining groups."""
    groups = sorted(groups, key=lambda members: min(part["id"] for part in members))
    base_groups: dict[str, list[list[dict]]] = {}
    for index, members in enumerate(groups, start=1):
        if mapping is None:
            code = f"P{index:02}"
        else:
            missing = [part["id"] for part in members if part["id"] not in mapping]
            if missing:
                raise ValueError(f"Part codes missing for: {', '.join(missing)}")
            codes = {mapping[part["id"]] for part in members}
            if len(codes) != 1:
                raise ValueError(f"Conflicting part codes in machining group: {codes}")
            code = codes.pop()
        base_groups.setdefault(code, []).append(members)
    coded = []
    used = set()
    for base, variants in base_groups.items():
        for index, members in enumerate(variants, start=1):
            code = f"{base}-{index:02}" if len(variants) > 1 else base
            if code in used or (code != base and code in base_groups):
                raise ValueError(f"Part code collision: {code}")
            used.add(code)
            coded.append((code, members))
    return sorted(coded, key=lambda group: group[0])


def _part_label(part: dict) -> str:
    component = part.get("component", "panel").replace("_", " ")
    ident = part.get("id", "")
    if ident.startswith("frame."):
        return "Frame rail"
    if ".drawer." in ident or ".opening-" in ident:
        return f"Drawer {component}"
    if ident.startswith("upper."):
        return f"Upper {component}"
    return f"Carcass {component}"


def _group_label(members: list[dict]) -> str:
    labels = list(dict.fromkeys(_part_label(part) for part in members))
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def _grain_values(members: list[dict], key: str, part_codes: dict[str, str]) -> str:
    values = {part.get(key, "unknown") for part in members}
    if len(values) == 1:
        return next(iter(values))
    pairs = {(part_codes[part["id"]], part.get(key, "unknown")) for part in members}
    return "; ".join(f"{code}: {value}" for code, value in sorted(pairs))


def _table(groups: list[tuple[str, list[dict]]], part_codes: dict[str, str]) -> str:
    rows = []
    for code, members in groups:
        part = members[0]
        dims = part.get("blank_mm", part["finished_mm"])
        grain = _grain_values(members, "grain_direction", part_codes)
        status = _grain_values(members, "grain_status", part_codes)
        note = "" if status == "confirmed" else f" ({html.escape(status)})"
        quantity = sum(member.get("quantity", 1) for member in members)
        rows.append(
            f"<tr><td>{html.escape(code)} — {html.escape(_group_label(members))}</td>"
            f"<td>{quantity}</td>"
            f"<td>{dims['length']:g} × {dims['width']:g} × {dims['thickness']:g}</td>"
            f"<td>{html.escape(part['material'])}</td>"
            f"<td>{html.escape(grain)}{note}</td></tr>"
        )
    return (
        "<p>Blank sizes are maximum stock envelopes. Profile geometry is not "
        "a machining instruction.</p><table><thead><tr><th>Part code</th>"
        "<th>Quantity</th><th>Max blank size, mm</th><th>Material</th>"
        "<th>Grain</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _page(title: str, content: str) -> str:
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>"
        "body{font:16px/1.55 system-ui;max-width:1000px;"
        "margin:40px auto;padding:0 24px;"
        "color:#243233;background:#fafaf7}h1{line-height:1.2}"
        "table{border-collapse:collapse;width:100%;font-size:14px}"
        "td,th{padding:10px;text-align:left;border-bottom:1px solid #d8dcd6}"
        ".draft{padding:16px;background:#fff0d4;border-left:5px solid #b77419}"
        "a{color:#226458}code{overflow-wrap:anywhere}"
        ".panel{border-top:1px solid #d8dcd6;padding:12px 0}"
        ".panel-drawing{display:flex;flex-direction:column;align-items:center;"
        "width:620px;max-width:100%;background:white;border:1px solid #d8dcd6}"
        ".panel-drawing svg{display:block;width:100%;max-width:600px;height:auto}"
        ".panel-drawing svg rect{fill:#fff;stroke:#333}"
        ".panel-dimensions{font-weight:600;font-size:13px;"
        "margin:4px 8px 8px;text-align:center}"
        "@media print{body{margin:0}.draft{border:2px solid #444}}"
        "</style><body><p class='draft'><strong>"
        "DRAFT — NOT FOR MANUFACTURING.</strong></p>"
        f"<h1>{html.escape(title)}</h1>{content}</body></html>"
    )


def _drawer_summary(result: dict) -> str:
    drawers = result.get("drawers", [])
    if not drawers:
        return "<p>Bare cabinet; this input has no drawer section.</p>"
    layout = result.get("drawer_layout", {})
    dims = (
        layout.get("closed_dimensions_mm")
        or result.get("overall_dimensions_mm")
        or result["dimensions_mm"]
    )
    distance = layout.get("display_open_distance_mm")
    pose = (
        f"{distance} mm" if distance is not None else "the nominal depth of each drawer"
    )
    face_thickness = layout.get("face_thickness_mm")
    face_gap = layout.get("face_to_carcass_gap_mm")
    face_details = (
        f" Lower drawer fronts are {face_thickness} mm thick with a "
        f"{face_gap} mm face-to-carcass gap."
        if face_thickness is not None and face_gap is not None
        else ""
    )
    parts = sum(len(drawer.get("part_ids", [])) for drawer in drawers)
    panel_count = sum(part.get("quantity", 1) for part in result["parts"])
    return (
        f"<p>{len(drawers)} drawer instances with {parts} physical drawer parts. "
        f"The cut list retains {panel_count} total physical panels. "
        "Closed overall assembly dimensions: "
        f"{dims['width']:g} wide × {dims['height']:g} high × "
        f"{dims['depth']:g} deep, mm.{face_details} The preview opens the drawers by "
        f"{html.escape(pose)}. This pose does not change "
        "exported coordinates.</p><h2>Drawer layout</h2><ul>"
        + "".join(
            f"<li>{count} × box {box[0]:g} × {box[1]:g} × {box[2]:g} mm; "
            f"overlay face {face[0]:g} × {face[1]:g} × {face[2]:g} mm.</li>"
            for (box, face), count in Counter(
                (
                    tuple(
                        drawer["box_mm"][key] for key in ("width", "height", "depth")
                    ),
                    tuple(
                        drawer["face_mm"][key]
                        for key in ("width", "height", "thickness")
                    ),
                )
                for drawer in drawers
            ).items()
        )
        + "</ul>"
    )


def _hardware_table(
    result: dict, part_codes: dict | None = None, *, diagnostics: bool = True
) -> str:
    hardware = result.get("hardware", [])
    if not hardware:
        return "<p>No hardware requirements are listed in this result.</p>"

    def number(value):
        return (
            f"{value:.1f}".rstrip("0").rstrip(".")
            if isinstance(value, int | float)
            else str(value)
        )

    rows = []
    for item in hardware:
        kind = item.get("type", "")
        labels = {
            "domino": "Carcass Domino tenons",
            "drawer_runner": "Drawer runners",
            "compatible_grooved_bottom_catch_pair": "Grooved-bottom catches",
            "concealed_door_hinge": "Concealed door hinges",
        }
        label = (
            item.get("name") or labels.get(kind) or kind.replace("_", " ") or "Hardware"
        )
        details = []
        if item.get("model"):
            details.append(str(item["model"]))
        elif item.get("slide_key"):
            details.append(str(item["slide_key"]))
        if item.get("size"):
            details.append(str(item["size"]) + " mm")
        if item.get("length_mm") is not None:
            details.append(number(item["length_mm"]) + " mm")
        if item.get("quantity") is not None:
            details.append("× " + number(item["quantity"]))
        elif kind == "domino" and diagnostics:
            details.append("Quantity unverified")
        quantities = item.get("quantity_by_part_number", {})
        if quantities:
            details.append(
                "Part numbers: "
                + ", ".join(
                    f"{part}: {number(count)}" for part, count in quantities.items()
                )
            )
        elif item.get("part_numbers"):
            details.append("Part numbers: " + ", ".join(item["part_numbers"]))
        if kind == "concealed_door_hinge":
            if item.get("nominal_opening_angle_deg") is not None:
                details.append(
                    f"Nominal opening: {number(item['nominal_opening_angle_deg'])}°"
                )
            doors = []
            for door in item.get("doors", []):
                code = (part_codes or {}).get(door.get("door_id"), "Door")
                size = door.get("size_mm", {})
                dimensions = " × ".join(
                    number(size[k]) for k in ("x", "z", "y") if k in size
                )
                edge = door.get("hinge_edge")
                door_detail = f"{code}: {dimensions} mm" if dimensions else code
                if edge:
                    door_detail += f", {edge} hinge edge"
                doors.append(door_detail)
            if doors:
                details.append("Doors: " + "; ".join(doors))
            if diagnostics:
                details.append("Hinge count, mounting and clearance unverified")
        sources = item.get("sources", [])
        rendered = html.escape(
            "; ".join(details)
            or ("Quantity and fit unverified" if diagnostics else "—")
        )
        if sources:
            rendered += (
                f' · <a href="{html.escape(str(sources[0]), quote=True)}">Source</a>'
            )
        rows.append(f"<tr><td>{html.escape(str(label))}</td><td>{rendered}</td></tr>")
    return (
        "<table><thead><tr><th>Hardware requirement</th><th>Details</th></tr>"
        "</thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _map_legend(cabinet_id: str, part_codes: dict[str, str]) -> str:
    entries = [
        f"{label}: {html.escape(part_codes[part_id])}"
        for label, part_id in (
            ("Top", f"{cabinet_id}.carcass.top"),
            ("Bottom", f"{cabinet_id}.carcass.bottom"),
        )
        if part_id in part_codes
    ]
    return f"<p>Map part codes — {'; '.join(entries)}.</p>" if entries else ""


def _candidate_maps(configs, cabinets, part_codes, generate) -> str:
    grouped = {}
    for cfg, cabinet in zip(configs, cabinets, strict=True):
        cabinet_id = cabinet["id"]
        codes = tuple(
            part_codes.get(f"{cabinet_id}.carcass.{component}")
            for component in ("top", "bottom")
        )
        # A common title makes the complete generated map comparable, including
        # its geometry and settings. Missing codes cannot establish equivalence.
        markup = generate(cfg, "Cabinet")
        key = (codes, markup) if all(codes) else (codes, markup, cabinet_id)
        if key not in grouped:
            grouped[key] = [cabinet_id, []]
        grouped[key][1].append(cabinet_id)
    sections = []
    for key, (first_id, names) in grouped.items():
        sections.append(
            f"<p>Cabinets: {html.escape(', '.join(names))}.</p>"
            + _map_legend(first_id, part_codes)
            + key[1]
        )
    return "".join(sections) or "<p>Candidate carcass maps are unavailable.</p>"


def _mortise_summary(
    configs, cabinets, joints, machining=None, *, concise=False
) -> str:
    if configs is None:
        return "<p>Candidate mortise layout is unavailable.</p>"
    from cabineteer.assembly import _candidate_positions, generate_draft_mortise_maps

    layouts = {}
    for cfg, cabinet in zip(configs, cabinets, strict=True):
        cabinet_id = cabinet["id"]
        count = sum(
            joint.get("type") == "domino"
            and joint.get("cabinet_id") == cabinet_id
            and any(".carcass." in part for part in joint.get("parts", []))
            for joint in joints
        )
        if not count:
            continue
        span = float(cfg.interior_depth)
        positions = _candidate_positions(span, cfg.domino_spec)
        if not positions or "unavailable" in generate_draft_mortise_maps(cfg):
            return (
                "<p>Candidate mortise layout is unavailable "
                "for at least one cabinet.</p>"
            )
        key = (span, positions)
        layouts[key] = layouts.get(key, 0) + count
    if not layouts:
        return ""
    lines = []
    for (span, positions), count in layouts.items():
        centers = ", ".join(f"{position:g}" for position in positions)
        spacing = (
            ", ".join(
                f"{right - left:g}"
                for left, right in zip(positions, positions[1:], strict=False)
            )
            or "not applicable"
        )
        lines.append(
            f"<li>{count} carcass joints: {len(positions)} candidate centers per joint "
            f"at {centers} mm from the back over a {span:g} mm span; "
            f"spacing {spacing} mm; back and front margins "
            f"{positions[0]:g} and {span - positions[-1]:g} mm. "
            f"That is {count * len(positions)} candidate tenons.</li>"
        )
    if machining:
        face = machining["face_depth_mm"]
        edge = machining["edge_depth_mm"]
        tenon = machining["tenon_length_mm"]
        walls = machining["face_wall_mm_by_cabinet"]
        wall_details = "; ".join(
            f"{html.escape(cabinet)}: {wall['min']:g}–{wall['max']:g} mm"
            for cabinet, wall in walls.items()
        )
        setup = (
            f"<p>User-specified router cutter: {machining['cutter_diameter_mm']:g} mm; "
            f"face depth {face['min']:g}–{face['max']:g} mm, paired with edge depth "
            f"{edge['max']:g}–{edge['min']:g} mm. Each pair totals {tenon:g} mm, "
            "with no glue clearance included. Nominal remaining side face wall "
            "for perimeter joints: "
            f"{wall_details}.</p>"
        )
    else:
        setup = ""
    return (
        (
            ""
            if concise
            else "<p>These candidate centers satisfy the configured grid, "
            "edge clearance and spacing limits.</p>"
        )
        + "<ul>"
        + "".join(lines)
        + "</ul>"
        + setup
    )


def render_documents(
    directory: Path, result: dict, configs=None, panel_views=None, panel_groups=None
) -> None:
    panel_maps = {}
    if configs is not None:
        from cabineteer.assembly import _panel_svg, draft_mortise_panel_maps

        centered = (
            result.get("domino_machining", {}).get("face_reference") == "centered"
            if result.get("domino_machining")
            else False
        )
        for cfg, cabinet in zip(configs, result["cabinets"], strict=True):
            if cfg.roof_angle_deg:
                continue
            maps = draft_mortise_panel_maps(cfg, centered_face_rows=centered)
            for component, canonical in (
                ("left_side", "side"),
                ("right_side", "side"),
                ("top", "top"),
                ("bottom", "bottom"),
            ):
                if canonical in maps:
                    panel_map = maps[canonical]
                    right_side = component == "right_side"
                    drawing = _panel_svg(
                        panel_map,
                        precise_ticks=True,
                        front_at_right=right_side,
                        panel_thickness=getattr(cfg, f"{canonical}_thickness"),
                        reference_back=True,
                    )
                    panel_maps[f"{cabinet['id']}.carcass.{component}"] = drawing
    # Drawer joints carry their own candidate centers. The native renderer
    # displays them on a flat map; the CAD view remains alongside it.
    from cabineteer.assembly import MortiseRow, PanelMortiseMap, _panel_svg

    parts_by_id = {part["id"]: part for part in result["parts"]}
    drawer_rows = {}
    for joint in result.get("joints", []):
        centers = joint.get("candidate_centers_from_bottom_mm")
        if joint.get("type") != "drawer_domino" or not centers:
            continue
        members = [parts_by_id.get(ident) for ident in joint.get("parts", [])]
        side = next(
            (
                part
                for part in members
                if part and part.get("component") in {"side_left", "side_right"}
            ),
            None,
        )
        end = next(
            (
                part
                for part in members
                if part and part.get("component") in {"inner_front", "back"}
            ),
            None,
        )
        if not side or not end:
            continue
        side_width = side["finished_mm"]["length"]
        inset = end["finished_mm"]["thickness"] / 2
        side_offset = inset if end["component"] == "inner_front" else side_width - inset
        end_width = end["finished_mm"]["length"]
        end_offset = 0 if side["component"] == "side_left" else end_width
        drawer_rows.setdefault(side["id"], []).append(
            MortiseRow("", "v", side_offset, tuple(centers), "face")
        )
        drawer_rows.setdefault(end["id"], []).append(
            MortiseRow("", "v", end_offset, tuple(centers), "edge")
        )
    for ident, rows in drawer_rows.items():
        part = parts_by_id[ident]
        size = part["finished_mm"]
        canonical = (
            "drawer_side" if part["component"].startswith("side_") else "drawer_end"
        )
        panel_map = PanelMortiseMap(
            part["component"],
            "",
            size["length"],
            size["width"],
            canonical,
            "width",
            "height",
            tuple(rows),
        )
        panel_maps[ident] = _panel_svg(
            panel_map,
            precise_ticks=True,
            panel_thickness=size["thickness"],
            drawer_map=True,
        )
    original_groups = panel_groups or [[part] for part in result["parts"]]
    views_by_part = {}
    split_groups = []
    for members in original_groups:
        view = (panel_views or {}).get(members[0]["id"])
        variants = {}
        for member in members:
            views_by_part[member["id"]] = view
            variants.setdefault(panel_maps.get(member["id"]), []).append(member)
        split_groups.extend(variants.values())
    groups = _coded_groups(
        split_groups,
        result.get("variables", {}).get("part_codes") if panel_groups else None,
    )
    part_codes = {part["id"]: code for code, members in groups for part in members}
    parts_by_id = {part["id"]: part for part in result["parts"]}
    cut_groups = [
        (
            ", ".join(sorted({part_codes[ident] for ident in group["members"]})),
            [parts_by_id[ident] for ident in group["members"]],
        )
        for group in group_cutting_blanks(result["parts"])
    ]
    cut_groups.sort(key=lambda group: (group[1][0]["material"].casefold(), group[0]))
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "status",
            "part_code",
            "quantity",
            "max_blank_length_mm",
            "max_blank_width_mm",
            "blank_thickness_mm",
            "material",
            "grain_direction",
            "grain_status",
        ]
    )
    for code, members in cut_groups:
        part = members[0]
        blank = part.get("blank_mm", part["finished_mm"])
        writer.writerow(
            [
                "DRAFT_NOT_FOR_MANUFACTURING",
                code,
                sum(member.get("quantity", 1) for member in members),
                blank["length"],
                blank["width"],
                blank["thickness"],
                part["material"],
                _grain_values(members, "grain_direction", part_codes),
                _grain_values(members, "grain_status", part_codes),
            ]
        )
    (directory / "parts.csv").write_text(buffer.getvalue(), encoding="utf-8")
    if result.get("assembly"):
        buffer = io.StringIO(newline="")
        fields = (
            "id",
            "owner",
            "component",
            "material",
            "quantity",
            "stock_mm",
            "local_frame",
            "geometry",
            "profile_mm",
            "extrusion_mm",
            "operations",
            "mounting",
        )
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        for part in result["assembly"]["parts"]:
            writer.writerow(
                {
                    key: json.dumps(value)
                    if isinstance(value, dict | list | tuple)
                    else value
                    for key, value in part.items()
                }
            )
        (directory / "parts.csv").write_text(buffer.getvalue(), encoding="utf-8")
    unique_checks = {
        (issue["severity"], issue["code"], issue["message"])
        for issue in result["checks"]
        if issue["severity"] == "error"
    }
    part_codes = {part["id"]: code for code, members in groups for part in members}
    checks = "".join(
        f"<li><strong>{html.escape(severity)}: {html.escape(code)}</strong>"
        f" — {html.escape(message)}</li>"
        for severity, code, message in sorted(unique_checks)
    )
    mortise_summary = _mortise_summary(
        configs, result["cabinets"], result["joints"], result.get("domino_machining")
    )
    dims = result["dimensions_mm"]
    dimension_label = (
        "Carcass dimensions" if result.get("drawers") else "Cabinet dimensions"
    )
    content = (
        f"<p>{dimension_label}: {dims['width']:g} wide × {dims['height']:g} high × "
        f"{dims['depth']:g} deep, mm.</p>"
        + _drawer_summary(result)
        + (
            '<p><a href="preview.html">Inspect 3D model</a> · '
            '<a href="parts.csv">Draft cut list</a> · '
            '<a href="assembly.html">Draft assembly guide</a> · '
            '<a href="result.json">Calculation JSON</a></p>'
        )
        + _table(cut_groups, part_codes)
        + (f"<h2>Calculation errors</h2><ul>{checks}</ul>" if checks else "")
        + (
            "<h2>Hardware requirements</h2>"
            + _hardware_table(result, part_codes, diagnostics=False)
            if result.get("drawers")
            else ""
        )
        + "<h2>Carcass mortise layout</h2>"
        + mortise_summary
        + "<h2>Dimension rules</h2><ul>"
        + "".join(
            f"<li>{html.escape(text)}</li>" for text in result["explanations"].values()
        )
        + f"</ul><p>Input identity: <code>{result['input_identity']}</code></p>"
    )
    if result.get("assembly"):
        operations = []
        for part in result["assembly"]["parts"]:
            for operation in part["operations"]:
                operations.append(
                    f"<li>{html.escape(part['id'])}: "
                    f"{html.escape(operation['kind'])} on "
                    f"{html.escape(operation['target'])} "
                    f"({html.escape(operation['status'])})</li>"
                )
        content = (
            f"<p>Occupied dimensions: {dims['width']:g} × {dims['height']:g} × "
            f"{dims['depth']:g} mm.</p>"
            '<p><a href="preview.html">Inspect 3D model</a> · '
            '<a href="parts.csv">Draft cut list</a> · '
            '<a href="result.json">Calculation JSON</a></p>'
            + _table(cut_groups, part_codes)
            + "<h2>Profile operations</h2><ul>"
            + "".join(operations)
            + "</ul><h2>Selected hardware</h2>"
            + _hardware_table(result, part_codes, diagnostics=False)
            + "<p>Hardware, support, joinery and installation "
            "remain unverified.</p>"
        )
    (directory / "report.html").write_text(
        _page(result["name"], content), encoding="utf-8"
    )
    joint_lines = set()
    for joint in result["joints"]:
        if joint.get("type") == "cabinet_connection":
            names = " and ".join(joint.get("cabinet_ids", []))
            codes = sorted(
                {part_codes[part] for part in joint["parts"] if part in part_codes}
            )
            joint_lines.add(f"{' ↔ '.join(codes)}: Cabinet connection between {names}.")
            continue
        codes = sorted(
            {part_codes[part] for part in joint["parts"] if part in part_codes}
        )
        label = " ↔ ".join(codes) or "Joint"
        if joint.get("type") == "domino" and any(
            ".carcass." in part for part in joint["parts"]
        ):
            continue
        # Drawer maps provide the corresponding candidate positions.
        if joint.get("type") == "drawer_domino" and all(
            part in drawer_rows for part in joint.get("parts", [])
        ):
            joint_lines.add(f"{label}: 6 × 40 mm Domino")
            continue
        if joint.get("type") != "domino":
            joint_lines.add(f"{label}: {joint.get('type', 'Joint').replace('_', ' ')}")
    joints = "".join(f"<li>{html.escape(line)}</li>" for line in sorted(joint_lines))
    panel_sections = []
    previous_material = None
    previous_prefix = None
    for code, members in sorted(
        groups, key=lambda group: (group[1][0]["material"].casefold(), group[0])
    ):
        part = members[0]
        material = part["material"]
        prefix = code[0] if code else ""
        if material != previous_material:
            panel_sections.append(f"<h3>{html.escape(material)}</h3>")
            previous_material = material
            previous_prefix = None
        if prefix != previous_prefix:
            panel_sections.append(f"<h4>{html.escape(prefix)}</h4>")
            previous_prefix = prefix
        view = views_by_part.get(part["id"])
        mortise_map = panel_maps.get(part["id"])
        illustration = mortise_map or view or "<p>Panel view unavailable.</p>"
        if part["id"] in drawer_rows and part["component"] == "back" and view:
            illustration += "<p>CAD profile</p>" + view
        quantity = sum(member.get("quantity", 1) for member in members)
        count = f" × {quantity}" if quantity > 1 else ""
        panel_sections.append(
            f"<section class='panel'><h5>{html.escape(code)} — "
            f"{html.escape(_group_label(members))}{count}</h5>"
            f"<div class='panel-drawing'>{illustration}</div>" + "</section>"
        )
    assembly = (
        "<p>Dimensions are in millimetres. Mortise marks show center positions.</p>"
        + "<h2>Carcass mortise layout</h2>"
        + _mortise_summary(
            configs,
            result["cabinets"],
            result["joints"],
            result.get("domino_machining"),
            concise=True,
        )
        + "<h2>Joint requirements</h2><ul>"
        + joints
        + "</ul>"
        + "<h2>Modeled panels</h2>"
        + "".join(panel_sections)
        + (
            "<h2>Drawer hardware and assembly limits</h2>"
            + _hardware_table(result, part_codes, diagnostics=False)
            if result.get("drawers")
            else ""
        )
        + "<p><a href='report.html'>Return to the review report</a></p>"
    )
    if result.get("assembly"):
        assembly = (
            "<p>Assembly and installation are unverified. See the modeled "
            "panel profiles in the calculation JSON.</p>" + "".join(panel_sections)
        )
    (directory / "assembly.html").write_text(
        _page("Draft cabinet assembly", assembly), encoding="utf-8"
    )


def render_geometry(root: Path, directory: Path, calculation):
    from cabineteer.visualize import visualize_assembly

    assembly, geometry = make_geometry(calculation)
    viewer_data = {
        **calculation.result,
        "title": calculation.result.get("name", "Cabinet preview"),
        "viewer_links": {"report": "report.html", "cutlist": "parts.csv"},
    }
    assembly_viewer = calculation.result.get("assembly", {}).get("viewer")
    if assembly_viewer:
        metadata = assembly_viewer.get("parts", {})
        viewer_data["parts"] = [
            {
                **part,
                **metadata.get(part["id"], {}),
                "finished_mm": part.get("finished_mm", part.get("stock_mm", {})),
            }
            for part in calculation.result.get("parts", [])
        ]
        viewer_data["cutting_groups"] = assembly_viewer.get("cutting_groups", [])
        viewer_data["drawers"] = assembly_viewer.get("drawers", [])
    generated = visualize_assembly(
        assembly,
        geometry,
        output_dir=directory,
        name="cabinet",
        open_browser=False,
        info={
            "status": "DRAFT — NOT FOR MANUFACTURING",
            **calculation.result["dimensions_mm"],
        },
        viewer_data=viewer_data,
    )
    original = Path(generated["html"])
    viewer = original.read_text(encoding="utf-8")
    remote = "https://cdn.jsdelivr.net/npm/three@0.165.0/"
    if remote not in viewer:
        raise ValueError("The pinned viewer asset contract changed.")
    viewer = viewer.replace(remote, "./assets/three/")
    for relative in (
        "build/three.module.js",
        "examples/jsm/loaders/GLTFLoader.js",
        "examples/jsm/controls/OrbitControls.js",
        "examples/jsm/utils/BufferGeometryUtils.js",
        "LICENSE",
    ):
        target = directory / "assets/three" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / ".local/viewer/three" / relative, target)
    (directory / "preview.html").write_text(viewer, encoding="utf-8")
    original.unlink()
    return assembly


def build_project(root: Path, path: Path) -> dict:
    environment = doctor(root)
    if not environment["ok"]:
        raise InputError("environment_invalid", "Run doctor and setup before building.")
    project = load_project(path)
    calculation = calculate(project)
    errors = [
        item for item in calculation.result["checks"] if item["severity"] == "error"
    ]
    if errors:
        raise InputError("calculation_invalid", json.dumps(errors))
    builds = project.path / "build"
    builds.mkdir(exist_ok=True)
    lock = builds / ".lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise InputError("build_busy", f"Another build owns {lock}.") from exc
    revision = f"{project.identity[:12]}-{uuid.uuid4().hex[:8]}"
    stage = builds / f".staging-{revision}"
    published = None
    pointer = None
    try:
        os.close(descriptor)
        stage.mkdir()
        write_json(stage / "result.json", calculation.result)
        snapshots = stage / "inputs"
        snapshots.mkdir()
        (snapshots / "project.py").write_text(project.source, encoding="utf-8")
        write_json(snapshots / "variables.json", project.variables)
        write_json(snapshots / "calculated.json", project.calculated)
        built_drawer_configs = {
            item["drawer_id"]: item["config"] for item in calculation.drawer_instances
        }
        write_json(
            snapshots / "native-config.json",
            native_snapshot(project, built_drawer_configs),
        )
        for name in ("uv.lock", "cabineteer.lock.json", "viewer-assets.lock.json"):
            shutil.copy2(root / name, snapshots / name)
        shutil.copytree(
            root / "vendor/cabineteer/src/cabineteer",
            snapshots / "engine-source",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        runtime = root / ".local/runtime.json"
        if runtime.is_file():
            shutil.copy2(runtime, snapshots / "runtime.json")
        shutil.copytree(
            root / "src/buratino",
            snapshots / "adapter-source",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        for directory in ("profiles", "catalog"):
            source_dir = root / directory
            if source_dir.is_dir():
                shutil.copytree(source_dir, snapshots / directory)
        assembly = render_geometry(root, stage, calculation)
        if input_identity(path) != project.identity:
            raise InputError(
                "inputs_changed", "Inputs changed during the build; rebuild."
            )
        from .panel_views import panel_groups, panel_views

        groups = panel_groups(
            assembly, calculation.result["parts"], calculation.result["joints"]
        )
        views = panel_views(assembly, [group[0] for group in groups])
        render_documents(
            stage,
            calculation.result,
            None if calculation.native_assembly is not None else calculation.configs,
            views,
            groups,
        )
        if input_identity(path) != project.identity:
            raise InputError(
                "inputs_changed", "Inputs changed during the build; rebuild."
            )
        manifest = {
            "schema_version": 1,
            "revision": revision,
            "status": "draft",
            "manufacturing_ready": False,
            "input_identity": project.identity,
            "project_source_sha256": project.source_hash,
            "rule_files": project.rule_files,
            "created_at": datetime.now(UTC).isoformat(),
            "engine": read_json(root / "cabineteer.lock.json"),
            "dependency_lock_sha256": file_hash(root / "uv.lock"),
            "files": {
                str(file.relative_to(stage)): file_hash(file)
                for file in stage.rglob("*")
                if file.is_file()
            },
        }
        write_json(stage / "manifest.json", manifest)
        published = builds / revision
        stage.rename(published)
        pointer = builds / ".latest.tmp"
        write_json(pointer, {"revision": revision})
        pointer.replace(builds / "latest.json")
        pointer = None
        return {
            "status": "draft",
            "manufacturing_ready": False,
            "revision": revision,
            "input_identity": project.identity,
            "directory": str(published),
            "checks": calculation.result["checks"],
        }
    except Exception as exc:
        failed = builds / f"failed-{revision}"
        try:
            if stage.exists():
                stage.rename(failed)
            elif published is not None and published.exists():
                published.rename(failed)
            if failed.exists():
                write_json(
                    failed / "failure.json",
                    {"status": "failed", "error": str(exc)},
                )
        except OSError:
            # Preserve the triggering error if even the diagnostic write fails.
            pass
        raise
    finally:
        if pointer is not None:
            pointer.unlink(missing_ok=True)
        lock.unlink()

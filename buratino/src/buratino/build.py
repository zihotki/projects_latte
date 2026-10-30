"""Draft packages. Each build is staged before it becomes the latest result."""

import csv
import html
import io
import json
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .cut_service_report import write_cutlists
from .engine import calculate, make_geometry
from .environment import doctor, file_hash, read_json
from .grouping import group_cutting_blanks
from .machining_notes import machining_notes
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
    if component == "carcass":
        component = part["id"].rsplit("/", 1)[-1].replace("_", " ")
    if component.startswith("drawer "):
        return component.replace("drawer ", "Drawer ", 1)
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
        dims = part.get("blank_mm") or part.get("finished_mm", {})
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
        "a{color:#226458}code{overflow-wrap:anywhere}"
        ".panel{border-top:1px solid #d8dcd6;padding:12px 0}"
        ".panel-drawing{display:flex;flex-direction:column;align-items:center;"
        "width:620px;max-width:100%;margin:0;background:white;"
        "border:1px solid #d8dcd6}"
        ".panel-drawing figcaption{padding:0 16px;font-size:14px;width:100%;"
        "box-sizing:border-box}"
        ".panel-drawing svg{display:block;width:100%;max-width:600px;height:auto}"
        ".panel-drawing svg rect{fill:#fff;stroke:#333}"
        ".panel-dimensions{font-weight:600;font-size:13px;"
        "margin:4px 8px 8px;text-align:center}"
        "@media print{body{margin:0}}"
        "</style><body>"
        f"<h1>{html.escape(title)}</h1>{content}</body></html>"
    )


def render_documents(
    directory: Path,
    result: dict,
    configs=None,
    panel_views=None,
    panel_groups=None,
    *,
    assembly_geometry=None,
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
    if result.get("space_model"):
        cut_groups = [
            (
                ", ".join(
                    sorted(
                        {
                            part_codes[ident]
                            for ident in group["members"]
                            if ident in part_codes
                        }
                    )
                ),
                [parts_by_id[ident] for ident in group["members"]],
            )
            for group in result["cutting_groups"]
        ]
    else:
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
    fields = [
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
    if result.get("space_model"):
        fields.extend(("part_ids", "operation_record_ids"))
    writer.writerow(fields)
    for code, members in cut_groups:
        part = members[0]
        blank = part.get("blank_mm") or part.get("finished_mm", {})
        row = [
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
        if result.get("space_model"):
            row.extend(
                (
                    ", ".join(member["id"] for member in members),
                    ", ".join(
                        operation["id"]
                        for member in members
                        for operation in member.get("operations", [])
                    ),
                )
            )
        writer.writerow(row)
    (directory / "parts.csv").write_text(buffer.getvalue(), encoding="utf-8")
    if result.get("assembly") and not result.get("space_model"):
        buffer = io.StringIO(newline="")
        fields = (
            "id",
            "owner",
            "component",
            "material",
            "quantity",
            "stock_mm",
            "local_frame",
            "grain_axis_local",
            "grain_direction",
            "grain_status",
            "surface_normal_axis_local",
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
    navigation = (
        '<nav aria-label="Report navigation"><a href="preview.html">Model</a> · '
        '<a href="#cutlists">Cut lists</a> · '
        '<a href="#part-drawings">Part drawings</a> · '
        '<a href="#assembly">Assembly</a></nav>'
    )
    dims = result.get("overall_dimensions_mm") or result["dimensions_mm"]
    overview = (
        f"<p>Dimensions: {dims['width']:g} wide × {dims['height']:g} high × "
        f"{dims['depth']:g} deep, mm.</p>"
    )
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
        illustration = view or mortise_map or "<p>Panel view unavailable.</p>"
        if mortise_map and view:
            illustration += "<p>Mortise center positions</p>" + mortise_map
        quantity = sum(member.get("quantity", 1) for member in members)
        count = f" × {quantity}" if quantity > 1 else ""
        blank = part.get("blank_mm") or part.get("finished_mm", {})
        notes = machining_notes(part)
        caption = (
            "<ul class='machining-dimensions'>"
            + "".join(f"<li>{html.escape(note)}</li>" for note in notes)
            + "</ul>"
            if notes
            else ""
        )
        panel_sections.append(
            f"<section class='panel'><h5>{html.escape(code)} — "
            f"{html.escape(_group_label(members))}{count}</h5>"
            f"<p>Quantity: {quantity}. Stock: {blank['length']:g} × "
            f"{blank['width']:g} × {blank['thickness']:g} mm.</p>"
            f"<figure class='panel-drawing'>{illustration}"
            f"<figcaption>{caption}</figcaption></figure></section>"
        )
    drawings = (
        "<h2>Part drawings</h2>"
        "<p>Dimensions are in millimetres. Dashed edges show hidden cuts. "
        "For stock XYZ, measure from the uncut stock minimum corner. "
        "Face U/V follow the other two XYZ axes in order; depth runs inward. "
        "For stock L/W/T, L is length, W is width and T is thickness.</p>"
        + "".join(panel_sections)
    )
    from .exploded_views import exploded_views

    assembly_parts = result["parts"]
    viewer = result.get("assembly", {}).get("viewer")
    if viewer:
        metadata = viewer.get("parts", {})
        if isinstance(metadata, list):
            metadata = {part["id"]: part for part in metadata}
        assembly_parts = [
            {
                **part,
                **metadata.get(part["id"], {}),
                **{key: part[key] for key in ("role", "geometry") if key in part},
                **(
                    {"finished_mm": part["finished_mm"]}
                    if part.get("finished_mm")
                    else {}
                ),
            }
            for part in result["parts"]
        ]
    assembly_view = exploded_views(assembly_geometry, assembly_parts, part_codes)
    assembly_section = (
        '<section id="assembly"><h2>Assembly</h2>'
        + (assembly_view or "<p>Exploded assembly view unavailable.</p>")
        + "</section>"
    )
    content = (
        navigation
        + overview
        + write_cutlists(directory, result, part_codes)
        + '<section id="part-drawings">'
        + drawings
        + "</section>"
        + assembly_section
        + '<p><a href="parts.csv">Parts data</a> · '
        '<a href="result.json">Calculation JSON</a></p>'
    )
    (directory / "report.html").write_text(
        _page(result["name"], content), encoding="utf-8"
    )


def render_geometry(root: Path, directory: Path, calculation):
    from cabineteer.visualize import visualize_assembly

    assembly, geometry = make_geometry(calculation)
    viewer_data = {
        **calculation.result,
        "title": calculation.result.get("name", "Cabinet preview"),
        "viewer_links": {"report": "report.html"},
    }
    assembly_viewer = calculation.result.get("assembly", {}).get("viewer")
    if assembly_viewer:
        metadata = assembly_viewer.get("parts", {})
        if isinstance(metadata, list):
            metadata = {part["id"]: part for part in metadata}
        viewer_data["parts"] = [
            {
                **part,
                **metadata.get(part["id"], {}),
                **(
                    {"finished_mm": part["finished_mm"]}
                    if part.get("finished_mm")
                    else {}
                ),
            }
            for part in calculation.result.get("parts", [])
        ]
        viewer_data["cutting_groups"] = calculation.result.get(
            "cutting_groups", assembly_viewer.get("cutting_groups", [])
        )
        viewer_data["drawers"] = assembly_viewer.get("drawers", [])
        viewer_data["instances"] = assembly_viewer.get("instances", [])
        viewer_data["cabinets"] = assembly_viewer.get(
            "cabinets", calculation.result.get("cabinets", [])
        )
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
        shutil.copy2(root / "vendor/three" / relative, target)
    (directory / "preview.html").write_text(viewer, encoding="utf-8")
    original.unlink()
    return assembly


def build_project(
    root: Path, path: Path, *, expected_identity: str | None = None
) -> dict:
    environment = doctor(root)
    if not environment["ok"]:
        raise InputError("environment_invalid", "Run doctor and setup before building.")
    project = load_project(path)
    if expected_identity is not None and project.identity != expected_identity:
        raise InputError(
            "inputs_changed", "Inputs changed before the build captured them; rebuild."
        )
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
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        stage.mkdir()
        calculation.result["source_revision"] = revision
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
        runtime = root / ".cache/runtime.json"
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
        if calculation.space_model is not None:
            from cabineteer.space_adapter import validate_model

            calculation.result["physical_validation"] = validate_model(
                calculation.space_model, shapes=calculation.space_shapes
            )
            write_json(stage / "result.json", calculation.result)
        if input_identity(path) != project.identity:
            raise InputError(
                "inputs_changed", "Inputs changed during the build; rebuild."
            )
        from .panel_views import panel_groups, panel_views

        panel_assembly = assembly
        if calculation.space_model is not None:
            import cadquery as cq

            panel_assembly = cq.Assembly(name="physical_space_parts")
            for part in calculation.result["parts"]:
                panel_assembly.add(
                    calculation.space_shapes[part["id"]], name=part["role"]
                )
        groups = panel_groups(
            panel_assembly,
            calculation.result["parts"],
            calculation.result["joints"],
        )
        views = panel_views(panel_assembly, [group[0] for group in groups])
        render_documents(
            stage,
            calculation.result,
            None
            if calculation.native_assembly is not None
            or calculation.space_model is not None
            else calculation.configs,
            views,
            groups,
            assembly_geometry=panel_assembly,
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
            "physical_validation": calculation.result.get("physical_validation"),
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

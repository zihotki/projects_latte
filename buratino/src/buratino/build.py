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

from .engine import calculate, make_geometry
from .environment import doctor, file_hash, read_json
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


def _table(result: dict) -> str:
    rows = []
    for group in result["cutting_groups"]:
        dims = group.get("blank_mm", group["finished_mm"])
        members = ", ".join(group["members"])
        rows.append(
            f"<tr><td>{html.escape(group['label'])}</td>"
            f"<td>{group['quantity']}</td>"
            f"<td>{dims['length']:g} × {dims['width']:g} × {dims['thickness']:g}</td>"
            f"<td>{html.escape(group['material'])}</td>"
            f"<td>{html.escape(group['grain_direction'])} "
            f"({html.escape(group['grain_status'])})</td>"
            f"<td>{html.escape(members)}</td></tr>"
        )
    return (
        "<p>Equal stock blanks are grouped. Blank size is the maximum local-axis "
        "stock envelope; profile geometry is not a machining instruction.</p>"
        "<table><thead><tr><th>Cutting group</th><th>Quantity</th>"
        "<th>Max blank size, mm</th><th>Material</th><th>Grain</th>"
        "<th>Physical part IDs</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
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
        "@media print{body{margin:0}.draft{border:2px solid #444}}"
        "</style><body><p class='draft'><strong>"
        "DRAFT — NOT FOR MANUFACTURING.</strong> "
        "Unconfirmed dimensions, materials and machining remain open.</p>"
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
    face_thickness = layout.get("face_thickness_mm", "unknown")
    face_gap = layout.get("face_to_carcass_gap_mm", "unknown")
    parts = sum(len(drawer.get("part_ids", [])) for drawer in drawers)
    panel_count = sum(part.get("quantity", 1) for part in result["parts"])
    return (
        f"<p>{len(drawers)} drawer instances with {parts} physical drawer parts. "
        f"The cut list retains {panel_count} total physical panels. "
        f"Closed cabinet dimensions, including {face_thickness} mm overlay "
        f"fronts and a {face_gap} mm face-to-carcass gap: "
        f"{dims['width']:g} wide × {dims['height']:g} high × "
        f"{dims['depth']:g} deep, mm. The preview opens the drawers by "
        f"{html.escape(pose)}, using nominal drawer depth as an "
        "approximation; actual "
        "runner travel is unverified. This pose does not change "
        "exported coordinates.</p><h2>Drawer layout</h2><ul>"
        + "".join(
            f"<li>Drawer {drawer.get('drawer_index', index)}: box "
            f"{drawer['box_mm']['width']:g} × {drawer['box_mm']['height']:g} × "
            f"{drawer['box_mm']['depth']:g} mm; overlay face "
            f"{drawer['face_mm']['width']:g} × {drawer['face_mm']['height']:g} × "
            f"{drawer['face_mm']['thickness']:g} mm.</li>"
            for index, drawer in enumerate(drawers, start=1)
        )
        + "</ul><p>Drawer box corner fastening and groove dimensions are "
        "unverified. Bottom groove fit needs workshop confirmation. A metal "
        "brace is future manual work and is not modeled.</p>"
    )


def _hardware_table(result: dict) -> str:
    hardware = result.get("hardware", [])
    if not hardware:
        return "<p>No hardware requirements are listed in this result.</p>"
    rows = []
    for item in hardware:
        kind = item.get("type", "")
        labels = {
            "domino": "Carcass Domino tenons",
            "drawer_runner": "Hettich Quadro V6 runners",
            "compatible_grooved_bottom_catch_pair": "Grooved-bottom catch pairs",
        }
        label = (
            item.get("name") or labels.get(kind) or kind or item.get("id") or "Hardware"
        )
        detail_rows = []
        for key, value in item.items():
            if key in {"name", "type", "id"}:
                continue
            label_key = html.escape(str(key).replace("_", " "))
            if key == "sources" and isinstance(value, list):
                shown = ", ".join(
                    f'<a href="{html.escape(str(url), quote=True)}">source</a>'
                    for url in value
                )
            elif isinstance(value, list):
                shown = html.escape(", ".join(str(item) for item in value))
            else:
                shown = html.escape(str(value))
            detail_rows.append(f"{label_key}: {shown}")
        details = "; ".join(detail_rows)
        rows.append(
            f"<tr><td>{html.escape(str(label))}</td>"
            f"<td>{details or 'Quantity and fit unverified'}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Hardware requirement</th><th>Details</th></tr>"
        "</thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def render_documents(directory: Path, result: dict) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "status",
            "id",
            "quantity",
            "max_blank_length_mm",
            "max_blank_width_mm",
            "blank_thickness_mm",
            "material",
            "grain_direction",
            "grain_status",
            "member_ids",
            "length_mm",
            "width_mm",
            "thickness_mm",
            "member_details_json",
        ]
    )
    for group in result["cutting_groups"]:
        dims = group["finished_mm"]
        blank = group.get("blank_mm", dims)
        writer.writerow(
            [
                "DRAFT_NOT_FOR_MANUFACTURING",
                group["id"],
                group["quantity"],
                blank["length"],
                blank["width"],
                blank["thickness"],
                group["material"],
                group["grain_direction"],
                group["grain_status"],
                ", ".join(group["members"]),
                dims["length"],
                dims["width"],
                dims["thickness"],
                json.dumps(
                    group.get("member_details", []),
                    separators=(",", ":"),
                    ensure_ascii=True,
                ),
            ]
        )
    (directory / "parts.csv").write_text(buffer.getvalue(), encoding="utf-8")
    checks = "".join(
        f"<li><strong>{html.escape(issue['severity'])}: "
        f"{html.escape(issue['code'])}</strong> — {html.escape(issue['message'])}</li>"
        for issue in result["checks"]
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
        + _table(result)
        + "<h2>Checks and open inputs</h2><ul>"
        + checks
        + "</ul>"
        + (
            "<h2>Hardware requirements</h2>"
            + _hardware_table(result)
            + "<p>These are requirements only. No hardware geometry is rendered, "
            "and the machining details remain unverified.</p>"
            if result.get("drawers")
            else ""
        )
        + (
            "<h2>Machining status</h2><p>Drawer machining locations, corner "
            "fastening and hardware clearances remain unverified. The package "
            "is a draft and is not a manufacturing release.</p>"
            if result.get("drawers")
            else "<h2>Machining status</h2><p>Carcass mortise positions, depths, "
            "settings, and quantities remain unverified. This package is a "
            "draft and is not a manufacturing release.</p>"
        )
        + "<h2>Dimension rules</h2><ul>"
        + "".join(
            f"<li>{html.escape(text)}</li>" for text in result["explanations"].values()
        )
        + f"</ul><p>Input identity: <code>{result['input_identity']}</code></p>"
    )
    (directory / "report.html").write_text(
        _page(result["name"], content), encoding="utf-8"
    )
    joints = "".join(
        f"<li>{html.escape(joint['id'])}: "
        f"{html.escape(' ↔ '.join(joint['parts']))}; "
        + (
            "6×40 mm Domino carcass joint. Mortise positions, depths, settings, "
            "and quantity are unverified."
            if joint.get("type") == "domino"
            and any(".carcass." in part for part in joint["parts"])
            else (
                "Cabinet connection between "
                + html.escape(" and ".join(joint["cabinet_ids"]))
                + "; fastening and capacity are unverified."
                if joint.get("type") == "cabinet_connection"
                else (
                    "Drawer corner fastening is unverified; "
                    "no Domino recipe is claimed."
                )
            )
        )
        + "</li>"
        for joint in result["joints"]
    )
    assembly = (
        "<p>This guide describes the assembly order only. It does not authorize "
        "cutting, drilling, or gluing.</p>"
        + _table(result)
        + "<h2>Joint requirements</h2><ul>"
        + joints
        + "</ul>"
        + (
            "<h2>Drawer hardware and assembly limits</h2>"
            + _hardware_table(result)
            + "<p>Do not infer drawer machining from this list. Drawer corners "
            "have no Domino claim; their fastening and hardware preparation "
            "remain unverified. A metal brace is future "
            "manual work and is not modeled.</p>"
            if result.get("drawers")
            else ""
        )
        + "<h2>Planned sequence</h2><ol>"
        "<li>Confirm fit allowances, stock, edge treatment, back attachment, and "
        "6×40 mortise data. Regenerate the documents after each change.</li>"
        "<li>Label the left and right sides, top, bottom, and back "
        "by their part IDs.</li>"
        "<li>After machining is verified, dry-fit both sides with the top and bottom. "
        "Check diagonals and outside dimensions before glue-up.</li>"
        "<li>Check back insertion and fastening access during the dry fit. "
        "The current back construction is provisional.</li>"
        "<li>Resolve any fit issue in the input files and rebuild "
        "before final assembly.</li>"
        "</ol><p><a href='report.html'>Return to the review report</a></p>"
    )
    (directory / "assembly.html").write_text(
        _page("Draft cabinet assembly", assembly), encoding="utf-8"
    )


def render_geometry(root: Path, directory: Path, calculation) -> None:
    from cabineteer.visualize import visualize_assembly

    from .viewer import viewer_extension

    assembly, geometry = make_geometry(calculation)
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
    # Extend the upstream viewer without changing the pinned engine source.
    for name in ("preview.js", "preview.css"):
        shutil.copy2(
            Path(__file__).parent / "assets" / name, directory / "assets" / name
        )
    extension = viewer_extension()
    (directory / "preview.html").write_text(
        viewer.replace("</body>", extension + "</body>"), encoding="utf-8"
    )
    original.unlink()


def build_project(root: Path, path: Path) -> dict:
    environment = doctor(root)
    if not environment["ok"]:
        raise InputError("environment_invalid", "Run doctor and setup before building.")
    project = load_project(path)
    calculation = calculate(project)
    # Preserve the native machining errors in every report. The audited 6x40
    # depth is unverified, so these block manufacturing, not a geometric draft.
    errors = [
        item
        for item in calculation.result["checks"]
        if item["severity"] == "error"
        and item["code"] != "cabineteer.domino_panel_thickness"
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
        render_documents(stage, calculation.result)
        render_geometry(root, stage, calculation)
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

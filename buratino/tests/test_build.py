import csv
import json
import shutil
import threading
import urllib.error
import urllib.request

import pytest

from buratino import build
from buratino.environment import file_hash, read_json, runtime_status
from buratino.preview import input_status, latest_build, preview_server
from buratino.project import InputError, load_project


def test_build_captures_consistent_outputs_without_editing_inputs(root, project):
    before = load_project(project).identity
    outcome = build.build_project(root, project)
    directory, manifest = latest_build(project)
    result = read_json(directory / "result.json")
    assert len(result["parts"]) == 5
    assert outcome["status"] == "draft"
    assert manifest["manufacturing_ready"] is False
    assert (
        manifest["engine"]["commit"]
        == read_json(root / "cabineteer.lock.json")["commit"]
    )
    assert load_project(project).identity == before
    engine = root / "vendor/cabineteer/src/cabineteer"
    captured = directory / "inputs/engine-source"
    assert (captured / "assembly.py").read_bytes() == (
        engine / "assembly.py"
    ).read_bytes()
    assert manifest["rule_files"][
        "vendor/cabineteer/src/cabineteer/assembly.py"
    ] == file_hash(captured / "assembly.py")
    with (directory / "parts.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4
    assert sum(int(row["quantity"]) for row in rows) == 5
    assert len({row["part_code"] for row in rows}) == len(rows)
    assert all(float(row["max_blank_length_mm"]) > 0 for row in rows)
    assert all(row["status"] == "DRAFT_NOT_FOR_MANUFACTURING" for row in rows)
    report = (directory / "report.html").read_text()
    assembly = (directory / "assembly.html").read_text()
    assert "Physical part IDs" not in report and "carcass.left_side" not in report
    assert "Physical part IDs" not in assembly and "carcass.left_side" not in assembly
    assert all(
        row["part_code"] in report
        and all(code in assembly for code in row["part_code"].split(", "))
        for row in rows
    )
    viewer = (directory / "preview.html").read_text()
    assert "cdn.jsdelivr.net" not in viewer
    assert (directory / "assets/three/examples/jsm/loaders/GLTFLoader.js").is_file()
    assert (directory / "cabinet.glb").read_bytes()[:4] == b"glTF"
    first_hashes = dict(manifest["files"])
    second = build.build_project(root, project)
    assert second["revision"] != outcome["revision"]
    assert all(
        file_hash(directory / name) == digest for name, digest in first_hashes.items()
    )
    assert (directory / "inputs/project.py").read_text() == (
        project / "project.py"
    ).read_text()
    assert read_json(directory / "inputs/variables.json")["width_mm"] == 720
    assert read_json(directory / "inputs/native-config.json")["project"]["name"] == (
        "simple-cabinet"
    )
    assert (
        read_json(directory / "inputs/native-config.json")["resolved_cabinets"][0][
            "config"
        ]["width"]
        == 720
    )
    profile = read_json(directory / "inputs/native-config.json")["hardware_profiles"][
        "hettich_quadro_v6_eb20"
    ]
    assert profile["source_data"]["runner_length_mm"] == 450
    assert profile["native_slide_spec"]["available_lengths"] == [450]


def test_native_real_assembly_build_reports_resolved_contents(root, tmp_path):
    project = tmp_path / "real-assembly-native"
    shutil.copytree(root / "projects/real-assembly-native", project)
    outcome = build.build_project(root, project)
    directory, _ = latest_build(project)
    result = read_json(directory / "result.json")
    assert outcome["status"] == "draft"
    assert len(result["cabinets"]) == 2
    assert len(result["frames"]) == 2
    assert len(result["upper_cabinets"]) == 1
    assert len(result["drawers"]) == 9
    assert len(result["parts"]) == 91
    assert (directory / "report.html").is_file()
    assert (directory / "cabinet.glb").read_bytes()[:4] == b"glTF"


def test_drawer_reports_keep_actual_parts_and_unverified_work_visible(root, tmp_path):
    project = tmp_path / "drawer-cabinet"
    shutil.copytree(
        root / "projects/drawer-cabinet",
        project,
        ignore=shutil.ignore_patterns("build"),
    )
    outcome = build.build_project(root, project)
    directory, _manifest = latest_build(project)
    result = read_json(directory / "result.json")
    report = (directory / "report.html").read_text()
    assembly = (directory / "assembly.html").read_text()
    viewer = (directory / "preview.html").read_text()

    assert outcome["status"] == "draft"
    assert len(result["drawers"]) == 4
    assert sum(group["quantity"] for group in result["cutting_groups"]) == 29
    assert "4 drawer instances with 24 physical drawer parts" in report
    assert "29 total physical panels" in report
    assert "Lower drawer fronts are 18 mm thick" in report
    assert "2 mm face-to-carcass gap" in report
    assert "520 deep" in report
    assert "runner" in report.lower() and "catch" in report.lower()
    assert "future manual work" not in report
    assert "groove dimensions" not in report
    assert "groove fit" not in report
    assert "candidate centers per joint" in assembly
    assert "Drawer corners have no Domino claim" not in assembly
    assert "Candidate carcass mortise maps" not in assembly
    assert "EDGE mortise centers from BACK (mm)" in assembly
    assert "class='panel-drawing'" in assembly
    assert "Stock thickness:" in assembly
    assert "Physical part IDs:" not in assembly
    assert 'id="drawer-pose-toggle"' in viewer
    assert 'id="drawer-pose-toggle" type="button" aria-pressed="false" hidden' in viewer
    assert 'id="viewer-toolbar" aria-label="Cabinet viewer controls"' in viewer
    assert 'id="viewer-sheet" aria-label="Cabinet details"' in viewer
    assert 'id="parts-tab"' in viewer
    assert 'id="focus-selection" type="button" aria-pressed="false" disabled' in viewer
    assert "ui.drawerPose.setAttribute('aria-pressed', String(open))" in viewer
    assert "result.overall_dimensions_mm ?? result.dimensions_mm" in viewer
    assert "mm overall" in viewer
    native_config = read_json(directory / "inputs/native-config.json")[
        "drawer_configs"
    ]["cabinet/column-0/opening-0"]
    assert native_config["buratino_material"] == (
        "Melamine-faced board; core and measured thickness unverified"
    )
    assert native_config["buratino_box_bottom_clearance_mm"] == 30
    assert native_config["buratino_rear_corner_clearance_width_mm"] == 30


def test_failed_export_preserves_previous_build_and_releases_lock(
    root, project, monkeypatch
):
    first = build.build_project(root, project)

    def fail_export(*_args):
        raise RuntimeError("controlled export failure")

    monkeypatch.setattr(build, "render_geometry", fail_export)
    with pytest.raises(RuntimeError, match="controlled export failure"):
        build.build_project(root, project)
    assert latest_build(project)[1]["revision"] == first["revision"]
    failures = list((project / "build").glob("failed-*/failure.json"))
    assert len(failures) == 1
    assert read_json(failures[0])["status"] == "failed"
    assert not (project / "build/.lock").exists()


def test_failed_latest_pointer_replace_isolated_from_published_build(
    root, project, monkeypatch
):
    first = build.build_project(root, project)
    replace = type(project).replace

    def fail_latest_pointer(source, target):
        if source.name == ".latest.tmp" and target.name == "latest.json":
            raise OSError("controlled latest pointer failure")
        return replace(source, target)

    monkeypatch.setattr(type(project), "replace", fail_latest_pointer)
    with pytest.raises(OSError, match="controlled latest pointer failure"):
        build.build_project(root, project)

    assert latest_build(project)[1]["revision"] == first["revision"]
    assert not (project / "build/.latest.tmp").exists()
    failed = list((project / "build").glob("failed-*/failure.json"))
    assert len(failed) == 1
    assert read_json(failed[0])["status"] == "failed"
    failed_revision = failed[0].parent.name.removeprefix("failed-")
    assert not (project / "build" / failed_revision).exists()


def test_failed_diagnostic_write_keeps_pointer_failure_isolated(
    root, project, monkeypatch
):
    first = build.build_project(root, project)
    replace = type(project).replace
    write_json = build.write_json

    def fail_latest_pointer(source, target):
        if source.name == ".latest.tmp" and target.name == "latest.json":
            raise OSError("controlled latest pointer failure")
        return replace(source, target)

    def fail_failure_diagnostic(path, value):
        if path.name == "failure.json":
            raise OSError("controlled diagnostic write failure")
        return write_json(path, value)

    monkeypatch.setattr(type(project), "replace", fail_latest_pointer)
    monkeypatch.setattr(build, "write_json", fail_failure_diagnostic)
    with pytest.raises(OSError, match="controlled latest pointer failure"):
        build.build_project(root, project)

    assert latest_build(project)[1]["revision"] == first["revision"]
    assert not (project / "build/.latest.tmp").exists()
    assert not (project / "build/.lock").exists()
    failed = list((project / "build").glob("failed-*"))
    assert len(failed) == 1
    failed_revision = failed[0].name.removeprefix("failed-")
    assert not (project / "build" / failed_revision).exists()
    assert not (failed[0] / "failure.json").exists()


def test_changed_inputs_during_export_are_not_published(root, project, monkeypatch):
    first = build.build_project(root, project)

    def edit_during_export(*_args):
        source = (project / "project.py").read_text()
        (project / "project.py").write_text(
            source.replace('"width_mm": 720', '"width_mm": 700')
        )

    monkeypatch.setattr(build, "render_geometry", edit_during_export)
    with pytest.raises(InputError) as failure:
        build.build_project(root, project)
    assert failure.value.code == "inputs_changed"
    assert latest_build(project)[1]["revision"] == first["revision"]
    assert input_status(project, first["input_identity"])["status"] == "stale"


def test_preview_serves_only_allowlisted_build_files_and_reports_invalid_inputs(
    root, project
):
    build.build_project(root, project)
    with preview_server(project) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(base + "/preview.html") as response:
                assert response.status == 200
                assert b"draft-badge" in response.read()
            with urllib.request.urlopen(base + "/status.json") as response:
                assert json.load(response)["status"] == "current"
            for private_path in (
                "/inputs/project.py",
                "/inputs/adapter-source/build.py",
                "/assets/",
                "/manifest.json",
            ):
                with pytest.raises(urllib.error.HTTPError) as failure:
                    urllib.request.urlopen(base + private_path)
                assert failure.value.code == 404
                request = urllib.request.Request(base + private_path, method="HEAD")
                with pytest.raises(urllib.error.HTTPError) as head_failure:
                    urllib.request.urlopen(request)
                assert head_failure.value.code == 404
            (project / "project.py").write_text("broken")
            with urllib.request.urlopen(base + "/status.json") as response:
                assert json.load(response)["status"] == "stale"
            with pytest.raises(urllib.error.HTTPError) as failure:
                urllib.request.urlopen(base + "/../design.json")
            assert failure.value.code == 404
        finally:
            server.shutdown()
            thread.join()


def test_modified_package_cannot_be_previewed(root, project):
    build.build_project(root, project)
    directory, _ = latest_build(project)
    (directory / "parts.csv").write_text("tampered")
    with pytest.raises(InputError, match="changed or is missing"):
        latest_build(project)


def test_existing_build_lock_is_not_removed(root, project):
    builds = project / "build"
    builds.mkdir()
    lock = builds / ".lock"
    lock.write_text("other builder")
    with pytest.raises(InputError) as failure:
        build.build_project(root, project)
    assert failure.value.code == "build_busy"
    assert lock.read_text() == "other builder"


def test_changed_dependency_lock_is_detected(root, tmp_path):
    (tmp_path / ".local").mkdir()
    state = read_json(root / ".local/runtime.json")
    build.write_json(tmp_path / ".local/runtime.json", state)
    (tmp_path / "uv.lock").write_text("different lock")
    assert runtime_status(tmp_path)["ok"] is False


def test_connection_guide_labels_the_actual_joint(root, tmp_path):
    from buratino.engine import calculate

    result = calculate(load_project(root / "projects/linked-row-fixture")).result
    build.render_documents(tmp_path, result)
    assembly = (tmp_path / "assembly.html").read_text()
    joint = next(
        line for line in assembly.split("<li>") if "Cabinet connection between" in line
    ).split("</li>", 1)[0]
    assert "unit-a.carcass" not in joint and "unit-b.carcass" not in joint
    assert "Cabinet connection between unit-a and unit-b" in joint
    assert "fastening and capacity are unverified" not in joint
    assert "Drawer corner" not in joint


def test_build_captures_resolved_native_helper_drawer_configs(root, linked_row_project):
    source_path = linked_row_project / "project.py"
    source_path.write_text(source_path.read_text().split("drawer_configs = {", 1)[0])
    build.build_project(root, linked_row_project)
    directory, _ = latest_build(linked_row_project)
    snapshot = read_json(directory / "inputs/native-config.json")
    assert snapshot["drawer_configs"] == {}
    built = snapshot["built_drawer_configs"]
    assert set(built) == {
        "unit-a.drawer.column-0.opening-0",
        "unit-b.drawer.column-0.opening-0",
    }
    config = built["unit-a.drawer.column-0.opening-0"]
    assert config["slide_key"] == "buratino_hettich_quadro_v6_eb20"
    assert config["front_gap"] == 2
    assert config["applied_face"] is False
    assert config["buratino_box_bottom_clearance_mm"] == 0
    assert config["buratino_rear_corner_clearance_width_mm"] == 0


def test_preview_reload_uses_latest_build_and_keeps_old_resources(root, project):
    first = build.build_project(root, project)
    with preview_server(project) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(base + "/preview.html") as response:
                first_page = response.read()
            first_prefix = f"/revisions/{first['revision']}/"
            assert f'<base href="{first_prefix}">'.encode() in first_page
            (project / "project.py").write_text(
                (project / "project.py").read_text() + "\n# changed\n"
            )
            second = build.build_project(root, project)
            with urllib.request.urlopen(base + "/preview.html") as response:
                second_page = response.read()
            second_prefix = f"/revisions/{second['revision']}/"
            assert f'<base href="{second_prefix}">'.encode() in second_page
            for resource in ("result.json", "cabinet.glb", "preview.html"):
                with urllib.request.urlopen(base + first_prefix + resource) as response:
                    original = project / "build" / first["revision"] / resource
                    assert response.read() == original.read_bytes()
            with urllib.request.urlopen(
                base + first_prefix + "status.json"
            ) as response:
                assert json.load(response)["status"] == "stale"
            with urllib.request.urlopen(
                base + second_prefix + "status.json"
            ) as response:
                assert json.load(response)["status"] == "current"
        finally:
            server.shutdown()
            thread.join()


def test_confirmed_grain_has_no_display_label(project, tmp_path):
    import csv

    from buratino.engine import calculate

    inputs = load_project(project)
    inputs.variables["grain_direction_confirmed"] = True
    result = calculate(inputs).result
    build.render_documents(tmp_path, result)
    for name in ("report.html", "assembly.html"):
        assert "length (confirmed)" not in (tmp_path / name).read_text()
    with (tmp_path / "parts.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    assert rows and all(row["grain_status"] == "confirmed" for row in rows)
    assert all(
        group["grain_status"] == "confirmed" for group in result["cutting_groups"]
    )


def test_panel_groups_split_when_candidate_positions_differ(root, tmp_path):
    from copy import deepcopy
    from dataclasses import replace

    from cabineteer.joinery import DominoSpec

    from buratino.engine import calculate

    calculation = calculate(load_project(root / "projects/simple-cabinet"))
    result = calculation.result
    cabinet = result["cabinets"][0]
    top = next(part for part in result["parts"] if part["id"].endswith(".carcass.top"))
    other = deepcopy(top)
    other["id"] = other["id"].replace(cabinet["id"], "other", 1)
    result["parts"] = [top, other]
    result["cabinets"] = [cabinet, {**cabinet, "id": "other"}]
    result["joints"] = []
    result["variables"]["part_codes"] = {top["id"]: "T", other["id"]: "T"}
    cfg = calculation.configs[0]
    cfg2 = replace(cfg, domino_spec=DominoSpec(size_key="6x40", max_spacing=100))
    build.render_documents(tmp_path, result, [cfg, cfg2], panel_groups=[[top, other]])
    rows = list(csv.DictReader((tmp_path / "parts.csv").open()))
    assert [row["part_code"] for row in rows] == ["T-01, T-02"]
    assert [row["quantity"] for row in rows] == ["2"]
    report = (tmp_path / "report.html").read_text()
    assert "T-01, T-02" in report
    assembly = (tmp_path / "assembly.html").read_text()
    assert assembly.count("EDGE mortise centers from BACK (mm)") == 2


def test_review_report_shows_errors_without_unknown_check_list(root, tmp_path):
    from buratino.engine import calculate

    result = calculate(load_project(root / "projects/simple-cabinet")).result
    result["checks"] = [
        {"severity": "unknown", "code": "open_input", "message": "Unknown detail"},
        {"severity": "error", "code": "bad_fit", "message": "Panel does not fit"},
    ]
    build.render_documents(tmp_path, result)
    report = (tmp_path / "report.html").read_text()
    assert "Panel does not fit" in report
    assert "Unknown detail" not in report
    assert "Checks and open inputs" not in report


def test_reports_order_materials_and_keep_mixed_codes_in_one_cut_row(root, tmp_path):
    from copy import deepcopy

    from buratino.engine import calculate

    result = calculate(load_project(root / "projects/simple-cabinet")).result
    first = deepcopy(result["parts"][0])
    second = deepcopy(first)
    second["id"] = "upper.same_blank"
    third = deepcopy(first)
    third["id"] = "frame.other"
    first["material"] = second["material"] = "Birch"
    third["material"] = "Ash"
    result["parts"] = [first, second, third]
    result["joints"] = []
    result["variables"]["part_codes"] = {
        first["id"]: "L01",
        second["id"]: "U01",
        third["id"]: "F01",
    }
    build.render_documents(tmp_path, result, panel_groups=[[first], [second], [third]])
    rows = list(csv.DictReader((tmp_path / "parts.csv").open()))
    assert [row["material"] for row in rows] == ["Ash", "Birch"]
    assert rows[1]["part_code"] == "L01, U01"
    assert rows[1]["quantity"] == "2"
    assembly = (tmp_path / "assembly.html").read_text()
    assert assembly.index("<h3>Ash</h3>") < assembly.index("<h3>Birch</h3>")
    assert assembly.index("<h4>L</h4>") < assembly.index("<h4>U</h4>")
    assert "× 1</h5>" not in assembly

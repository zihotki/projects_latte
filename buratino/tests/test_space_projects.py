import builtins
import shutil

import pytest

from buratino.build import (
    _drawer_summary,
    _physical_validation_summary,
    _space_model_summary,
)
from buratino.engine import calculate
from buratino.environment import read_json
from buratino.preview import latest_build
from buratino.project import input_identity, load_project, native_snapshot


@pytest.mark.parametrize(
    ("name", "expected_heights"),
    [
        ("spaces-fixed-drawers", [240, 240, 402]),
        ("spaces-fixed-open", [291, 291, 300]),
        ("spaces-covered-drawers", [240, 360, 300]),
    ],
)
def test_space_projects_use_resolved_native_records(root, name, expected_heights):
    project_path = root / "projects" / name
    inputs = load_project(project_path)
    identity = input_identity(project_path)
    calculation = calculate(inputs)
    result = calculation.result
    model = result["space_model"]

    assert inputs.identity == identity
    assert [space["size"][2] for space in model["spaces"][1:]] == expected_heights
    assert result["parts"]
    assert {part["id"] for part in result["parts"]} == {
        part["id"] for part in model["part_plan"]["parts"]
    }
    assert result["cutting_groups"]
    assert result["cabinets"] and result["frames"] == []
    assert result["drawers"]
    assert all(drawer.get("box_mm") for drawer in result["drawers"])
    assert all(drawer["box_mm"]["depth"] == 480 for drawer in result["drawers"])
    assert all(content["slide_key"].endswith("_480") for content in model["contents"])
    assert all(part.get("stock_mm", {}).get("thickness") for part in result["parts"])
    parts_by_id = {part["id"]: part for part in result["parts"]}
    assert parts_by_id["/root/lower/box-lower/side_L"]["stock_mm"]["thickness"] == 16
    assert parts_by_id["/root/lower/box-lower/sub_front"]["stock_mm"]["thickness"] == 18
    assert parts_by_id["/root/lower/box-lower/bottom"]["stock_mm"]["thickness"] == 12
    assert parts_by_id["/carcass/side_left"]["stock_mm"]["thickness"] == 18
    assert calculation.native_assembly is None
    assert calculation.space_model is not None
    snapshot = native_snapshot(inputs)
    assert "buratino_hettich_quadro_v6_eb20_480" in snapshot["hardware_profiles"]
    if name == "spaces-covered-drawers":
        assert snapshot["selected_hinge_keys"] == ["blum_clip_top_blumotion_110_full"]


def test_space_project_keeps_drawers_fronts_and_door_visibility_separate(root):
    fixed = calculate(load_project(root / "projects/spaces-fixed-drawers")).result
    covered = calculate(load_project(root / "projects/spaces-covered-drawers")).result

    fixed_parts = {part["id"]: part for part in fixed["parts"]}
    lower = fixed_parts["/root/lower/box-lower/side_L"]
    lower_front = fixed_parts["/front/lower-front"]
    assert lower["instance_id"] == "/root/lower/box-lower"
    assert lower_front["instance_id"] == "/root/lower/box-lower"
    assert lower_front["motion_group"] == lower["instance_id"]
    assert "instance_id" not in fixed_parts["/root/adjustable-shelf"]
    assert not any(part["component"] == "door" for part in fixed["parts"])

    covered_parts = {part["id"]: part for part in covered["parts"]}
    assert covered_parts["/front/parent-door"].get("instance_id") is None
    assert covered["hardware"] == [
        {
            "type": "drawer_runner",
            "slide_key": "buratino_hettich_quadro_v6_eb20_480",
            "quantity": 4,
        },
        {
            "type": "concealed_door_hinge",
            "name": "blum_clip_top_blumotion_110_full",
            "quantity": None,
        },
    ]
    assert covered_parts["/root/lower/box-lower/side_L"]["instance_id"] == (
        "/root/lower/box-lower"
    )
    assert covered_parts["/root/middle/box-middle/side_L"]["instance_id"] == (
        "/root/middle/box-middle"
    )


def test_space_calculation_and_reports_do_not_import_cad(root, monkeypatch):
    inputs = load_project(root / "projects/spaces-fixed-drawers")
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "cadquery":
            raise ImportError("CAD is unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    result = calculate(inputs).result

    assert result["parts"]
    assert "Resolved spaces" in _space_model_summary(result)
    assert "198 mm" in _drawer_summary(result)


def test_build_validates_the_materialized_shape_map_once(root, tmp_path, monkeypatch):
    from cabineteer import space_adapter

    from buratino import build

    project = tmp_path / "spaces-fixed-drawers"
    shutil.copytree(
        root / "projects/spaces-fixed-drawers",
        project,
        ignore=shutil.ignore_patterns("build"),
    )
    materialize = space_adapter.materialize_model
    calls = []

    def count_materialization(model):
        calls.append(model)
        return materialize(model)

    monkeypatch.setattr(space_adapter, "materialize_model", count_materialization)
    outcome = build.build_project(root, project)
    directory, _manifest = latest_build(project)
    result = read_json(directory / "result.json")

    assert outcome["physical_validation"]["status"] == "passed"
    assert len(calls) == 1
    assert result["physical_validation"] == {
        "status": "passed",
        "diagnostics": [],
    }
    assert "Status: passed" in (directory / "report.html").read_text()
    assert "No CAD diagnostics." in (directory / "report.html").read_text()


def test_physical_validation_report_keeps_stable_part_ids():
    result = {
        "physical_validation": {
            "status": "failed",
            "diagnostics": [{"code": "missing_contact", "part_ids": ["/a", "/b"]}],
        }
    }

    summary = _physical_validation_summary(result)

    assert "missing_contact" in summary
    assert "/a, /b" in summary

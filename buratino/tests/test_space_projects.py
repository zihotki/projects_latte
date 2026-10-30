import builtins
import shutil

import pytest

from buratino.build import _drawer_summary
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
    assert (
        parts_by_id["/cabinet/root/lower/box-lower/side_L"]["stock_mm"]["thickness"]
        == 16
    )
    assert (
        parts_by_id["/cabinet/root/lower/box-lower/sub_front"]["stock_mm"]["thickness"]
        == 18
    )
    assert (
        parts_by_id["/cabinet/root/lower/box-lower/bottom"]["stock_mm"]["thickness"]
        == 12
    )
    assert parts_by_id["/cabinet/carcass/side_left"]["stock_mm"]["thickness"] == 18
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
    lower = fixed_parts["/cabinet/root/lower/box-lower/side_L"]
    lower_front = fixed_parts["/cabinet/front/lower-front"]
    assert lower["instance_id"] == "/cabinet/root/lower/box-lower"
    assert lower_front["instance_id"] == "/cabinet/root/lower/box-lower"
    assert lower_front["motion_group"] == lower["instance_id"]
    assert "instance_id" not in fixed_parts["/cabinet/root/adjustable-shelf"]
    assert not any(part["component"] == "door" for part in fixed["parts"])

    covered_parts = {part["id"]: part for part in covered["parts"]}
    assert covered_parts["/cabinet/front/parent-door"].get("instance_id") is None
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
    assert covered_parts["/cabinet/root/lower/box-lower/side_L"]["instance_id"] == (
        "/cabinet/root/lower/box-lower"
    )
    assert covered_parts["/cabinet/root/middle/box-middle/side_L"]["instance_id"] == (
        "/cabinet/root/middle/box-middle"
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
    report = (directory / "report.html").read_text()
    assert "Physical validation" not in report
    assert "No CAD diagnostics." not in report


def _space_dimensions(point):
    if isinstance(point, dict):
        return point["x"], point["y"], point["z"]
    return tuple(point)


def test_assembled_space_uses_one_plan_for_reports_cutlists_and_fronts(root):
    inputs = load_project(root / "projects/space-assembly-fronts")
    calculation = calculate(inputs)
    result = calculation.result
    plan = result["space_plan"]
    placements = plan["placements"]

    def placement_named(name):
        return next(
            item for item in placements if item["id"].rstrip("/").endswith(name)
        )

    fronts = {item["id"].rsplit("/", 1)[-1]: item for item in plan["fronts"]}
    physical = {item["id"]: item for item in plan["part_plan"]["parts"]}

    assert result["plan_version"] == plan["plan_version"]
    assert result["dimensions_mm"]["width"] == 953
    assert plan["structural_bounds"]["max_x"] == 953
    assert plan["occupied_bounds"]["max_x"] == 952
    assert max(part["bounds"][1][0] for part in physical.values()) == 952
    assert _space_dimensions(placement_named("left")["size"])[0] == 240
    assert _space_dimensions(placement_named("right")["size"])[0] == 233
    assert _space_dimensions(placement_named("far-right")["size"])[0] == 467
    row_allocation = next(
        item for item in plan["allocations"] if item["path"].endswith("main-row")
    )
    assert row_allocation["used_span"] == 952
    assert row_allocation["slack"] == 1
    assert {part["id"] for part in result["parts"]} == set(physical)
    assert result["cutting_groups"]
    assert {
        front["hinge_side"] for front in fronts.values() if front.get("hinge_side")
    } == {"left", "right"}
    assert any(item["slide_key"].endswith("_380") for item in plan["contents"])
    assert any(
        item.get("slide_key", "").endswith("_380") for item in result["hardware"]
    )
    assert all(
        item["stock"]["thickness_axis"] in (0, 1, 2) for item in physical.values()
    )
    assert any(item.get("motion_group") for item in result["parts"])
    assert all(
        definition.carcass.door_gap
        == definition.carcass.drawer_front_gap
        == definition.carcass.outer_reveal
        == 2
        for definition in inputs.native_project.space_cabinets
    )

    snapshot = native_snapshot(inputs)
    assert snapshot["resolved_space_assembly"]["plan_version"] == plan["plan_version"]
    assert snapshot["selected_hinge_keys"]
    assert "buratino_hettich_quadro_v6_eb20_380" in snapshot["hardware_profiles"]


def test_nested_bare_and_complete_references_keep_qualified_part_ids(root):
    inputs = load_project(root / "projects/space-nested-inserts")
    calculation = calculate(inputs)
    plan = calculation.result["space_plan"]
    part_ids = {item["id"] for item in plan["part_plan"]["parts"]}
    content_ids = {item["id"] for item in plan["contents"]}
    instance_paths = {
        item.get("instance_id")
        for item in calculation.result["parts"]
        if item.get("instance_id")
    }
    viewer = calculation.result["assembly"]["viewer"]
    instances = viewer["instances"]
    host = next(item for item in instances if not item.get("parent_id"))
    nested = next(
        item for item in instances if "complete-cabinet-instance" in item["id"]
    )
    nested_parts = [
        item for item in viewer["parts"] if "complete-cabinet-instance" in item["id"]
    ]

    assert any("bare-insert-instance" in ident for ident in part_ids)
    assert any("complete-cabinet-instance" in ident for ident in part_ids)
    assert any("insert-box" in ident for ident in content_ids)
    assert any(
        "box" in ident and "complete-cabinet-instance" in ident for ident in content_ids
    )
    assert all(path.startswith("/") for path in instance_paths)
    assert all(
        item["stock"]["thickness_axis"] in (0, 1, 2)
        for item in plan["part_plan"]["parts"]
    )
    assert any(item.get("slide_key", "").endswith("_480") for item in plan["contents"])
    assert any(item["hinge_side"] == "right" for item in plan["fronts"])
    assert host["id"] in nested["ancestor_ids"]
    assert nested_parts and host["id"] in nested_parts[0]["ancestor_ids"]
    assert nested["parent_id"] in {item["id"] for item in instances}
    snapshot = native_snapshot(inputs)
    assert snapshot["resolved_space_plan"]["plan_version"] == plan["plan_version"]

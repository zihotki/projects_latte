import shutil
from dataclasses import replace

import pytest

from buratino import build
from buratino.engine import calculate, make_geometry
from buratino.environment import read_json
from buratino.preview import latest_build
from buratino.project import InputError, load_project

RUNNER_KEYS = {
    450: "buratino_hettich_quadro_v6_eb20",
    480: "buratino_hettich_quadro_v6_eb20_480",
}


def _mixed_project(root, tmp_path):
    path = tmp_path / "mixed-real-assembly"
    shutil.copytree(root / "projects/real-assembly", path)
    source_path = path / "project.py"
    source = source_path.read_text(encoding="utf-8")
    source = source.replace(
        '# "left-drawers": 450,',
        '"left-drawers": 450,',
        1,
    )
    source_path.write_text(source, encoding="utf-8")
    return path


def test_cabinet_runner_override_applies_to_all_drawers_and_keeps_frames(
    root, tmp_path
):
    inputs = load_project(_mixed_project(root, tmp_path))
    calculation = calculate(inputs)
    result = calculation.result

    for index in range(4):
        assert (
            inputs.drawer_configs[f"left-drawers/column-0/opening-{index}"].slide_key
            == RUNNER_KEYS[450]
        )
        assert (
            inputs.drawer_configs[f"right-drawers/column-0/opening-{index}"].slide_key
            == RUNNER_KEYS[480]
        )
    assert [drawer["box_mm"]["depth"] for drawer in result["drawers"]] == [
        450,
        450,
        450,
        450,
        480,
        480,
        480,
        480,
    ]
    cabinets = {cabinet["id"]: cabinet for cabinet in result["cabinets"]}
    assert cabinets["left-drawers"]["hardware_profile"]["runner_length_mm"] == 450
    assert cabinets["right-drawers"]["hardware_profile"]["runner_length_mm"] == 480

    frame_ids = {part["id"] for part in result["parts"] if "frame_id" in part}
    expected_frame_ids = {
        f"frame.{frame}.{rail}"
        for frame in ("bottom", "top")
        for rail in ("front", "back", "left", "right")
    }
    assert len(result["frames"]) == 2
    assert frame_ids == expected_frame_ids
    assembly, geometry = make_geometry(calculation)
    assert len(geometry) == len(result["parts"])
    frame_roles = {part["role"] for part in result["parts"] if "frame_id" in part}
    assert frame_roles <= set(assembly.objects)


def test_two_cabinet_profiles_keep_bom_warnings_geometry_and_snapshot(root, tmp_path):
    project_path = _mixed_project(root, tmp_path)
    inputs = load_project(project_path)
    calculation = calculate(inputs)
    result = calculation.result

    drawers_by_cabinet = {
        cabinet_id: [
            drawer for drawer in result["drawers"] if drawer["cabinet_id"] == cabinet_id
        ]
        for cabinet_id in ("left-drawers", "right-drawers")
    }
    assert [
        drawer["box_mm"]["depth"] for drawer in drawers_by_cabinet["left-drawers"]
    ] == [
        450,
        450,
        450,
        450,
    ]
    assert [
        drawer["box_mm"]["depth"] for drawer in drawers_by_cabinet["right-drawers"]
    ] == [
        480,
        480,
        480,
        480,
    ]
    assert {
        drawer["hardware_profile"]["runner_length_mm"]
        for drawer in drawers_by_cabinet["left-drawers"]
    } == {450}
    assert {
        drawer["hardware_profile"]["runner_length_mm"]
        for drawer in drawers_by_cabinet["right-drawers"]
    } == {480}
    assert result["hardware_profile"] is None
    assert set(result["hardware_profiles"]) == set(RUNNER_KEYS.values())
    assert result["hardware_profiles"][RUNNER_KEYS[450]]["minimum_body_depth_mm"] == 463
    assert result["hardware_profiles"][RUNNER_KEYS[480]]["minimum_body_depth_mm"] == 493

    runners = {
        item["length_mm"]: item
        for item in result["hardware"]
        if item["type"] == "drawer_runner"
    }
    assert runners[450]["quantity"] == runners[480]["quantity"] == 8
    assert runners[450]["part_numbers"] == ["9047751", "9047752"]
    assert runners[480]["part_numbers"] == ["9047756", "9047757"]
    assert runners[450]["quantity_by_part_number"] == {
        "9047751": 4,
        "9047752": 4,
    }
    assert runners[480]["quantity_by_part_number"] == {
        "9047756": 4,
        "9047757": 4,
    }
    catches = next(
        item
        for item in result["hardware"]
        if item["type"] == "compatible_grooved_bottom_catch_pair"
    )
    assert catches["quantity"] == 8
    assert catches["quantity_by_part_number"] == {
        "9144830": 8,
        "9144841": 8,
    }

    assert result["manufacturing_ready"] is False
    issue_codes = {issue["code"] for issue in result["checks"]}
    assert {
        "drawer.hardware_limits_unverified",
        "drawer.load_capacity_unverified",
        "drawer.runner_mounting_unverified",
    } <= issue_codes
    assert not any(
        issue["code"] == "drawer.runner_depth_does_not_fit"
        for issue in result["checks"]
    )

    assembly, geometry = make_geometry(calculation)
    assert len(geometry) == len(result["parts"])
    assert {part["role"] for part in result["parts"]} <= set(assembly.objects)
    for drawer in result["drawers"]:
        expected_length = 450 if drawer["cabinet_id"] == "left-drawers" else 480
        part = next(
            part
            for part in result["parts"]
            if part["id"] == f"{drawer['instance_id']}.side_left"
        )
        assert part["finished_mm"]["length"] == expected_length
        assert drawer["box_mm"]["depth"] == expected_length

    build.build_project(root, project_path)
    directory, _manifest = latest_build(project_path)
    snapshot = read_json(directory / "inputs/native-config.json")
    assert set(snapshot["hardware_profiles"]) == set(RUNNER_KEYS.values())
    assert (
        snapshot["hardware_profiles"][RUNNER_KEYS[450]]["source_data"][
            "runner_length_mm"
        ]
        == 450
    )
    assert (
        snapshot["hardware_profiles"][RUNNER_KEYS[480]]["source_data"][
            "runner_length_mm"
        ]
        == 480
    )
    cabinet_profiles = snapshot["cabinet_hardware_profiles"]
    assert cabinet_profiles["left-drawers"]["slide_key"] == RUNNER_KEYS[450]
    assert cabinet_profiles["left-drawers"]["source_data"]["runner_length_mm"] == 450
    assert cabinet_profiles["right-drawers"]["slide_key"] == RUNNER_KEYS[480]
    assert cabinet_profiles["right-drawers"]["source_data"]["runner_length_mm"] == 480
    built = snapshot["built_drawer_configs"]
    for index in range(4):
        assert (
            built[f"left-drawers.drawer.column-0.opening-{index}"]["slide_key"]
            == RUNNER_KEYS[450]
        )
        assert (
            built[f"right-drawers.drawer.column-0.opening-{index}"]["slide_key"]
            == RUNNER_KEYS[480]
        )


def test_conflicting_runner_profiles_within_one_cabinet_are_rejected(root, tmp_path):
    inputs = load_project(_mixed_project(root, tmp_path))
    cabinets = list(inputs.native_project.cabinets)
    left = cabinets[0]
    openings = list(left.config.openings)
    openings[0] = replace(openings[0], slide_key=RUNNER_KEYS[480])
    cabinets[0] = replace(left, config=replace(left.config, openings=openings))
    for key, config in inputs.drawer_configs.items():
        if key.startswith("left-drawers/") and key.endswith("opening-0"):
            config.slide_key = RUNNER_KEYS[480]
    inputs = replace(
        inputs,
        native_project=replace(inputs.native_project, cabinets=tuple(cabinets)),
    )

    with pytest.raises(InputError) as error:
        calculate(inputs)

    assert error.value.code == "cabinet_runner_profile_mismatch"


def test_cabinet_runner_selection_rejects_unsupported_profile(root, tmp_path):
    inputs = load_project(_mixed_project(root, tmp_path))
    inputs.drawer_configs["left-drawers/column-0/opening-0"].slide_key = "unknown_slide"

    with pytest.raises(InputError) as error:
        calculate(inputs)

    assert error.value.code == "unsupported_drawer_profile"


def test_480_cabinet_runner_checks_its_own_minimum_cavity_depth(root, tmp_path):
    inputs = load_project(_mixed_project(root, tmp_path))
    cabinets = tuple(
        replace(cabinet, config=replace(cabinet.config, depth=498))
        for cabinet in inputs.native_project.cabinets
    )
    native_project = replace(inputs.native_project, cabinets=cabinets)
    cavity_depth = dict(native_project.resolved())["left-drawers"].interior_depth
    for config in inputs.drawer_configs.values():
        config.opening_depth = cavity_depth
    inputs = replace(inputs, native_project=native_project)

    with pytest.raises(InputError) as error:
        calculate(inputs)

    assert error.value.code == "invalid_drawer_config"
    assert "at least 493 mm" in str(error.value)

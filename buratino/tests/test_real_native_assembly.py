"""Buratino reports the native assembly as one resolved result."""

import math
from dataclasses import replace

import pytest
from cabineteer.cabinet import OpeningConfig

from buratino.engine import calculate
from buratino.project import load_project, native_snapshot


def test_real_native_report_has_cabinet_and_drawer_summaries(root):
    project = load_project(root / "projects/real-assembly-native")
    result = calculate(project).result
    assert result["overall_dimensions_mm"]["width"] == 1440
    assert result["overall_dimensions_mm"]["depth"] == 526
    roof_slope = 969 / 1071
    expected_top = 1030 + 1204 + 8 * roof_slope - 2 * math.hypot(1, roof_slope)
    assert result["overall_dimensions_mm"]["height"] == pytest.approx(expected_top)
    assert [item["placement_mm"] for item in result["cabinets"]] == [
        {"x": 0, "y": 0, "z": 50},
        {"x": 720, "y": 0, "z": 50},
    ]
    assert [(item["id"], item["z"]) for item in result["frames"]] == [
        ("frame.bottom", 0),
        ("frame.support", 980),
    ]
    assert len(result["upper_cabinets"]) == 1
    assert result["upper_cabinets"][0]["id"] == "upper"
    assert len(result["parts"]) == 91
    assert len(result["drawers"]) == len(result["hardware"]) == 9
    assert {item["slide_key"] for item in result["drawers"]} == {
        "buratino_hettich_quadro_v6_eb20_480",
        "buratino_hettich_quadro_v6_eb20_380",
    }
    assert all(item["part_ids"] for item in result["drawers"])
    assert result["manufacturing_ready"] is False
    snapshot = native_snapshot(project)
    assert snapshot["project"]["input_schema_version"] == 2
    assert snapshot["project"]["layout"]["type"] == "Stack"
    assert snapshot["project"]["layout"]["size_x"] == {
        "type": "Fixed",
        "mm": 1440,
    }
    assert snapshot["project"]["layout"]["size_z"] == {
        "type": "Fixed",
        "mm": 2234,
    }
    assert snapshot["project"]["layout"]["children"][1]["size_x"] == {
        "type": "Fixed",
        "mm": 1440,
    }
    selected_keys = {
        key for key in snapshot["hardware_profiles"] if key.startswith("buratino_")
    }
    assert selected_keys == {
        "buratino_hettich_quadro_v6_eb20_480",
        "buratino_hettich_quadro_v6_eb20_380",
    }
    assert snapshot["project"]["profile_assembly"]["lower_drawers"]
    assert snapshot["project"]["profile_assembly"]["continuous_bottom"] is True


def test_mixed_opening_runner_selection_is_reported_without_false_single_key(root):
    inputs = load_project(root / "projects/real-assembly-native")
    native = inputs.native_project
    left = native.cabinets[0]
    opening_height = left.config.interior_height / 4
    openings = [
        OpeningConfig(
            opening_height,
            "drawer",
            slide_key="buratino_hettich_quadro_v6_eb20_380"
            if index == 0
            else "buratino_hettich_quadro_v6_eb20_480",
        )
        for index in range(4)
    ]
    changed = replace(
        inputs,
        native_project=replace(
            native,
            cabinets=(
                replace(left, config=replace(left.config, openings=openings)),
                native.cabinets[1],
            ),
        ),
    )
    result = calculate(changed).result
    left_summary = result["cabinets"][0]
    assert left_summary["slide_key"] is None
    assert left_summary["hardware_profile"] is None
    assert left_summary["slide_keys"] == [
        "buratino_hettich_quadro_v6_eb20_380",
        "buratino_hettich_quadro_v6_eb20_480",
    ]
    assert [
        item["slide_key"]
        for item in result["hardware"]
        if item["instance_id"].startswith("left-drawers.")
    ] == [
        "buratino_hettich_quadro_v6_eb20_380",
        *["buratino_hettich_quadro_v6_eb20_480"] * 3,
    ]
    snapshot = native_snapshot(changed)
    cabinet_profile = snapshot["cabinet_hardware_profiles"]["left-drawers"]
    assert cabinet_profile["slide_key"] is None
    assert cabinet_profile["slide_keys"] == left_summary["slide_keys"]
    assert set(cabinet_profile["source_data_by_key"]) == set(left_summary["slide_keys"])
    all_380 = replace(
        changed,
        native_project=replace(
            changed.native_project,
            cabinets=(
                replace(
                    changed.native_project.cabinets[0],
                    config=replace(
                        left.config,
                        openings=[
                            replace(
                                item, slide_key="buratino_hettich_quadro_v6_eb20_380"
                            )
                            for item in openings
                        ],
                    ),
                ),
                changed.native_project.cabinets[1],
            ),
        ),
    )
    assert calculate(all_380).result["cabinets"][0]["slide_key"] == (
        "buratino_hettich_quadro_v6_eb20_380"
    )
    assert native_snapshot(all_380)["cabinet_hardware_profiles"]["left-drawers"][
        "slide_key"
    ] == ("buratino_hettich_quadro_v6_eb20_380")


def test_native_drawer_report_keeps_stock_and_describes_cuts(root, tmp_path):
    from buratino.build import render_documents

    result = calculate(load_project(root / "projects/real-assembly-native")).result
    drawer_parts = [part for part in result["parts"] if ".drawer." in part["id"]]
    assert len(drawer_parts) == 45
    for part in drawer_parts:
        assert part["blank_mm"] == part["stock_mm"]
        if part["component"] == "bottom":
            assert part["operations"] == []
            continue
        groove = next(op for op in part["operations"] if op["role"] == "bottom_groove")
        assert groove["depth_mm"] == 6
        assert groove["kind"] == "pocket"
        assert groove["target"] in {"thickness+", "thickness-"}
        points = groove["local_profile_mm"]
        assert min(p[1] for p in points) == 13
        assert max(p[1] for p in points) == 25
        assert max(p[0] for p in points) == part["stock_mm"]["length"]
        assert all(0 <= p[2] <= part["stock_mm"]["thickness"] for p in points)
    render_documents(tmp_path, result)
    document = (tmp_path / "assembly.html").read_text()
    assert "bottom_groove" in document
    assert "face polygon in stock L/W/T (mm):" in document
    assert "depth 6 mm; inward" in document
    assert "profile_trim" in document or "edge_bevel" in document

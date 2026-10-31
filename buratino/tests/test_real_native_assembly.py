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
    assert len(result["joints"]) == 136
    assert all(len(joint["mortises"]) == 2 for joint in result["joints"])
    assert any(
        check["code"] == "joinery.sloped_cap_unverified" for check in result["checks"]
    )
    assert len(result["drawers"]) == len(result["hardware"]) == 9
    assert {item["slide_key"] for item in result["drawers"]} == {
        "buratino_hettich_quadro_v6_eb20_480",
        "buratino_hettich_quadro_v6_eb20_380",
    }
    assert all(item["part_ids"] for item in result["drawers"])
    eligible = [
        p
        for p in result["parts"]
        if p["component"] not in {"door", "drawer_front", "applied_faceboard"}
    ]
    assert all(p.get("report") for p in eligible)
    assert all(
        p["report"]["axes"] == ((1, 0, 0), (0, 1, 0), (0, 0, 1)) for p in eligible
    )
    caps = [p for p in eligible if p["component"] == "cap"]
    assert {p["owner"] for p in caps} == {"upper.roof"}
    assert {p["report"]["item_id"] for p in caps} == {"upper"}
    assert {p["report"]["recipe"] for p in caps} == {"profiled"}
    rails = [p for p in eligible if p["owner"].startswith("frame.")]
    assert {p["report"]["member"] for p in rails} == {
        "rail_left",
        "rail_right",
        "rail_front",
        "rail_back",
    }
    assert all(p["report"]["recipe"] == "frame" for p in rails)
    drawer = next(p for p in eligible if p["id"] == "upper.section-1.drawer.side_left")
    assert drawer["report"]["item_id"] == "upper.section-1.drawer"
    assert drawer["report"]["recipe"] == "drawer"
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
    document = (tmp_path / "report.html").read_text()
    assert "Bottom groove: 12 mm wide × 6 mm deep; bottom inset 13 mm" in document
    assert "face T+ (stock L/W/T)" in document
    assert "Profile cut: follow the dimensioned outline shown." in document
    assert "Bevel:" in document
    assert "20 × 6 mm; depth 12 mm" in document
    assert "20 × 6 mm; depth 28 mm" in document
    assert "Hardware requirements" not in document
    assert 'id="assembly"' in document
    assert "Profile operations" not in document
    assert "calculation JSON" not in document
    assert not (tmp_path / "assembly.html").exists()


def test_native_mortise_notes_use_the_stock_plane_axes():
    from buratino.machining_notes import machining_notes

    notes = machining_notes(
        {
            "operations": [
                {
                    "type": "mortise",
                    "coordinate_frame": "stock_lwt",
                    "face": "x-",
                    "axis": "u",
                    "u": 50,
                    "v": 9,
                    "length": 20,
                    "width": 6,
                    "depth": 28,
                }
            ]
        }
    )
    assert notes == [
        "Mortise: 20 × 6 mm; depth 28 mm; center W 50, T 9 mm; "
        "length along W; face L- (stock L/W/T)."
    ]


def test_exploded_view_receives_native_group_metadata_without_mutating_result(
    root, tmp_path, monkeypatch
):
    from copy import deepcopy

    from buratino import exploded_views
    from buratino.build import render_documents

    result = calculate(load_project(root / "projects/real-assembly-native")).result
    original = deepcopy(result["parts"])
    captured = {}

    def capture(assembly, parts, part_codes):
        captured.update(assembly=assembly, parts=parts, part_codes=part_codes)
        return "<figure>test exploded view</figure>"

    monkeypatch.setattr(exploded_views, "exploded_views", capture)
    geometry = object()
    render_documents(tmp_path, result, assembly_geometry=geometry)

    assert captured["assembly"] is geometry
    assert any(part.get("cabinet_id") for part in captured["parts"])
    assert any(part.get("instance_id") for part in captured["parts"])
    assert [part["role"] for part in captured["parts"]] == [
        part["role"] for part in original
    ]
    assert [part.get("geometry") for part in captured["parts"]] == [
        part.get("geometry") for part in original
    ]
    assert result["parts"] == original
    assert "test exploded view" in (tmp_path / "report.html").read_text()

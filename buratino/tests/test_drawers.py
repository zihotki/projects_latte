import pytest

from buratino.drawers import (
    EB20_SLIDE_380,
    EB20_SLIDE_KEYS,
    HETTICH_PROFILES,
    drawer_shapes,
    eb20_profile_for_key,
    make_eb20_drawer_config,
)
from buratino.engine import calculate, make_geometry
from buratino.project import load_project


def test_native_drawer_reference_dimensions_and_metadata(root):
    calculation = calculate(load_project(root / "projects/drawer-cabinet"))
    result = calculation.result
    by_id = {part["id"]: part for part in result["parts"]}
    assert result["dimensions_mm"] == {"width": 720, "height": 970, "depth": 500}
    assert result["overall_dimensions_mm"] == {
        "width": 720,
        "height": 970,
        "depth": 520,
    }
    assert len(result["parts"]) == 29
    assert len(result["cutting_groups"]) == 8
    assert sum(group["quantity"] for group in result["cutting_groups"]) == 29
    assert by_id["cabinet.drawer.column-0.opening-0.side_left"]["finished_mm"] == {
        "length": 450,
        "width": 180,
        "thickness": 16,
    }
    assert by_id["cabinet.drawer.column-0.opening-0.inner_front"]["finished_mm"] == {
        "length": 644,
        "width": 180,
        "thickness": 18,
    }
    assert by_id["cabinet.drawer.column-0.opening-0.bottom"]["finished_mm"] == {
        "length": 656,
        "width": 426,
        "thickness": 12,
    }
    assert by_id["cabinet.drawer.column-0.opening-0.face"]["finished_mm"] == {
        "length": 716,
        "width": 240,
        "thickness": 18,
    }
    assert [drawer["face_position_mm"]["z"] for drawer in result["drawers"]] == [
        2,
        244,
        486,
        728,
    ]
    assert [drawer["closed_position_mm"]["z"] for drawer in result["drawers"]] == [
        48,
        281.5,
        515,
        748.5,
    ]
    assert all(
        drawer["box_mm"] == {"width": 676, "height": 180, "depth": 450}
        for drawer in result["drawers"]
    )
    assert len({part["id"] for part in result["parts"]}) == 29
    assert all("." not in part["role"] for part in result["parts"])
    assert all(part["cabinet_id"] == "cabinet" for part in result["parts"])
    assert result["hardware"][1]["quantity"] == 8
    assert result["hardware"][2]["quantity"] == 4
    catch_pair = result["hardware"][2]
    assert catch_pair["part_numbers"] == ["9144830", "9144841"]
    assert catch_pair["quantity_by_part_number"] == {
        "9144830": 4,
        "9144841": 4,
    }
    assert result["manufacturing_ready"] is False
    back = by_id["cabinet.drawer.column-0.opening-0.back"]
    assert back["rear_clearance_mm"] == {"width": 30, "height": 13}
    relief = back["machining_assumptions"][0]
    assert relief["dimensions_mm"] == {"width": 30, "height": 13, "depth": 18}
    assert relief["status"] == "unverified_draft_interpretation"
    relief_check = next(
        issue
        for issue in result["checks"]
        if issue["code"] == "drawer.rear_corner_clearance_assumption"
    )
    assert "30 mm wide by 13 mm high" in relief_check["message"]
    issue_codes = {issue["code"] for issue in result["checks"]}
    assert "cabineteer.domino_panel_thickness" in issue_codes
    assert {
        "drawer.hardware_limits_unverified",
        "drawer.load_capacity_unverified",
    } <= issue_codes
    assert "drawer.catch_identity_unresolved" not in issue_codes
    assert "drawer.runner_mounting_unverified" in issue_codes

    assembly, geometry = make_geometry(calculation)
    bounds = assembly.toCompound().BoundingBox()
    assert len(geometry) == 29
    assert [bounds.xlen, bounds.ylen, bounds.zlen] == pytest.approx([720, 520, 970])
    faces = [
        assembly.objects[part["role"]].toCompound().BoundingBox()
        for part in result["parts"]
        if part["component"] == "face"
    ]
    assert [face.zmin for face in faces] == pytest.approx([2, 244, 486, 728])
    assert [face.zmax for face in faces] == pytest.approx([242, 484, 726, 968])
    first_side = (
        assembly.objects[by_id["cabinet.drawer.column-0.opening-0.side_left"]["role"]]
        .toCompound()
        .BoundingBox()
    )
    assert [first_side.xmin, first_side.ymin, first_side.zmin] == pytest.approx(
        [22, 0, 48]
    )

    from cabineteer.drawer import make_drawer_front_back

    cfg = calculation.drawer_instances[0]["config"]
    native_back = make_drawer_front_back(cfg, "back")
    adapted_back = drawer_shapes(
        cfg,
        rear_corner_clearance_width_mm=cfg.buratino_rear_corner_clearance_width_mm,
    )[0]["back"]
    assert native_back.val().Volume() - adapted_back.val().Volume() == pytest.approx(
        2 * 30 * 18 * 13
    )


def test_eb20_profile_rejects_unverified_side_and_length_choices():
    args = dict(
        opening_width=684,
        opening_height=233.5,
        opening_depth=494,
        side_thickness=16,
        front_back_thickness=18,
        bottom_thickness=12,
        box_height=180,
        vertical_gap=30,
    )
    with pytest.raises(ValueError, match="16 mm or thinner"):
        make_eb20_drawer_config(**{**args, "side_thickness": 16.1})
    with pytest.raises(ValueError, match="only 380, 450, 480 mm"):
        make_eb20_drawer_config(**{**args, "runner_length_mm": 500})
    with pytest.raises(ValueError, match="usable cavity depth"):
        make_eb20_drawer_config(**{**args, "opening_depth": 462})
    with pytest.raises(ValueError, match="fit the opening"):
        make_eb20_drawer_config(**{**args, "box_height": 220})


def test_draft_groove_and_relief_limits():
    args = dict(
        opening_width=684,
        opening_height=233.5,
        opening_depth=494,
        side_thickness=16,
        front_back_thickness=18,
        bottom_thickness=12,
        box_height=180,
        vertical_gap=30,
        bottom_dado_inset=13,
        bottom_dado_depth=6,
    )
    for relief in (0, 30):
        cfg = make_eb20_drawer_config(**args, rear_corner_clearance_width_mm=relief)
        assert cfg.buratino_rear_corner_clearance_width_mm == relief
    with pytest.raises(ValueError, match="groove depth"):
        make_eb20_drawer_config(**{**args, "bottom_dado_depth": 16})
    with pytest.raises(ValueError, match="relief"):
        make_eb20_drawer_config(**args, rear_corner_clearance_width_mm=400)
    with pytest.raises(ValueError, match="positive center"):
        make_eb20_drawer_config(
            **{**args, "opening_width": 90}, rear_corner_clearance_width_mm=30
        )


def test_480_runner_uses_manufacturer_depth_limit():
    args = dict(
        opening_width=684,
        opening_height=233.5,
        opening_depth=493,
        side_thickness=16,
        front_back_thickness=18,
        bottom_thickness=12,
        box_height=180,
        vertical_gap=30,
        runner_length_mm=480,
    )
    config = make_eb20_drawer_config(**args)
    assert config.box_depth == 480
    with pytest.raises(ValueError, match="at least 493 mm"):
        make_eb20_drawer_config(**{**args, "opening_depth": 492})


def test_380_runner_profile_and_minimum_body_depth():
    from cabineteer.hardware import SLIDES

    profile = HETTICH_PROFILES[380]
    assert profile["runner_length_mm"] == 380
    assert profile["box_length_mm"] == 380
    assert profile["minimum_body_depth_mm"] == 393
    assert profile["side_thickness_max_mm"] == 16
    assert profile["left_runner_sku"] == "9047682"
    assert profile["right_runner_sku"] == "9047683"
    assert EB20_SLIDE_KEYS[380] != EB20_SLIDE_KEYS[450]
    assert eb20_profile_for_key(EB20_SLIDE_KEYS[380]) is profile
    assert SLIDES[EB20_SLIDE_KEYS[380]] is EB20_SLIDE_380

    args = dict(
        opening_width=684,
        opening_height=233.5,
        opening_depth=393,
        side_thickness=16,
        front_back_thickness=18,
        bottom_thickness=12,
        box_height=180,
        vertical_gap=30,
        runner_length_mm=380,
    )
    config = make_eb20_drawer_config(**args)
    assert config.box_depth == 380
    assert config.slide_key == EB20_SLIDE_KEYS[380]
    with pytest.raises(ValueError, match="at least 393 mm"):
        make_eb20_drawer_config(**{**args, "opening_depth": 392})

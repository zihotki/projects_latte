import math

import pytest

from buratino.engine import calculate, make_geometry
from buratino.project import load_project
from buratino.upper import make_upper_parts


def _upper_parts(result):
    return [part for part in result["parts"] if part["id"].startswith("upper.")]


def _bounds(shape):
    box = shape.BoundingBox()
    return {
        "min": {"x": box.xmin, "y": box.ymin, "z": box.zmin},
        "max": {"x": box.xmax, "y": box.ymax, "z": box.zmax},
    }


@pytest.mark.parametrize("change", [{"thickness_mm": 0}, {"cabinet_width_mm": 72}])
def test_upper_rejects_stock_without_usable_section_width(root, change):
    spec = dict(load_project(root / "projects/real-assembly").variables["upper"])
    spec.update(change)
    with pytest.raises(ValueError, match="usable width and depth"):
        make_upper_parts(spec)


def test_upper_assembly_extends_the_unchanged_drawer_row_and_frame(root):
    result = calculate(load_project(root / "projects/real-assembly")).result

    assert result["overall_dimensions_mm"] == {
        "width": 1440,
        "height": pytest.approx(2238.097, abs=0.001),
        "depth": 526,
    }
    assert [cabinet["id"] for cabinet in result["cabinets"]] == [
        "left-drawers",
        "right-drawers",
    ]
    assert [cabinet["dimensions_mm"] for cabinet in result["cabinets"]] == [
        {"width": 720, "height": 930, "depth": 506},
        {"width": 720, "height": 930, "depth": 506},
    ]

    assert [cabinet["id"] for cabinet in result["upper_cabinets"]] == [
        "upper-left",
        "upper-right",
    ]
    for cabinet in result["upper_cabinets"]:
        assert cabinet["placement_mm"]["y"] == 80
        assert cabinet["placement_mm"]["z"] == 1030
        assert cabinet["bounds_mm"]["min"]["y"] == 80
        assert cabinet["bounds_mm"]["max"]["y"] == 506

    frames = {frame["id"]: frame for frame in result["frames"]}
    assert {
        key: (
            frame["width"],
            frame["depth"],
            frame["height"],
            frame["thickness"],
            frame["x"],
            frame["y"],
            frame["z"],
        )
        for key, frame in frames.items()
    } == {
        "bottom": (1440, 506, 50, 18, 0, 0, 0),
        "top": (1440, 380, 50, 18, 0, 126, 980),
    }


def test_height_fit_includes_upper_fronts(root):
    project = load_project(root / "projects/real-assembly")
    project.variables["space_mm"] = {"height": 2236}
    calculation = calculate(project)
    assembly, _ = make_geometry(calculation)
    fronts = [
        part
        for part in _upper_parts(calculation.result)
        if part["component"] in {"face", "door"}
    ]
    physical_top = max(
        assembly.objects[part["role"]].toCompound().BoundingBox().zmax
        for part in fronts
    )
    assert calculation.result["overall_dimensions_mm"]["height"] == pytest.approx(
        physical_top
    )
    assert "survey.height_exceeded" in {
        issue["code"] for issue in calculation.result["checks"]
    }


def test_upper_panels_are_native_solids_and_slope_uses_a_local_stock_blank(root):
    calculation = calculate(load_project(root / "projects/real-assembly"))
    result = calculation.result
    assembly, geometry = make_geometry(calculation)
    parts = _upper_parts(result)
    by_id = {part["id"]: part for part in parts}

    assert len(geometry) == len(result["parts"])
    assert set(by_id) == {
        "upper.left.left_side",
        "upper.left.divider",
        "upper.left.right_side",
        "upper.left.back",
        "upper.left.bottom_1",
        "upper.left.bottom_2",
        "upper.left.section_2_shelf_1",
        "upper.left.column-0.opening-0.side_left",
        "upper.left.column-0.opening-0.side_right",
        "upper.left.column-0.opening-0.inner_front",
        "upper.left.column-0.opening-0.back",
        "upper.left.column-0.opening-0.bottom",
        "upper.left.column-0.opening-0.face",
        "upper.left.section-2.door",
        "upper.right.left_side",
        "upper.right.divider",
        "upper.right.right_side",
        "upper.right.back",
        "upper.right.bottom_1",
        "upper.right.bottom_2",
        "upper.right.section_1_shelf_1",
        "upper.right.section_1_shelf_2",
        "upper.right.section_1_shelf_3",
        "upper.right.section_2_shelf_1",
        "upper.right.section_2_shelf_2",
        "upper.right.section_2_shelf_3",
        "upper.right.section-1.door",
        "upper.right.section-2.door",
        "upper.shared.top_sloped",
        "upper.shared.top_level",
    }

    assert by_id["upper.shared.top_sloped"]["quantity"] == 1
    assert by_id["upper.shared.top_level"]["quantity"] == 1
    assert sum(part["id"] == "upper.shared.top_sloped" for part in parts) == 1

    for part in parts:
        solid = assembly.objects[part["role"]].toCompound()
        assert solid.isValid()
        assert solid.Volume() > 0
        actual = _bounds(solid)
        if "position_mm" in part and "size_mm" in part:
            position = part["position_mm"]
            size = part["size_mm"]
            for axis in ("x", "y", "z"):
                assert actual["min"][axis] == pytest.approx(position[axis])
                assert actual["max"][axis] == pytest.approx(position[axis] + size[axis])

    roof = by_id["upper.shared.top_sloped"]
    roof_box = _bounds(assembly.objects[roof["role"]].toCompound())
    joint_x = 1071
    slope = (2234 - 1265) / joint_x
    assert roof_box["min"]["x"] == pytest.approx(0)
    assert roof_box["max"]["x"] == pytest.approx(joint_x)
    slope_drop = 18 * math.sqrt(1 + slope * slope)
    assert roof_box["min"]["z"] == pytest.approx(1265 - slope_drop)
    assert roof_box["max"]["z"] == pytest.approx(2234)
    points = roof["profile"]["points_mm"]
    position = roof["position_mm"]
    assert position["x"] + points[2][0] == pytest.approx(joint_x)
    assert position["z"] + points[2][1] == pytest.approx(2234)
    assert position["x"] + points[3][0] == pytest.approx(0)
    assert position["z"] + points[3][1] == pytest.approx(1265)

    level = by_id["upper.shared.top_level"]
    level_box = _bounds(assembly.objects[level["role"]].toCompound())
    assert level_box["min"]["x"] == pytest.approx(joint_x)
    assert level_box["max"]["x"] == pytest.approx(1440)
    assert level_box["min"]["z"] == pytest.approx(2234 - 18)
    assert level_box["max"]["z"] == pytest.approx(2234)

    blank = roof["blank_mm"]
    expected_sloped_length = math.hypot(joint_x, 2234 - 1265) + 18 * slope
    assert blank["length"] == pytest.approx(expected_sloped_length)
    assert blank["width"] == pytest.approx(420)
    assert blank["thickness"] == pytest.approx(18)
    assert blank["length"] > roof["size_mm"]["x"]
    assert roof["profile"]["extrusion_mm"] == pytest.approx(420)

    spec = load_project(root / "projects/real-assembly").variables["upper"]
    assert spec["left_height_mm"] == 235
    assert spec["right_height_mm"] == 1204
    slope_end = spec["x"] + 1.5 * spec["cabinet_width_mm"] - spec["thickness_mm"] / 2
    starts = (
        ("left", spec["x"]),
        ("right", spec["x"] + spec["cabinet_width_mm"]),
    )
    for cabinet, start in starts:
        back = by_id[f"upper.{cabinet}.back"]
        back_end_x = start + spec["cabinet_width_mm"]
        back_height = spec["left_height_mm"] + (
            (spec["right_height_mm"] - spec["left_height_mm"])
            * min((back_end_x - spec["x"]) / (slope_end - spec["x"]), 1)
        )
        assert back["blank_mm"]["length"] == pytest.approx(back_height)
        assert back["blank_mm"]["width"] == pytest.approx(720)
        assert back["blank_mm"]["thickness"] == pytest.approx(6)
        assert back["profile"]["extrusion_mm"] == pytest.approx(6)


def test_upper_panels_do_not_interpenetrate(root):
    calculation = calculate(load_project(root / "projects/real-assembly"))
    result = calculation.result
    assembly, _ = make_geometry(calculation)
    parts = [
        part
        for part in _upper_parts(result)
        if part["component"]
        in {"left_side", "divider", "right_side", "back", "bottom", "shelf", "top"}
    ]
    solids = [assembly.objects[part["role"]].toCompound() for part in parts]

    for index, solid in enumerate(solids):
        box = solid.BoundingBox()
        for other_index in range(index + 1, len(solids)):
            other = solids[other_index]
            other_box = other.BoundingBox()
            overlaps_in_volume = (
                min(box.xmax, other_box.xmax) - max(box.xmin, other_box.xmin) > 1e-6
                and min(box.ymax, other_box.ymax) - max(box.ymin, other_box.ymin) > 1e-6
                and min(box.zmax, other_box.zmax) - max(box.zmin, other_box.zmin) > 1e-6
            )
            if not overlaps_in_volume:
                continue
            assert solid.intersect(other).Volume() <= 1e-5


def test_upper_roof_butts_against_divider_and_flat_top_bears_on_it(root):
    calculation = calculate(load_project(root / "projects/real-assembly"))
    result = calculation.result
    assembly, _ = make_geometry(calculation)
    by_id = {part["id"]: part for part in _upper_parts(result)}

    sloped_top = assembly.objects[by_id["upper.shared.top_sloped"]["role"]].toCompound()
    divider = assembly.objects[by_id["upper.right.divider"]["role"]].toCompound()
    flat_top = assembly.objects[by_id["upper.shared.top_level"]["role"]].toCompound()

    # OCC may omit tangent faces from a solid common. Check the shared planes
    # and their positive face overlap from the measured bounds and roof profile.
    roof_box = sloped_top.BoundingBox()
    divider_box = divider.BoundingBox()
    flat_box = flat_top.BoundingBox()
    assert roof_box.xmax == pytest.approx(divider_box.xmin)
    assert roof_box.ymin == pytest.approx(divider_box.ymin)
    assert roof_box.ymax == pytest.approx(divider_box.ymax)

    roof_profile = by_id["upper.shared.top_sloped"]["profile"]["points_mm"]
    roof_position = by_id["upper.shared.top_sloped"]["position_mm"]
    right_edge = [
        point for point in roof_profile if point[0] == max(p[0] for p in roof_profile)
    ]
    roof_end_z = sorted(roof_position["z"] + point[1] for point in right_edge)
    shared_side_height = min(roof_end_z[1], divider_box.zmax) - max(
        roof_end_z[0], divider_box.zmin
    )
    assert shared_side_height > 1

    # The level top rests on the divider over its full thickness and depth.
    assert flat_box.zmin == pytest.approx(divider_box.zmax)
    assert flat_box.xmin == pytest.approx(divider_box.xmin)
    assert min(flat_box.xmax, divider_box.xmax) - max(
        flat_box.xmin, divider_box.xmin
    ) == pytest.approx(18)
    assert min(flat_box.ymax, divider_box.ymax) - max(
        flat_box.ymin, divider_box.ymin
    ) == pytest.approx(420)
    assert sloped_top.intersect(divider).Volume() <= 1e-5
    assert flat_top.intersect(divider).Volume() <= 1e-5

    joint_x = 1071
    slope = (2234 - 1265) / joint_x
    slope_drop = 18 * math.sqrt(1 + slope * slope)
    expected_blank_length = math.hypot(joint_x, 2234 - 1265) + 18 * slope
    blank = by_id["upper.shared.top_sloped"]["blank_mm"]
    assert blank["length"] == pytest.approx(expected_blank_length)
    assert blank["length"] > math.hypot(joint_x, 2234 - 1265)
    assert by_id["upper.shared.top_sloped"]["size_mm"]["z"] == pytest.approx(
        969 + slope_drop
    )


def test_shelf_levels_align_and_fit_below_the_roof(root):
    project = load_project(root / "projects/real-assembly")
    spec = project.variables["upper"]
    parts = _upper_parts(calculate(project).result)
    shelves = [part for part in parts if part["component"] == "shelf"]
    assert shelves
    horizontal = [
        part
        for part in parts
        if part["component"] in {"bottom", "shelf"} and "column-0" not in part["id"]
    ]
    assert horizontal
    assert {part["blank_mm"]["length"] for part in horizontal} == {333}
    assert {part["blank_mm"]["width"] for part in horizontal} == {420}
    assert {part["blank_mm"]["thickness"] for part in horizontal} == {18}
    bottom_starts = sorted(
        part["position_mm"]["x"] for part in horizontal if part["component"] == "bottom"
    )
    assert bottom_starts == [18, 369, 738, 1089]
    assert not any(part["id"].startswith("upper.left.section_1_") for part in shelves)

    levels_by_section = {}
    joint_x = spec["x"] + 1.5 * spec["cabinet_width_mm"] - spec["thickness_mm"] / 2
    slope = (spec["right_height_mm"] - spec["left_height_mm"]) / (joint_x - spec["x"])
    slope_drop = spec["thickness_mm"] * math.sqrt(1 + slope * slope)
    for shelf in shelves:
        section = shelf["id"].split("_shelf_")[0]
        height = shelf["position_mm"]["z"]
        levels_by_section.setdefault(section, set()).add(height)
        x = shelf["position_mm"]["x"]
        if x >= joint_x:
            ceiling = spec["z"] + spec["right_height_mm"] - spec["thickness_mm"]
        else:
            ceiling = (
                spec["z"]
                + spec["left_height_mm"]
                + slope * (x - spec["x"])
                - slope_drop
            )
        assert height + spec["thickness_mm"] <= ceiling
        assert height - spec["z"] in spec["shelf_levels_mm"]

    assert (
        levels_by_section["upper.left.section_2"]
        & levels_by_section["upper.right.section_1"]
    )
    assert (
        levels_by_section["upper.left.section_2"]
        <= levels_by_section["upper.right.section_1"]
    )
    assert (
        levels_by_section["upper.right.section_1"]
        == levels_by_section["upper.right.section_2"]
    )


def test_invalid_shelf_levels_are_rejected(root):
    spec = dict(load_project(root / "projects/real-assembly").variables["upper"])
    spec["shelf_levels_mm"] = [270, 275]
    with pytest.raises(ValueError, match="shelf thickness"):
        make_upper_parts(spec)

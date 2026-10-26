import shutil

import pytest

from buratino.engine import calculate, make_geometry
from buratino.project import load_project


def test_real_assembly_keeps_two_equal_independent_drawer_carcasses(root):
    project = load_project(root / "projects/real-assembly")
    calculation = calculate(project)
    result = calculation.result

    assert [config.width for config in calculation.configs] == [720, 720]
    assert [config.height for config in calculation.configs] == [930, 930]
    assert [config.depth for config in calculation.configs] == [510, 510]
    assert [cabinet["id"] for cabinet in result["cabinets"]] == [
        "left-drawers",
        "right-drawers",
    ]
    assert [cabinet["placement_mm"]["x"] for cabinet in result["cabinets"]] == [
        0,
        720,
    ]
    assert result["dimensions_mm"] == {"width": 1440, "height": 1030, "depth": 510}
    assert result["overall_dimensions_mm"] == {
        "width": 1440,
        "height": 1030,
        "depth": 530,
    }
    assert [cabinet["placement_mm"]["z"] for cabinet in result["cabinets"]] == [
        50,
        50,
    ]
    assert [cabinet["bounds_mm"]["max"]["z"] for cabinet in result["cabinets"]] == [
        980,
        980,
    ]

    frames = {frame["id"]: frame for frame in result["frames"]}
    assert set(frames) == {"bottom", "top"}
    assert {
        frame_id: (
            frame["width"],
            frame["depth"],
            frame["height"],
            frame["thickness"],
            frame["z"],
        )
        for frame_id, frame in frames.items()
    } == {
        "bottom": (1440, 510, 50, 18, 0),
        "top": (1440, 380, 50, 18, 980),
    }
    assert all("plywood" in frame["material"].lower() for frame in frames.values())
    assert frames["top"]["y"] + frames["top"]["depth"] == 510

    carcass_sides = [
        part
        for part in result["parts"]
        if part["id"].endswith((".carcass.left_side", ".carcass.right_side"))
    ]
    assert len(carcass_sides) == 4
    assert len(result["drawers"]) == 8
    assert all(drawer["box_mm"]["depth"] == 480 for drawer in result["drawers"])
    assert result["drawer_layout"]["display_open_distance_mm"] == 480
    assert result["hardware_profile"]["runner_length_mm"] == 480
    assert result["hardware_profile"]["minimum_body_depth_mm"] == 493
    runner = next(
        item for item in result["hardware"] if item["type"] == "drawer_runner"
    )
    assert runner["length_mm"] == 480
    assert runner["part_numbers"] == ["9047756", "9047757"]
    frame_ids = {
        f"frame.{frame_id}.{rail}"
        for frame_id in ("bottom", "top")
        for rail in ("front", "back", "left", "right")
    }
    assert frame_ids <= {part["id"] for part in result["parts"]}
    assert len(result["parts"]) == 66

    frame_cut_groups = [
        group for group in result["cutting_groups"] if set(group["members"]) & frame_ids
    ]
    assert sorted(group["quantity"] for group in frame_cut_groups) == [2, 2, 4]
    grouped_frame_ids = set().union(
        *(set(group["members"]) for group in frame_cut_groups)
    )
    assert grouped_frame_ids == frame_ids

    connection = next(
        joint for joint in result["joints"] if joint["type"] == "cabinet_connection"
    )
    assert connection["status"] == "unverified"
    assert connection["parts"] == [
        "left-drawers.carcass.right_side",
        "right-drawers.carcass.left_side",
    ]
    assert any(
        issue["code"] == "assembly.connection_unverified" for issue in result["checks"]
    )

    assert project.variables["space_mm"] == {}
    assert project.variables["first_compartment_space_mm"] == {
        "width": 720,
        "height": 970,
        "depth_min": 500,
        "depth_max": 550,
    }
    assert project.variables["observations"] == [
        (
            "User-reported space the furniture must fit within; "
            "this is not a measured fit survey."
        ),
        "Depth is reported as 500 to 550 mm. Exact clear depth remains open.",
    ]
    assert project.variables["future_upper_cabinet_count"] == 2
    assert project.variables["future_upper_dimensions_mm"] is None
    assert project.variables["future_upper_connection"] is None
    assert not result["manufacturing_ready"]


def test_shared_root_height_updates_both_units_without_creating_site_width(
    root, tmp_path
):
    path = tmp_path / "real-assembly-shared-height"
    shutil.copytree(root / "projects/real-assembly", path)
    source_path = path / "project.py"
    source_path.write_text(
        source_path.read_text().replace('"height_mm": 930,', '"height_mm": 910,', 1)
    )

    project = load_project(path)
    result = calculate(project).result

    assert [cabinet["dimensions_mm"]["height"] for cabinet in result["cabinets"]] == [
        910,
        910,
    ]
    assert [cabinet["placement_mm"]["x"] for cabinet in result["cabinets"]] == [
        0,
        720,
    ]
    assert result["overall_dimensions_mm"]["width"] == 1440
    assert project.variables["space_mm"] == {}


def test_real_assembly_front_gap_and_native_geometry(root):
    calculation = calculate(load_project(root / "projects/real-assembly"))
    result = calculation.result

    faces_by_cabinet = {
        cabinet["id"]: [
            drawer
            for drawer in result["drawers"]
            if drawer["cabinet_id"] == cabinet["id"]
        ]
        for cabinet in result["cabinets"]
    }
    for faces in faces_by_cabinet.values():
        assert [drawer["face_mm"]["width"] for drawer in faces] == [717] * 4
        assert [drawer["face_mm"]["height"] for drawer in faces] == [230] * 4

    left_face = faces_by_cabinet["left-drawers"][-1]
    right_face = faces_by_cabinet["right-drawers"][0]
    left_right = left_face["face_position_mm"]["x"] + left_face["face_mm"]["width"]
    right_left = 720 + right_face["face_position_mm"]["x"]
    assert right_left - left_right == pytest.approx(2)

    assembly, geometry = make_geometry(calculation)
    assert len(geometry) == len(result["parts"])

    side_boxes = []
    for part in result["parts"]:
        if part["id"].endswith((".carcass.left_side", ".carcass.right_side")):
            side_boxes.append(assembly.objects[part["role"]].toCompound().BoundingBox())
    assert len(side_boxes) == 4
    assert sorted((box.xmin, box.xmax) for box in side_boxes) == pytest.approx(
        [(0, 18), (702, 720), (720, 738), (1422, 1440)]
    )


def test_real_assembly_frame_rails_have_native_geometry(root):
    calculation = calculate(load_project(root / "projects/real-assembly"))
    result = calculation.result
    assembly, geometry = make_geometry(calculation)

    frame_parts = [part for part in result["parts"] if part["id"].startswith("frame.")]
    assert len(frame_parts) == 8
    assert len(geometry) == len(result["parts"])
    expected_rails = {
        "frame.bottom.front": ((0, 0, 0), (1440, 18, 50)),
        "frame.bottom.back": ((0, 492, 0), (1440, 18, 50)),
        "frame.bottom.left": ((0, 18, 0), (18, 474, 50)),
        "frame.bottom.right": ((1422, 18, 0), (18, 474, 50)),
        "frame.top.front": ((0, 130, 980), (1440, 18, 50)),
        "frame.top.back": ((0, 492, 980), (1440, 18, 50)),
        "frame.top.left": ((0, 148, 980), (18, 344, 50)),
        "frame.top.right": ((1422, 148, 980), (18, 344, 50)),
    }
    for part in frame_parts:
        box = assembly.objects[part["role"]].toCompound().BoundingBox()
        pos = part["position_mm"]
        size = part["size_mm"]
        expected_pos, expected_size = expected_rails[part["id"]]
        assert tuple(pos[axis] for axis in ("x", "y", "z")) == expected_pos
        assert tuple(size[axis] for axis in ("x", "y", "z")) == expected_size
        assert (box.xmin, box.ymin, box.zmin) == pytest.approx(
            (pos["x"], pos["y"], pos["z"])
        )
        assert (box.xmax, box.ymax, box.zmax) == pytest.approx(
            (
                pos["x"] + size["x"],
                pos["y"] + size["y"],
                pos["z"] + size["z"],
            )
        )

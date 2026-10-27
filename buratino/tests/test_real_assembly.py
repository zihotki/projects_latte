import shutil

import pytest

from buratino.engine import calculate, make_geometry
from buratino.project import load_project


def test_drawer_domino_candidates_use_actual_box_heights(root):
    result = calculate(load_project(root / "projects/real-assembly")).result
    joints = [joint for joint in result["joints"] if joint["type"] == "drawer_domino"]
    assert len(joints) == 36
    part_ids = {part["id"] for part in result["parts"]}
    assert all(set(joint["parts"]) <= part_ids for joint in joints)
    assert all(joint["status"] == "unverified" for joint in joints)
    assert all(joint["quantity"] == 2 for joint in joints)
    for joint in joints:
        expected = [50, 90] if joint["drawer_id"].startswith("upper.") else [50, 130]
        assert joint["candidate_centers_from_bottom_mm"] == expected
        assert "catch" in joint["limitations"]


def test_real_assembly_keeps_two_equal_independent_drawer_carcasses(root):
    project = load_project(root / "projects/real-assembly")
    calculation = calculate(project)
    result = calculation.result

    assert [config.width for config in calculation.configs] == [720, 720]
    assert [config.height for config in calculation.configs] == [930, 930]
    assert [config.depth for config in calculation.configs] == [506, 506]
    codes = project.variables["part_codes"]
    assert {
        codes[f"{cabinet}.carcass.{panel}"]
        for cabinet in ("left-drawers", "right-drawers")
        for panel in ("top", "bottom")
    } == {"L03"}
    assert [cabinet["id"] for cabinet in result["cabinets"]] == [
        "left-drawers",
        "right-drawers",
    ]
    assert [cabinet["placement_mm"]["x"] for cabinet in result["cabinets"]] == [
        0,
        720,
    ]
    assert result["dimensions_mm"] == {"width": 1440, "height": 2234, "depth": 506}
    assert result["overall_dimensions_mm"] == {
        "width": 1440,
        "height": pytest.approx(2238.097, abs=0.001),
        "depth": 526,
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
        "bottom": (1440, 506, 50, 18, 0),
        "top": (1440, 380, 50, 18, 980),
    }
    assert all("plywood" in frame["material"].lower() for frame in frames.values())
    assert frames["top"]["y"] + frames["top"]["depth"] == 506

    carcass_sides = [
        part
        for part in result["parts"]
        if part["id"].endswith((".carcass.left_side", ".carcass.right_side"))
    ]
    assert len(carcass_sides) == 4
    lower_drawers = [
        drawer
        for drawer in result["drawers"]
        if drawer["cabinet_id"] in {"left-drawers", "right-drawers"}
    ]
    upper_drawers = [
        drawer for drawer in result["drawers"] if drawer["cabinet_id"] == "upper-left"
    ]
    assert len(lower_drawers) == 8
    assert len(upper_drawers) == 1
    assert all(drawer["box_mm"]["depth"] == 480 for drawer in lower_drawers)
    assert all(
        drawer["hardware_profile"]["runner_length_mm"] == 480
        and drawer["hardware_profile"]["minimum_body_depth_mm"] == 493
        for drawer in lower_drawers
    )
    assert upper_drawers[0]["box_mm"]["depth"] == 380
    assert result["drawer_layout"]["display_open_distance_mm"] is None
    assert result["drawer_layout"]["face_thickness_by_cabinet_mm"] == {
        "left-drawers": 18,
        "right-drawers": 18,
    }
    assert result["hardware_profile"] is None
    runners_by_length = {
        item["length_mm"]: item
        for item in result["hardware"]
        if item["type"] == "drawer_runner"
    }
    assert set(runners_by_length) == {380, 480}
    assert runners_by_length[480]["quantity"] == 16
    assert runners_by_length[480]["part_numbers"] == ["9047756", "9047757"]
    assert runners_by_length[380]["quantity"] == 2
    assert runners_by_length[380]["part_numbers"] == ["9047682", "9047683"]
    frame_ids = {
        f"frame.{frame_id}.{rail}"
        for frame_id in ("bottom", "top")
        for rail in ("front", "back", "left", "right")
    }
    assert frame_ids <= {part["id"] for part in result["parts"]}
    assert len(result["parts"]) == 96

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
    assert len(result["upper_cabinets"]) == 2
    assert not result["manufacturing_ready"]


def test_shared_root_height_updates_both_units_without_creating_site_width(
    root, tmp_path
):
    path = tmp_path / "real-assembly-shared-height"
    shutil.copytree(
        root / "projects/real-assembly", path, ignore=shutil.ignore_patterns("build")
    )
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
    assert all((box.ymin, box.ymax) == pytest.approx((0, 500)) for box in side_boxes)
    for part in result["parts"]:
        if part["id"].endswith(".carcass.back"):
            box = assembly.objects[part["role"]].toCompound().BoundingBox()
            assert (box.xlen, box.ymin, box.ymax, box.zlen) == pytest.approx(
                (720, 500, 506, 930)
            )
    assert all(config.interior_depth == 500 for config in calculation.configs)
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
        "frame.bottom.back": ((0, 488, 0), (1440, 18, 50)),
        "frame.bottom.left": ((0, 18, 0), (18, 470, 50)),
        "frame.bottom.right": ((1422, 18, 0), (18, 470, 50)),
        "frame.top.front": ((0, 126, 980), (1440, 18, 50)),
        "frame.top.back": ((0, 488, 980), (1440, 18, 50)),
        "frame.top.left": ((0, 144, 980), (18, 344, 50)),
        "frame.top.right": ((1422, 144, 980), (18, 344, 50)),
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


def test_real_assembly_uses_project_materials_without_groove_warnings(root):
    project = load_project(root / "projects/real-assembly")
    result = calculate(project).result

    assert {part["material"] for part in result["parts"]} <= {
        "Melamine-faced board",
        "6 mm board",
        "18 mm plywood",
    }
    assert not any(
        issue["code"]
        in {"drawer.bottom_groove_assumption", "drawer.material_unverified"}
        or "groove" in issue["message"].lower()
        for issue in result["checks"]
    )
    assert any("fastening" in issue["message"].lower() for issue in result["checks"])


def test_router_depth_ranges_are_paired_and_nominal(root):
    from buratino.engine import calculate
    from buratino.project import load_project

    result = calculate(load_project(root / "projects/real-assembly")).result
    data = result["domino_machining"]
    assert data["cutter_diameter_mm"] == 6
    assert data["face_depth_mm"] == {"min": 12, "max": 15}
    assert data["edge_depth_mm"] == {"min": 25, "max": 28}
    assert data["face_depth_mm"]["min"] + data["edge_depth_mm"]["max"] == 40
    assert data["face_depth_mm"]["max"] + data["edge_depth_mm"]["min"] == 40
    assert data["face_wall_mm_by_cabinet"] == {
        "left-drawers": {"min": 3, "max": 6},
        "right-drawers": {"min": 3, "max": 6},
    }
    assert result["manufacturing_ready"] is False


def test_router_depth_rejects_invalid_ranges():
    from types import SimpleNamespace

    import pytest

    from buratino.engine import _domino_machining
    from buratino.project import InputError

    cfg = [
        (
            "cabinet",
            SimpleNamespace(
                side_thickness=18, domino_spec=SimpleNamespace(size_key="6x40")
            ),
        )
    ]
    for depths in ({"min": 16, "max": 12}, {"min": 12, "max": 18}):
        with pytest.raises(InputError, match="depth"):
            _domino_machining(
                {
                    "domino_machining": {
                        "cutter_diameter_mm": 6,
                        "face_depth_mm": depths,
                    }
                },
                cfg,
            )

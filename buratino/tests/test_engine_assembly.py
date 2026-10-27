import shutil

import pytest

from buratino.engine import calculate, make_geometry
from buratino.project import InputError, load_project


def test_separate_carcass_row_places_shared_fronts_and_connections(root, tmp_path):
    path = tmp_path / "linked-row-fixture"
    shutil.copytree(
        root / "projects/linked-row-fixture",
        path,
        ignore=shutil.ignore_patterns("build"),
    )
    source = (path / "project.py").read_text()
    source = source.replace('"width": 1192', '"width": 1200', 1)
    source = source.replace('"cabinet_gap_mm": 0', '"cabinet_gap_mm": 8', 1)
    (path / "project.py").write_text(source)
    calculation = calculate(load_project(path))
    result = calculation.result
    assert [cabinet["placement_mm"]["x"] for cabinet in result["cabinets"]] == [0, 608]
    faces = [drawer["face_position_mm"] for drawer in result["drawers"]]
    face_sizes = [drawer["face_mm"] for drawer in result["drawers"]]
    first_right = faces[0]["x"] + face_sizes[0]["width"]
    second_left = result["cabinets"][1]["placement_mm"]["x"] + faces[1]["x"]
    assert second_left - first_right == pytest.approx(2)
    assert faces[0]["x"] == pytest.approx(2)
    row_right = (
        result["cabinets"][-1]["dimensions_mm"]["width"]
        + result["cabinets"][-1]["placement_mm"]["x"]
    )
    assert second_left + face_sizes[1]["width"] == pytest.approx(row_right - 2)
    assert result["dimensions_mm"]["width"] == 1200
    connection = next(
        joint for joint in result["joints"] if joint["type"] == "cabinet_connection"
    )
    assert connection["status"] == "unverified"
    assert connection["parts"] == [
        "unit-a.carcass.right_side",
        "unit-b.carcass.left_side",
    ]
    part_ids = {part["id"] for part in result["parts"]}
    assert all(
        part_id in part_ids
        for joint in result["joints"]
        for part_id in joint["parts"]
        if ".carcass." in part_id
    )
    connection_warning = next(
        issue
        for issue in result["checks"]
        if issue["code"] == "assembly.connection_unverified"
    )
    assert "Fastening details" in connection_warning["message"]
    assert "capacity" in connection_warning["message"]

    assembly, geometry = make_geometry(calculation)
    assert len(geometry) == len(result["parts"])
    first_face = next(
        part
        for part in result["parts"]
        if part.get("component") == "face" and part["cabinet_id"] == "unit-a"
    )
    second_face = next(
        part
        for part in result["parts"]
        if part.get("component") == "face" and part["cabinet_id"] == "unit-b"
    )
    a = assembly.objects[first_face["role"]].toCompound().BoundingBox()
    b = assembly.objects[second_face["role"]].toCompound().BoundingBox()
    assert b.xmin - a.xmax == pytest.approx(2)


def test_shared_column_builder_has_one_divider_and_continuous_panels(root):
    calculation = calculate(load_project(root / "projects/shared-column-fixture"))
    result = calculation.result
    carcass = [
        part for part in result["parts"] if part["id"].startswith("cabinet.carcass.")
    ]
    assert len(carcass) == 6
    assert len([part for part in carcass if part["component"] == "divider"]) == 1
    faces = [drawer for drawer in result["drawers"]]
    assert len(faces) == 2
    assert faces[1]["face_position_mm"]["x"] - (
        faces[0]["face_position_mm"]["x"] + faces[0]["face_mm"]["width"]
    ) == pytest.approx(2)

    assembly, geometry = make_geometry(calculation)
    assert len(geometry) == len(result["parts"])
    divider = next(part for part in carcass if part["component"] == "divider")
    box = assembly.objects[divider["role"]].toCompound().BoundingBox()
    assert [box.xmin, box.xmax, box.zmin, box.zmax] == pytest.approx(
        [291, 309, 18, 682]
    )
    left = next(part for part in carcass if part["component"] == "left_side")
    right = next(part for part in carcass if part["component"] == "right_side")
    left_box = assembly.objects[left["role"]].toCompound().BoundingBox()
    right_box = assembly.objects[right["role"]].toCompound().BoundingBox()
    assert [left_box.xmin, left_box.xmax] == pytest.approx([0, 18])
    assert [right_box.xmin, right_box.xmax] == pytest.approx([582, 600])


def test_each_cabinet_keeps_its_native_face_thickness_and_aligns_fronts(root, tmp_path):
    path = tmp_path / "linked-row-face-thickness"
    shutil.copytree(
        root / "projects/linked-row-fixture",
        path,
        ignore=shutil.ignore_patterns("build"),
    )
    source = (path / "project.py").read_text()
    needle = 'face_thickness=variables["drawer_face_thickness_mm"],'
    before, after = source.rsplit(needle, 1)
    (path / "project.py").write_text(before + "face_thickness=22," + after)

    calculation = calculate(load_project(path))
    result = calculation.result
    assert [drawer["face_mm"]["thickness"] for drawer in result["drawers"]] == [18, 22]
    assert [cabinet["placement_mm"]["y"] for cabinet in result["cabinets"]] == [-4, 0]
    assert result["overall_dimensions_mm"]["depth"] == 504

    assembly, _ = make_geometry(calculation)
    face_parts = [part for part in result["parts"] if part.get("component") == "face"]
    face_bounds = [
        assembly.objects[part["role"]].toCompound().BoundingBox() for part in face_parts
    ]
    assert [box.ymin for box in face_bounds] == pytest.approx([-24, -24])
    assert [box.ylen for box in face_bounds] == pytest.approx([18, 22])


def test_shared_values_update_each_native_config_and_override_scope(root, tmp_path):
    path = tmp_path / "linked-row-values"
    shutil.copytree(
        root / "projects/linked-row-fixture",
        path,
        ignore=shutil.ignore_patterns("build"),
    )
    source_path = path / "project.py"

    source_original = source_path.read_text()
    source_path.write_text(
        source_original.replace('"top_thickness_mm": 18', '"top_thickness_mm": 20', 1)
    )
    top_changed = calculate(load_project(path))
    assert [config.top_thickness for config in top_changed.configs] == [20, 22]

    source_path.write_text(
        source_original.replace('"front_gap_mm": 2', '"front_gap_mm": 4', 1)
    )
    gap_changed = calculate(load_project(path))
    faces = gap_changed.result["drawers"]
    first_right = faces[0]["face_position_mm"]["x"] + faces[0]["face_mm"]["width"]
    second_left = (
        gap_changed.result["cabinets"][1]["placement_mm"]["x"]
        + faces[1]["face_position_mm"]["x"]
    )
    assert second_left - first_right == pytest.approx(4)
    assert gap_changed.result["overall_dimensions_mm"]["depth"] == 500

    source_path.write_text(
        source_original.replace('"height_mm": 700', '"height_mm": 660', 1)
    )
    height_changed = load_project(path)
    assert height_changed.calculated["unit_a_interior_mm"]["height"] == 624
    assert height_changed.calculated["unit_b_interior_mm"]["height"] == 620
    assert [cfg.height for _, cfg in height_changed.native_project.resolved()] == [
        660,
        660,
    ]
    assert [cfg.opening_height for cfg in height_changed.drawer_configs.values()] == [
        624,
        620,
    ]


@pytest.mark.parametrize(
    "key,value",
    [
        ("edge_gap_mm", -1),
        ("face_to_carcass_gap_mm", -5),
        ("front_gap_mm", float("inf")),
        ("cabinet_gap_mm", True),
    ],
)
def test_rejects_invalid_front_and_cabinet_gaps(root, key, value):
    project = load_project(root / "projects/linked-row-fixture")
    project.variables[key] = value
    with pytest.raises(InputError, match=key):
        calculate(project)


def test_rejects_drawer_config_height_mismatch_and_box_overflow(root):
    project = load_project(root / "projects/linked-row-fixture")
    cfg = project.drawer_configs["unit-a/column-0/opening-0"]
    cfg.opening_height += 1
    with pytest.raises(InputError, match="opening width, height"):
        calculate(project)

    project = load_project(root / "projects/linked-row-fixture")
    cfg = project.drawer_configs["unit-a/column-0/opening-0"]
    cfg.buratino_box_bottom_clearance_mm = cfg.opening_height + 1
    with pytest.raises(InputError, match="box height and bottom clearance"):
        calculate(project)


def test_missing_drawer_configs_use_native_opening_helper(root):
    from cabineteer.cabinet import opening_stack
    from cabineteer.drawer import box_config_for_opening

    project = load_project(root / "projects/linked-row-fixture")
    project.drawer_configs.clear()
    resolved = list(project.native_project.resolved())
    calculation = calculate(project)
    for (_, cabinet), instance in zip(
        resolved, calculation.drawer_instances, strict=True
    ):
        opening = opening_stack(cabinet)[0].opening
        expected = box_config_for_opening(
            cabinet,
            cabinet.interior_width,
            opening.height_mm,
            cabinet.interior_depth,
            opening,
        )
        actual = instance["config"]
        assert actual.box_height == expected.box_height
        assert actual.vertical_gap == expected.vertical_gap
        assert (
            actual.front_back_thickness
            == actual.side_thickness
            == cabinet.drawer_box_thickness
        )
        assert actual.bottom_thickness == expected.bottom_thickness
        assert actual.box_height < opening.height_mm
        assert actual.applied_face is False
        assert instance["box_position"]["y"] == expected.front_gap


@pytest.mark.parametrize(
    "attribute,value,match",
    [
        ("bottom_dado_depth", 16, "groove depth"),
        ("buratino_rear_corner_clearance_width_mm", 400, "relief"),
        ("buratino_rear_corner_clearance_width_mm", -1, "relief"),
        ("bottom_thickness", float("nan"), "bottom_thickness"),
        ("bottom_dado_inset", 11, "recess"),
    ],
)
def test_invalid_native_drawer_config_fails_before_cad(
    root, monkeypatch, attribute, value, match
):
    project = load_project(root / "projects/linked-row-fixture")
    cfg = project.drawer_configs["unit-a/column-0/opening-0"]
    setattr(cfg, attribute, value)
    monkeypatch.setattr(
        "buratino.engine._build_native_carcass", lambda *_: pytest.fail("CAD started")
    )
    with pytest.raises(InputError, match=match):
        calculate(project)


def test_native_helper_honors_cabinet_stock_and_opening_bottom(root, tmp_path):
    path = tmp_path / "row-native-defaults"
    shutil.copytree(
        root / "projects/linked-row-fixture",
        path,
        ignore=shutil.ignore_patterns("build"),
    )
    source_path = path / "project.py"
    source = source_path.read_text().replace(
        '"drawer_side_thickness_mm": 16', '"drawer_side_thickness_mm": 15'
    )
    source = source.replace(
        'slide_key="buratino_hettich_quadro_v6_eb20",',
        'slide_key="buratino_hettich_quadro_v6_eb20",'
        "\n            bottom_thickness=10,",
        1,
    )
    source_path.write_text(source)
    project = load_project(path)
    project.drawer_configs.clear()
    cfg = calculate(project).drawer_instances[0]["config"]
    assert cfg.side_thickness == cfg.front_back_thickness == 15
    assert cfg.bottom_thickness == 10
    assert cfg.slide_key == "buratino_hettich_quadro_v6_eb20"

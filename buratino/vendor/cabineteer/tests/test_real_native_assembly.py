"""Check measured assembly choices against independent world coordinates."""

from dataclasses import replace
from pathlib import Path
import runpy

import pytest

from cabineteer.profiles import assembly_records, lower_drawer_parts, resolved_profile_spec


@pytest.fixture(scope="module")
def assembly():
    root = Path(__file__).resolve().parents[3]
    project = runpy.run_path(str(root / "projects/real-assembly-native/project.py"))[
        "project"
    ]
    return project.resolved_assembly()


def test_four_shared_sections_and_two_frames(assembly):
    placements = {item.name: item.origin_mm for item in assembly.layout.placements}
    assert placements == {
        "frame.bottom": (0, 0, 0),
        "left-drawers": (0, 0, 50),
        "right-drawers": (720, 0, 50),
        "frame.support": (0, 126, 980),
        "upper": (0, 80, 1030),
    }
    parts = {part.id: part for part in assembly.parts}
    left_face = parts["left-drawers.opening.0.drawer_front"].solid().val().BoundingBox()
    right_face = parts["right-drawers.opening.0.drawer_front"].solid().val().BoundingBox()
    assert (left_face.xmin, left_face.xmax) == (2, 719)
    assert (right_face.xmin, right_face.xmax) == (721, 1438)
    assert right_face.xmin - left_face.xmax == 2
    assert len(parts) == len(assembly.parts) == 91
    for name in ("left-drawers", "right-drawers"):
        back = parts[f"{name}.carcass.back"]
        assert back.material == "6 mm board"
        assert back.stock_mm[2] == 6
    assert len([part for part in parts.values() if part.component == "divider"]) == 3
    assert (
        len(
            [
                part
                for part in parts.values()
                if part.component == "back" and part.owner == "upper"
            ]
        )
        == 1
    )
    for i, x in enumerate((351, 711, 1071), 1):
        divider = parts[f"upper.divider.{i}"].solid().val().BoundingBox()
        assert (divider.xmin, divider.xmax) == (x, x + 18)
    assert parts["upper.divider.3"].profile_xz_mm == (
        (1071, 18),
        (1089, 18),
        (1089, 1186),
        (1071, 1186),
    )
    bottom = parts["upper.bottom"]
    bounds = bottom.solid().val().BoundingBox()
    assert bottom.stock_mm == (1440, 420, 18)
    assert bottom.profile_xz_mm == ((0, 0), (1440, 0), (1440, 18), (0, 18))
    assert (bounds.xmin, bounds.xmax, bounds.ymin, bounds.ymax) == (0, 1440, 80, 500)
    assert (bounds.zmin, bounds.zmax) == (1030, 1048)
    assert not any(
        part.id.startswith("upper.section-")
        and part.component == "bottom"
        and not part.id.endswith(".drawer.bottom")
        for part in parts.values()
    )
    verticals = [
        part
        for part in parts.values()
        if part.owner == "upper"
        and part.component in {"side_left", "side_right", "divider"}
        and ".drawer." not in part.id
    ]
    assert len(verticals) == 5
    for part in verticals:
        wall = part.solid().val().BoundingBox()
        assert wall.zmin == 1048
    back = parts["upper.back"]
    back_bounds = back.solid().val().BoundingBox()
    assert (back_bounds.ymin, back_bounds.ymax) == (500, 506)
    assert parts["upper.roof.cap.slope"].profile_xz_mm[1][0] == 1071
    assert parts["upper.roof.cap.level"].profile_xz_mm[0][0] == 1071
    assert {part.id for part in parts.values() if part.owner == "frame.bottom"} == {
        f"frame.bottom.{rail}" for rail in ("front", "back", "left", "right")
    }
    assert {part.id for part in parts.values() if part.owner == "frame.support"} == {
        f"frame.support.{rail}" for rail in ("front", "back", "left", "right")
    }


def test_nine_drawers_and_clear_upper_shelves(assembly):
    data = assembly_records(assembly)
    drawers = data["drawers"]
    assert len(drawers) == len(assembly.hardware) == 9
    assert len({item["instance_id"] for item in drawers}) == 9
    assert len({item["instance_id"] for item in assembly.hardware}) == 9
    for item in drawers:
        assert len(item["part_ids"]) == 6
        assert item["face_mm"]["thickness"] == 18
        if item["cabinet_id"] == "upper":
            assert item["box_mm"]["depth"] == pytest.approx(380)
            assert item["box_mm"]["height"] == pytest.approx(140)
        else:
            index = item["drawer_index"] - 1
            assert item["closed_position_mm"]["z"] == pytest.approx(98 + 223.5 * index)
            assert item["face_position_mm"]["z"] == 52 + 232 * index
            assert item["face_position_mm"]["y"] == -20
            assert item["face_mm"]["width"] == 717
            assert item["face_mm"]["height"] == 230
            assert item["box_mm"]["depth"] == pytest.approx(480)
    parts = {part.id: part for part in assembly.parts}
    for section, width, x, levels in (
        (2, 342, 369, (270,)),
        (3, 342, 729, (270, 550, 830)),
        (4, 333, 1089, (270, 550, 830)),
    ):
        shelves = [
            part
            for part in parts.values()
            if part.id.startswith(f"upper.section-{section}.shelf.")
        ]
        assert len(shelves) == len(levels)
        for part, level in zip(
            sorted(shelves, key=lambda p: p.local_frame.origin_mm[2]), levels
        ):
            bounds = part.solid().val().BoundingBox()
            assert (bounds.xmin, bounds.xmax) == (x, x + width)
            assert (bounds.ymin, bounds.ymax) == (83, 500)
            assert bounds.zmin == 1030 + level
    viewer = data["viewer"]["parts"]
    for item in drawers:
        assert {viewer[part_id]["instance_id"] for part_id in item["part_ids"]} == {
            item["instance_id"]
        }
    assert not any(
        "instance_id" in viewer[part.id]
        for part in parts.values()
        if part.component in ("divider", "adjustable_shelf")
    )


def test_invalid_shared_layout_and_drawer_recipe(assembly):
    root = Path(__file__).resolve().parents[3]
    project = runpy.run_path(str(root / "projects/real-assembly-native/project.py"))[
        "project"
    ]
    spec = project.profile_assembly
    assert resolved_profile_spec(spec).roof.points[1][0] == 1071
    with pytest.raises(ValueError, match="contiguous"):
        replace(
            project,
            profile_assembly=replace(
                spec,
                boxes=(
                    spec.boxes[0],
                    replace(spec.boxes[1], x_mm=361),
                    *spec.boxes[2:],
                ),
            ),
        ).resolved_assembly()
    with pytest.raises(ValueError, match="each lower cabinet"):
        replace(
            project,
            profile_assembly=replace(spec, lower_drawers=spec.lower_drawers[:1]),
        ).resolved_assembly()


def test_continuous_bottom_is_opt_in_and_requires_shared_owner(assembly):
    root = Path(__file__).resolve().parents[3]
    project = runpy.run_path(str(root / "projects/real-assembly-native/project.py"))[
        "project"
    ]
    sectioned = replace(project.profile_assembly, continuous_bottom=False)
    legacy = replace(project, profile_assembly=sectioned).resolved_assembly()
    legacy_bottoms = [
        part
        for part in legacy.parts
        if part.owner == "upper"
        and part.component == "bottom"
        and not part.id.endswith(".drawer.bottom")
    ]
    assert {part.id for part in legacy_bottoms} == {
        "upper.section-1.bottom",
        "upper.section-2.bottom",
        "upper.section-3.bottom",
        "upper.section-4.bottom",
    }
    assert len(legacy_bottoms) == 4
    upper_carcass_components = {"side_left", "side_right", "divider", "bottom", "back"}
    old_volume = sum(
        part.solid().val().Volume()
        for part in legacy.parts
        if part.owner == "upper" and part.component in upper_carcass_components
    )
    new_volume = sum(
        part.solid().val().Volume()
        for part in assembly.parts
        if part.owner == "upper" and part.component in upper_carcass_components
    )
    assert new_volume == pytest.approx(old_volume)
    with pytest.raises(ValueError, match="requires a shared carcass"):
        replace(
            project,
            profile_assembly=replace(
                sectioned, shared_owner=None, continuous_bottom=True
            ),
        ).resolved_assembly()


def test_single_lower_cabinet_keeps_two_outer_reveals(assembly):
    root = Path(__file__).resolve().parents[3]
    project = runpy.run_path(
        str(root / "projects/real-assembly-native/project.py")
    )["project"]
    placement = next(item for item in assembly.layout.placements
                     if item.name == "left-drawers")
    spec = replace(project.profile_assembly,
                   lower_drawers=project.profile_assembly.lower_drawers[:1])
    parts, hardware = lower_drawer_parts(
        spec, {"left-drawers": project.resolved()[0][1]},
        {"left-drawers": placement},
    )
    fronts = [part for part in parts if part.component == "drawer_front"]
    assert len(fronts) == len(hardware) == 4
    assert all(part.stock_mm[0] == 716 for part in fronts)

"""Under-window stock, runner fit, and registered contact-face joints."""

from collections import Counter

import pytest
from cabineteer.drawer import DrawerConfig
from cabineteer.project import project_from_dict, project_to_dict
from cabineteer.space_adapter import materialize_box_part

from buratino.build import render_documents
from buratino.engine import calculate
from buratino.project import load_project


def test_depth_override_preserves_runner_fit():
    cfg = DrawerConfig(
        1012,
        312,
        554,
        slide_key="ferretti_hdsc500v90",
        box_depth_override=544,
        front_gap=0,
    )
    assert cfg.box_depth == 544
    assert cfg.slide.slide_length_for_depth(554) == 500
    assert cfg.slide.travel_mm == 500
    assert cfg.slide.part_numbers == {500: "HDSC500V90"}
    assert cfg.side_gap == 19.5
    assert DrawerConfig(1012, 312, 554, slide_key=cfg.slide_key).box_depth == 500


@pytest.mark.parametrize("depth", [499, 555, 0, -1, float("nan"), float("inf"), True])
def test_invalid_side_mount_depth_override(depth):
    cfg = DrawerConfig(
        1012,
        312,
        554,
        slide_key="ferretti_hdsc500v90",
        box_depth_override=depth,
        front_gap=0,
    )
    with pytest.raises(ValueError):
        _ = cfg.box_depth


def test_undermount_retains_runner_specific_depth():
    cfg = DrawerConfig(1012, 312, 564, box_depth_override=544)
    with pytest.raises(ValueError, match="runner-specific"):
        _ = cfg.box_depth
    cfg.box_depth_override = 550
    assert cfg.box_depth == 550


def test_under_window_stock_joint_pairs_and_report(root, tmp_path):
    source = load_project(root / "projects/two-under-window")
    encoded = project_to_dict(source.native_project)
    assert project_to_dict(project_from_dict(encoded)) == encoded
    result = calculate(source).result
    assert result["overall_dimensions_mm"] == {
        "width": 2096,
        "height": 679,
        "depth": 590,
    }
    assert len(result["parts"]) == 36
    assert all(
        d["box_mm"] == {"width": 973, "depth": 544, "height": 270}
        and d["runner_travel_mm"] == 500
        for d in result["drawers"]
    )
    parts = {p["id"]: p for p in result["parts"]}
    for part in parts.values():
        if "/box-" in part["id"] and part["id"].endswith("/bottom"):
            assert part["profile"]["size"] == [949, 520, 12]
        elif "/carcass/" in part["id"] or part["id"].endswith("/front-rail"):
            assert part["material"] == "melamine"
        else:
            assert part["material"] == "plywood"
    joints = result["joints"]
    assert len(joints) == 52
    assert {j["id"] for j in joints} == {
        f"{row.id}-{position:g}"
        for row in source.native_project.joints
        for position in row.positions
    }
    cuts = [
        op
        for p in parts.values()
        for op in p["operations"]
        if op.get("source") == "joint"
    ]
    assert Counter(op["joint_id"] for op in cuts) == {j["id"]: 2 for j in joints}
    assert all(
        j["slot_mm"] == {"length": 20, "width": 6}
        and sorted(op["depth"] for op in j["mortises"]) == [12, 28]
        for j in joints
    )
    for op in cuts:
        if "/box-" in op["part_id"]:
            # These x-face mortises have local v = Z. The groove ends at 25.
            assert op["v"] - op["length"] / 2 > 25
    assert (
        next(h for h in result["hardware"] if h["type"] == "domino")["quantity"] == 52
    )
    render_documents(tmp_path, result)
    assembly = (tmp_path / "assembly.html").read_text()
    assert "2 × 6 × 40 mm Domino" in assembly
    assert "1 × 6 × 40 mm Domino" in assembly
    assert "20 × 6 mm slots" in assembly
    assert "12/28 mm depths" in assembly


def test_declared_mortises_remove_stock(root):
    source = load_project(root / "projects/two-under-window")
    parts = source.native_project.resolved_space_assembly().part_plan.parts
    # One drawer side includes a groove plus four actual mortises.
    part = next(
        p for p in parts if p["id"] == "/cabinet-row/left/root/lower/box-lower/side_L"
    )
    groove_only = dict(
        part,
        operations=[op for op in part["operations"] if op.get("source") != "joint"],
    )
    solid = materialize_box_part(part).val()
    assert solid.isValid()
    assert solid.Volume() < materialize_box_part(groove_only).val().Volume()

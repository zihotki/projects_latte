"""Under-window stock, runner fit, and registered contact-face joints."""

from collections import Counter
from hashlib import sha256

import pytest
from cabineteer.drawer import DrawerConfig
from cabineteer.project import project_from_dict, project_to_dict
from cabineteer.space_adapter import materialize_box_part

from buratino.build import render_documents
from buratino.cut_services import plan_export
from buratino.engine import calculate
from buratino.project import load_project

_PROVIDER_CSV_SHA256 = {
    "zagenzagen-front-panel-panel-18mm-14791277f2b4-001.csv": (
        "473607e6b253d6781426285be02aee0f0dcaeacd61a6ef683f068fb16b0167ae"
    ),
    "opmaatzagen-front-panel-panel-18mm-14791277f2b4-001.csv": (
        "59e2bdd5be44ba03c07fc774857490d3723b1bb9031efd2e2cf896f5ed3c7c00"
    ),
    "zagenzagen-melamine-panel-18mm-c9f85f74df9c-001.csv": (
        "afe1c73873c07de44145a75ad05dddeea1b03f8a6158818a703bee23a1474210"
    ),
    "zagenzagen-plywood-panel-12mm-58d0115cf732-001.csv": (
        "da8c87ada840c08f371b7c384946c5eb718414442487511795015623fc5eb973"
    ),
    "zagenzagen-plywood-panel-18mm-109afb8af209-001.csv": (
        "27dc0255b964529c8f3d1a0837379fac584a1160437e1368d3a7e55f864548cf"
    ),
    "opmaatzagen-melamine-panel-18mm-c9f85f74df9c-001.csv": (
        "1734ba237a08fe4c29bfbf3906aa51b46c49535147a213ce5ff520893bc3ed3d"
    ),
    "opmaatzagen-plywood-panel-12mm-58d0115cf732-001.csv": (
        "85840a09b774462a43054f51618037e3e7b713e7acf3211156127c707af4a7dd"
    ),
    "opmaatzagen-plywood-panel-18mm-109afb8af209-001.csv": (
        "c9ed079bfa958037a1271e19438780535ac4ddafa219dfdce9aa49fc3187f90f"
    ),
}


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
        d["box_mm"] == {"width": 973, "depth": 544, "height": 260}
        and d["runner_travel_mm"] == 500
        for d in result["drawers"]
    )
    parts = {p["id"]: p for p in result["parts"]}
    for part in parts.values():
        if "/box-" in part["id"] and part["id"].endswith("/bottom"):
            assert part["profile"]["size"] == [953, 524, 12]
        elif "/box-" in part["id"]:
            grooves = [
                op for op in part["operations"] if op.get("role") == "bottom_groove"
            ]
            assert len(grooves) == 1 and grooves[0]["depth"] == 8
            assert part["material"] == "plywood"
        elif "/carcass/" in part["id"] or part["id"].endswith("/front-rail"):
            assert part["material"] == "melamine"
        else:
            assert part["material"] == "front-panel"
    joints = result["joints"]
    assert len(joints) == 76
    assert all(len(joint["mortises"]) == 2 for joint in joints)
    geometry = sorted(
        (
            mortise["part_id"],
            mortise["face"],
            mortise["u"],
            mortise["v"],
            mortise["axis"],
            mortise["length"],
            mortise["width"],
            mortise["depth"],
        )
        for joint in joints
        for mortise in joint["mortises"]
    )
    assert len(geometry) == 152
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
        next(h for h in result["hardware"] if h["type"] == "domino")["quantity"] == 76
    )
    assert len(result["cutting_groups"]) == 11
    for provider in ("zagenzagen", "opmaatzagen"):
        export = plan_export(result, provider)
        expected = {
            filename: digest
            for filename, digest in _PROVIDER_CSV_SHA256.items()
            if filename.startswith(f"{provider}-")
        }
        actual = {
            name: sha256(content.encode()).hexdigest()
            for name, content in export.files.items()
        }
        assert actual == expected
    render_documents(tmp_path, result)
    report = (tmp_path / "report.html").read_text()
    assert 'id="assembly"' in report
    assert "Joint requirements" not in report
    assert "6 × 40 mm; × 92" not in report
    assert "20 × 6 mm slots" not in report
    assert "12/28 mm depths" not in report
    assert not (tmp_path / "assembly.html").exists()


def test_declared_mortises_remove_stock(root):
    source = load_project(root / "projects/two-under-window")
    parts = source.native_project.resolved_space_assembly().part_plan.parts
    # One drawer side includes a groove plus six actual mortises.
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

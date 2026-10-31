"""Authored grain for the two current designs and the native viewer frame."""

import csv
import json
import subprocess

import pytest
from cabineteer.part_grain import GrainRule, PartGrain, resolve_part_grain
from cabineteer.project import project_from_dict, project_to_dict

from buratino.build import render_documents
from buratino.cut_services import plan_export
from buratino.engine import calculate
from buratino.grouping import group_cutting_blanks
from buratino.project import load_project


@pytest.mark.parametrize(
    ("name", "count", "examples"),
    [
        (
            "two-under-window",
            36,
            {
                "/cabinet-row/left/carcass/side_left": "z",
                "/cabinet-row/right/front/upper-front": "z",
                "/cabinet-row/left/root/lower/box-lower/side_L": "y",
                "/cabinet-row/right/root/front-rail": "x",
            },
        ),
        (
            "attic-clothing-storage",
            91,
            {
                "upper.side_left": "x",
                "upper.roof.cap.slope": "x",
                "upper.section-2.door": "y",
                "left-drawers.opening.0.drawer.side_left": "x",
                "right-drawers.opening.3.drawer.inner_front": "x",
                "frame.support.left": "x",
                "upper.back": "y",
            },
        ),
    ],
)
def test_actual_project_grain_round_trip_and_result(
    root, tmp_path, name, count, examples
):
    source = load_project(root / "projects" / name)
    encoded = project_to_dict(source.native_project)
    assert project_to_dict(project_from_dict(encoded)) == encoded
    result = calculate(source).result
    parts = {part["id"]: part for part in result["parts"]}
    assert len(parts) == count
    assert all(part["grain_status"] == "confirmed" for part in parts.values())
    assert all(
        part["grain_direction"] in {"length", "width"} for part in parts.values()
    )
    for part_id, axis in examples.items():
        assert parts[part_id]["grain_axis_local"] == axis
    render_documents(tmp_path, result)
    with (tmp_path / "parts.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(row["grain_direction"] in {"length", "width"} for row in rows)
    assert all(row["grain_status"] == "confirmed" for row in rows)
    if name == "attic-clothing-storage":
        assert {row["id"] for row in rows} == set(parts)
        assert all(row["grain_axis_local"] in {"x", "y"} for row in rows)
        assembly_parts = {part["id"]: part for part in result["assembly"]["parts"]}
        assert {
            part_id: part["grain_axis_local"]
            for part_id, part in assembly_parts.items()
        } == {part_id: part["grain_axis_local"] for part_id, part in parts.items()}
        cap_viewer = result["assembly"]["viewer"]["parts"]["upper.roof.cap.slope"]
        assert cap_viewer["grain_axis_local"] == "x"
        plan = plan_export(result, "opmaatzagen")
        trace = {item["source_id"]: item for item in plan.summary["trace"]}
        assert set(trace) == set(parts)
        assert all(item["outcome"] == "exported" for item in trace.values())
        assert trace["upper.roof.cap.slope"]["grain"] == "x"
        assert trace["upper.section-2.door"]["grain"] == "y"


def test_rule_override_unknown_and_invalid_axes():
    def part(part_id):
        return {
            "id": part_id,
            "stock_mm": {"length": 300, "width": 100, "thickness": 18},
            "local_frame": {"origin_mm": (0, 0, 0)},
        }

    parts = [part("side.left"), part("side.right"), part("new.part")]
    resolve_part_grain(
        parts,
        (
            PartGrain("exact", "side.left", "none"),
            GrainRule("sides", "side.*", "x"),
            GrainRule("right", "side.right", "y"),
        ),
    )
    assert [(item["grain_direction"], item["grain_status"]) for item in parts] == [
        ("none", "nondirectional"),
        ("width", "confirmed"),
        ("unknown", "unverified"),
    ]
    with pytest.raises(ValueError, match="thickness axis"):
        resolve_part_grain([part("side.left")], (GrainRule("bad", "side.*", "z"),))
    with pytest.raises(ValueError, match="no resolved part matches"):
        resolve_part_grain([part("side.left")], (GrainRule("bad", "missing.*", "x"),))
    with pytest.raises(ValueError, match="duplicate part grain for"):
        resolve_part_grain(
            [part("side.left")],
            (
                PartGrain("a", "side.left", "x"),
                PartGrain("b", "side.left", "y"),
            ),
        )
    with pytest.raises(ValueError, match="axis must be"):
        GrainRule("bad", "side.*", "length")

    source = {
        "role": "panel",
        "component": "top",
        "material": "sheet",
        "quantity": 1,
        "blank_mm": {"length": 300, "width": 100, "thickness": 18},
        "local_frame": {"origin_mm": (0, 0, 0)},
        "grain_status": "confirmed",
    }
    groups = group_cutting_blanks(
        [
            {**source, "id": "along", "grain_axis_local": "x"},
            {**source, "id": "across", "grain_axis_local": "y"},
        ]
    )
    assert len(groups) == 2


def test_native_glb_marks_follow_real_stock_faces(root, tmp_path):
    import cadquery as cq
    from cabineteer.visualize import export_glb

    source = load_project(root / "projects/attic-clothing-storage")
    calculation = calculate(source)
    selected = (
        "upper.side_left",
        "upper.roof.cap.slope",
        "upper.section-1.drawer_front",
    )
    records = {part["id"]: part for part in calculation.result["parts"]}
    assembly = cq.Assembly(name="base_cabinet")
    for part in calculation.native_assembly.parts:
        if part.id in selected:
            assembly.add(part.solid(), name=part.id)
    glb = export_glb(assembly, tmp_path / "native-grain.glb")
    metadata = tmp_path / "parts.json"
    metadata.write_text(json.dumps([records[part_id] for part_id in selected]))
    viewer_tests = root / "vendor/cabineteer/tests"
    subprocess.run(
        [
            "node",
            "--no-warnings",
            "--experimental-loader",
            str(viewer_tests / "three_test_loader.mjs"),
            str(viewer_tests / "test_viewer_native_grain.mjs"),
            str(glb),
            str(metadata),
        ],
        check=True,
    )

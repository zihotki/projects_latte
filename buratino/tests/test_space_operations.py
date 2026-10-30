import csv
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import cadquery as cq

from buratino.build import _space_operations_table, render_documents, render_geometry
from buratino.engine import calculate
from buratino.grouping import group_cutting_blanks
from buratino.panel_views import panel_groups
from buratino.project import load_project


def test_machined_space_report_uses_resolved_records_and_keeps_stock_as_blank(root):
    project = load_project(root / "projects/machined-drawer")
    plan = project.native_project.resolved_space_model()
    result = calculate(project).result
    resolved = {part["id"]: part for part in plan.part_plan.parts}
    reported = {part["id"]: part for part in result["parts"]}

    assert reported.keys() == resolved.keys()
    assert all(
        reported[ident]["operations"] == resolved[ident]["operations"]
        for ident in resolved
    )
    machined = [part for part in result["parts"] if part["operations"]]
    operation_types = {
        operation["type"] for part in machined for operation in part["operations"]
    }
    assert operation_types == {
        "pocket",
        "rabbet",
        "bevel",
        "bore",
        "mortise",
    }
    assert all(part["blank_mm"] == part["stock_mm"] for part in machined)
    assert all("finished_mm" not in part for part in machined)
    bores = {
        operation["id"]: operation
        for part in machined
        for operation in part["operations"]
        if operation["type"] == "bore"
    }
    side_id = "/cabinet/carcass/side_left"
    back_id = "/cabinet/carcass/back"
    assert bores["user/side-edge-bore"]["face"] == "y-"
    assert (
        bores["user/side-edge-bore"]["face"][0]
        != "xyz"[resolved[side_id]["stock"]["thickness_axis"]]
    )
    assert (
        bores["user/back-face-bore"]["face"][0]
        == "xyz"[resolved[back_id]["stock"]["thickness_axis"]]
    )
    assert bores["user/side-edge-bore"]["depth"] == 10
    assert bores["user/back-face-bore"]["depth"] == 6
    assert all(
        part["local_datum"]
        == {
            "origin": "unmachined_stock_min_xyz",
            "face_uv": "remaining_axes_ascending_xyz",
            "depth": "inward_from_selected_face",
        }
        for part in machined
    )

    table = _space_operations_table(result["parts"])
    groove = next(
        operation
        for part in machined
        for operation in part["operations"]
        if operation.get("input_type") == "groove"
    )
    assert "Resolved machining operations" in table
    assert "joint/side-to-back/a" in table
    assert "user/side-edge-bore" in table
    assert ">Groove<" in table
    assert "offset 320 mm" in table
    assert f"groove_length {groove['groove']['length']:g} mm" in table
    assert "unmachined stock minimum XYZ corner" in table
    assert "Depth runs inward" in table


def test_cutting_groups_keep_parts_with_different_cuts_apart():
    first = {
        "id": "/part-a",
        "role": "panel",
        "quantity": 1,
        "material": "maple",
        "blank_mm": {"length": 300, "width": 100, "thickness": 18},
        "operations": [{"id": "user/cut-a", "type": "pocket", "u": 10}],
    }
    second = deepcopy(first)
    second["id"] = "/part-b"
    second["operations"] = [{"id": "user/cut-b", "type": "pocket", "u": 20}]

    groups = group_cutting_blanks([first, second])

    assert len(groups) == 2
    assert {tuple(group["members"]) for group in groups} == {
        ("/part-a",),
        ("/part-b",),
    }
    assert all(
        group["grouping_scope"] == "cutting_blank_and_machining" for group in groups
    )


def test_equal_solids_with_different_cuts_keep_codes_csv_and_preview_distinct(
    root, tmp_path, monkeypatch
):
    blank = cq.Workplane("XY").box(100, 100, 10, centered=False).val()
    one_pocket = (
        cq.Workplane("XY").box(10, 10, 10, centered=False).translate((20, 20, 0)).val()
    )
    first_half = (
        cq.Workplane("XY").box(5, 10, 10, centered=False).translate((20, 20, 0)).val()
    )
    second_half = (
        cq.Workplane("XY").box(5, 10, 10, centered=False).translate((25, 20, 0)).val()
    )
    single_solid = blank.cut(one_pocket)
    split_solid = blank.cut(first_half).cut(second_half)
    assert single_solid.cut(split_solid).Volume() < 1e-5
    assert split_solid.cut(single_solid).Volume() < 1e-5

    first_id, second_id = "/parts/single", "/parts/split"
    operations = (
        [
            {
                "id": "user/single-pocket",
                "part_id": first_id,
                "type": "pocket",
                "source": "user",
                "face": "z-",
                "u": 20,
                "v": 20,
                "size_u": 10,
                "size_v": 10,
                "depth": 10,
            }
        ],
        [
            {
                "id": "user/split-pocket-a",
                "part_id": second_id,
                "type": "pocket",
                "source": "user",
                "face": "z-",
                "u": 20,
                "v": 20,
                "size_u": 5,
                "size_v": 10,
                "depth": 10,
            },
            {
                "id": "user/split-pocket-b",
                "part_id": second_id,
                "type": "pocket",
                "source": "user",
                "face": "z-",
                "u": 25,
                "v": 20,
                "size_u": 5,
                "size_v": 10,
                "depth": 10,
            },
        ],
    )
    parts = [
        {
            "id": ident,
            "role": ident,
            "component": "panel",
            "quantity": 1,
            "material": "maple",
            "blank_mm": {"length": 100, "width": 100, "thickness": 10},
            "stock_mm": {"length": 100, "width": 100, "thickness": 10},
            "operations": ops,
            "grain_direction": "unknown",
            "grain_status": "unverified",
            "edge_treatment": "unverified",
        }
        for ident, ops in zip((first_id, second_id), operations, strict=True)
    ]
    assembly = cq.Assembly(name="root")
    assembly.add(single_solid, name=first_id)
    assembly.add(split_solid, name=second_id)

    cad_groups = panel_groups(assembly, parts)
    report_groups = group_cutting_blanks(parts)
    assert len(cad_groups) == len(report_groups) == 2

    result = calculate(load_project(root / "projects/machined-drawer")).result
    result["parts"] = parts
    result["cutting_groups"] = report_groups
    result["joints"] = []
    render_documents(tmp_path, result, panel_groups=cad_groups)
    with (tmp_path / "parts.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["part_code"] for row in rows] == ["P01", "P02"]
    assert [row["part_ids"] for row in rows] == [first_id, second_id]
    assert [row["operation_record_ids"] for row in rows] == [
        "user/single-pocket",
        "user/split-pocket-a, user/split-pocket-b",
    ]

    captured = {}

    def fake_visualize_assembly(*_args, output_dir, **kwargs):
        captured["viewer_data"] = kwargs["viewer_data"]
        html_path = Path(output_dir) / "generated.html"
        html_path.write_text(
            "<html>https://cdn.jsdelivr.net/npm/three@0.165.0/</html>",
            encoding="utf-8",
        )
        return {"html": str(html_path)}

    from cabineteer import visualize

    monkeypatch.setattr(
        "buratino.build.make_geometry", lambda _calculation: (assembly, {})
    )
    monkeypatch.setattr(visualize, "visualize_assembly", fake_visualize_assembly)
    monkeypatch.setattr("buratino.build.shutil.copy2", lambda *_args, **_kwargs: None)
    render_geometry(root, tmp_path, SimpleNamespace(result=result))
    assert captured["viewer_data"]["cutting_groups"] == report_groups

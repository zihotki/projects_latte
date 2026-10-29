from copy import deepcopy

from buratino.build import _space_operations_table
from buratino.engine import calculate
from buratino.grouping import group_cutting_blanks
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
        operation["type"]
        for part in machined
        for operation in part["operations"]
    }
    assert operation_types == {
        "pocket", "rabbet", "bevel", "bore", "mortise",
    }
    assert all(part["blank_mm"] == part["stock_mm"] for part in machined)
    assert all("finished_mm" not in part for part in machined)
    assert all(
        part["local_datum"] == {
            "origin": "unmachined_stock_min_xyz",
            "face_uv": "remaining_axes_ascending_xyz",
            "depth": "inward_from_selected_face",
        }
        for part in machined
    )

    table = _space_operations_table(result["parts"])
    assert "Resolved machining operations" in table
    assert "joint/side-to-back/a" in table
    assert "user/side-edge-bore" in table
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
        ("/part-a",), ("/part-b",),
    }
    assert all(
        group["grouping_scope"] == "cutting_blank_and_machining"
        for group in groups
    )

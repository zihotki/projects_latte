import asyncio
import json

import pytest
from cabineteer.part_grain import PartGrain, grain_direction_for_stock
from cabineteer.project import (
    CabinetProject,
    SpaceModelSpec,
    apply_project_patch,
    build_project,
    project_from_dict,
    project_to_dict,
)
from cabineteer.space_adapter import space_model_records
from cabineteer.spaces import Carcass, PhysicalPartPlan, ResolvedModel, Space


def _project(part_grain=()):
    return CabinetProject(
        name="grain-test",
        space_model=SpaceModelSpec(
            carcass=Carcass(
                width=300,
                height=400,
                depth=280,
                side_thickness=18,
                bottom_thickness=18,
                top_thickness=18,
                back_thickness=6,
            ),
            root=Space("root"),
        ),
        part_grain=part_grain,
    )


def test_part_grain_round_trip_and_resolved_unknown_none_and_axes():
    authored = (
        PartGrain("left-side", "/cabinet/carcass/side_left", "z"),
        PartGrain("top", "/cabinet/carcass/top", "x"),
        PartGrain("back", "/cabinet/carcass/back", "none"),
    )
    project = _project(authored)
    encoded = project_to_dict(project)
    restored = project_from_dict(encoded)
    assert project_to_dict(restored) == encoded

    parts = {
        part["id"]: part
        for part in restored.resolved_space_assembly().part_plan.parts
    }
    side = parts["/cabinet/carcass/side_left"]
    assert (side["grain_axis_local"], side["surface_normal_axis_local"],
            side["grain_status"]) == ("z", "x", "confirmed")
    assert parts["/cabinet/carcass/top"]["grain_axis_local"] == "x"
    assert parts["/cabinet/carcass/back"]["grain_axis_local"] is None
    assert parts["/cabinet/carcass/back"]["grain_status"] == "nondirectional"
    assert parts["/cabinet/carcass/bottom"]["grain_direction"] == "unknown"
    assert parts["/cabinet/carcass/bottom"]["grain_status"] == "unverified"


def test_update_replaces_and_clears_grain_block():
    encoded = project_to_dict(_project())
    replaced, changes = apply_project_patch(encoded, {
        "part_grain": [{
            "type": "PartGrain",
            "id": "top",
            "part_id": "/cabinet/carcass/top",
            "axis": "x",
        }],
    })
    assert changes == ["part_grain replaced"]
    assert build_project(replaced).part_grain == (
        PartGrain("top", "/cabinet/carcass/top", "x"),
    )
    cleared, changes = apply_project_patch(replaced, {"part_grain": None})
    assert changes == ["part_grain replaced"]
    assert "part_grain" not in cleared


def test_grain_intent_separates_same_blank_groups_and_records_csv_fields():
    project = _project((
        PartGrain("top", "/cabinet/carcass/top", "x"),
        PartGrain("bottom", "/cabinet/carcass/bottom", "y"),
        PartGrain("back", "/cabinet/carcass/back", "none"),
    ))
    records = space_model_records(project.resolved_space_assembly())
    parts = {part["id"]: part for part in records["parts"]}
    top = parts["/cabinet/carcass/top"]
    bottom = parts["/cabinet/carcass/bottom"]
    back = parts["/cabinet/carcass/back"]
    assert top["transform"]["axes"] == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert top["grain_axis_local"] == "x"
    assert top["grain_direction"] == "width"
    assert top["grain_status"] == "confirmed"
    assert bottom["grain_axis_local"] == "y"
    assert bottom["grain_direction"] == "length"
    assert back["grain_direction"] == "none"
    groups = records["viewer"]["cutting_groups"]
    top_group = next(group for group in groups if top["id"] in group["members"])
    bottom_group = next(group for group in groups if bottom["id"] in group["members"])
    assert top_group["id"] != bottom_group["id"]


def test_stock_local_grain_normalizes_to_reported_blank_axes_for_both_groupers():
    def part(part_id, dimensions, axis=None, direction="unknown", status="unverified"):
        return {
            "id": part_id,
            "kind": "panel",
            "role": part_id,
            "origin": [0, 0, 0],
            "size": list(dimensions),
            "bounds": [[0, 0, 0], list(dimensions)],
            "material": "maple",
            "thickness": dimensions[2],
            "stock": {
                "dimensions": list(dimensions),
                "thickness": dimensions[2],
                "thickness_axis": 2,
            },
            "profile": {"type": "box", "size": list(dimensions)},
            "transform": {
                "translation": [0, 0, 0],
                "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            },
            "operations": [],
            "grain_axis_local": axis,
            "grain_direction": direction,
            "grain_status": status,
        }

    source_parts = [
        part("long-x", (200, 100, 18), "x", "x", "confirmed"),
        part("rotated-y", (100, 200, 18), "y", "y", "confirmed"),
        part("short-x", (100, 200, 18), "x", "x", "confirmed"),
        part("square-x", (100, 100, 18), "x", "x", "confirmed"),
        part("square-y", (100, 100, 18), "y", "y", "confirmed"),
        part("none", (100, 100, 18), None, "none", "nondirectional"),
        part("unknown", (100, 100, 18)),
    ]
    assert grain_direction_for_stock(source_parts[0]) == "length"
    assert grain_direction_for_stock(source_parts[1]) == "length"
    assert grain_direction_for_stock(source_parts[2]) == "width"
    assert grain_direction_for_stock(source_parts[3]) == "length"
    assert grain_direction_for_stock(source_parts[4]) == "width"
    assert grain_direction_for_stock(source_parts[5]) == "none"
    assert grain_direction_for_stock(source_parts[6]) == "unknown"

    model = ResolvedModel(
        spaces=[], dividers=[], allowances=[], contents=[], fronts=[],
        part_plan=PhysicalPartPlan(source_parts), inputs={},
    )
    records = space_model_records(model)
    viewer_groups = records["viewer"]["cutting_groups"]
    compatible = next(group for group in viewer_groups if "long-x" in group["members"])
    assert compatible["members"] == ["long-x", "rotated-y"]
    assert compatible["grain_direction"] == "length"
    assert "grain_axis_local" not in compatible
    assert len(viewer_groups) == 6

    from buratino.grouping import group_cutting_blanks

    cutlist_parts = [
        {**item, "blank_mm": dict(item["stock_mm"])} for item in records["parts"]
    ]
    cutlist_groups = group_cutting_blanks(cutlist_parts)
    compatible = next(group for group in cutlist_groups if "long-x" in group["members"])
    assert compatible["members"] == ["long-x", "rotated-y"]
    assert compatible["grain_direction"] == "length"
    assert len(cutlist_groups) == 6


@pytest.mark.parametrize("records, message", [
    ((PartGrain("bad", "/missing/part", "x"),), "unknown resolved Space part"),
    ((PartGrain("thickness", "/cabinet/carcass/top", "z"),), "thickness axis"),
    ((PartGrain("same", "/cabinet/carcass/top", "x"),
      PartGrain("same", "/cabinet/carcass/bottom", "y")), "duplicate part grain id"),
    ((PartGrain("top", "/cabinet/carcass/top", "x"),
      PartGrain("top-again", "/cabinet/carcass/top", "y")), "duplicate part grain for"),
])
def test_resolver_rejects_bad_grain_references(records, message):
    with pytest.raises(ValueError, match=message):
        _project(records).resolved_space_assembly()


def test_design_update_load_and_recompute_keep_grain_metadata(tmp_path, monkeypatch):
    from cabineteer import project as project_module
    from cabineteer import server

    monkeypatch.setattr(project_module, "project_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr(server, "data_dir", lambda: tmp_path)

    def call(handler, args):
        loop = asyncio.new_event_loop()
        try:
            return json.loads(loop.run_until_complete(handler(args))[0].text)
        finally:
            loop.close()

    designed = call(server._tool_design_project, project_to_dict(_project()))
    updated = call(server._tool_update_project, {
        "name": "grain-test",
        "part_grain": [{
            "type": "PartGrain",
            "id": "top",
            "part_id": "/cabinet/carcass/top",
            "axis": "x",
        }],
    })
    assert designed["project"]["name"] == "grain-test"
    assert updated["changes"] == ["part_grain replaced"]
    top = next(
        part for part in updated["records"]["parts"]
        if part["id"] == "/cabinet/carcass/top"
    )
    assert top["grain_axis_local"] == "x"
    loaded = call(server._tool_load_project, {"name": "grain-test"})
    assert loaded["project"]["part_grain"][0]["axis"] == "x"

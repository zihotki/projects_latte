import pytest

from buratino.engine import calculate, make_geometry
from buratino.project import InputError, load_project


def test_upper_drawer_uses_380_runner_and_one_front(root):
    calculation = calculate(load_project(root / "projects/real-assembly"))
    result = calculation.result
    drawer = next(
        d
        for d in result["drawers"]
        if d["instance_id"] == "upper.left.column-0.opening-0"
    )
    assert drawer["box_mm"] == {"width": 325, "height": 140, "depth": 380}
    cfg = next(
        i["config"]
        for i in calculation.drawer_instances
        if i["drawer_id"] == drawer["instance_id"]
    )
    assert cfg.box_inside_width == 293
    assert cfg.side_gap == 4
    assert len(drawer["part_ids"]) == 6
    assert (
        len(
            [
                p
                for p in result["parts"]
                if p.get("instance_id") == drawer["instance_id"]
            ]
        )
        == 6
    )
    runner = next(h for h in result["hardware"] if h.get("length_mm") == 380)
    assert runner["quantity_by_part_number"] == {"9047682": 1, "9047683": 1}
    grouped = {
        member for group in result["cutting_groups"] for member in group["members"]
    }
    assert set(drawer["part_ids"]) <= grouped
    assembly, geometry = make_geometry(calculation)
    assert len(geometry) == len(result["parts"])
    for part in result["parts"]:
        if part.get("instance_id") == drawer["instance_id"]:
            assert part["role"] in assembly.objects


def test_upper_drawer_rejects_box_above_low_roof(root):
    project = load_project(root / "projects/real-assembly")
    project.variables["upper"]["drawer_box_height_mm"] = 300
    with pytest.raises(InputError, match="fit the opening"):
        calculate(project)

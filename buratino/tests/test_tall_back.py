"""A tall applied back remains one panel in a resolved assembly."""

from dataclasses import replace
from pathlib import Path
from runpy import run_path

import pytest
from cabineteer.project import project_from_dict, project_to_dict
from cabineteer.spaces import Carcass, Space, resolve_model


def test_bench_is_two_units_with_tall_back_panels():
    path = Path(__file__).parents[1] / "projects/osb-bench/project.py"
    project = run_path(str(path))["project"]
    restored = project_from_dict(project_to_dict(project))
    plan = restored.resolved_space_assembly()
    parts = plan.part_plan.parts
    back = [part for part in parts if part["id"].endswith("/carcass/back")]
    assert len(back) == 2
    assert all(part["stock"]["dimensions"] == [1190, 18, 590] for part in back)
    assert [part["bounds"] for part in back] == [
        [[0, 482, 70], [1190, 500, 660]],
        [[1190, 482, 70], [2380, 500, 660]],
    ]
    assert plan.occupied_bounds["max_z"] == 660
    assert not any("backrest" in part["id"] for part in parts)
    sides = [part for part in parts if "/carcass/side_" in part["id"]]
    dividers = [part for part in parts if "/divider-" in part["id"]]
    assert len(sides) == 4 and len(dividers) == 4
    assert all(
        part["stock"]["dimensions"] == [18, 482, 304] for part in sides + dividers
    )
    assert plan.structural_bounds["max_z"] == 410
    for name in ("top", "bottom"):
        panels = [part for part in parts if part["id"].endswith(f"/carcass/{name}")]
        assert len(panels) == 2
        assert all(panel["stock"]["dimensions"] == [1190, 482, 18] for panel in panels)
    sections = [space for space in plan.spaces if "/section-" in space["id"]]
    assert sorted(space["size"][0] for space in sections) == [
        372,
        372,
        373,
        373,
        373,
        373,
    ]


def test_back_height_cannot_be_shorter_than_carcass():
    carcass = Carcass(600, 330, 500, back_height=329)
    with pytest.raises(ValueError, match="back_height"):
        resolve_model(carcass, Space("root"))
    assert resolve_model(replace(carcass, back_height=None), Space("root"))

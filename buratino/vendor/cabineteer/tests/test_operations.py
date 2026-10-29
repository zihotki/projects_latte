import pytest

from cabineteer.operations import (
    Bevel,
    Bore,
    DominoJoint,
    Mortise,
    Pocket,
    Rabbet,
    resolve_operations,
)
from cabineteer.project import (
    CabinetProject,
    SpaceModelSpec,
    build_project,
    project_from_dict,
    project_to_dict,
)
from cabineteer.spaces import Carcass, Space


def part(name, origin, size):
    return dict(
        id=name,
        profile=dict(type="box", size=size),
        transform=dict(translation=origin, axes=[[1, 0, 0], [0, 1, 0], [0, 0, 1]]),
    )


def test_operations_validate_footprints_and_opposite_faces():
    parts = [part("/a", [0, 0, 0], [20, 100, 100])]
    records = resolve_operations(
        parts,
        [
            Bore("one", "/a", "x+", 50, 50, 10, 8),
            Pocket("two", "/a", "x-", 0, 0, 10, 20, 5),
        ],
        [],
    )
    assert [(r["id"], r["face"]) for r in records] == [
        ("user/one", "x+"),
        ("user/two", "x-"),
    ]
    with pytest.raises(ValueError, match="exceeds stock"):
        resolve_operations(parts, [Bore("bad", "/a", "x+", 2, 50, 10, 8)], [])
    with pytest.raises(ValueError, match="unknown part"):
        resolve_operations(parts, [Bore("bad", "/missing", "x+", 50, 50, 10, 8)], [])


def test_joint_resolves_one_centre_to_both_parts():
    parts = [
        part("/a", [0, 0, 0], [20, 100, 100]),
        part("/b", [20, 0, 0], [20, 100, 100]),
    ]
    joint = DominoJoint(
        "joint", "/a", "x+", "/b", "x-", (20, 50, 50), "y", 30, 8, 10, 12
    )
    a, b = resolve_operations(parts, [], [joint])
    assert (a["u"], a["v"], a["axis"], a["depth"]) == (50, 50, "u", 10)
    assert (b["u"], b["v"], b["axis"], b["depth"]) == (50, 50, "u", 12)
    assert a["joint_id"] == b["joint_id"] == "joint"
    with pytest.raises(ValueError, match="not on both faces"):
        resolve_operations(
            parts,
            [],
            [
                DominoJoint(
                    "bad", "/a", "x+", "/b", "x-", (19, 50, 50), "y", 30, 8, 10, 12
                )
            ],
        )


def test_edge_and_mortise_bounds_and_duplicate_ids():
    parts = [part("/a", [0, 0, 0], [20, 100, 100])]
    cuts = [
        Rabbet("r", "/a", "x+", "y-", 0, 100, 5, 4),
        Bevel("v", "/a", "x+", "z+", 10, 50, 5, 4),
        Mortise("m", "/a", "x+", 50, 50, "v", 30, 8, 10),
    ]
    assert [r["type"] for r in resolve_operations(parts, cuts, [])] == [
        "mortise",
        "rabbet",
        "bevel",
    ]
    with pytest.raises(ValueError, match="adjacent"):
        resolve_operations(parts, [Rabbet("r", "/a", "x+", "x-", 0, 10, 5, 4)], [])
    with pytest.raises(ValueError, match="duplicate"):
        resolve_operations(parts, [cuts[0], cuts[0]], [])
    with pytest.raises(ValueError, match="dimensions"):
        resolve_operations(parts, [Mortise("m", "/a", "x+", 50, 50, "v", 4, 8, 10)], [])


def test_project_round_trip_and_resolves_updated_operations():
    project = CabinetProject(
        "test",
        space_model=SpaceModelSpec(Carcass(600, 700, 500), Space("root")),
        operations=(Bore("hole", "/cabinet/carcass/side_left", "x-", 50, 50, 8, 5),),
    )
    restored = project_from_dict(project_to_dict(project))
    assert restored.operations == project.operations
    records = restored.resolved_space_model().part_plan.parts[0]["operations"]
    assert records[0]["diameter"] == 8
    payload = project_to_dict(project)
    payload["operations"][0]["diameter"] = 12
    assert (
        build_project(payload)
        .resolved_space_model()
        .part_plan.parts[0]["operations"][0]["diameter"]
        == 12
    )
    with pytest.raises(ValueError, match="Space project"):
        CabinetProject("bad", operations=project.operations)

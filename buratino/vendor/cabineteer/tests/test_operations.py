import pytest
import asyncio
from dataclasses import replace

from cabineteer.operations import (
    Bevel,
    Bore,
    DominoJoint,
    Groove,
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
from cabineteer.server import list_tools


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
        Rabbet("r", "/a", "x+", "y-", 5, 4, start=0, length=100),
        Bevel("v", "/a", "x+", "z+", 5, 4, start=10, length=50),
        Mortise("m", "/a", "x+", 50, 50, "v", 30, 8, 10),
    ]
    assert [r["type"] for r in resolve_operations(parts, cuts, [])] == [
        "mortise",
        "rabbet",
        "bevel",
    ]
    with pytest.raises(ValueError, match="adjacent"):
        resolve_operations(parts, [Rabbet("r", "/a", "x+", "x-", 5, 4, length=10)], [])
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


def test_validation_errors_identify_input_part_and_field():
    parts = [
        part("/a", [0, 0, 0], [20, 100, 100]),
        part("/b", [20, 0, 0], [20, 100, 100]),
    ]
    with pytest.raises(ValueError, match=r"user cut1 part /a: depth:"):
        resolve_operations(parts, [Pocket("cut1", "/a", "x-", 0, 0, 1, 1, -1)], [])
    with pytest.raises(ValueError, match=r"user cut2 part /a: face:"):
        resolve_operations(parts, [Bore("cut2", "/a", "bad", 50, 50, 8, 5)], [])
    with pytest.raises(ValueError, match=r"joint joint1 part /a: depth_a:"):
        resolve_operations(
            parts,
            [],
            [
                DominoJoint(
                    "joint1", "/a", "x+", "/b", "x-", (20, 50, 50), "y", 30, 8, -1, 10
                )
            ],
        )
    with pytest.raises(ValueError, match=r"joint joint2 part /b face_b:"):
        resolve_operations(
            parts,
            [],
            [
                DominoJoint(
                    "joint2", "/a", "x+", "/b", "bad", (20, 50, 50), "y", 30, 8, 10, 10
                )
            ],
        )


def test_mcp_schemas_expose_all_tagged_inputs_and_fields():
    tools = {
        tool.name: tool.input_schema
        for tool in asyncio.get_event_loop().run_until_complete(list_tools())
    }
    for name in ("design_project", "update_project"):
        props = tools[name]["properties"]
        operations = props["operations"]["items"]["oneOf"]
        assert {item["properties"]["type"]["enum"][0] for item in operations} == {
            "Pocket",
            "Rabbet",
            "Bevel",
            "Groove",
            "Bore",
            "Mortise",
        }
        for item in operations:
            tag = item["properties"]["type"]["enum"][0]
            optional = (
                {"start", "length"} if tag in {"Rabbet", "Bevel", "Groove"} else set()
            )
            assert set(item["required"]) == set(item["properties"]) - optional
            assert item["additionalProperties"] is False
        joint = props["joints"]["items"]["oneOf"][0]
        assert joint["properties"]["type"]["enum"] == ["DominoJoint"]
        assert set(joint["required"]) == set(joint["properties"])
        assert (
            joint["properties"]["centre"]["minItems"]
            == joint["properties"]["centre"]["maxItems"]
            == 3
        )


def test_edge_spans_follow_current_stock_and_validate_bounds():
    parts = [part("/a", [0, 0, 0], [20, 100, 100])]
    cuts = [
        Rabbet("r", "/a", "x+", "z-", 5, 4, start=12),
        Bevel("b", "/a", "x+", "z+", 5, 4, start=20),
    ]
    records = resolve_operations(parts, cuts, [])
    assert [(r["start"], r["length"]) for r in records] == [(20, 80), (12, 88)]
    assert cuts[0].length is None
    resized = part("/a", [0, 0, 0], [20, 120, 100])
    assert resolve_operations([resized], [cuts[0]], [])[0]["length"] == 108
    with pytest.raises(ValueError, match="length must be positive"):
        resolve_operations(
            parts, [Rabbet("zero", "/a", "x+", "z-", 5, 4, start=100)], []
        )
    with pytest.raises(ValueError, match="exceeds stock"):
        resolve_operations(
            parts, [Bevel("overrun", "/a", "x+", "z+", 5, 4, start=80, length=21)], []
        )


@pytest.mark.parametrize(
    "face,edge,offset,expected",
    [
        ("x+", "z-", 20, ("pocket", 0, 20, 100, 6, 100)),
        ("x+", "z+", 20, ("pocket", 0, 74, 100, 6, 100)),
        ("x-", "y-", 20, ("pocket", 20, 0, 6, 100, 100)),
        ("y-", "x+", 5, ("pocket", 9, 0, 6, 100, 100)),
        ("y+", "x-", 5, ("pocket", 5, 0, 6, 100, 100)),
        ("z+", "x+", 5, ("pocket", 9, 0, 6, 100, 100)),
        ("z-", "y+", 5, ("pocket", 0, 89, 20, 6, 20)),
    ],
)
def test_groove_resolves_to_pocket_at_named_edge(face, edge, offset, expected):
    parts = [part("/a", [0, 0, 0], [20, 100, 100])]
    groove = Groove("g", "/a", face, edge, offset, 6, 3)
    record = resolve_operations(parts, [groove], [])[0]
    assert record["type"] == expected[0]
    assert (
        record["u"],
        record["v"],
        record["size_u"],
        record["size_v"],
        record["groove"]["length"],
    ) == expected[1:]
    assert record["groove"]["edge"] == edge
    assert record["groove"]["offset"] == offset


def test_project_round_trip_preserves_automatic_edge_intent_and_groove_schema():
    project = CabinetProject(
        "edge-cuts",
        space_model=SpaceModelSpec(Carcass(600, 700, 500), Space("root")),
        operations=(
            Rabbet("r", "/cabinet/carcass/side_left", "x+", "z-", 6, 3),
            Groove("g", "/cabinet/carcass/side_left", "x+", "z-", 320, 6, 2),
        ),
    )
    payload = project_to_dict(project)
    assert payload["operations"][0]["length"] is None
    restored = project_from_dict(payload)
    assert restored.operations == project.operations
    original_parts = restored.resolved_space_model().part_plan.parts
    side = next(
        part for part in original_parts if part["id"] == "/cabinet/carcass/side_left"
    )
    original_span = next(
        op["length"] for op in side["operations"] if op["type"] == "rabbet"
    )
    resized = replace(
        restored,
        space_model=replace(
            restored.space_model,
            carcass=replace(restored.space_model.carcass, depth=600),
        ),
    )
    resized_side = next(
        part
        for part in resized.resolved_space_model().part_plan.parts
        if part["id"] == "/cabinet/carcass/side_left"
    )
    resized_span = next(
        op["length"] for op in resized_side["operations"] if op["type"] == "rabbet"
    )
    assert resized_span == original_span + 100
    tool_schemas = {
        tool.name: tool.input_schema
        for tool in asyncio.get_event_loop().run_until_complete(list_tools())
    }
    groove_schema = next(
        item
        for item in tool_schemas["design_project"]["properties"]["operations"]["items"][
            "oneOf"
        ]
        if item["properties"]["type"]["enum"] == ["Groove"]
    )
    assert (
        "start" not in groove_schema["required"]
        and "length" not in groove_schema["required"]
    )


@pytest.mark.parametrize(
    "operation",
    [
        Rabbet("bad", "/a", "x+", "z-", 5, 3, start="bad"),
        Bevel("bad", "/a", "x+", "z-", 5, 3, start=float("nan")),
        Groove("bad", "/a", "x+", "z-", "bad", 5, 3),
    ],
)
def test_invalid_edge_fields_are_rejected_before_span_math(operation):
    with pytest.raises(ValueError):
        resolve_operations([part("/a", [0, 0, 0], [20, 100, 100])], [operation], [])


def test_nonbox_edge_cuts_are_rejected_before_dimension_access():
    profile = part("/a", [0, 0, 0], [20, 100, 100])
    profile["profile"]["type"] = "profiled"
    with pytest.raises(ValueError, match="only box profiles"):
        resolve_operations([profile], [Groove("g", "/a", "x+", "z-", 20, 6, 3)], [])


def test_stopped_mortise_length_cannot_be_null():
    with pytest.raises(ValueError, match="length: expected positive"):
        resolve_operations(
            [part("/a", [0, 0, 0], [20, 100, 100])],
            [Mortise("m", "/a", "x+", 50, 50, "u", None, 8, 5)],
            [],
        )


def test_domino_row_uses_translated_contact_overlap():
    from cabineteer.operations import DominoRow

    parts = [
        part("/a", [100, 200, 300], [18, 100, 200]),
        part("/b", [118, 220, 330], [80, 60, 140]),
    ]
    row = DominoRow("row", "/a", "x+", "/b", "x-", (20, 40), "y", 20, 6, 12, 28)
    cuts = resolve_operations(parts, [], [row])
    assert [(op["joint_id"], op["part_id"], op["u"], op["v"]) for op in cuts] == [
        ("row-20", "/a", 40, 100), ("row-40", "/a", 60, 100),
        ("row-20", "/b", 20, 70), ("row-40", "/b", 40, 70),
    ]
    # Expansion reuses the same two-mortise resolver as explicit world centres.
    explicit = [replace(DominoJoint("row", "/a", "x+", "/b", "x-",
                                    (118, 240, 400), "y", 20, 6, 12, 28),
                        id=f"row-{offset}", centre=(118, 220 + offset, 400))
                for offset in (20, 40)]
    assert cuts == resolve_operations(parts, [], explicit)


@pytest.mark.parametrize("change", [
    {"face_b": "x+"}, {"axis": "x"}, {"positions": ()},
    {"positions": (float("nan"),)}, {"positions": (-1,)},
    {"positions": (61,)}, {"positions": (0,)}, {"positions": (20, 20)},
    {"length": 80},
])
def test_domino_row_rejects_invalid_pattern_or_slot(change):
    from cabineteer.operations import DominoRow

    parts = [part("/a", [0, 0, 0], [18, 100, 200]),
             part("/b", [18, 20, 30], [80, 60, 140])]
    row = DominoRow("row", "/a", "x+", "/b", "x-", (20,), "y", 20, 6, 12, 28)
    with pytest.raises(ValueError):
        resolve_operations(parts, [], [replace(row, **change)])


@pytest.mark.parametrize("origin", [[19, 20, 30], [18, 120, 30]])
def test_domino_row_requires_coincident_overlapping_faces(origin):
    from cabineteer.operations import DominoRow

    parts = [part("/a", [0, 0, 0], [18, 100, 200]),
             part("/b", origin, [80, 60, 140])]
    row = DominoRow("row", "/a", "x+", "/b", "x-", (20,), "y", 20, 6, 12, 28)
    with pytest.raises(ValueError, match="coincident|overlap"):
        resolve_operations(parts, [], [row])


def test_domino_row_project_and_schema_round_trip():
    from cabineteer.operations import DominoRow
    from cabineteer.server import _machining_schema

    row = DominoRow("row", "/cabinet/carcass/side_left", "x+", "/cabinet/carcass/top", "x-",
                    (70, 480), "y", 20, 6, 12, 28)
    project = CabinetProject(name="row", space_model=SpaceModelSpec(
        Carcass(1048, 679, 572, back_thickness=18), Space("root")), joints=(row,))
    encoded = project_to_dict(project)
    assert project_to_dict(project_from_dict(encoded)) == encoded
    assert len(project_from_dict(encoded).resolved_space_model().part_plan.parts) == 5
    schemas = {item["properties"]["type"]["enum"][0]: item
               for item in _machining_schema(joints=True)["items"]["oneOf"]}
    assert schemas["DominoRow"]["properties"]["positions"]["uniqueItems"] is True
    assert set(schemas["DominoRow"]["required"]) == set(schemas["DominoRow"]["properties"])

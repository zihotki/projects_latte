from buratino.engine import calculate
from buratino.project import load_project


def test_upper_door_hinges_are_draft_and_manufacturer_backed(root):
    result = calculate(load_project(root / "projects/real-assembly")).result

    hinge = next(
        item for item in result["hardware"] if item["type"] == "concealed_door_hinge"
    )
    assert hinge["manufacturer"] == "Hettich"
    assert hinge["model"] == "Sensys 8645i"
    assert hinge["nominal_opening_angle_deg"] == 110
    assert hinge["soft_close"] == "integrated Silent System"
    assert hinge["supported_front_thickness_mm"] == [15, 22]
    assert hinge["project_front_thickness_mm"] == 18
    assert hinge["draft_shared_gap_mm"] == 3
    assert hinge["minimum_shared_gap_mm"] == 2
    assert "quantity" not in hinge

    doors = {door["door_id"]: door for door in hinge["doors"]}
    assert set(doors) == {
        "upper.left.section-2.door",
        "upper.right.section-1.door",
        "upper.right.section-2.door",
    }
    assert doors["upper.left.section-2.door"]["application"] == "full_overlay"
    assert doors["upper.right.section-1.door"]["application"] == "half_overlay"
    assert doors["upper.right.section-2.door"]["application"] == "full_overlay"
    assert doors["upper.left.section-2.door"]["carcass_mount"] == (
        "double carcass side at x=720 mm"
    )
    assert doors["upper.right.section-1.door"]["carcass_mount"] == (
        "shared divider at x=1071..1089 mm"
    )
    assert doors["upper.right.section-2.door"]["carcass_mount"] == (
        "outer carcass side at x=1440 mm"
    )
    for door in doors.values():
        assert door["hinge_edge"] == "right"
        assert door["hinge_count"] is None
        assert door["door_weight_kg"] is None
        assert door["mounting_plate"] is None
        assert door["cup_distance_mm"] is None
        assert door["vertical_hinge_positions_mm"] is None

    assert hinge["actual_opening_travel_deg"] is None
    assert hinge["edge_treatment"].endswith("unverified")
    assert "upper.door_hinges_unverified" in {
        issue["code"] for issue in result["checks"]
    }
    assert result["manufacturing_ready"] is False

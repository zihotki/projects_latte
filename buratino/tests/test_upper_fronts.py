import math

import pytest

from buratino.project import load_project
from buratino.upper import add_upper_geometry, make_upper_parts
from buratino.upper_fronts import make_upper_front_parts


def test_front_profiles_clear_roof_perimeter_and_seams(root):
    spec = load_project(root / "projects/real-assembly").variables["upper"]
    parts = make_upper_front_parts(spec)
    assert len(parts) == 4
    assert [p["component"] for p in parts] == ["face", "door", "door", "door"]
    assert parts[0]["instance_id"] == "upper.left.column-0.opening-0"
    assert all(
        p["hinge_side"] == "right" and p["hinge_status"] == "unverified"
        for p in parts[1:]
    )
    joint_x = spec["x"] + 1.5 * spec["cabinet_width_mm"] - spec["thickness_mm"] / 2
    slope = (spec["right_height_mm"] - spec["left_height_mm"]) / (joint_x - spec["x"])
    gap = spec["front_gap_mm"]
    drop = gap * math.hypot(1, slope)
    assert parts[0]["position_mm"]["x"] == pytest.approx(spec["x"] + gap)
    assert parts[-1]["position_mm"]["x"] + parts[-1]["size_mm"]["x"] == pytest.approx(
        spec["x"] + 2 * spec["cabinet_width_mm"] - gap
    )
    for a, b in zip(parts, parts[1:], strict=False):
        assert b["position_mm"]["x"] - (
            a["position_mm"]["x"] + a["size_mm"]["x"]
        ) == pytest.approx(gap)
    right_of_seam = parts[3]["position_mm"]["x"] - gap / 2
    left_of_seam = parts[2]["position_mm"]["x"] + parts[2]["size_mm"]["x"] + gap / 2
    assert (left_of_seam + right_of_seam) / 2 == pytest.approx(
        spec["x"] + 1.5 * spec["cabinet_width_mm"]
    )
    for part in parts:
        pos = part["position_mm"]
        assert pos["z"] == pytest.approx(spec["z"] - spec["front_bottom_projection_mm"])
        assert pos["y"] + part["size_mm"]["y"] == pytest.approx(spec["y"] - gap)
        for px, pz in part["profile"]["points_mm"][2:]:
            x, z = pos["x"] + px, pos["z"] + pz
            slope_roof = spec["z"] + spec["left_height_mm"] + slope * (x - spec["x"])
            flat_top = (
                spec["z"]
                + spec["left_height_mm"]
                + slope * (1.5 * spec["cabinet_width_mm"])
                - drop
            )
            assert z == pytest.approx(min(slope_roof - drop, flat_top))
        assert part["blank_mm"]["length"] == pytest.approx(part["size_mm"]["z"])
        assert part["blank_mm"]["width"] == pytest.approx(part["size_mm"]["x"])


def test_front_solids_are_valid_and_clear_carcass(root):
    import cadquery as cq

    spec = load_project(root / "projects/real-assembly").variables["upper"]
    fronts = make_upper_front_parts(spec)
    carcass, _ = make_upper_parts(spec)
    assembly = cq.Assembly()
    geometry = add_upper_geometry(assembly, fronts + carcass)
    assert len(geometry) == len(fronts) + len(carcass)
    for part in fronts:
        solid = assembly.objects[part["role"]].toCompound()
        assert solid.isValid() and solid.Volume() > 0
        assert solid.BoundingBox().ymax == pytest.approx(
            spec["y"] - spec["front_gap_mm"]
        )
        for other in fronts + carcass:
            if other is not part:
                assert (
                    solid.intersect(
                        assembly.objects[other["role"]].toCompound()
                    ).Volume()
                    <= 1e-5
                )


@pytest.mark.parametrize("gap", [2, 3])
def test_front_edges_overlay_their_supporting_panels(root, gap):
    spec = dict(load_project(root / "projects/real-assembly").variables["upper"])
    spec["front_gap_mm"] = gap
    fronts = make_upper_front_parts(spec)
    x = spec["x"]
    width = spec["cabinet_width_mm"]
    stock = spec["thickness_mm"]
    edges = [
        (p["position_mm"]["x"], p["position_mm"]["x"] + p["size_mm"]["x"])
        for p in fronts
    ]

    assert edges[0][1] - (x + width / 2 - stock / 2) == pytest.approx((stock - gap) / 2)
    assert (x + width / 2 + stock / 2) - edges[1][0] == pytest.approx((stock - gap) / 2)
    assert edges[1][1] - (x + width - stock) == pytest.approx(stock - gap / 2)
    assert (x + width + stock) - edges[2][0] == pytest.approx(stock - gap / 2)
    seam_center = x + 1.5 * width
    assert edges[2][1] - (seam_center - stock / 2) == pytest.approx((stock - gap) / 2)
    assert (seam_center + stock / 2) - edges[3][0] == pytest.approx((stock - gap) / 2)
    assert edges[3][1] - (x + 2 * width - stock) == pytest.approx(stock - gap)


def test_last_doors_have_simple_tops_aligned_at_seam(root):
    spec = load_project(root / "projects/real-assembly").variables["upper"]
    sloped, flat = make_upper_front_parts(spec)[-2:]
    assert len(sloped["profile"]["points_mm"]) == 4
    assert len(flat["profile"]["points_mm"]) == 4
    slope = (spec["right_height_mm"] - spec["left_height_mm"]) / (
        1.5 * spec["cabinet_width_mm"] - spec["thickness_mm"] / 2
    )
    sloped_top_right = sloped["position_mm"]["z"] + sloped["profile"]["points_mm"][2][1]
    flat_top = flat["position_mm"]["z"] + flat["profile"]["points_mm"][2][1]
    assert flat_top - sloped_top_right == pytest.approx(
        slope * spec["front_gap_mm"] / 2
    )


@pytest.mark.parametrize(
    "change",
    [
        {"front_gap_mm": 0},
        {"front_gap_mm": float("nan")},
        {"front_bottom_projection_mm": -1},
        {"front_thickness_mm": -1},
        {"left_height_mm": 1},
        {"cabinet_width_mm": 2},
    ],
)
def test_fronts_reject_invalid_dimensions(root, change):
    spec = dict(load_project(root / "projects/real-assembly").variables["upper"])
    spec.update(change)
    with pytest.raises(ValueError):
        make_upper_front_parts(spec)

"""Native recipes cut existing panels without changing stock or placement."""

from dataclasses import asdict, replace
from pathlib import Path
import math
import runpy

import pytest

from cabineteer.joinery import DominoJoinery
from cabineteer.native_joinery import apply_native_joinery
from cabineteer.project import project_from_dict, project_to_dict
from cabineteer.profiles import (
    ProfilePart,
    profile_spec_from_dict,
    profile_spec_to_dict,
)


@pytest.fixture(scope="module")
def models():
    root = Path(__file__).resolve().parents[3]
    project = runpy.run_path(str(root / "projects/attic-clothing-storage/project.py"))[
        "project"
    ]
    machined = project.resolved_assembly()
    plain = replace(
        project,
        profile_assembly=replace(
            project.profile_assembly, joinery=None, corner_joinery=None
        ),
    ).resolved_assembly()
    return project, machined, plain


def test_real_recipe_has_safe_owned_pairs(models):
    _, machined, plain = models
    assert len(machined.parts) == len(plain.parts) == 91
    assert len(machined.joints) == 136
    assert machined.layout == plain.layout
    assert machined.part_grain == plain.part_grain
    assert machined.joinery_checks[0]["code"] == "joinery.sloped_cap_unverified"
    pairs = {frozenset(j["parts"]) for j in machined.joints}
    assert frozenset(("upper.bottom", "upper.divider.1")) in pairs
    assert frozenset(("upper.roof.cap.level", "upper.divider.3")) in pairs
    assert not any("upper.roof.cap.slope" in pair for pair in pairs)
    for part in machined.parts:
        original = next(p for p in plain.parts if p.id == part.id)
        assert part.stock_mm == original.stock_mm
        assert part.local_frame == original.local_frame
        assert part.local_profile_mm == original.local_profile_mm
        assert part.local_extrusion_mm == original.local_extrusion_mm
        assert type(part) is type(original)
        cuts = [op for op in part.operations if getattr(op, "type", "") == "mortise"]
        if part.component in {
            "back",
            "adjustable_shelf",
            "door",
            "drawer_front",
        } or part.owner.startswith("frame."):
            assert cuts == []
        if cuts:
            # Exact capsule area times depth proves that these are solid cuts.
            volume = sum(
                ((cut.length - cut.width) * cut.width + math.pi * (cut.width / 2) ** 2)
                * cut.depth
                for cut in cuts
            )
            assert (
                original.solid().val().Volume() - part.solid().val().Volume()
                == pytest.approx(volume, abs=0.01)
            )
        if isinstance(part, ProfilePart):
            assert part.profile_xz_mm == original.profile_xz_mm


def test_each_pair_has_matching_world_centers_and_blind_depths(models):
    _, machined, _ = models
    parts = {p.id: p for p in machined.parts}
    for joint in machined.joints:
        assert len(joint["mortises"]) == 2
        assert sorted(m["depth_mm"] for m in joint["mortises"]) == [12, 28]
        for member in joint["mortises"]:
            part = parts[member["part_id"]]
            cut = next(
                op
                for op in part.operations
                if getattr(op, "id", None) == member["operation_id"]
            )
            assert (cut.length, cut.width) == (20, 6)
            normal = "xyz".index(cut.face[0])
            uv = [i for i in range(3) if i != normal]
            local = [0.0, 0.0, 0.0]
            local[normal] = part.stock_mm[normal] if cut.face[1] == "+" else 0
            local[uv[0]], local[uv[1]] = cut.u, cut.v
            axes = [
                getattr(part.local_frame, key)
                for key in ("length_axis", "width_axis", "thickness_axis")
            ]
            world = tuple(
                part.local_frame.origin_mm[i]
                + sum(local[j] * axes[j][i] for j in range(3))
                for i in range(3)
            )
            assert world == pytest.approx(joint["center_mm"], abs=1e-5)
            assert cut.depth < part.stock_mm[normal]
            assert "world_center_mm" not in asdict(cut)


def test_recipe_round_trip_and_validation(models):
    project, _, _ = models
    assert (
        project_from_dict(project_to_dict(project)).profile_assembly
        == project.profile_assembly
    )
    assert (
        profile_spec_from_dict(profile_spec_to_dict(project.profile_assembly))
        == project.profile_assembly
    )
    with pytest.raises(ValueError, match="profile_assembly.joinery"):
        replace(project.profile_assembly, joinery="domino")
    # A 16 mm drawer wall must retain a blind outer wall.
    with pytest.raises(ValueError, match="blind mortise depth"):
        replace(
            project,
            profile_assembly=replace(
                project.profile_assembly, corner_joinery=DominoJoinery(face_depth=16)
            ),
        ).resolved_assembly()


def test_machined_profile_can_be_placed_again(models):
    _, machined, _ = models
    part = next(p for p in machined.parts if p.id == "upper.bottom")
    offset = tuple(
        value + delta for value, delta in zip(part.world_offset_mm, (10, 20, 30))
    )
    moved = part.placed(offset)
    assert moved.solid().val().Volume() == pytest.approx(part.solid().val().Volume())
    before, after = part.solid().val().BoundingBox(), moved.solid().val().BoundingBox()
    assert (
        after.xmin - before.xmin,
        after.ymin - before.ymin,
        after.zmin - before.zmin,
    ) == pytest.approx((10, 20, 30))
    assert tuple(
        b - a for a, b in zip(part.local_frame.origin_mm, moved.local_frame.origin_mm)
    ) == pytest.approx((10, 20, 30))


def test_stock_box_contact_cannot_cut_outside_actual_profile(models):
    project, _, plain = models
    wall = ProfilePart(
        "wall",
        "upper",
        "side_left",
        "board",
        ((0, 0), (18, 0), (18, 40), (0, 20)),
        0,
        100,
        (40, 100, 18),
        orientation="side",
    )
    cap = ProfilePart(
        "cap",
        "roof",
        "cap",
        "board",
        ((0, 40), (18, 40), (18, 58), (0, 58)),
        0,
        100,
        (18, 100, 18),
        orientation="bottom",
    )
    with pytest.raises(ValueError, match="does not fit the finished profile"):
        apply_native_joinery(
            replace(plain, parts=(wall, cap)), project.profile_assembly
        )

"""Native profile geometry and contact checks."""

import math

import pytest
from cabineteer.layout import Frame
from cabineteer.profiles import (
    ProfiledBox,
    RoofProfile,
    box_parts,
    frame_parts,
    roof_parts,
)


@pytest.mark.parametrize(
    ("points", "width", "names"),
    [
        (((0, 300), (720, 600)), 360, ("slope",)),
        (((0, 300), (360, 600), (720, 600)), 360, ("slope", "level")),
        (((0, 235), (1071, 1204), (1440, 1204)), 720, ("slope", "level")),
    ],
)
def test_caps_and_boxes_share_contact_without_overlap(points, width, names):
    roof = RoofProfile(points, 18)
    caps = roof_parts(roof, 414, "roof", names, "plywood")
    boxes = [
        ProfiledBox(f"upper.{name}", x, width, 420, 18, 18, 6)
        for name, x in (("left", 0), ("right", width))
    ]
    parts = [part for box in boxes for part in box_parts(box, roof)]
    assert len(parts) == 8
    for cap in caps:
        for part in parts:
            assert cap.solid().intersect(part.solid()).val().Volume() == pytest.approx(
                0, abs=0.01
            )
    for part in parts:
        if part.component.startswith("side"):
            assert (
                min(cap.solid().val().distance(part.solid().val()) for cap in caps)
                <= 0.01
            )
        if part.component == "back":
            assert part.y_mm == 414
            assert part.extrusion_mm == 6


def test_exact_cap_profiles_and_stock_blanks():
    a = roof_parts(RoofProfile(((0, 300), (720, 600)), 18), 414, "roof", ("slope",))[0]
    assert a.profile_xz_mm == ((0, 300), (720, 600), (720, 580.5), (0, 280.5))
    assert a.stock_mm == pytest.approx((787.5, 414, 18))
    b = roof_parts(
        RoofProfile(((0, 300), (360, 600), (720, 600)), 18),
        414,
        "roof",
        ("slope", "level"),
    )
    assert b[0].profile_xz_mm[2][1] == pytest.approx(600 - 3 * math.sqrt(61))
    assert b[0].stock_mm == pytest.approx((60 * math.sqrt(61) + 15, 414, 18))
    assert b[1].profile_xz_mm == ((360, 600), (720, 600), (720, 582), (360, 582))
    assert b[1].stock_mm == (360, 414, 18)


def test_frame_rails_have_stable_ids_and_butt_geometry():
    parts = frame_parts(Frame("frame.support", 720, 380, 50, 18, "plywood"))
    assert [part.id for part in parts] == [
        f"frame.support.{name}" for name in ("front", "back", "left", "right")
    ]
    assert [part.stock_mm for part in parts] == [
        (720, 50, 18),
        (720, 50, 18),
        (344, 50, 18),
        (344, 50, 18),
    ]
    for i, part in enumerate(parts):
        for other in parts[i + 1 :]:
            assert part.solid().intersect(
                other.solid()
            ).val().Volume() == pytest.approx(0, abs=0.01)


def test_layout_places_native_profiles_and_right_handed_stock_frames():
    from cabineteer.layout import LayoutLeaf, Row, Stack
    from cabineteer.profiles import resolve_profile_assembly

    frame = Frame("frame.support", 720, 380, 50, 18, "plywood")
    layout = Stack(
        "assembly",
        (
            LayoutLeaf("lower", 720, 550, 720),
            frame,
            Row(
                "upper",
                (
                    LayoutLeaf("upper.left", 360, 420, 450),
                    LayoutLeaf("upper.right", 360, 420, 600),
                ),
            ),
        ),
    )
    boxes = (
        ProfiledBox("upper.left", 0, 360, 420, 18, 18, 6),
        ProfiledBox("upper.right", 360, 360, 420, 18, 18, 6),
    )
    result = resolve_profile_assembly(
        layout,
        RoofProfile(((0, 300), (720, 600)), 18),
        boxes,
        "roof",
        ("slope",),
        frame,
    )
    parts = {p.id: p for p in result.parts}
    assert len(parts) == 13
    assert parts["upper.left.side_left"].world_offset_mm == (0, 130, 770)
    assert parts["frame.support.front"].world_offset_mm == (0, 170, 720)
    assert parts["upper.left.side_left"].profile_xz_mm == (
        (0, 0),
        (18, 0),
        (18, 288),
        (0, 280.5),
    )
    for part in parts.values():
        frame = part.local_frame
        a, b, c = frame.length_axis, frame.width_axis, frame.thickness_axis
        assert (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        ) == pytest.approx(c)
        assert sum(x * x for x in a) == pytest.approx(1)
        assert sum(x * x for x in b) == pytest.approx(1)
        assert sum(x * x for x in c) == pytest.approx(1)
        vertices = [
            point
            for vertex in part.local_profile_mm
            for point in (
                vertex,
                tuple(
                    x + d for x, d in zip(vertex, part.local_extrusion_mm, strict=True)
                ),
            )
        ]
        spans = tuple(
            max(v[i] for v in vertices) - min(v[i] for v in vertices) for i in range(3)
        )
        assert spans == pytest.approx(part.stock_mm, abs=0.01)


def test_project_round_trip_resolves_lower_and_profile_parts():
    from cabineteer.cabinet import CabinetConfig, OpeningConfig
    from cabineteer.layout import LayoutLeaf, Row, Stack
    from cabineteer.profiles import ProfileAssemblySpec
    from cabineteer.project import (
        CabinetProject,
        ProjectCabinet,
        project_from_dict,
        project_to_dict,
    )

    frame = Frame("frame.support", 720, 380, 50, 18, "18 mm plywood")
    boxes = (
        ProfiledBox("upper.left", 0, 360, 420, 18, 18, 6),
        ProfiledBox("upper.right", 360, 360, 420, 18, 18, 6),
    )
    layout = Stack(
        "assembly",
        (
            LayoutLeaf("lower", 720, 550, 720),
            frame,
            Row(
                "upper",
                (
                    LayoutLeaf("upper.left", 360, 420, 600),
                    LayoutLeaf("upper.right", 360, 420, 600),
                ),
            ),
        ),
    )
    cfg = CabinetConfig(
        width=720,
        height=720,
        depth=550,
        back_thickness=6,
        openings=[OpeningConfig(240, "drawer"), OpeningConfig(444, "door")],
    )
    spec = ProfileAssemblySpec(
        RoofProfile(((0, 300), (360, 600), (720, 600)), 18),
        boxes,
        "roof",
        ("slope", "level"),
        frame,
        "lower",
    )
    project = CabinetProject(
        "fixture", (ProjectCabinet("lower", cfg),), layout=layout, profile_assembly=spec
    )
    restored = project_from_dict(project_to_dict(project))
    assert restored.profile_assembly == spec
    assert restored.resolved() == project.resolved()
    parts = {p.id: p for p in restored.resolved_assembly().parts}
    assert len(parts) == 20
    assert {p for p in parts if p.startswith("lower.")} == {
        "lower.carcass.side_left",
        "lower.carcass.side_right",
        "lower.carcass.bottom",
        "lower.carcass.top",
        "lower.carcass.back",
        "lower.carcass.floor",
    }
    assert parts["lower.carcass.floor"].solid().val().Volume() > 0
    assert parts["roof.cap.slope"].profile_xz_mm[2][1] == pytest.approx(
        600 - 3 * math.sqrt(61)
    )


def test_clipped_kinks_keep_back_vertices_and_side_cap_heights():
    b = RoofProfile(((0, 300), (360, 600), (720, 600)), 18)
    left = box_parts(ProfiledBox("left", 0, 360, 420, 18, 18, 6), b)
    right = box_parts(ProfiledBox("right", 360, 360, 420, 18, 18, 6), b)
    assert left[1].profile_xz_mm[2][1] == pytest.approx(600 - 3 * math.sqrt(61))
    assert right[0].profile_xz_mm[3] == (360, 582)
    c = RoofProfile(((0, 235), (1071, 1204), (1440, 1204)), 18)
    parts = box_parts(ProfiledBox("right", 720, 720, 420, 18, 18, 6), c)
    assert parts[-1].profile_xz_mm == (
        (720, 0),
        (1440, 0),
        (1440, 1204),
        (1071, 1204),
        (720, 235 + 969 * 720 / 1071),
    )
    caps = roof_parts(c, 414, "roof", ("slope", "level"))
    assert caps[0].profile_xz_mm[2][1] == pytest.approx(
        1204 - 18 * math.hypot(1, 969 / 1071)
    )
    assert caps[1].profile_xz_mm == (
        (1071, 1204),
        (1440, 1204),
        (1440, 1186),
        (1071, 1186),
    )

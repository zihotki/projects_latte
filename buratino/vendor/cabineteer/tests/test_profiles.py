"""Native profile geometry and contact checks."""

import math
import runpy
from pathlib import Path

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


def test_profile_height_controls_bounds_and_following_stack_position():
    from cabineteer.layout import LayoutLeaf, Row, Stack
    from cabineteer.profiles import resolve_profile_assembly

    frame = Frame("frame.support", 720, 380, 50, 18)
    layout = Stack(
        "stack",
        (
            LayoutLeaf("lower", 720, 550, 720),
            frame,
            Row(
                "upper",
                (
                    LayoutLeaf("upper.left", 360, 420, 100),
                    LayoutLeaf("upper.right", 360, 420, 100),
                ),
            ),
            LayoutLeaf("next", 720, 420, 10),
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
    placements = {p.name: p for p in result.layout.placements}
    assert placements["upper.left"].carcass_bounds_mm.height_mm == 450
    assert placements["upper.right"].carcass_bounds_mm.height_mm == 600
    assert placements["next"].origin_mm[2] == 1370
    assert result.layout.occupied_world_bounds_mm.max_z == 1380
    assert max(
        p.solid().val().BoundingBox().zmax for p in result.parts
    ) == pytest.approx(1370)


def test_roof_peak_in_gap_is_counted_once_in_stack_height():
    from cabineteer.layout import LayoutLeaf, Row, Stack
    from cabineteer.profiles import resolve_profile_assembly

    frame = Frame("frame", 720, 380, 50, 18)
    layout = Stack(
        "stack",
        (
            frame,
            Row(
                "upper",
                (LayoutLeaf("left", 360, 420, 1), LayoutLeaf("right", 320, 420, 1)),
                gap_mm=40,
            ),
            LayoutLeaf("next", 720, 420, 10),
        ),
    )
    boxes = (
        ProfiledBox("left", 0, 360, 420, 18, 18, 6),
        ProfiledBox("right", 400, 320, 420, 18, 18, 6),
    )
    roof = RoofProfile(((0, 300), (360, 400), (380, 600), (400, 400), (720, 300)), 18)
    result = resolve_profile_assembly(
        layout, roof, boxes, "roof", ("a", "b", "c", "d"), frame
    )
    placements = {p.name: p for p in result.layout.placements}
    assert placements["left"].carcass_bounds_mm.height_mm == 400
    assert placements["right"].carcass_bounds_mm.height_mm == 400
    assert placements["next"].origin_mm[2] == 650


def test_short_frame_rail_stock_follows_its_length_axis():
    parts = frame_parts(Frame("frame", 40, 40, 50, 18))
    for part in parts[2:]:
        assert part.stock_mm == (4, 50, 18)
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
        assert spans == pytest.approx(part.stock_mm)


def test_roof_dip_in_gap_is_included_in_stack_bounds():
    from cabineteer.layout import LayoutLeaf, Row, Stack
    from cabineteer.profiles import resolve_profile_assembly

    frame = Frame("frame", 720, 380, 50, 18)
    layout = Stack(
        "stack",
        (
            frame,
            Row(
                "upper",
                (LayoutLeaf("left", 360, 420, 1), LayoutLeaf("right", 320, 420, 1)),
                gap_mm=40,
            ),
            LayoutLeaf("next", 720, 420, 10),
        ),
    )
    boxes = (
        ProfiledBox("left", 0, 360, 420, 18, 18, 6),
        ProfiledBox("right", 400, 320, 420, 18, 18, 6),
    )
    roof = RoofProfile(((0, 300), (360, 300), (380, -30), (400, 300), (720, 300)), 18)
    result = resolve_profile_assembly(
        layout, roof, boxes, "roof", ("a", "b", "c", "d"), frame
    )
    placements = {p.name: p for p in result.layout.placements}
    minimum = -30 - 18 * math.hypot(1, 330 / 20)
    origin_z = 50 - minimum
    assert placements["left"].occupied_world_bounds_mm.min_z == pytest.approx(50)
    assert placements["left"].origin_mm[2] == pytest.approx(origin_z)
    assert placements["next"].origin_mm[2] == pytest.approx(origin_z + 300)
    caps = [p for p in result.parts if p.owner == "roof"]
    assert min(p.solid().val().BoundingBox().zmin for p in caps) == pytest.approx(50)
    assert result.layout.occupied_world_bounds_mm.max_z == pytest.approx(origin_z + 310)


def test_face_offsets_intersect_at_shifted_kink():
    from cabineteer.profiles import profile_face

    roof = RoofProfile(((0, 300), (360, 600), (720, 600)), 18)
    face = profile_face(
        roof,
        name="fixture.face.applied_faceboard",
        owner="fixture.face",
        face_type="applied_faceboard",
        x0=2,
        x1=718,
        bottom=2,
        thickness=18,
        outer_reveal=2,
        depth_offset=2,
    )
    expected = (
        (2, 2),
        (718, 2),
        (718, 598),
        (360 + (2 * math.sqrt(61) - 12) / 5, 598),
        (2, 300 + 5 * 2 / 6 - math.sqrt(61) / 3),
    )
    for actual, target in zip(face.profile_xz_mm, expected, strict=True):
        assert actual == pytest.approx(target)
    assert face.y_mm == -20
    assert face.extrusion_mm == 18


def test_independent_face_gaps_and_snapshot():
    from cabineteer.cabinet import CabinetConfig, OpeningConfig, face_layout
    from cabineteer.project import (
        CabinetProject,
        ProjectCabinet,
        project_from_dict,
        project_to_dict,
    )

    for door_gap, drawer_gap in ((3, 2), (2, 3)):
        cfg = CabinetConfig(
            height=836,
            face_gap_mm=4,
            door_gap_mm=door_gap,
            drawer_front_gap_mm=drawer_gap,
            openings=[
                OpeningConfig(200, "drawer"),
                OpeningConfig(200, "drawer"),
                OpeningConfig(200, "door"),
                OpeningConfig(200, "door"),
            ],
        )
        project = CabinetProject("gaps", (ProjectCabinet("cabinet", cfg),))
        restored = project_from_dict(project_to_dict(project)).resolved()[0][1]
        assert (restored.door_gap_mm, restored.drawer_front_gap_mm) == (
            door_gap,
            drawer_gap,
        )
        panels = [p for p in face_layout([restored]) if p.kind != "top_cap"]
        assert [
            panels[i + 1].z - panels[i].z - panels[i].height for i in range(3)
        ] == pytest.approx([drawer_gap, max(door_gap, drawer_gap), door_gap])


@pytest.mark.parametrize("level", [False, True])
@pytest.mark.parametrize("overlay_top", [3, 7])
def test_full_native_profile_assembly(level, overlay_top):
    from cabineteer.cabinet import CabinetConfig, OpeningConfig
    from cabineteer.drawer import DrawerConfig, build_drawer, drawer_part_offsets
    from cabineteer.layout import LayoutLeaf, Row, Stack
    from cabineteer.profiles import ProfileAssemblySpec, ProfileFaceSpec
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
        door_gap_mm=2,
        drawer_front_gap_mm=2,
        openings=[OpeningConfig(240, "drawer"), OpeningConfig(444, "door")],
    )
    drawer_data = dict(
        opening_width=cfg.interior_width,
        opening_height=240,
        opening_depth=cfg.interior_depth,
        slide_key="buratino_hettich_quadro_v6_eb20_480",
        side_thickness=16,
        front_back_thickness=18,
        bottom_thickness=12,
        bottom_dado_depth=6,
        bottom_dado_inset=13,
        front_gap=0,
        vertical_gap=60,
        use_standard_height=False,
        applied_face=False,
        joinery_style="butt",
        face_overlay_top=overlay_top,
        face_overlay_bottom=3,
    )
    drawer = DrawerConfig(
        **{
            **drawer_data,
            "joinery_style": __import__(
                "cabineteer.joinery", fromlist=["DrawerJoineryStyle"]
            ).DrawerJoineryStyle.BUTT,
        }
    )
    assert drawer.box_height == 180
    assert drawer.opening_depth == 544
    roof = RoofProfile(
        ((0, 300), (360, 600), (720, 600)) if level else ((0, 300), (720, 600)), 18
    )
    spec = ProfileAssemblySpec(
        roof,
        boxes,
        "roof",
        ("slope", "level") if level else ("slope",),
        frame,
        "lower",
        faces=ProfileFaceSpec(drawer_data, 30),
    )
    project = CabinetProject(
        "fixture", (ProjectCabinet("lower", cfg),), layout=layout, profile_assembly=spec
    )
    result = project_from_dict(project_to_dict(project)).resolved_assembly()
    parts = {part.id: part for part in result.parts}
    assert len(parts) == (29 if level else 28)
    assert parts["upper.left.door"].profile_xz_mm[0:2] == ((2, 2), (359, 2))
    assert parts["upper.right.door"].profile_xz_mm[0:2] == ((361, 2), (718, 2))
    for name, x0, x1 in (("upper.left.door", 2, 359), ("upper.right.door", 361, 718)):
        if level and x0 >= 360:
            heights = (598, 598)
        else:
            slope = 5 / 6 if level else 5 / 12
            drop = math.sqrt(61) / 3 if level else 13 / 6
            heights = (300 + slope * x0 - drop, 300 + slope * x1 - drop)
        expected = ((x0, 2), (x1, 2), (x1, heights[1]), (x0, heights[0]))
        for actual, target in zip(parts[name].profile_xz_mm, expected, strict=True):
            assert actual == pytest.approx(target)
    assert parts["upper.left.door"].y_mm == -20
    drawer_face = parts["lower.drawer.face"]
    lower_door = parts["lower.face.door"]
    assert drawer_face.profile_xz_mm[0][0] == pytest.approx(2)
    assert drawer_face.profile_xz_mm[1][0] == pytest.approx(718)
    assert drawer_face.stock_mm[0] == pytest.approx(716)
    assert lower_door.profile_xz_mm[0][0] == pytest.approx(2)
    assert lower_door.profile_xz_mm[1][0] == pytest.approx(718)
    assert lower_door.stock_mm[0] == pytest.approx(716)
    assert drawer_face.profile_xz_mm[0][1] == 15
    assert drawer_face.profile_xz_mm[2][1] == 258 + overlay_top
    assert lower_door.profile_xz_mm[0][1] == 260 + overlay_top
    assert drawer_face.solid().intersect(
        lower_door.solid()
    ).val().Volume() == pytest.approx(0)
    if level and overlay_top == 3:
        from dataclasses import replace
        from cabineteer.cabinet import face_layout

        for num_doors in (1, 2):
            adjusted_cfg = replace(
                cfg,
                openings=[
                    cfg.openings[0],
                    replace(cfg.openings[1], num_doors=num_doors),
                ],
            )
            adjusted_spec = replace(
                spec,
                faces=replace(spec.faces, outer_reveal_mm=3),
            )
            adjusted_project = replace(
                project,
                cabinets=(ProjectCabinet("lower", adjusted_cfg),),
                profile_assembly=adjusted_spec,
            )
            adjusted_parts = adjusted_project.resolved_assembly().parts
            adjusted_drawer = next(
                part for part in adjusted_parts if part.id == "lower.drawer.face"
            )
            adjusted_doors = sorted(
                (part for part in adjusted_parts if part.id == "lower.face.door"),
                key=lambda part: part.profile_xz_mm[0][0],
            )
            assert len(adjusted_doors) == num_doors
            assert adjusted_drawer.profile_xz_mm[0][0] == pytest.approx(3)
            assert adjusted_drawer.profile_xz_mm[1][0] == pytest.approx(717)
            assert adjusted_drawer.stock_mm[0] == pytest.approx(714)
            assert adjusted_doors[0].profile_xz_mm[0][0] == pytest.approx(3)
            assert adjusted_doors[-1].profile_xz_mm[1][0] == pytest.approx(717)
            if num_doors == 2:
                native_doors = sorted(
                    (
                        panel
                        for panel in face_layout([adjusted_cfg])
                        if panel.kind == "door"
                    ),
                    key=lambda panel: panel.x,
                )
                assert adjusted_doors[0].profile_xz_mm[1][0] == pytest.approx(
                    native_doors[0].x + native_doors[0].width
                )
                assert adjusted_doors[1].profile_xz_mm[0][0] == pytest.approx(
                    native_doors[1].x
                )
    placements = {p.name: p for p in result.layout.placements}
    assert placements["upper.left"].occupied_world_bounds_mm.min_y == 110
    assert result.layout.occupied_world_bounds_mm.min_y == -18
    for part in parts.values():
        bounds = part.solid().val().BoundingBox()
        occupied = result.layout.occupied_world_bounds_mm
        assert occupied.min_x <= bounds.xmin + 0.01
        assert occupied.min_y <= bounds.ymin + 0.01
        assert occupied.min_z <= bounds.zmin + 0.01
        assert occupied.max_x >= bounds.xmax - 0.01
        assert occupied.max_y >= bounds.ymax - 0.01
        assert occupied.max_z >= bounds.zmax - 0.01
    if not level and overlay_top == 3:
        from dataclasses import replace

        legacy = replace(cfg, face_gap_mm=3, door_gap_mm=None, drawer_front_gap_mm=None)
        fallback = replace(
            project, cabinets=(ProjectCabinet("lower", legacy),)
        ).resolved_assembly()
        doors = {p.id: p for p in fallback.parts}
        assert doors["upper.left.door"].profile_xz_mm[1][0] == 358.5
        assert doors["upper.right.door"].profile_xz_mm[0][0] == 361.5
        explicit = replace(legacy, door_gap_mm=4)
        overridden = replace(
            project, cabinets=(ProjectCabinet("lower", explicit),)
        ).resolved_assembly()
        doors = {p.id: p for p in overridden.parts}
        assert doors["upper.left.door"].profile_xz_mm[1][0] == 358
        assert doors["upper.right.door"].profile_xz_mm[0][0] == 362
        assert (
            doors["lower.face.door"].profile_xz_mm[0][1]
            - doors["lower.drawer.face"].profile_xz_mm[2][1]
        ) == 4
        shifted_face = replace(
            spec.faces, drawer={**drawer_data, "face_overlay_bottom": 25}
        )
        shifted = replace(
            project, profile_assembly=replace(spec, faces=shifted_face)
        ).resolved_assembly()
        shifted_placements = {p.name: p for p in shifted.layout.placements}
        assert shifted_placements["lower"].origin_mm[2] == 7
        assert shifted_placements["frame.support"].origin_mm[2] == 727
    from cabineteer.profiles import assembly_records

    records = assembly_records(result)
    viewer_parts = records["viewer"]["parts"]
    assert "viewer" not in records["parts"][0]
    door_record = viewer_parts["upper.left.door"]
    assert door_record["role"] == "upper.left.door"
    assert door_record["cabinet_id"] == "upper.left"
    assert door_record["hinge_side"] == "right"
    assert door_record["hinge_side_status"] == "assumed_for_preview"
    assert len(door_record["hinge_pivot_mm"]) == 3
    assert viewer_parts["lower.drawer.side_left"]["instance_id"] == "lower.drawer"
    assert any(
        "upper.left.door" in group["members"]
        for group in records["viewer"]["cutting_groups"]
    )
    assert parts["upper.left.side_left"].operations[0].kind == "edge_bevel"
    assert parts["upper.left.door"].operations[0].kind == "profile_trim"
    side = parts["lower.drawer.side_left"]
    assert side.stock_mm[1] == pytest.approx(180)
    _, native_parts = build_drawer(drawer)
    native_side = next(p for p in native_parts if p.name == "drawer_side_L")
    off = drawer_part_offsets(drawer)["side_L"]
    expected_origin = (
        cfg.side_thickness + drawer.side_gap + off[0],
        drawer.front_gap + off[1],
        cfg.bottom_thickness + 30 + off[2],
    )
    expected_shape = native_side.shape.translate(expected_origin)
    assert side.solid().val().Volume() == pytest.approx(expected_shape.val().Volume())
    assert side.solid().val().distance(expected_shape.val()) == pytest.approx(0)
    assert result.hardware_status == "unverified"
    for part in parts.values():
        frame = part.local_frame
        a, b, c = frame.length_axis, frame.width_axis, frame.thickness_axis
        assert (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        ) == pytest.approx(c)
        for op in part.operations:
            for point in op.local_profile_mm:
                assert all(
                    -0.01 <= point[i] <= part.stock_mm[i] + 0.01 for i in range(3)
                )


def test_face_types_share_outline_and_keep_mounting_metadata():
    from cabineteer.profiles import profile_face, with_profile_operations

    roof = RoofProfile(((0, 300), (360, 600), (720, 600)), 18)
    parts = [
        profile_face(
            roof,
            name=f"fixture.face.{kind}",
            owner="fixture.face",
            face_type=kind,
            x0=2,
            x1=359,
            bottom=2,
            thickness=18,
            outer_reveal=2,
            depth_offset=2,
        )
        for kind in ("door", "drawer_front", "applied_faceboard")
    ]
    expected = (
        (2, 2),
        (359, 2),
        (359, 300 + 5 * 359 / 6 - math.sqrt(61) / 3),
        (2, 300 + 5 * 2 / 6 - math.sqrt(61) / 3),
    )
    for part in parts:
        for actual, target in zip(part.profile_xz_mm, expected, strict=True):
            assert actual == pytest.approx(target)
        assert with_profile_operations(part).operations[0].kind == "profile_trim"
    assert [p.mounting for p in parts] == ["hinged", "drawer-mounted", "fixed"]
    assert [p.component for p in parts] == ["door", "drawer_front", "applied_faceboard"]


def test_face_rejects_concave_roof_and_invalid_offset():
    from cabineteer.profiles import profile_face

    with pytest.raises(ValueError, match="convex"):
        profile_face(
            RoofProfile(((0, 100), (50, 100), (100, 120)), 18),
            name="face",
            owner="fixture",
            face_type="door",
            x0=2,
            x1=98,
            bottom=0,
            thickness=18,
            outer_reveal=2,
            depth_offset=2,
        )


def test_fixed_faceboard_boundary_gap():
    from cabineteer.profiles import face_boundary_gap

    assert (
        face_boundary_gap(
            "applied_faceboard", "door", door_gap_mm=3, drawer_front_gap_mm=2
        )
        == 3
    )
    assert (
        face_boundary_gap(
            "drawer_front", "applied_faceboard", door_gap_mm=3, drawer_front_gap_mm=2
        )
        == 2
    )
    assert (
        face_boundary_gap(
            "applied_faceboard",
            "door",
            door_gap_mm=3,
            drawer_front_gap_mm=2,
            explicit_gap_mm=4,
        )
        == 4
    )


def test_legacy_paired_door_gap_survives_snapshot():
    from cabineteer.cabinet import CabinetConfig, OpeningConfig, face_layout
    from cabineteer.project import (
        CabinetProject,
        ProjectCabinet,
        project_from_dict,
        project_to_dict,
    )

    cfg = CabinetConfig(face_gap_mm=3, openings=[OpeningConfig(684, "door_pair")])
    project = CabinetProject("legacy", (ProjectCabinet("cabinet", cfg),))
    restored = project_from_dict(project_to_dict(project)).resolved()[0][1]
    doors = [p for p in face_layout([restored]) if p.kind == "door"]
    assert doors[1].x - (doors[0].x + doors[0].width) == pytest.approx(2)
    restored.door_gap_mm = 4
    doors = [p for p in face_layout([restored]) if p.kind == "door"]
    assert doors[1].x - (doors[0].x + doors[0].width) == pytest.approx(4)


def test_upper_drawer_uses_native_opening_and_replaces_one_door():
    from dataclasses import replace

    from cabineteer.profiles import (
        assembly_records,
        profile_spec_from_dict,
        profile_spec_to_dict,
        resolved_profile_spec,
        upper_drawer_configs,
    )
    from cabineteer.project import project_from_dict, project_to_dict

    root = Path(__file__).resolve().parents[3]
    project = runpy.run_path(str(root / "projects/profile-row-drawers/project.py"))[
        "project"
    ]
    spec = resolved_profile_spec(project.profile_assembly)
    assert profile_spec_from_dict(profile_spec_to_dict(spec)) == spec
    restored = project_from_dict(project_to_dict(project))
    item, drawer, x0, floor = upper_drawer_configs(spec)["upper.left"]
    assert (x0, floor, drawer.opening_width, drawer.opening_depth) == (18, 18, 333, 414)
    assert drawer.opening_height == pytest.approx(273.705798046485)
    assert (drawer.box_width, drawer.box_height, drawer.box_depth) == (325, 140, 380)
    assert drawer.side_gap == 4

    assembly = restored.resolved_assembly()
    parts = {part.id: part for part in assembly.parts}
    assert "upper.left.door" not in parts
    assert "upper.right.door" in parts
    front = parts["upper.left.drawer_front"]
    assert front.component == "drawer_front"
    assert front.mounting == "drawer-mounted"
    assert front.operations[0].kind == "profile_trim"
    assert parts["upper.left.drawer.side_left"].stock_mm == (380, 140, 16)
    assert parts["upper.left.drawer.bottom"].stock_mm[2] == 12
    assert front.profile_xz_mm[1][0] == 359
    assert parts["upper.right.door"].profile_xz_mm[0][0] == 361
    records = assembly_records(assembly)
    drawers = {d["instance_id"]: d for d in records["viewer"]["drawers"]}
    assert drawers["lower.drawer"]["box_mm"]["depth"] == 480
    assert drawers["upper.left.drawer"]["box_mm"]["depth"] == 380
    assert records["viewer"]["parts"][front.id]["instance_id"] == "upper.left.drawer"
    assert records["viewer"]["parts"][front.id]["cabinet_id"] == "upper"
    assert (
        records["viewer"]["parts"]["upper.left.drawer.side_left"]["cabinet_id"]
        == "upper"
    )
    assert [h["quantity"] for h in assembly.hardware] == [2, 2]
    assert assembly.hardware[1]["slide_key"] == item.slide_key
    upper_bounds = next(
        p.occupied_world_bounds_mm
        for p in assembly.layout.placements
        if p.name == "upper"
    )
    assert upper_bounds.min_y <= front.y_mm + front.world_offset_mm[1]

    cfg = restored.cabinets[0].config
    wider_gap = replace(cfg, door_gap_mm=3, drawer_front_gap_mm=5)
    changed = replace(
        restored, cabinets=(replace(restored.cabinets[0], config=wider_gap),)
    )
    changed_parts = {part.id: part for part in changed.resolved_assembly().parts}
    assert changed_parts["upper.left.drawer_front"].profile_xz_mm[1][0] == 357.5
    assert changed_parts["upper.right.door"].profile_xz_mm[0][0] == 362.5


def test_upper_drawer_rejects_bad_section_and_roof_fit():
    from dataclasses import replace

    from cabineteer.profiles import (
        ProfileDrawerSpec,
        resolved_profile_spec,
        upper_drawer_configs,
    )

    root = Path(__file__).resolve().parents[3]
    project = runpy.run_path(str(root / "projects/profile-row-drawers/project.py"))[
        "project"
    ]
    spec = resolved_profile_spec(project.profile_assembly)
    drawer = spec.upper_drawers[0]
    with pytest.raises(ValueError, match="distinct"):
        upper_drawer_configs(replace(spec, upper_drawers=(drawer, drawer)))
    with pytest.raises(ValueError, match="unknown"):
        upper_drawer_configs(
            replace(spec, upper_drawers=(replace(drawer, section="missing"),))
        )
    with pytest.raises(ValueError, match="roof underside"):
        upper_drawer_configs(
            replace(spec, upper_drawers=(replace(drawer, box_height_mm=260),))
        )
    with pytest.raises(ValueError, match="positive and finite"):
        ProfileDrawerSpec("upper.left", drawer.slide_key, float("nan"), 20)
    with pytest.raises(ValueError):
        upper_drawer_configs(
            replace(
                spec,
                upper_drawers=(
                    replace(drawer, slide_key="buratino_hettich_quadro_v6_eb20_480"),
                ),
            )
        )


def test_two_upper_sections_keep_distinct_drawer_instances():
    from dataclasses import replace

    from cabineteer.profiles import assembly_records, upper_drawer_configs

    root = Path(__file__).resolve().parents[3]
    project = runpy.run_path(str(root / "projects/profile-row-drawers/project.py"))[
        "project"
    ]
    spec = project.profile_assembly
    right = replace(spec.upper_drawers[0], section="upper.right")
    changed = replace(
        project,
        profile_assembly=replace(spec, upper_drawers=(spec.upper_drawers[0], right)),
    )
    openings = upper_drawer_configs(changed.profile_assembly)
    assert openings["upper.right"][1].opening_width == 333
    assert openings["upper.right"][1].opening_height == pytest.approx(564)
    assembly = changed.resolved_assembly()
    assert len({part.id for part in assembly.parts}) == len(assembly.parts)
    records = assembly_records(assembly)
    drawers = {item["instance_id"]: item for item in records["viewer"]["drawers"]}
    assert drawers.keys() == {"lower.drawer", "upper.left.drawer", "upper.right.drawer"}
    assert drawers["upper.right.drawer"]["box_mm"]["depth"] == 380
    assert len(assembly.hardware) == 3
    assert all(part.id != "upper.right.door" for part in assembly.parts)


def test_unshared_upper_drawer_keeps_section_as_cabinet_owner():
    from dataclasses import replace
    from types import SimpleNamespace

    from cabineteer.profiles import assembly_faces, assembly_records, ProfileAssembly

    root = Path(__file__).resolve().parents[3]
    project = runpy.run_path(str(root / "projects/profile-row-drawers/project.py"))[
        "project"
    ]
    spec = replace(project.profile_assembly, shared_owner=None, roof_joint=None)
    cfg = project.cabinets[0].config
    parts = assembly_faces(spec, cfg, SimpleNamespace(origin_mm=(0, 0, 0)), (0, 0, 0))
    records = assembly_records(
        ProfileAssembly(project.resolved_assembly().layout, parts)
    )
    viewer = records["viewer"]["parts"]["upper.left.drawer.side_left"]
    assert viewer["cabinet_id"] == "upper.left"
    assert viewer["instance_id"] == "upper.left.drawer"

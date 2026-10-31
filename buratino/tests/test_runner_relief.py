"""Runner rebates retain full stock sizing and use the shared cut path."""

from dataclasses import asdict, replace

import cadquery as cq
import pytest
from cabineteer.drawer import DrawerConfig, drawer_recipe
from cabineteer.joinery import DrawerJoineryStyle
from cabineteer.profiles import _placed_drawer_parts, upper_drawer_configs
from cabineteer.space_adapter import materialize_box_part
from cabineteer.spaces import Carcass, DrawerBox, Space, resolve_model

from buratino.drawers import register_eb20_profile
from buratino.machining_dimensions import groove_dimensions
from buratino.machining_notes import machining_notes
from buratino.project import load_project, native_snapshot


def config(**overrides):
    register_eb20_profile()
    values = dict(
        opening_width=684,
        opening_height=200,
        opening_depth=500,
        slide_key="buratino_hettich_quadro_v6_eb20_480",
        side_thickness=18,
        front_back_thickness=18,
        bottom_thickness=12,
        bottom_dado_depth=10,
        bottom_dado_inset=13,
        runner_relief_depth=2,
        use_standard_height=False,
        applied_face=False,
        joinery_style=DrawerJoineryStyle.BUTT,
    )
    return DrawerConfig(**(values | overrides))


def test_runner_limit_and_sizing_use_finished_land_but_bottom_uses_stock():
    with pytest.raises(ValueError, match="at most 16"):
        _ = config(runner_relief_depth=0).box_depth
    relieved = config()
    original = config(side_thickness=16, runner_relief_depth=0)
    assert relieved.box_depth == original.box_depth == 480
    assert relieved.runner_zone_thickness == original.runner_zone_thickness == 16
    assert relieved.box_width == original.box_width == 676
    assert relieved.box_inside_width == original.box_inside_width - 4 == 640
    assert relieved.side_gap == original.side_gap == 4
    assert (
        relieved.front_back_panel_length == original.front_back_panel_length - 4 == 640
    )
    assert relieved.bottom_panel_width == 660
    assert relieved.bottom_panel_depth == 464
    assert all(
        cut["role"] != "runner_relief"
        for part in drawer_recipe(original)
        for cut in part.get("operations", [])
    )


@pytest.mark.parametrize("length,inset", [(480, 13), (380, 12)])
def test_inner_rebate_removes_full_length_material_only(length, inset):
    cfg = config(
        slide_key=f"buratino_hettich_quadro_v6_eb20_{length}",
        bottom_dado_inset=inset,
    )
    for panel in drawer_recipe(cfg)[:2]:
        cut = panel["operations"][-1]
        left = panel["id"] == "side_L"
        assert cut["role"] == "runner_relief"
        assert cut["face"] == ("x+" if left else "x-")
        assert (cut["u"], cut["v"], cut["size_u"], cut["size_v"], cut["depth"]) == (
            0,
            0,
            length,
            inset,
            2,
        )
        plain = dict(panel, operations=panel["operations"][:-1])
        original = materialize_box_part(plain).val()
        actual = materialize_box_part(panel).val()
        removed = cq.Solid.makeBox(2, length, inset, cq.Vector(16 if left else 0, 0, 0))
        assert actual.isValid()
        assert original.Volume() - actual.Volume() == pytest.approx(2 * length * inset)
        expected = original.cut(removed)
        assert actual.cut(expected).Volume() < 1e-6
        assert expected.cut(actual).Volume() < 1e-6
        assert panel["stock"]["thickness"] == 18


@pytest.mark.parametrize("depth", [-1, float("nan"), float("inf"), True, 18, 20])
def test_invalid_relief_depth_rejected(depth):
    with pytest.raises(ValueError, match="runner"):
        drawer_recipe(config(runner_relief_depth=depth))


@pytest.mark.parametrize("depth", [10, 11])
def test_relief_and_bottom_groove_leave_positive_bottom_bearing(depth):
    # The groove floor must extend beyond the inner runner land.
    with pytest.raises(ValueError, match="positive bottom bearing"):
        drawer_recipe(config(runner_relief_depth=depth))
    assert config(runner_relief_depth=2).runner_zone_thickness == 16


@pytest.mark.parametrize("inset", [0, -1, float("nan"), 200])
def test_relief_requires_meaningful_bottom_inset(inset):
    with pytest.raises(ValueError, match="bottom inset"):
        drawer_recipe(config(bottom_dado_inset=inset))


def test_native_operations_keep_rebate_dimensions_and_stock():
    cfg = config()
    parts = _placed_drawer_parts(cfg, (0, 0, 0), "test", "owner", "plywood")
    for part in parts[:2]:
        record = dict(
            operations=[asdict(cut) for cut in part.operations],
            stock_mm=dict(
                zip(("length", "width", "thickness"), part.stock_mm, strict=True)
            ),
            local_frame=asdict(part.local_frame),
        )
        groove, relief = record["operations"]
        assert relief["target"] == groove["target"]
        assert relief["inward_axis_local"] == groove["inward_axis_local"]
        assert relief["target"] == (
            "thickness+" if part.id.endswith("side_left") else "thickness-"
        )
        feature = groove_dimensions(record)[-1]
        assert (
            feature.width_mm,
            feature.inset_mm,
            feature.depth_mm,
            feature.thickness_mm,
        ) == (
            13,
            0,
            2,
            18,
        )
        assert any(
            "Runner rebate: 480 mm long × 13 mm high; depth 2 mm" in note
            for note in machining_notes(record)
        )


def test_space_authoring_preserves_relief():
    cfg = config()
    model = resolve_model(
        Carcass(720, 300, 506),
        Space(
            "root",
            content=DrawerBox(
                "box",
                20,
                140,
                slide_key=cfg.slide_key,
                side_thickness=18,
                runner_relief_depth=2,
                bottom_dado_inset=13,
            ),
        ),
    )
    cuts = [
        cut
        for p in model.part_plan.parts
        for cut in p.get("operations", [])
        if cut.get("role") == "runner_relief"
    ]
    assert len(cuts) == 2
    assert all(cut["depth"] == 2 for cut in cuts)


def test_profile_authoring_and_worker_snapshot_keep_relief(root):
    project = load_project(root / "projects/attic-clothing-storage")
    spec = project.native_project.profile_assembly
    assert all(recipe.runner_relief_depth_mm == 2 for recipe in spec.lower_drawers)
    assert spec.upper_drawers[0].runner_relief_depth_mm == 2
    upper = upper_drawer_configs(spec)["upper.section-1"][1]
    assert upper.runner_relief_depth == 2
    assert (upper.bottom_panel_width, upper.bottom_panel_depth) == (309, 364)
    snapshot = native_snapshot(project)
    assert (
        snapshot["project"]["profile_assembly"]["upper_drawers"][0][
            "runner_relief_depth_mm"
        ]
        == 2
    )
    for recipe in (*spec.lower_drawers, *spec.upper_drawers):
        with pytest.raises(ValueError):
            replace(recipe, runner_relief_depth_mm=-1)


def test_automatic_bottom_thickness_with_inner_relief():
    # The width participates in the heavy-bottom rule during initialization.
    cfg = config(bottom_thickness=None, opening_height=320)
    assert cfg.bottom_thickness == 12
    assert cfg.box_width == 676
    assert len(drawer_recipe(cfg)) == 5


@pytest.mark.parametrize("depth", [-1, float("nan"), float("inf"), True, 18])
def test_invalid_bottom_groove_depth_rejected(depth):
    with pytest.raises(ValueError, match="bottom groove"):
        drawer_recipe(config(bottom_dado_depth=depth))


def test_same_face_relief_can_overlap_corner_rabbet_depth():
    cfg = config(joinery_style=DrawerJoineryStyle.HALF_LAP, runner_relief_depth=9)
    assert cfg.runner_zone_thickness == 9
    assert len(drawer_recipe(cfg)) == 5


def test_side_mounted_envelope_and_default_relief_are_unchanged():
    from cabineteer.hardware import SLIDES, SlideMountLocation

    key = next(
        k
        for k, slide in SLIDES.items()
        if slide.mount_location == SlideMountLocation.SIDE
    )
    original = config(slide_key=key, runner_relief_depth=0)
    relieved = config(slide_key=key)
    assert relieved.box_width == original.box_width
    assert relieved.side_gap == original.side_gap
    assert relieved.box_inside_width == original.box_inside_width
    assert DrawerConfig(684, 200, 500).runner_relief_depth == 0


@pytest.mark.parametrize(
    "opening,length,height,outer,upper_clear,runner_clear,bottom_width",
    [(684, 480, 180, 676, 640, 644, 660), (333, 380, 140, 325, 289, 293, 309)],
)
def test_actual_inner_lands_bottom_bearing_and_groove_engagement(
    opening, length, height, outer, upper_clear, runner_clear, bottom_width
):
    from cabineteer.drawer import drawer_part_offsets

    cfg = config(
        opening_width=opening,
        slide_key=f"buratino_hettich_quadro_v6_eb20_{length}",
        opening_height=height + 20,
    )
    panels = drawer_recipe(cfg)
    offsets = drawer_part_offsets(cfg)
    shapes = {
        panel["id"]: materialize_box_part(panel).val().translate(offsets[panel["id"]])
        for panel in panels
    }
    left, right = shapes["side_L"], shapes["side_R"]

    def band(shape, z):
        return shape.intersect(
            cq.Solid.makeBox(outer, 1, 1, cq.Vector(0, length / 2, z))
        ).BoundingBox()

    lower_l, lower_r = band(left, 5), band(right, 5)
    upper_l, upper_r = band(left, 30), band(right, 30)
    groove_l, groove_r = band(left, 15), band(right, 15)
    assert (lower_l.xmin, lower_r.xmax) == pytest.approx((0, outer))
    assert (lower_l.xlen, lower_r.xlen) == pytest.approx((16, 16))
    assert lower_r.xmin - lower_l.xmax == pytest.approx(runner_clear)
    assert upper_r.xmin - upper_l.xmax == pytest.approx(upper_clear)
    assert (groove_l.xlen, groove_r.xlen) == pytest.approx((8, 8))
    assert cfg.side_gap == 4
    assert cfg.front_back_panel_length == upper_clear
    bottom = shapes["bottom"].BoundingBox()
    assert (bottom.xlen, bottom.ylen, bottom.zlen) == pytest.approx(
        (bottom_width, length - 16, 12)
    )
    assert (bottom.xmin, bottom.ymin, bottom.zmin) == pytest.approx((8, 8, 13))
    assert upper_l.xmax - bottom.xmin == pytest.approx(10)
    assert bottom.xmax - upper_r.xmin == pytest.approx(10)
    assert lower_l.xmax - bottom.xmin == pytest.approx(8)
    assert bottom.xmax - lower_r.xmin == pytest.approx(8)
    assert shapes["sub_front"].BoundingBox().xlen == pytest.approx(upper_clear)
    assert shapes["back"].BoundingBox().xlen == pytest.approx(upper_clear)
    for wall in (left, right, shapes["sub_front"], shapes["back"]):
        assert wall.intersect(shapes["bottom"]).Volume() < 1e-6


@pytest.mark.parametrize("stock,relief", [(18, 2), (16, 0)])
def test_hardware_evaluation_uses_finished_runner_contact(stock, relief):
    from cabineteer.evaluation import check_drawer_hardware_clearances

    cfg = config(side_thickness=stock, runner_relief_depth=relief)
    assert not check_drawer_hardware_clearances(cfg)

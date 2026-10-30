"""The shared recipe must retain drawer stock, cuts and native stock frames."""

from dataclasses import asdict

import cadquery as cq
import pytest

from cabineteer.drawer import DrawerConfig, drawer_recipe
from cabineteer.joinery import (
    DrawerJoineryStyle,
    apply_drawer_joinery_to_side,
    apply_drawer_joinery_to_front_back,
)
from cabineteer.profiles import _placed_drawer_parts
from cabineteer.space_adapter import materialize_box_part
from cabineteer.spaces import Carcass, DrawerBox, Space, resolve_model


def _config(thickness, style):
    return DrawerConfig(
        opening_width=564,
        opening_height=264,
        opening_depth=564,
        slide_key="ferretti_hdsc550v90",
        side_thickness=thickness,
        front_back_thickness=18,
        bottom_thickness=12,
        bottom_dado_depth=6,
        bottom_dado_inset=13,
        vertical_gap=64,
        use_standard_height=False,
        applied_face=False,
        joinery_style=style,
    )


@pytest.mark.parametrize("thickness", [16, 18])
@pytest.mark.parametrize("style", list(DrawerJoineryStyle))
def test_space_recipe_keeps_stock_operations_and_placement(thickness, style):
    cfg = _config(thickness, style)
    model = resolve_model(
        Carcass(600, 300, 570),
        Space(
            "root",
            content=DrawerBox(
                "box",
                30,
                cfg.box_height,
                slide_key=cfg.slide_key,
                side_thickness=thickness,
                front_back_thickness=18,
                bottom_thickness=12,
                bottom_dado_inset=13,
                joinery_style=style.value,
            ),
        ),
    )
    panels = drawer_recipe(cfg, "/root/box/")
    actual = {p["id"]: p for p in model.part_plan.parts}
    box_origin = model.contents[0]["origin"]
    for panel in panels:
        part = actual[panel["id"]]
        assert part["stock"] == panel["stock"]
        assert part["operations"] == panel["operations"]
        assert part["transform"]["translation"] == pytest.approx(
            [a + b for a, b in zip(box_origin, panel["transform"]["translation"])]
        )
    bottom = panels[-1]
    x, y, z = bottom["transform"]["translation"]
    w, d, _ = bottom["stock"]["dimensions"]
    assert x == thickness - 6
    assert cfg.box_width - thickness - (x + w) == -6
    assert y == 18 - 6
    assert cfg.box_depth - 18 - (y + d) == -6
    assert z == 13


def _legacy_shape(cfg, panel):
    """Use the former native CAD cuts as an independent geometry reference."""
    name = panel["id"]
    x, y, z = panel["stock"]["dimensions"]
    shape = cq.Workplane("XY").box(x, y, z, centered=False)
    if name == "bottom":
        return shape
    if name.startswith("side"):
        cut = (
            cq.Workplane("XY")
            .box(6, y, 12, centered=False)
            .translate((x - 6 if name == "side_L" else 0, 0, 13))
        )
        return apply_drawer_joinery_to_side(
            shape.cut(cut),
            cfg.joinery,
            y,
            z,
            side="left" if name == "side_L" else "right",
        )
    cut = (
        cq.Workplane("XY")
        .box(x, 6, 12, centered=False)
        .translate((0, y - 6 if name == "sub_front" else 0, 13))
    )
    return apply_drawer_joinery_to_front_back(
        shape.cut(cut),
        cfg.joinery,
        x,
        z,
        position="front" if name == "sub_front" else "back",
    )


def _same_solid(actual, expected):
    assert actual.cut(expected).Volume() < 1e-5
    assert expected.cut(actual).Volume() < 1e-5


@pytest.mark.parametrize(
    "thickness,style",
    [
        (16, DrawerJoineryStyle.BUTT),
        (16, DrawerJoineryStyle.QQQ),
        (18, DrawerJoineryStyle.HALF_LAP),
        (18, DrawerJoineryStyle.DRAWER_LOCK),
    ],
)
def test_native_stock_frame_operations_reconstruct_unchanged_geometry(thickness, style):
    cfg = _config(thickness, style)
    origin = (37, 53, 71)
    native = _placed_drawer_parts(cfg, origin, "test", "owner", "ply")
    recipe = drawer_recipe(cfg)
    for part, panel in zip(native, recipe):
        offset = tuple(a + b for a, b in zip(origin, panel["transform"]["translation"]))
        expected = _legacy_shape(cfg, panel).translate(offset).val()
        _same_solid(part.shape.val(), expected)
        assert part.solid().val().isValid()
        # Rebuild the cuts using only the native report's declared L/W/T data.
        stock = cq.Workplane("XY").box(*part.stock_mm, centered=False)
        for operation in part.operations:
            record = asdict(operation)
            assert record["kind"] == "pocket"
            wire = cq.Wire.makePolygon(
                [cq.Vector(*p) for p in record["local_profile_mm"]], close=True
            )
            vector = cq.Vector(
                *(v * record["depth_mm"] for v in record["inward_axis_local"])
            )
            stock = stock.cut(cq.Solid.extrudeLinear(wire, [], vector))
        frame = part.local_frame
        # Transform the stock-local solid back to the placed world frame.
        plane = cq.Plane(
            origin=frame.origin_mm, xDir=frame.length_axis, normal=frame.thickness_axis
        )
        actual = stock.val().moved(cq.Location(plane))
        _same_solid(actual, expected)
        assert part.stock_mm[2] == panel["stock"]["thickness"]


@pytest.mark.parametrize("thickness", [16, 18])
def test_materialized_bottom_seats_in_all_four_walls(thickness):
    cfg = _config(thickness, DrawerJoineryStyle.HALF_LAP)
    panels = drawer_recipe(cfg)
    shapes = {
        p["id"]: materialize_box_part(p).translate(p["transform"]["translation"]).val()
        for p in panels
    }
    bottom = shapes["bottom"]
    bounds = bottom.BoundingBox()
    assert bounds.xmin == pytest.approx(thickness - 6)
    assert bounds.xmax == pytest.approx(cfg.box_width - thickness + 6)
    assert bounds.ymin == pytest.approx(12)
    assert bounds.ymax == pytest.approx(cfg.box_depth - 12)
    assert bounds.zmin == pytest.approx(13)
    for name in ("side_L", "side_R", "sub_front", "back"):
        wall = shapes[name]
        assert bottom.intersect(wall).Volume() < 1e-5
        assert bottom.distance(wall) < 1e-6

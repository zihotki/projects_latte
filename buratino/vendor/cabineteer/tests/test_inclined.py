import math
from dataclasses import replace

import pytest
from cabineteer.cabinet import (
    CabinetConfig,
    build_cabinet,
    carcass_panel_dims,
    dispatch_cabinet_geometry,
)
from cabineteer.hardware import SLIDES
from cabineteer.hettich_eb20 import EB20_SLIDE_KEYS
from cabineteer.inclined import height_at
from cabineteer.project import _config_to_dict, config_from_dict


def _native_server():
    """Load the real native server module with the installed MCP SDK."""
    import importlib

    return importlib.import_module("cabineteer.server")


def _mcp_is_error(result):
    for attribute in ("is_error", "isError"):
        try:
            return getattr(result, attribute)
        except AttributeError:
            continue
    raise AssertionError("MCP result has no error flag")


def _run(coro):
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def test_native_mcp_server_registers_tools_with_installed_sdk():
    import json

    from mcp.server import NotificationOptions
    from mcp.types import CallToolRequestParams

    native = _native_server()
    tools = _run(native.list_tools())
    assert any(tool.name == "visualize_project" for tool in tools)
    assert (
        native.server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ).tools
        is not None
    )
    response = _run(native._mcp_list_tools(None, None))
    assert len(response.tools) == len(tools)

    valid = _run(
        native._mcp_call_tool(
            None,
            CallToolRequestParams(
                name="list_hardware", arguments={"category": "slides"}
            ),
        )
    )
    assert not _mcp_is_error(valid)
    assert json.loads(valid.content[0].text)["slides"]

    invalid = _run(
        native._mcp_call_tool(
            None,
            CallToolRequestParams(
                name="list_hardware", arguments={"category": "invalid"}
            ),
        )
    )
    assert _mcp_is_error(invalid)
    assert "category" in invalid.content[0].text


def test_native_mcp_registration_supports_legacy_decorator_api(monkeypatch):
    native = _native_server()

    class LegacyServer:
        def __init__(self, _name):
            self.handlers = {}

        def list_tools(self):
            return lambda function: self.handlers.setdefault("list_tools", function)

        def call_tool(self):
            return lambda function: self.handlers.setdefault("call_tool", function)

    monkeypatch.setattr(native, "Server", LegacyServer)
    instance = native._create_server()
    assert instance.handlers == {
        "list_tools": native.list_tools,
        "call_tool": native.call_tool,
    }


@pytest.mark.parametrize("angle", [-40, -10, 10, 40])
def test_roof_solids_and_blanks(angle):
    cfg = CabinetConfig(
        width=720,
        height=970,
        depth=500,
        roof_angle_deg=angle,
        back_style="under_top",
        face_top_style="plain",
        leg_count=0,
    )
    assembly, parts = build_cabinet(cfg)
    panels = {p.name: p for p in carcass_panel_dims(cfg)}
    drop = cfg.top_thickness / math.cos(math.radians(angle))
    assert panels["left_side"].length == pytest.approx(
        max(height_at(cfg, 0), height_at(cfg, 18)) - drop
    )
    assert panels["right_side"].length == pytest.approx(
        max(height_at(cfg, 702), height_at(cfg, 720)) - drop
    )
    assert config_from_dict(_config_to_dict(cfg)).roof_angle_deg == angle
    shapes = [p.shape.val().located(assembly.objects[p.name].loc) for p in parts]
    top = next(
        shape for part, shape in zip(parts, shapes, strict=True) if part.name == "top"
    )
    radians = math.radians(angle)
    projected = [
        vertex.X * math.cos(radians) + vertex.Z * math.sin(radians)
        for vertex in top.Vertices()
    ]
    assert panels["top"].length == pytest.approx(max(projected) - min(projected))
    assert top.BoundingBox().xmin == pytest.approx(0)
    assert top.BoundingBox().xmax == pytest.approx(cfg.width)
    for i, left in enumerate(shapes):
        for right in shapes[i + 1 :]:
            assert left.intersect(right).Volume() == pytest.approx(0, abs=1e-5)
    assert assembly.toCompound().BoundingBox().zmax == pytest.approx(970)


def test_unsupported_roof_rejected():
    cfg = CabinetConfig(roof_angle_deg=5, back_style="under_top")
    for change in (
        {"fixed_shelf_positions": [100]},
        {"edge_band_mode": "hot_melt"},
        {"back_capture": "dado"},
    ):
        with pytest.raises(ValueError, match="Inclined cabinets"):
            carcass_panel_dims(replace(cfg, **change))


def test_native_dispatch_uses_inclined_geometry_and_rejects_multi_bay():
    _cabinet_assembly = _native_server()._cabinet_assembly

    cfg = CabinetConfig(
        width=720,
        height=970,
        depth=500,
        roof_angle_deg=math.degrees(math.atan2(120, 720)),
        back_style="under_top",
        face_top_style="plain",
        leg_count=0,
    )
    direct, direct_parts = dispatch_cabinet_geometry(cfg)
    viewed, viewed_parts, _ = _cabinet_assembly(cfg, None, include_feet=False)
    for assembly, parts in ((direct, direct_parts), (viewed, viewed_parts)):
        side = next(part for part in parts if part.name == "left_side")
        shape = side.shape.val().located(assembly.objects[side.name].loc)
        expected = {"left_side": 834.75, "right_side": 951.75}[side.name]
        assert shape.BoundingBox().zmax == pytest.approx(expected, abs=1)

    with pytest.raises(ValueError, match="multi-bay"):
        dispatch_cabinet_geometry(cfg, bay_configs=[cfg])
    with pytest.raises(ValueError, match="multi-bay"):
        _cabinet_assembly(cfg, [{"width_mm": 720, "openings": []}], include_feet=False)


def test_separate_native_inclines_share_the_same_roof_line():
    _cabinet_assembly = _native_server()._cabinet_assembly

    angle = math.degrees(math.atan2(120, 720))
    first = CabinetConfig(
        width=720,
        height=970,
        depth=500,
        roof_angle_deg=angle,
        back_style="under_top",
        leg_count=0,
    )
    second = replace(first, width=600, height=1070)
    first_assy, first_parts, _ = _cabinet_assembly(first, None, include_feet=False)
    second_assy, second_parts, _ = _cabinet_assembly(second, None, include_feet=False)

    def roof_edge(assembly, parts, name, x_offset):
        part = next(part for part in parts if part.name == name)
        shape = part.shape.val().located(assembly.objects[name].loc)
        return sorted(
            (round(vertex.X + x_offset, 3), round(vertex.Z, 3))
            for vertex in shape.Vertices()
            if vertex.Y < 1 and vertex.Z > 800
        )

    left_edge = roof_edge(first_assy, first_parts, "right_side", 0)
    right_edge = roof_edge(second_assy, second_parts, "left_side", 720)
    assert max(z for _, z in left_edge) == pytest.approx(
        min(z for _, z in right_edge), abs=0.01
    )
    assert max(x for x, _ in left_edge) == pytest.approx(min(x for x, _ in right_edge))


def test_native_flat_viewer_keeps_single_and_multi_bay_builders():
    _cabinet_assembly = _native_server()._cabinet_assembly

    single = CabinetConfig(openings=[[180, "drawer"], [400, "open"]])
    single_assy, single_parts, _ = _cabinet_assembly(single, None, include_feet=False)
    assert any("face" in part.name for part in single_parts)
    assert any("drawer" in name for name in single_assy.objects)

    multi = CabinetConfig(width=1200, openings=[])
    _, multi_parts, info = _cabinet_assembly(
        multi,
        [
            {"width_mm": 582, "openings": []},
            {"width_mm": 582, "openings": []},
        ],
        include_feet=False,
    )
    assert info["columns"] == 2
    assert any("divider" in part.name for part in multi_parts)


def test_catalog_available_natively_and_enforces_limits():
    for length, minimum, load in [(380, 393, 25), (450, 463, 30), (480, 493, 30)]:
        slide = SLIDES[EB20_SLIDE_KEYS[length]]
        assert slide.max_load_kg == load
        assert slide.slide_length_for_depth(minimum) == length
        with pytest.raises(ValueError):
            slide.slide_length_for_depth(minimum - 1)


def test_native_assembly_outputs_reject_inclined_roof():
    from cabineteer.assembly import build_assembly_plan, draft_mortise_panel_maps

    cfg = CabinetConfig(roof_angle_deg=5, back_style="under_top")
    for operation in (build_assembly_plan, draft_mortise_panel_maps):
        with pytest.raises(ValueError, match="inclined cabinets are not supported"):
            operation(cfg)


@pytest.mark.parametrize(
    "name",
    [
        "width",
        "height",
        "depth",
        "side_thickness",
        "top_thickness",
        "bottom_thickness",
        "back_thickness",
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, -1])
def test_inclined_dimensions_must_be_finite_positive(name, value):
    cfg = CabinetConfig(roof_angle_deg=5, back_style="under_top")
    setattr(cfg, name, value)
    with pytest.raises(ValueError, match=name):
        carcass_panel_dims(cfg)


@pytest.mark.parametrize("bad_recess", [False, True])
def test_evaluation_reports_stock_and_recess_errors(monkeypatch, bad_recess):
    from cabineteer import evaluation
    from cabineteer.drawer import DrawerConfig

    if bad_recess:

        def invalid_recess(**kwargs):
            return DrawerConfig(**kwargs, bottom_dado_inset=10)

        monkeypatch.setattr(evaluation, "DrawerConfig", invalid_recess)
    cfg = CabinetConfig(
        depth=550,
        drawer_box_thickness=15 if bad_recess else 18,
        openings=[[200, "drawer"]],
        drawer_slide=EB20_SLIDE_KEYS[480],
    )
    messages = [
        issue.message for issue in evaluation.check_drawer_carcass_clearances(cfg)
    ]
    assert any(
        ("bottom recess" if bad_recess else "drawer sides") in message
        for message in messages
    )
    assert not any("too shallow" in message for message in messages)

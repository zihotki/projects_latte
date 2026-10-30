from dataclasses import replace

import pytest
from cabineteer.assembly import (
    MortiseRow,
    PanelMortiseMap,
    _candidate_positions,
    _panel_svg,
    build_assembly_plan,
    draft_mortise_panel_maps,
    generate_draft_mortise_maps,
)
from cabineteer.joinery import DominoSpec

from buratino.engine import calculate
from buratino.project import load_project


def test_native_draft_maps_use_selected_spec_and_omit_machine_setup(project):
    cfg = calculate(load_project(project)).configs[0]
    spec = DominoSpec(size_key="6x40", max_spacing=123)
    cfg = replace(cfg, domino_spec=spec)
    plan = build_assembly_plan(cfg, domino_spec=spec)
    text = generate_draft_mortise_maps(cfg, "Test cabinet")

    assert plan.positions == tuple(
        round(p, 1) for p in spec.positions_for_span(cfg.interior_depth)
    )
    assert "Domino 6x40" in text
    assert "Face-row offsets are not specified" in text
    assert "not for machining" in text
    assert text.count("<svg") == 2
    positions = _candidate_positions(cfg.interior_depth, spec)
    assert all(f"{p:g}" in text for p in positions)
    assert "DF 500" not in text
    assert "groove" not in text.lower()
    assert build_assembly_plan(cfg).size_key != "6x40"


def test_side_map_uses_explicit_centered_rows_and_actual_thickness(project):
    cfg = calculate(load_project(project)).configs[0]
    cfg = replace(
        cfg,
        domino_spec=DominoSpec(size_key="6x40"),
        bottom_thickness=18,
        top_thickness=22,
    )
    assert "side" not in draft_mortise_panel_maps(cfg)
    maps = draft_mortise_panel_maps(cfg, centered_face_rows=True)
    side = maps["side"]
    assert "Thickness 22" in _panel_svg(maps["top"], panel_thickness=cfg.top_thickness)
    assert "Thickness 18" in _panel_svg(
        maps["bottom"], panel_thickness=cfg.bottom_thickness
    )
    assert "front edge at left" in side.width_label
    assert [row.offset for row in side.rows] == [9, cfg.height - 11]
    assert all(
        row.positions == _candidate_positions(cfg.interior_depth, cfg.domino_spec)
        for row in side.rows
    )
    assert all(row.kind == "face" for row in side.rows)
    assert set(maps) == {"side", "top", "bottom"}


def test_right_side_view_mirrors_positions_but_keeps_front_distances():
    import xml.etree.ElementTree as ET

    panel = PanelMortiseMap(
        panel="side",
        part_id="",
        draw_width=504,
        draw_height=970,
        canonical="side",
        width_label="depth",
        height_label="height",
        rows=(MortiseRow("bottom", "h", 9, (40, 460), "face"),),
    )
    left = ET.fromstring(_panel_svg(panel, precise_ticks=True))
    right = ET.fromstring(_panel_svg(panel, precise_ticks=True, front_at_right=True))
    ns = {"s": "http://www.w3.org/2000/svg"}
    left_marks = [float(e.get("cx")) for e in left.findall("s:ellipse", ns)]
    right_marks = [float(e.get("cx")) for e in right.findall("s:ellipse", ns)]
    assert left_marks[0] < left_marks[1]
    assert right_marks[0] > right_marks[1]
    left_ticks = {
        e.text: float(e.get("x"))
        for e in left.findall("s:text", ns)
        if e.text in {"40", "460"}
    }
    right_ticks = {
        e.text: float(e.get("x"))
        for e in right.findall("s:text", ns)
        if e.text in {"40", "460"}
    }
    assert left_ticks == dict(zip(("40", "460"), left_marks, strict=True))
    assert right_ticks == dict(zip(("40", "460"), right_marks, strict=True))
    assert (
        abs((left_marks[0] + right_marks[0]) - (left_marks[1] + right_marks[1])) < 0.2
    )


def test_native_draft_maps_skip_other_joinery(project):
    from cabineteer.cabinet import CarcassJoinery

    cfg = calculate(load_project(project)).configs[0]
    other = next(
        value for value in CarcassJoinery if value != CarcassJoinery.FLOATING_TENON
    )
    assert "unavailable" in generate_draft_mortise_maps(
        replace(cfg, carcass_joinery=other)
    )


def test_candidate_positions_respect_grid_clearance_and_spacing():
    spec = DominoSpec(size_key="6x40", max_spacing=123)
    assert _candidate_positions(503, spec) == (40, 140, 250, 350, 460)
    for span in (80, 89, 503, 508, 1000):
        positions = _candidate_positions(span, spec)
        assert positions
        assert all(p % 10 == 0 and 40 <= p <= span - 40 for p in positions)
        assert all(
            spec.size.nominal_width <= b - a <= spec.max_spacing
            for a, b in zip(positions, positions[1:], strict=False)
        )
        assert all(
            p >= spec.size.min_edge_distance + spec.size.nominal_width / 2
            and span - p >= spec.size.min_edge_distance + spec.size.nominal_width / 2
            for p in positions
        )
    assert _candidate_positions(140, replace(spec, max_spacing=50)) == (40, 70, 100)
    assert _candidate_positions(100, spec) == (40, 60)
    assert _candidate_positions(95, spec) == (50,)
    assert _candidate_positions(79, spec) == ()
    assert _candidate_positions(200, replace(spec, max_spacing=10)) == ()


def test_candidate_maps_are_unavailable_when_spacing_is_impossible(project):
    cfg = calculate(load_project(project)).configs[0]
    cfg = replace(cfg, domino_spec=DominoSpec(size_key="6x40", max_spacing=10))
    assert "unavailable" in generate_draft_mortise_maps(cfg)


def test_panel_codes_are_order_independent_and_distinguish_groups():
    from buratino.build import _coded_groups

    first = {"id": "left.side"}
    duplicate = {"id": "right.side"}
    other = {"id": "left.top"}
    mapping = {"left.side": "C01", "right.side": "C01", "left.top": "C02"}
    codes = _coded_groups([[first, duplicate], [other]], mapping)
    reordered = _coded_groups([[other], [duplicate, first]], mapping)
    assert [code for code, _ in codes] == [code for code, _ in reordered]
    assert {code for code, _ in codes} == {"C01", "C02"}
    assert _coded_groups([[first]], mapping)[0][0] == "C01"

    import pytest

    split = _coded_groups([[duplicate], [first]], mapping)
    assert [code for code, _ in split] == ["C01-01", "C01-02"]
    assert split == _coded_groups([[first], [duplicate]], mapping)
    with pytest.raises(ValueError, match="collision"):
        _coded_groups(
            [[first], [duplicate], [other]], {**mapping, "left.top": "C01-01"}
        )
    with pytest.raises(ValueError, match="missing"):
        _coded_groups([[{"id": "new"}]], mapping)


def test_hardware_details_render_nested_data_as_readable_text():
    from buratino.build import _hardware_table

    result = {
        "hardware": [
            {
                "type": "drawer_runner",
                "quantity_by_part_number": {"123": 2},
                "part_numbers": ["123"],
                "length_mm": 480,
            },
            {
                "type": "concealed_door_hinge",
                "doors": [
                    {
                        "door_id": "door",
                        "hinge_edge": "right",
                        "hinge_count": None,
                        "size_mm": {"x": 300, "z": 400, "y": 18},
                    }
                ],
            },
        ]
    }
    rendered = _hardware_table(result, {"door": "U01"})
    assert "123: 2" in rendered and "480" in rendered
    assert "U01" in rendered and "300 × 400 × 18 mm" in rendered
    assert "unverified" in rendered
    assert "{'" not in rendered and "None" not in rendered


def test_group_label_includes_each_distinct_component():
    from buratino.build import _group_label

    members = [
        {"id": "upper.section-1.bottom", "component": "bottom"},
        {"id": "upper.section-1.shelf", "component": "shelf"},
        {"id": "upper.section-2.shelf", "component": "shelf"},
    ]
    assert _group_label(members) == "Upper bottom and Upper shelf"


def test_mortise_summary_reports_computed_candidates(project):
    from buratino.build import _mortise_summary

    calculation = calculate(load_project(project))
    result = calculation.result
    summary = _mortise_summary(
        calculation.configs, result["cabinets"], result["joints"]
    )
    assert "4 carcass joints" in summary
    assert "4 candidate centers per joint" in summary
    assert "40, 170, 310, 450 mm" in summary
    assert "494 mm span" in summary
    assert "130, 140, 140 mm" in summary
    assert "40 and 44 mm" in summary
    assert "16 candidate tenons" in summary
    assert "candidate centers satisfy the configured grid" in summary
    assert "not determined" not in summary


def test_6x40_unknown_machining_is_not_treated_as_a_thickness_error(project):
    import pytest
    from cabineteer.assembly import generate_assembly_html
    from cabineteer.evaluation import check_domino_layout
    from cabineteer.joinery import apply_domino_mortises, miter_mortise_placement

    spec = DominoSpec(size_key="6x40")
    assert spec.size.nominal_width == 19.8
    assert spec.size.mortise_length is None
    assert spec.size.mortise_width is None
    assert spec.size.mortise_depth_per_side is None
    issues = check_domino_layout(spec, 494, 18)
    assert any(i.check == "domino_machining_unknown" for i in issues)
    assert not any(i.check == "domino_panel_thickness" for i in issues)
    assert any(
        i.check == "domino_span_too_short" for i in check_domino_layout(spec, 10, 18)
    )
    with pytest.raises(ValueError, match="unknown"):
        apply_domino_mortises(None, spec, 494, 0, 18)
    with pytest.raises(ValueError, match="unknown"):
        miter_mortise_placement(spec.size, 18)
    cfg = calculate(load_project(project)).configs[0]
    plan = build_assembly_plan(cfg, domino_spec=spec)
    with pytest.raises(ValueError, match="unknown"):
        generate_assembly_html([plan])
    assert (
        "actual slot dimensions and clearance are unknown"
        in generate_draft_mortise_maps(replace(cfg, domino_spec=spec))
    )


def test_mortise_summary_shows_supplied_router_depths(project):
    from buratino.build import _mortise_summary

    calculation = calculate(load_project(project))
    result = calculation.result
    machining = {
        "cutter_diameter_mm": 6,
        "face_depth_mm": {"min": 12, "max": 15},
        "edge_depth_mm": {"min": 25, "max": 28},
        "tenon_length_mm": 40,
        "face_wall_mm_by_cabinet": {"left-drawers": {"min": 3, "max": 6}},
    }
    summary = _mortise_summary(
        calculation.configs, result["cabinets"], result["joints"], machining
    )
    assert "cutter: 6 mm" in summary
    assert "face depth 12–15 mm" in summary and "edge depth 28–25 mm" in summary
    assert "totals 40 mm" in summary and "3–6 mm" in summary
    assert "no glue clearance" in summary


def test_real_bottom_map_matches_native_solid_and_side_mates(project):
    import xml.etree.ElementTree as ET

    from cabineteer.cabinet import make_bottom_panel

    cfg = calculate(load_project(project)).configs[0]
    maps = draft_mortise_panel_maps(cfg, centered_face_rows=True)
    bottom, top, side = maps["bottom"], maps["top"], maps["side"]
    bounds = make_bottom_panel(cfg).val().BoundingBox()
    assert (bottom.draw_width, bottom.draw_height) == (bounds.xlen, bounds.ylen)
    assert bottom.draw_width == 684
    assert bottom.draw_height == 494
    assert top.draw_height == 500
    assert side.draw_width == 500
    assert cfg.domino_spec.size.nominal_width == 19.8
    assert [row.offset for row in bottom.rows] == [0, bounds.xlen]
    assert all(row.kind == "edge" and row.axis == "v" for row in bottom.rows)
    assert all(row.positions == side.rows[0].positions for row in bottom.rows)
    assert side.rows[0].offset == cfg.bottom_thickness / 2
    assert all(0 < p < bounds.ylen for p in bottom.rows[0].positions)

    svg = ET.fromstring(_panel_svg(bottom, precise_ticks=True))
    ns = {"s": "http://www.w3.org/2000/svg"}
    labels = " ".join(e.text or "" for e in svg.findall("s:text", ns))
    assert all(
        label in labels
        for label in ("FRONT", "BACK", "LEFT SIDE", "RIGHT SIDE", "EDGE", "684", "494")
    )
    assert not svg.findall("s:ellipse", ns)
    marks = [e for e in svg.findall("s:line", ns) if e.get("stroke-width") == "3"]
    assert len(marks) == 2 * len(bottom.rows[0].positions)
    assert len({e.get("x1") for e in marks}) == 2
    assert sorted(e.get("y1") for e in marks[: len(marks) // 2]) == sorted(
        e.get("y1") for e in marks[len(marks) // 2 :]
    )


def test_native_center_dimensions_start_at_each_handed_front_datum():
    import xml.etree.ElementTree as ET

    import pytest

    panel = PanelMortiseMap(
        panel="side",
        part_id="",
        draw_width=500,
        draw_height=930,
        canonical="side",
        width_label="depth",
        height_label="height",
        rows=(MortiseRow("bottom", "h", 9, (40, 180, 460), "face"),),
    )
    ns = {"s": "http://www.w3.org/2000/svg"}
    for mirrored in (False, True):
        drawing = ET.fromstring(
            _panel_svg(panel, precise_ticks=True, front_at_right=mirrored)
        )
        outline = drawing.find("s:g/s:rect", ns)
        left = float(outline.get("x"))
        right = left + float(outline.get("width"))
        bottom = float(outline.get("y")) + float(outline.get("height"))
        dimensions = [
            line
            for line in drawing.findall("s:line", ns)
            if line.get("class") == "dimension"
            and float(line.get("y1")) == float(line.get("y2"))
            and float(line.get("y1")) > bottom
        ]
        assert len(dimensions) == 3
        assert len({line.get("y1") for line in dimensions}) == 3
        datum = right if mirrored else left
        for position, line in zip(panel.rows[0].positions, dimensions, strict=True):
            assert float(line.get("x1")) == pytest.approx(datum, abs=0.1)
            distance = abs(float(line.get("x2")) - float(line.get("x1")))
            assert distance / (right - left) == pytest.approx(position / 500, abs=0.001)
        assert drawing.findall("s:line[@class='extension']", ns)
        assert drawing.findall("s:line[@class='dimension-tick']", ns)


def test_mortise_maps_measure_from_back_for_both_faces_and_edges():
    import xml.etree.ElementTree as ET

    ns = {"s": "http://www.w3.org/2000/svg"}
    for mirrored in (False, True):
        panel = PanelMortiseMap(
            panel="side",
            part_id="",
            draw_width=503,
            draw_height=930,
            canonical="side",
            width_label="depth",
            height_label="height",
            rows=(MortiseRow("bottom", "h", 9, (40, 140), "face"),),
        )
        svg = ET.fromstring(
            _panel_svg(panel, front_at_right=mirrored, reference_back=True)
        )
        rect = svg.find("s:g/s:rect", ns)
        left = float(rect.get("x"))
        right = left + float(rect.get("width"))
        marks = [float(e.get("cx")) for e in svg.findall("s:ellipse", ns)]
        back = left if mirrored else right
        assert abs(marks[0] - back) / (right - left) == pytest.approx(
            40 / 503, abs=0.001
        )
        assert "BACK" in [e.text for e in svg.findall("s:text", ns)]

    panel = PanelMortiseMap(
        panel="bottom",
        part_id="",
        draw_width=684,
        draw_height=503,
        canonical="bottom",
        width_label="width",
        height_label="depth",
        rows=(MortiseRow("left", "v", 9, (40, 140), "edge"),),
    )
    svg = ET.fromstring(_panel_svg(panel, reference_back=True))
    rect = svg.find("s:g/s:rect", ns)
    top, height = float(rect.get("y")), float(rect.get("height"))
    marks = [e for e in svg.findall("s:line", ns) if e.get("stroke-width") == "3"]
    center = (float(marks[0].get("y1")) + float(marks[0].get("y2"))) / 2
    assert (center - top) / height == pytest.approx(40 / 503, abs=0.001)


@pytest.mark.parametrize(
    ("project_name", "groove_width"),
    [("two-under-window", 18), ("real-assembly-native", 12)],
)
def test_report_and_guide_share_part_drawings_and_machining_dimensions(
    root, tmp_path, project_name, groove_width
):
    from buratino.build import render_documents

    result = calculate(load_project(root / "projects" / project_name)).result
    part = next(
        part
        for part in result["parts"]
        if any(cut.get("role") == "bottom_groove" for cut in part["operations"])
    )
    svg = '<svg data-test="modeled-part"><path d="M0 0 L100 0"/></svg>'
    render_documents(tmp_path, result, panel_views={part["id"]: svg})
    report = (tmp_path / "report.html").read_text()
    guide = (tmp_path / "assembly.html").read_text()
    for document in (report, guide):
        assert svg in document
        assert f"Bottom groove: {groove_width} mm wide × 6 mm deep" in document
        assert "bottom inset 13 mm" in document
        assert '<a href="preview.html">Model</a>' in document
        assert '<a href="report.html#cutlists">Cut lists</a>' in document
        assert '<a href="assembly.html">Assembly guide</a>' in document
        assert "Quantity:" in document and "Stock:" in document
        assert "Hardware requirements" in document
        for obsolete in (
            "Resolved machining operations",
            "Profile operations",
            "Resolved spaces",
            "Plan diagnostics",
            "Physical validation",
            "Candidate mortise layout is unavailable",
            "Record ID",
            "local_profile_mm",
            "bottom_groove",
        ):
            assert obsolete not in document
    assert 'id="cutlists"' in report
    assert "Carcass mortise layout" not in guide

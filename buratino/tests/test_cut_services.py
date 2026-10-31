"""Provider export contracts from captured stock records."""

import csv
from copy import deepcopy
from io import StringIO

import pytest

from buratino.cut_services import plan_export


def space_part(ident="/cabinet/top", *, dimensions=(180, 400, 18), grain="x", bands=()):
    part = {
        "id": ident,
        "material": "birch",
        "quantity": 1,
        "stock": {
            "dimensions": list(dimensions),
            "thickness": dimensions[2],
            "thickness_axis": 2,
        },
        "stock_mm": {
            "length": max(dimensions[:2]),
            "width": min(dimensions[:2]),
            "thickness": dimensions[2],
        },
        "grain_status": "confirmed" if grain in "xyz" else "unverified",
        "grain_axis_local": grain if grain in "xyz" else None,
        "grain_direction": "none" if grain == "none" else "unknown",
        "edge_banding": [
            {"id": f"band-{i}", "edge": edge, "color": "#abcdef", "thickness_mm": 0}
            for i, edge in enumerate(bands)
        ],
    }
    if grain == "none":
        part["grain_status"] = "nondirectional"
    return part


def rows(plan, *, delimiter):
    return [
        list(csv.reader(StringIO(content), delimiter=delimiter))
        for content in plan.files.values()
    ]


def test_zagen_exact_header_shorter_grain_and_unchanged_band_dimensions():
    plain = space_part("/cabinet/plain")
    banded = space_part("/cabinet/banded", bands=("y-", "y+"))
    result = plan_export({"parts": [plain, banded]}, "zagenzagen")
    assert len(result.files) == 1
    content = next(iter(result.files.values()))
    assert content.startswith("Naam;Aantal;Lengte;Breedte;LV;LA;BL;BR\n")
    parsed = rows(result, delimiter=";")[0]
    assert parsed[1][2:4] == parsed[2][2:4] == ["180", "400"]
    assert sorted(row[4:] for row in parsed[1:]) == [
        ["", "", "", ""],
        ["7", "7", "", ""],
    ]
    assert result.status == "review"  # Supplier product eligibility remains open.
    assert result.summary["trace"][1]["original_stock_mm"]["thickness"] == 18
    assert result.summary["trace"][1]["edges"]["y-"]["kind"] == "band"


def test_negative_show_face_swaps_signed_w_edges_without_mirroring():
    part = space_part(bands=("y-",))
    default = plan_export({"parts": [part]}, "zagenzagen")
    flipped = plan_export(
        {"parts": [part]}, "zagenzagen", {"parts": {part["id"]: {"show_face": "b"}}}
    )
    assert rows(default, delimiter=";")[0][1][4:] == ["7", "", "", ""]
    assert rows(flipped, delimiter=";")[0][1][4:] == ["", "7", "", ""]
    assert flipped.summary["trace"][0]["basis"]["W"] == "y-"
    assert flipped.summary["trace"][0]["basis"]["origin_sides"]["y"] == "max"


def test_space_thickness_x_has_negative_w_and_signed_edge_mapping():
    part = {
        "id": "/x-thick",
        "material": "birch",
        "quantity": 1,
        "stock": {"dimensions": [18, 400, 180], "thickness": 18, "thickness_axis": 0},
        "stock_mm": {"length": 400, "width": 180, "thickness": 18},
        "grain_status": "confirmed",
        "grain_axis_local": "z",
        "edge_banding": [{"edge": "y+", "thickness_mm": 0}],
    }
    z = plan_export({"parts": [part]}, "zagenzagen")
    op = plan_export({"parts": [part]}, "opmaatzagen")
    assert z.summary["trace"][0]["basis"]["W"] == "y-"
    assert rows(z, delimiter=";")[0][1][2:5] == ["180", "400", "7"]
    assert rows(op, delimiter=",")[0][1][1:3] == ["180", "400"]
    assert rows(op, delimiter=",")[0][1][4] == "Long side 2"


def test_op_multi_edge_is_quoted_one_row_with_uniform_finish():
    part = space_part(bands=("y-", "x+"))
    plan = plan_export({"parts": [part]}, "opmaatzagen")
    content = next(iter(plan.files.values()))
    assert content.startswith(
        "Aantal,Lengte (mm),Breedte (mm),Eigen kenmerk,"
        "Afwerking zijdes,Afwerking type\n"
    )
    assert '"Long side 2, Short side 2",Edge band matching - 1mm' in content
    assert len(rows(plan, delimiter=",")[0]) == 2
    assert plan.status == "review"
    assert "opmaatzagen_multi_edge_unverified" in {
        i["code"] for i in plan.summary["issues"]
    }


def test_op_mixed_finishes_exports_one_plain_blank_for_manual_selection():
    part = space_part(bands=("y-",))
    plan = plan_export(
        {"parts": [part]},
        "opmaatzagen",
        {
            "parts": {
                part["id"]: {
                    "edge_finishes": {
                        "x+": {"kind": "chamfer", "size_mm": 2, "face": "b"}
                    }
                }
            }
        },
    )
    assert rows(plan, delimiter=",")[0][1][4:] == ["", ""]
    assert plan.summary["row_count"] == 1
    assert "opmaatzagen_mixed_finishes" in {i["code"] for i in plan.summary["issues"]}


def test_zagen_opposing_rule_and_exact_finish_codes():
    part = space_part(bands=("y-", "x+"))
    manual = plan_export({"parts": [part]}, "zagenzagen")
    assert rows(manual, delimiter=";")[0][1][4:] == ["", "", "", ""]
    assert "zagenzagen_band_eligibility" in {
        i["code"] for i in manual.summary["issues"]
    }
    plain = space_part(bands=())
    encoded = plan_export(
        {"parts": [plain]},
        "zagenzagen",
        {
            "parts": {
                plain["id"]: {
                    "edge_finishes": {
                        "y-": {"kind": "chamfer", "face": "both", "size_mm": 2},
                        "x-": {"kind": "roundover", "face": "a", "size_mm": 3},
                        "x+": {"kind": "mitre", "face": "b"},
                    }
                }
            }
        },
    )
    assert rows(encoded, delimiter=";")[0][1][4:] == ["3", "", "4", "9"]
    assert encoded.status == "complete"


def test_op_exact_finish_strings_and_override_declared_band():
    part = space_part(dimensions=(400, 180, 18), bands=("y-",))
    plan = plan_export(
        {"parts": [part]},
        "opmaatzagen",
        {
            "parts": {
                part["id"]: {
                    "edge_finishes": {
                        "y-": {"kind": "roundover", "face": "both", "size_mm": 4}
                    }
                }
            }
        },
    )
    assert rows(plan, delimiter=",")[0][1][4:] == [
        "Long side 2",
        "Rounding off top and bottom - 4mm",
    ]
    assert plan.status == "complete"


def test_zagen_splits_physical_quantity_at_500_and_preserves_trace():
    part = space_part(grain="none")
    part["quantity"] = 1001
    plan = plan_export({"parts": [part], "source_revision": "abc"}, "zagenzagen")
    assert len(plan.files) == 3
    assert [int(chunk[1][1]) for chunk in rows(plan, delimiter=";")] == [500, 500, 1]
    assert [group["quantity"] for group in plan.summary["groups"]] == [500, 500, 1]
    assert plan.summary["source_revision"] == "abc"
    assert plan.summary["trace"][0]["quantity"] == 1001


def test_groups_separate_material_panel_thickness_and_provider_context():
    parts = [
        space_part(f"/p/{i}", dimensions=(100, 200, thickness), grain="none")
        for i, thickness in enumerate((18, 18, 18.4))
    ]
    parts[1]["material"] = "oak"
    plan = plan_export(
        {"parts": parts},
        "opmaatzagen",
        {
            "materials": {
                "birch": {
                    "panel_type": "veneered",
                    "provider_material": "Birch veneer",
                    "purchase_type": "panel",
                }
            }
        },
    )
    assert len(plan.files) == 3
    assert any(
        name.startswith("opmaatzagen-birch-veneered-18mm-") for name in plan.files
    )
    assert any(
        name.startswith("opmaatzagen-birch-veneered-18.4mm-") for name in plan.files
    )
    assert {(g["material"], g["thickness_mm"]) for g in plan.summary["groups"]} == {
        ("birch", 18),
        ("oak", 18),
        ("birch", 18.4),
    }
    assert any(g["provider_material"] == "Birch veneer" for g in plan.summary["groups"])


def test_invalid_blank_and_missing_grain_keep_other_rows():
    valid = space_part("/valid", grain="x")
    invalid = space_part("/invalid", dimensions=(0, 200, 18), grain="x")
    unknown = space_part("/unknown", grain="unknown")
    plan = plan_export(
        {"parts": [valid, invalid, unknown]},
        "opmaatzagen",
        {"materials": {"birch": {"grain_required": True}}},
    )
    assert plan.status == "partial"
    assert plan.summary["row_count"] == 1
    assert [item["outcome"] for item in plan.summary["trace"]] == [
        "exported",
        "omitted",
        "omitted",
    ]
    assert sum(item["severity"] == "partial" for item in plan.summary["issues"]) == 2


def test_fractional_space_blank_rounds_up_without_band_compensation():
    plain = space_part("/plain", dimensions=(1450.2, 500, 18), bands=())
    banded = space_part("/banded", dimensions=(1450.2, 500, 18), bands=("y-",))
    source = deepcopy([plain, banded])
    plan = plan_export({"parts": [plain, banded]}, "zagenzagen")
    data = rows(plan, delimiter=";")[0]
    assert data[1][2:4] == data[2][2:4] == ["1451", "500"]
    assert sorted(row[4:] for row in data[1:]) == [["", "", "", ""], ["7", "", "", ""]]
    assert plan.summary["trace"][0]["original_stock_mm"]["length"] == 1450.2
    assert plan.summary["trace"][0]["order_dimensions_mm"]["length"] == 1451
    assert plan.summary["trace"][0]["rounding_allowance_mm"]["length"] == 0.8
    assert [plain, banded] == source
    assert (
        sum(item["code"] == "stock_rounded_up" for item in plan.summary["issues"]) == 2
    )


def test_fractional_native_profile_rounds_up_and_keeps_source_operations():
    frame = {
        "origin_mm": [10, 20, 30],
        "length_axis": [0, 0, 1],
        "width_axis": [0, 1, 0],
        "thickness_axis": [-1, 0, 0],
    }
    part = {
        "id": "native.fraction",
        "material": "oak",
        "quantity": 1,
        "stock_mm": {"length": 1450.2, "width": 500.1, "thickness": 18.4},
        "local_frame": frame,
        "operations": [{"type": "bevel", "leg_a": 2.5, "leg_b": 2.5}],
    }
    source = deepcopy(part)
    plan = plan_export({"parts": [part]}, "opmaatzagen")
    assert rows(plan, delimiter=",")[0][1][1:3] == ["1451", "501"]
    assert plan.summary["groups"][0]["thickness_mm"] == 18.4
    assert plan.summary["trace"][0]["original_stock_mm"] == source["stock_mm"]
    assert part == source


def test_general_blank_preserves_order_and_warns_when_edges_cannot_be_mapped():
    part = {
        "id": "general.part",
        "material": "M",
        "quantity": 1,
        "blank_mm": {"length": 300, "width": 120, "thickness": 19},
        "grain_direction": "width",
    }
    plain = plan_export({"parts": [part]}, "opmaatzagen")
    assert rows(plain, delimiter=",")[0][1][1:3] == ["120", "300"]
    requested = plan_export(
        {"parts": [part]},
        "opmaatzagen",
        {"parts": {part["id"]: {"edge_finishes": {"x+": {"kind": "band"}}}}},
    )
    assert rows(requested, delimiter=",")[0][1][4:] == ["", ""]
    assert "missing_stock_axes" in {i["code"] for i in requested.summary["issues"]}
    axes_unknown = plan_export(
        {"parts": [part]}, "opmaatzagen", {"parts": {part["id"]: {"grain_axis": "x"}}}
    )
    assert axes_unknown.status == "partial"
    assert not axes_unknown.files


def test_native_frame_keeps_local_lwt_and_world_trace():
    frame = {
        "origin_mm": [10, 20, 30],
        "length_axis": [0, 0, 1],
        "width_axis": [0, 1, 0],
        "thickness_axis": [-1, 0, 0],
    }
    part = {
        "id": "native.side",
        "material": "oak",
        "quantity": 2,
        "stock_mm": {"length": 210, "width": 500, "thickness": 18},
        "local_frame": frame,
    }
    plan = plan_export({"parts": [part]}, "zagenzagen")
    assert rows(plan, delimiter=";")[0][1][2:4] == ["210", "500"]
    assert plan.summary["trace"][0]["frame_world"] == frame
    assert plan.summary["trace"][0]["basis"] == {
        "L": "x+",
        "W": "y+",
        "A": "z+",
        "origin_sides": {"x": "min", "y": "min"},
    }


def test_bad_part_id_is_reported_per_part():
    plan = plan_export(
        {"parts": [{"id": ["bad"], "material": "M"}, space_part(grain="none")]},
        "opmaatzagen",
    )
    assert plan.status == "partial"
    assert plan.summary["row_count"] == 1
    assert plan.summary["trace"][0]["outcome"] == "omitted"


def test_huge_json_integer_in_part_does_not_stop_valid_peer():
    bad = {
        "id": "/huge",
        "material": "birch",
        "quantity": 1,
        "blank_mm": {"length": 10**1000, "width": 100, "thickness": 18},
    }
    plan = plan_export(
        {"parts": [bad, space_part("/valid", grain="none")]}, "opmaatzagen"
    )
    assert plan.status == "partial"
    assert plan.summary["row_count"] == 1
    assert [item["outcome"] for item in plan.summary["trace"]] == [
        "omitted",
        "exported",
    ]


def test_huge_json_integer_in_global_finish_size_is_value_error():
    part = space_part()
    with pytest.raises(ValueError, match="size_mm must be positive"):
        plan_export(
            {"parts": [part]},
            "zagenzagen",
            {
                "parts": {
                    part["id"]: {
                        "edge_finishes": {
                            "y-": {"kind": "chamfer", "size_mm": 10**1000}
                        }
                    }
                }
            },
        )


@pytest.mark.parametrize(
    "config",
    [
        {"extra": {}},
        {"materials": {"M": {"grain_required": "yes"}}},
        {"parts": {"stale": {"grain_axis": "x"}}},
        {
            "parts": {
                "/cabinet/top": {
                    "edge_finishes": {"x+": {"kind": "band", "size_mm": 0}}
                }
            }
        },
    ],
)
def test_invalid_global_config_is_rejected(config):
    with pytest.raises(ValueError):
        plan_export({"parts": [space_part()]}, "zagenzagen", config)


@pytest.mark.parametrize(
    "provider,delimiter,qindex,lindex",
    [
        ("opmaatzagen", ",", 0, 3),
        ("zagenzagen", ";", 1, 0),
    ],
)
def test_report_codes_merge_identical_parts_and_trace_chunk_sources(
    provider, delimiter, qindex, lindex
):
    parts = [space_part("a"), space_part("b"), space_part("c")]
    parts[0]["quantity"] = 300
    parts[1]["quantity"] = 301
    parts[2]["quantity"] = 1
    captured = {"parts": parts, "report_part_codes": {p["id"]: "P07" for p in parts}}
    plan = plan_export(captured, provider)
    reverse = plan_export({**captured, "parts": list(reversed(parts))}, provider)
    assert plan.files == reverse.files
    parsed = [row for chunk in rows(plan, delimiter=delimiter) for row in chunk[1:]]
    assert [int(row[qindex]) for row in parsed] == (
        [500, 102] if provider == "zagenzagen" else [602]
    )
    assert {row[lindex] for row in parsed} == {"P07"}
    for source in plan.summary["trace"]:
        assert (
            sum(item["quantity"] for item in source["csv_rows"]) == source["quantity"]
        )
        for location in source["csv_rows"]:
            data = list(
                csv.reader(StringIO(plan.files[location["file"]]), delimiter=delimiter)
            )
            assert data[location["row"] - 1][lindex] == source["label"]
    for group in plan.summary["groups"]:
        assert (
            sum(
                source["quantity"] for row in group["rows"] for source in row["sources"]
            )
            == group["quantity"]
        )
    if provider == "opmaatzagen":
        content = next(iter(plan.files.values()))
        assert len(content.split("\n")) == 2
        assert all(len(record.split(",")) == 6 for record in content.split("\n"))
    else:
        assert all(group["quantity"] <= 500 for group in plan.summary["groups"])
        assert len(plan.summary["trace"][1]["csv_rows"]) == 2


@pytest.mark.parametrize(
    "difference", ["grain", "finish", "machining", "exact_blank", "material", "code"]
)
def test_matching_code_does_not_merge_different_order_requirements(difference):
    first, second = space_part("a"), space_part("b")
    codes = {"a": "P01", "b": "P01"}
    config = None
    if difference == "grain":
        second["grain_axis_local"] = "y"
    elif difference == "finish":
        # Unsupported finishes produce equal CSV blanks, but remain distinct orders.
        config = {
            "parts": {
                "b": {"edge_finishes": {"y-": {"kind": "roundover", "size_mm": 3}}}
            }
        }
    elif difference == "machining":
        second["operations"] = [{"type": "drill", "diameter": 5}]
    elif difference == "exact_blank":
        second["stock"]["dimensions"][0] = 179.9
        second["stock_mm"]["width"] = 179.9
    elif difference == "material":
        second["material"] = "oak"
    else:
        codes["b"] = "P02"
    plan = plan_export(
        {"parts": [first, second]}, "opmaatzagen", config, part_codes=codes
    )
    assert plan.summary["row_count"] == 2
    trace = plan.summary["trace"]
    assert len({entry["label"] for entry in trace}) == 2
    assert all(len(entry["label"]) <= 24 for entry in trace)
    assert {entry["part_code"] for entry in trace} == set(codes.values())


def test_native_copy_placement_does_not_split_report_group():
    first = {
        "id": "a",
        "material": "oak",
        "quantity": 1,
        "stock_mm": {"length": 400, "width": 180, "thickness": 18},
        "grain_direction": "none",
        "grain_status": "nondirectional",
        "local_frame": {
            "origin_mm": [0, 0, 0],
            "length_axis": [1, 0, 0],
            "width_axis": [0, 1, 0],
            "thickness_axis": [0, 0, 1],
        },
    }
    second = deepcopy(first)
    second["id"] = "b"
    second["local_frame"]["origin_mm"] = [100, 200, 300]
    plan = plan_export(
        {"parts": [first, second]}, "opmaatzagen", part_codes={"a": "P01", "b": "P01"}
    )
    assert rows(plan, delimiter=",")[0][1][:4] == ["2", "400", "180", "P01"]
    assert plan.summary["trace"][1]["frame_world"]["origin_mm"] == [100, 200, 300]


def test_chunk_boundary_can_split_one_row_after_a_different_row():
    first, second = space_part("a"), space_part("b")
    first["quantity"], second["quantity"] = 499, 3
    plan = plan_export({"parts": [first, second]}, "zagenzagen")
    assert [group["quantity"] for group in plan.summary["groups"]] == [500, 2]
    assert sorted(
        item["quantity"] for item in plan.summary["trace"][1]["csv_rows"]
    ) == [1, 2]
    assert (
        sum(int(row[1]) for chunk in rows(plan, delimiter=";") for row in chunk[1:])
        == 502
    )


@pytest.mark.parametrize(
    "provider,delimiter,lindex",
    [
        ("opmaatzagen", ",", 3),
        ("zagenzagen", ";", 0),
    ],
)
def test_csv_aliases_preserve_custom_report_codes_and_bound_variants(
    provider, delimiter, lindex
):
    codes = {
        "a": "LEFT SIDE",
        "b": "a" * 20 + "-01",
        "c": "L01",
        "d": "P07",
        "e": "x" * 20,
        "f": "x" * 20,
        "g": "x" * 17 + "-01",
    }
    parts = [space_part(ident) for ident in codes]
    # Two different order variants of a report code at the label-length boundary.
    config = {"parts": {"f": {"show_face": "b"}}}
    captured = {"parts": parts, "report_part_codes": codes}
    plan = plan_export(captured, provider, config)
    reverse = plan_export(
        {**captured, "parts": list(reversed(parts))}, provider, config
    )
    assert plan.files == reverse.files
    labels = {item["source_id"]: item["label"] for item in plan.summary["trace"]}
    assert len(set(labels.values())) == len(parts)
    assert labels["c"] == "L01"
    assert labels["d"] == "P07"
    assert labels["g"] == codes["g"]
    assert all(0 < len(label) <= 20 and " " not in label for label in labels.values())
    assert {
        item["source_id"]: item["part_code"] for item in plan.summary["trace"]
    } == codes
    assert captured["report_part_codes"] == codes
    assert {
        row[lindex] for chunk in rows(plan, delimiter=delimiter) for row in chunk[1:]
    } == set(labels.values())

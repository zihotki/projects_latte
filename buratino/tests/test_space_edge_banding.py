import csv

from buratino.build import render_documents
from buratino.engine import calculate, make_geometry
from buratino.project import load_project


def test_buratino_keeps_original_part_and_exports_band_view(root, tmp_path):
    project = load_project(root / "projects/machined-drawer")
    calculation = calculate(project)
    result = calculation.result
    side = next(
        part for part in result["parts"] if part["id"] == "/cabinet/carcass/side_left"
    )
    assert side["edge_banding"][0]["edge"] == "y-"
    assert side["edge_banding"][0]["thickness_mm"] == 0

    assembly, geometry = make_geometry(calculation)
    viewer_part = assembly.objects[side["role"]]
    assert viewer_part.name == side["role"]
    assert len(viewer_part.children) >= 2
    physical_part = next(part for part in geometry if part.name == side["role"])
    assert (
        physical_part.shape.val().Volume()
        == calculation.space_shapes[side["id"]].val().Volume()
    )

    without_band_metadata = {
        **result,
        "parts": [dict(part) for part in result["parts"]],
    }
    for part in without_band_metadata["parts"]:
        part.pop("edge_banding", None)
    with_band = tmp_path / "with-band"
    without_band = tmp_path / "without-band"
    with_band.mkdir()
    without_band.mkdir()
    render_documents(with_band, result)
    render_documents(without_band, without_band_metadata)
    with_band_csv = (with_band / "parts.csv").read_bytes()
    without_band_csv = (without_band / "parts.csv").read_bytes()
    assert with_band_csv == without_band_csv
    with (with_band / "parts.csv").open(newline="") as stream:
        assert next(csv.reader(stream)) == [
            "status",
            "part_code",
            "quantity",
            "max_blank_length_mm",
            "max_blank_width_mm",
            "blank_thickness_mm",
            "material",
            "grain_direction",
            "grain_status",
            "part_ids",
            "operation_record_ids",
        ]

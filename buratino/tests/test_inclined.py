from cabineteer.hettich_eb20 import EB20_SLIDE_KEYS

from buratino.engine import calculate
from buratino.project import load_project


def test_example_parts_match_native_stock(root):
    result = calculate(load_project(root / "projects/inclined-cabinet")).result
    parts = {p["component"]: p["finished_mm"] for p in result["parts"]}
    assert parts["left_side"]["length"] < parts["right_side"]["length"]
    assert not result["joints"]


def test_legacy_slide_key_export():
    from buratino.drawers import EB20_SLIDE_KEY

    assert EB20_SLIDE_KEYS[450] == EB20_SLIDE_KEY

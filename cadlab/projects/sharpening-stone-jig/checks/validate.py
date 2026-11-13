"""Run with cadlab/bin/cadlab python; checks only this design, in a temporary copy."""

import json
import math
import shutil
import tempfile
from pathlib import Path

from soma import build, params

PROJECT = Path(__file__).resolve().parents[1]


def near(actual, expected):
    assert abs(actual - expected) < 1e-5, (actual, expected)


def check(root, values):
    (root / "parameters.json").write_text(json.dumps({"values": values}))
    parts = build.run_model(root)
    assert parts
    return build.LAST_RUN[1]


def inside(shape, point):
    return shape.val().isInside(point, 1e-6)


with tempfile.TemporaryDirectory(prefix="sharpening-jig-check-") as tmp:
    root = Path(tmp)
    shutil.copy2(PROJECT / "model.py", root / "model.py")
    shutil.copytree(PROJECT / "parts", root / "parts")
    state = check(root, {})
    specs = list(params.PARAMS)
    base = state["base"]
    bb = base.val().BoundingBox()
    for actual, expected in zip(
        (bb.xlen, bb.ylen, bb.zlen), (95, 190, 30), strict=True
    ):
        near(actual, expected)
    assert inside(base, (0, 0, 24.99))
    assert not inside(base, (0, 0, 25.01))
    # Check the four pocket boundaries away from the removal notch.
    for sign in (-1, 1):
        assert not inside(base, (sign * 37.79, 0, 29))
        assert inside(base, (sign * 37.81, 0, 29))
    assert not inside(base, (0, 85.29, 29))
    assert inside(base, (0, 85.31, 29))
    near(state["plate"].val().BoundingBox().zmax - bb.zmax, 1)
    for shape, angle, y in zip(state["placed"], (15, 20), (-42.5, 42.5), strict=True):
        face = max(shape.val().Faces(), key=lambda f: f.Area())
        normal = face.normalAt()
        near(math.degrees(math.acos(abs(normal.z))), angle)
        assert inside(shape, (43, y, 30.01))
        assert not inside(shape, (43, y, 29.99))
        assert not inside(shape, (0, y, 31.39))
        assert inside(shape, (0, y, 31.41))
        assert not inside(shape, (47.7, y, 28))
        assert inside(shape, (47.9, y, 28))
    cases = [({}, "default measured geometry")]
    numbers = [p for p in specs if p["kind"] == "number"]
    for spec in numbers:
        for limit in ("min", "max"):
            cases.append(({spec["name"]: spec[limit]}, f"{spec['name']} {limit}"))
    cases.extend(
        [
            ({"LAYOUT": "Print", "COUPON": True}, "print with fit coupon"),
            ({"REFERENCES": False}, "hide reference parts"),
            ({"COUPON": True}, "assembled fit coupon"),
            ({"ANGLE_A": 14.0, "ANGLE_B": 16.0}, "additional kitchen angles"),
            (
                {
                    "STONE_LENGTH": 140,
                    "GUIDE_RUN": 35,
                    "ANGLE_A": 25,
                    "ANGLE_B": 25,
                    "LAYOUT": "Print",
                    "COUPON": True,
                },
                "short stone with long steep guides and coupon",
            ),
        ]
    )
    for limit in ("min", "max"):
        values = {p["name"]: p[limit] for p in numbers}
        cases.append((values, f"all numeric {limit}"))
        cases.append(
            (dict(values, LAYOUT="Print", COUPON=True), f"print all numeric {limit}")
        )
    for values, label in cases:
        state = check(root, values)
        if values.get("COUPON"):
            coupon = state["coupon"]
            cb = coupon.val().BoundingBox()
            near(cb.xlen, state["OUTER_WIDTH"])
            # Test both opposing walls, so FIT changes the sample pocket width.
            y = cb.ymin + 20
            half = state["POCKET_WIDTH"] / 2
            for sign in (-1, 1):
                assert not inside(coupon, (cb.center.x + sign * (half - 0.01), y, 3.01))
                assert inside(coupon, (cb.center.x + sign * (half + 0.01), y, 3.01))
        if values.get("LAYOUT") == "Print":
            assert all(part["role"] == "part" for part in build.registry.REGISTRY)
            for shape in state["placed"]:
                face = max(shape.val().Faces(), key=lambda f: f.Area())
                near(face.normalAt().z, -1)
        print("PASS", label, flush=True)
    print(
        f"Passed {len(cases)} cases and independent dimension, clearance, "
        "and angle checks."
    )

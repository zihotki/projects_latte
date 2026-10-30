"""Build and update translation-only Space physical part records."""
from __future__ import annotations


IDENTITY_AXES = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def box_part(id, kind, dimensions, translation, material, thickness, thickness_axis, **extra):
    """Create a box part and derive its published aliases from stock and placement."""
    part = {
        "id": id,
        "kind": kind,
        "material": material,
        "thickness": thickness,
        "profile": {"type": "box"},
        "stock": {"thickness": thickness, "thickness_axis": thickness_axis},
        "transform": {"axes": [axis.copy() for axis in IDENTITY_AXES]},
        "operations": [],
        **extra,
    }
    update_box_part(part, dimensions=dimensions, translation=translation)
    return part


def update_box_part(part, *, dimensions=None, translation=None):
    """Update stock or placement, then derive all box geometry aliases."""
    if dimensions is not None:
        part["stock"]["dimensions"] = list(dimensions)
    if translation is not None:
        part["transform"]["translation"] = list(translation)

    size = list(part["stock"]["dimensions"])
    origin = list(part["transform"]["translation"])
    part["size"] = size
    part["origin"] = origin
    part["profile"]["size"] = size.copy()
    part["bounds"] = [origin.copy(), [point + span for point, span in zip(origin, size)]]


def check_box_part(part):
    """Return whether published box aliases match stock and translation."""
    try:
        size = part["stock"]["dimensions"]
        origin = part["transform"]["translation"]
        expected_bounds = [list(origin), [point + span for point, span in zip(origin, size)]]
        return (
            part["size"] == size
            and part["profile"]["size"] == size
            and part["origin"] == origin
            and part["bounds"] == expected_bounds
        )
    except (KeyError, TypeError):
        return False

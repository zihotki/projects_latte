"""Hettich EB20 profile adapter and native drawer construction helpers."""

from __future__ import annotations

import math

from cabineteer.hettich_eb20 import (
    EB20_SLIDE_KEY as EB20_SLIDE_KEY,
)
from cabineteer.hettich_eb20 import (
    EB20_SLIDE_KEYS,
    HETTICH_PROFILE,
    HETTICH_PROFILES,
)


def eb20_profile_for_key(slide_key):
    """Return sourced metadata for a registered EB20 slide key."""
    for length, key in EB20_SLIDE_KEYS.items():
        if slide_key == key:
            return HETTICH_PROFILES[length]
    raise ValueError("Unsupported EB20 slide profile.")


def register_eb20_profile(runner_length_mm=450):
    """Register a sourced length and explicit design allowances."""
    from cabineteer.hardware import SLIDES

    return SLIDES[EB20_SLIDE_KEYS[runner_length_mm]]


EB20_SLIDE = register_eb20_profile()
EB20_SLIDE_480 = register_eb20_profile(480)
EB20_SLIDE_380 = register_eb20_profile(380)


def make_eb20_drawer_config(
    *,
    opening_width: float,
    opening_height: float,
    opening_depth: float,
    side_thickness: float,
    front_back_thickness: float,
    bottom_thickness: float,
    box_height: float,
    vertical_gap: float = 0,
    bottom_dado_depth: float = 6,
    bottom_dado_inset: float = 12,
    front_gap: float = 0,
    face_thickness: float = 18,
    face_overlay_sides: float = 16,
    face_overlay_top: float = 3,
    face_overlay_bottom: float = 3,
    material: str = "drawer_stock_unverified",
    joinery_style=None,
    rear_corner_clearance_width_mm: float = 0,
    runner_length_mm: int = 450,
):
    """Return native DrawerConfig for a sourced EB20 selection.

    ``box_height`` and ``vertical_gap`` are project choices. Vertical hardware
    limits stay unknown and are not inferred.
    """
    from cabineteer.drawer import DrawerConfig
    from cabineteer.joinery import DrawerJoineryStyle

    if runner_length_mm not in HETTICH_PROFILES:
        supported = ", ".join(str(length) for length in sorted(HETTICH_PROFILES))
        raise ValueError(f"This profile supports only {supported} mm runners.")
    source = HETTICH_PROFILES[runner_length_mm]
    if side_thickness > HETTICH_PROFILE["side_thickness_max_mm"]:
        raise ValueError("EB20 drawer sides must be 16 mm or thinner.")
    if opening_depth < source["minimum_body_depth_mm"]:
        raise ValueError(
            f"EB20 needs at least {source['minimum_body_depth_mm']} mm "
            "usable cavity depth at the runner reference plane."
        )
    if not 12 <= bottom_dado_inset <= 13:
        raise ValueError("The documented EB20 draft recess range is 12 to 13 mm.")
    if joinery_style is not None and joinery_style != DrawerJoineryStyle.BUTT:
        raise ValueError("This adapter supports only native butt-corner drawer boxes.")
    # This project value controls box placement from the opening bottom.
    # DrawerConfig needs the total clearance above the box to resolve its
    # native height. It is derived from the explicit box-height choice.
    if vertical_gap < 0 or box_height + vertical_gap > opening_height:
        raise ValueError("Box height and bottom clearance must fit the opening.")
    native_top_gap = opening_height - box_height
    cfg = DrawerConfig(
        opening_width=opening_width,
        opening_height=opening_height,
        opening_depth=opening_depth,
        side_thickness=side_thickness,
        front_back_thickness=front_back_thickness,
        bottom_thickness=bottom_thickness,
        bottom_dado_depth=bottom_dado_depth,
        bottom_dado_inset=bottom_dado_inset,
        front_gap=front_gap,
        vertical_gap=native_top_gap,
        slide_key=EB20_SLIDE_KEYS[runner_length_mm],
        joinery_style=DrawerJoineryStyle.BUTT,
        use_standard_height=False,
        applied_face=False,
        face_thickness=face_thickness,
        face_overlay_sides=face_overlay_sides,
        face_overlay_top=face_overlay_top,
        face_overlay_bottom=face_overlay_bottom,
    )
    # Material is a project output value; native DrawerConfig does not own it.
    cfg.buratino_material = material
    cfg.buratino_box_bottom_clearance_mm = vertical_gap
    cfg.buratino_rear_corner_clearance_width_mm = rear_corner_clearance_width_mm
    validate_drawer_config(cfg)
    return cfg


def validate_drawer_config(cfg):
    """Validate the resolved native box and the supported draft recipe."""
    from cabineteer.joinery import DrawerJoineryStyle

    def number(value, name, *, positive=True):
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or (value <= 0 if positive else value < 0)
        ):
            kind = "positive" if positive else "non-negative"
            raise ValueError(f"{name} must be finite and {kind}.")

    for name in (
        "opening_width",
        "opening_height",
        "opening_depth",
        "side_thickness",
        "front_back_thickness",
        "bottom_thickness",
        "face_thickness",
        "bottom_dado_depth",
    ):
        number(getattr(cfg, name), name)
    for name in ("vertical_gap", "front_gap", "bottom_dado_inset"):
        number(getattr(cfg, name), name, positive=False)
    clearance = getattr(cfg, "buratino_box_bottom_clearance_mm", 0)
    relief = getattr(cfg, "buratino_rear_corner_clearance_width_mm", 0)
    number(clearance, "box bottom clearance", positive=False)
    number(relief, "rear corner relief", positive=False)
    if cfg.joinery_style != DrawerJoineryStyle.BUTT:
        raise ValueError("This adapter supports only native butt-corner drawer boxes.")
    if cfg.side_thickness > HETTICH_PROFILE["side_thickness_max_mm"]:
        raise ValueError("EB20 drawer sides must be 16 mm or thinner.")
    minimum_depth = eb20_profile_for_key(cfg.slide_key)["minimum_body_depth_mm"]
    if cfg.opening_depth < minimum_depth:
        raise ValueError(
            f"EB20 needs at least {minimum_depth} mm usable cavity depth "
            "at the runner reference plane."
        )
    if not 12 <= cfg.bottom_dado_inset <= 13:
        raise ValueError("The documented EB20 draft recess range is 12 to 13 mm.")
    if cfg.bottom_dado_depth >= min(cfg.side_thickness, cfg.front_back_thickness):
        raise ValueError(
            "Bottom groove depth must be less than side and front/back stock thickness."
        )
    for name in (
        "box_width",
        "box_height",
        "box_depth",
        "front_back_panel_length",
        "bottom_panel_width",
        "bottom_panel_depth",
    ):
        number(getattr(cfg, name), name)
    if cfg.bottom_dado_inset + cfg.bottom_thickness > cfg.box_height:
        raise ValueError("Bottom groove and stock must fit the box height.")
    if relief > 30:
        raise ValueError(
            "Rear corner relief exceeds the supported 30 mm draft recipe limit."
        )
    if 2 * relief >= cfg.front_back_panel_length:
        raise ValueError(
            "Rear corner relief must leave a positive center on the back panel."
        )
    if cfg.box_height + clearance > cfg.opening_height:
        raise ValueError("Drawer box height and bottom clearance must fit the opening.")


def drawer_shapes(cfg, *, rear_corner_clearance_width_mm: float = 0):
    """Build native drawer parts and return their local offsets.

    Rear back-corner relief is the only post-processing operation. It is a
    draft interpretation of the Hettich sketch, not approved machining.
    """
    from cabineteer.drawer import (
        drawer_part_offsets,
        make_drawer_bottom,
        make_drawer_face,
        make_drawer_front_back,
        make_drawer_side,
    )

    shapes = {
        "side_left": make_drawer_side(cfg, "left"),
        "side_right": make_drawer_side(cfg, "right"),
        "inner_front": make_drawer_front_back(cfg, "front"),
        "back": make_drawer_front_back(cfg, "back"),
        "bottom": make_drawer_bottom(cfg),
    }
    if rear_corner_clearance_width_mm:
        import cadquery as cq

        clear = rear_corner_clearance_width_mm
        relief_height = cfg.bottom_dado_inset
        for x in (0, cfg.front_back_panel_length - clear):
            cutter = (
                cq.Workplane("XY")
                .transformed(offset=(x, 0, 0))
                .box(clear, cfg.front_back_thickness, relief_height, centered=False)
            )
            shapes["back"] = shapes["back"].cut(cutter)
    if cfg.applied_face:
        shapes["face"] = make_drawer_face(cfg)
    native = drawer_part_offsets(cfg)
    offsets = {
        "side_left": native["side_L"],
        "side_right": native["side_R"],
        "inner_front": native["sub_front"],
        "back": native["back"],
        "bottom": native["bottom"],
    }
    if "face" in shapes:
        offsets["face"] = (
            -(cfg.face_width - cfg.box_width) / 2,
            -cfg.face_thickness,
            -cfg.face_overlay_bottom,
        )
    return shapes, offsets

"""Hettich EB20 profile adapter and native drawer construction helpers."""

from __future__ import annotations

import math

HETTICH_PROFILE = {
    "manufacturer": "Hettich",
    "model": "Quadro V6 Silent System, EB20, slide-on",
    "runner_length_mm": 450,
    "left_runner_sku": "9047751",
    "right_runner_sku": "9047752",
    "side_thickness_max_mm": 16,
    "installation_width_per_side_mm": 20,
    "minimum_body_depth_mm": 463,
    "box_length_mm": 450,
    "bottom_underside_recess_mm": {"min": 12, "max": 13},
    "sources": [
        "https://shop.hettich.com/nl_NL/Ladegeleidersystemen/Verborgen-ladegeleiders/Ladegeleiders-Quadro/Quadro-V6/c/group15252148656799",
        "https://shop.hettich.com/gb_EN/Runner-systems/Concealed-drawer-runners/Quadro-drawer-runners/Quadro-V6/Quadro-V6-with-Silent-System%2C-450-mm%2C-left/p/9047751",
        "https://shop.hettich.com/us_EN/Runner-systems/Concealed-drawer-runners/Quadro-drawer-runners/Quadro-V6/Quadro-V6-with-Silent-System%2C-450-mm%2C-right/p/9047752",
        "https://hta.hettich.com/en-de/runner-systems/quadro/quadro-v6",
        "https://www.hettich.com/fileadmin/Media_Center/Catalogue/HAU_Quadro_Runner_15789_en.pdf",
    ],
    "design_allowances": {
        "side_clearance_per_side_mm": 20,
        "box_bottom_recess_mm": "selected within sourced 12-13 mm range",
        "vertical_gap_mm": "project-selected per opening",
        "front_gap_mm": 0,
    },
    "unverified": [
        "minimum and maximum side clearance",
        "vertical runner clearance",
        "mounting details",
        "catch identity and adjustment",
        "load capacity",
    ],
}
HETTICH_PROFILES = {
    450: HETTICH_PROFILE,
    480: {
        **HETTICH_PROFILE,
        "runner_length_mm": 480,
        "left_runner_sku": "9047756",
        "right_runner_sku": "9047757",
        "minimum_body_depth_mm": 493,
        "box_length_mm": 480,
        "sources": [
            "https://shop.hettich.com/gb_EN/Runner-systems/Concealed-drawer-runners/Quadro-drawer-runners/Quadro-V6/Quadro-V6-with-Silent-System%2C-480-mm%2C-left/p/9047756",
            "https://shop.hettich.com/gb_EN/Runner-systems/Concealed-drawer-runners/Quadro-drawer-runners/Quadro-V6/Quadro-V6-with-Silent-System%2C-480-mm%2C-right/p/9047757",
            "https://hta.hettich.com/fileadmin/Hettich_Technical_Assistant/PDFs/MTA_929680000_QV6_SFG_SFD_EB20.pdf",
        ],
    },
}
EB20_SLIDE_KEY = "buratino_hettich_quadro_v6_eb20"
EB20_SLIDE_KEYS = {450: EB20_SLIDE_KEY, 480: f"{EB20_SLIDE_KEY}_480"}


def register_eb20_profile(runner_length_mm=450):
    """Register a sourced length and explicit design allowances."""
    from cabineteer.hardware import (
        SLIDES,
        ClearanceReference,
        DrawerSlideSpec,
        SlideMountLocation,
        SlideType,
    )

    source = HETTICH_PROFILES[runner_length_mm]
    profile = DrawerSlideSpec(
        name=f"Hettich Quadro V6 EB20 {runner_length_mm} mm",
        manufacturer="Hettich",
        slide_type=SlideType.UNDERMOUNT,
        mount_location=SlideMountLocation.BOTTOM,
        # The 20 mm installation width is sourced. Hettich limits are not
        # established here; the native model's min/max fields hold this
        # selected allowance and stay labeled unverified in project output.
        min_side_clearance=20,
        max_side_clearance=20,
        nominal_side_clearance=20,
        min_top_clearance=0,
        min_bottom_clearance=0,
        available_lengths=(runner_length_mm,),
        max_load_kg=30,
        min_drawer_height=0,
        max_drawer_width=0,
        rear_bracket_inset=0,
        front_bracket_inset=0,
        part_numbers={
            runner_length_mm: [source["left_runner_sku"], source["right_runner_sku"]]
        },
        # The published sketch gives a 12-13 mm range, not one required value.
        bottom_recess=None,
        clearance_reference=ClearanceReference.INSIDE,
    )
    SLIDES[EB20_SLIDE_KEYS[runner_length_mm]] = profile
    return profile


EB20_SLIDE = register_eb20_profile()
EB20_SLIDE_480 = register_eb20_profile(480)


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
        raise ValueError("This profile supports only 450 or 480 mm runners.")
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
    length = next(
        (length for length, key in EB20_SLIDE_KEYS.items() if key == cfg.slide_key),
        None,
    )
    if length is None:
        raise ValueError("Unsupported EB20 slide profile.")
    minimum_depth = HETTICH_PROFILES[length]["minimum_body_depth_mm"]
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

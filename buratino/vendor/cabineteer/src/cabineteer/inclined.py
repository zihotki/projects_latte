"""Geometry for a bare cabinet with a straight inclined roof."""

import math


def resolve(cfg):
    for name in ("width", "height", "depth", "side_thickness", "top_thickness",
                 "bottom_thickness", "back_thickness"):
        value = getattr(cfg, name)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive for an inclined cabinet.")
    angle = math.radians(cfg.roof_angle_deg)
    if not math.isfinite(angle) or abs(angle) >= math.pi / 2:
        raise ValueError("Roof angle must be finite and between -90 and 90 degrees.")
    if (cfg.openings or cfg.columns or cfg.fixed_shelf_positions or cfg.adj_shelf_holes
            or cfg.edge_band_mode != "none" or cfg.carcass_corner_style != "butt"
            or cfg.back_capture not in ("pocket", "overlay")
            or cfg.carcass_joinery.value == "dado_rabbet"
            or (cfg.back_capture == "pocket" and cfg.back_style != "under_top")):
        raise ValueError("Inclined cabinets support only bare butt cases with an unmachined back.")
    slope = math.tan(angle)
    intercept = cfg.height - max(0, slope * cfg.width)
    thickness_z = cfg.top_thickness / math.cos(angle)
    if cfg.width <= 2 * cfg.side_thickness or min(intercept, intercept + slope * cfg.width) <= thickness_z + cfg.bottom_thickness:
        raise ValueError("Inclined roof leaves no usable cabinet interior.")
    return slope, intercept, thickness_z


def height_at(cfg, x):
    slope, intercept, _ = resolve(cfg)
    return intercept + slope * x


def blank_sizes(cfg):
    slope, _, drop = resolve(cfg)
    t, w = cfg.side_thickness, cfg.width
    left = max(height_at(cfg, 0), height_at(cfg, t)) - drop
    right = max(height_at(cfg, w - t), height_at(cfg, w)) - drop
    angle = math.radians(cfg.roof_angle_deg)
    top = w / math.cos(angle) + cfg.top_thickness * abs(math.tan(angle))
    if cfg.back_capture == "overlay":
        back = max(height_at(cfg, 0), height_at(cfg, w))
    else:
        back = max(height_at(cfg, t), height_at(cfg, w - t)) - drop
    return left, right, top, back


def prism(points, depth):
    """Extrude an X/Z profile towards positive Y."""
    import cadquery as cq
    return cq.Workplane("XZ").polyline(points).close().extrude(depth).translate((0, depth, 0))

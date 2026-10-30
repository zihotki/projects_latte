"""Stock-face layouts from resolved mortises, beside the actual CAD overview."""

from dataclasses import dataclass
from html import escape
from itertools import groupby


@dataclass(frozen=True)
class MortiseFace:
    selector: str
    label: str
    axes: tuple[str, str]
    size: tuple[float, float]
    cuts: tuple[dict, ...]
    centers_world: tuple
    rims_world: tuple
    inward_world: tuple


def mortise_faces(part: dict) -> list[MortiseFace]:
    """Use stock coordinates; signed faces do not reverse the U/V datum.

    Space face U/V are the two remaining XYZ axes in ascending order. Native
    local frames use L/W/T for the same recorded coordinate slots. Native
    profile pockets are not treated as mortises.
    """
    cuts = [
        cut
        for cut in part.get("operations", [])
        if cut.get("type") == "mortise" and "face" in cut
    ]
    if not cuts:
        return []
    native = part.get("local_frame")
    stock = part.get("stock", {})
    if native:
        size = [part["stock_mm"][key] for key in ("length", "width", "thickness")]
        thickness = 2
        names = ("L", "W", "T")
        origin = native["origin_mm"]
        axes = [native[key] for key in ("length_axis", "width_axis", "thickness_axis")]
    else:
        thickness = stock.get("thickness_axis")
        if thickness not in (0, 1, 2):
            # A missing stock axis cannot safely classify an edge as a face.
            return []
        size = stock.get("dimensions") or part["profile"]["size"]
        names = ("X", "Y", "Z")
        transform = part.get("transform", {})
        origin = transform.get("translation", (0, 0, 0))
        axes = transform.get("axes", ((1, 0, 0), (0, 1, 0), (0, 0, 1)))

    def world(point):
        return tuple(
            origin[i] + sum(point[j] * axes[j][i] for j in range(3)) for i in range(3)
        )

    result = []
    for selector, members in groupby(
        sorted(cuts, key=lambda cut: cut["face"]), key=lambda cut: cut["face"]
    ):
        normal = "xyz".index(selector[0])
        uv = [i for i in range(3) if i != normal]
        face_cuts = tuple(sorted(members, key=lambda cut: (cut["u"], cut["v"])))
        centers, rims = [], []
        for cut in face_cuts:
            point = [0.0, 0.0, 0.0]
            point[normal] = size[normal] if selector[1] == "+" else 0.0
            point[uv[0]], point[uv[1]] = cut["u"], cut["v"]
            centers.append(world(point))
            along = uv[0 if cut["axis"] == "u" else 1]
            across = next(i for i in uv if i != along)
            rim = []
            # Tip and side points lie on the real capsule rim, at its cut plane.
            for axis, distance in (
                (along, cut["length"] / 2),
                (across, cut["width"] / 2),
            ):
                for sign in (-1, 1):
                    edge = point.copy()
                    edge[axis] += sign * distance
                    rim.append(world(edge))
            rims.append(tuple(rim))
        inward = tuple(
            value * (-1 if selector[1] == "+" else 1) for value in axes[normal]
        )
        end = "max" if selector[1] == "+" else "min"
        label = "PANEL FACE" if normal == thickness else "PANEL EDGE"
        result.append(
            MortiseFace(
                selector,
                f"{label} · {names[normal]} {end} ({selector})",
                tuple(names[i] for i in uv),
                tuple(size[i] for i in uv),
                face_cuts,
                tuple(centers),
                tuple(rims),
                inward,
            )
        )
    return result


def _text(x, y, value, size=12, anchor="start", color="#163e50"):
    return (
        f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size}" '
        f'text-anchor="{anchor}" fill="{color}">{escape(value)}</text>'
    )


def _center_rows(cuts):
    """Combine repeated station lists without losing the U/V correspondence."""
    options = []
    for fixed, varying in (("v", "u"), ("u", "v")):
        rows = {}
        for cut in cuts:
            rows.setdefault(cut[fixed], set()).add(cut[varying])
        groups = {}
        for station, values in sorted(rows.items()):
            groups.setdefault(tuple(sorted(values)), []).append(station)
        options.append((len(groups), fixed, varying, groups))
    _, fixed, varying, groups = min(options, key=lambda option: option[0])
    lines = []
    for values, stations in groups.items():
        lines.append(f"{fixed.upper()} = " + ", ".join(f"{v:g}" for v in stations))
        # Bound text length at 38 characters for the 360 px viewport.
        prefix = f"{varying.upper()} = "
        line = prefix
        for value in values:
            token = f"{value:g}"
            if len(line) + len(token) + 2 > 38:
                lines.append(line.rstrip(", "))
                line = "    "
            line += token + ", "
        lines.append(line.rstrip(", "))
    return lines


def mortise_layouts(part: dict, start_y: float) -> tuple[str, float]:
    """Draw true-proportion stock faces with strong slot rims and centre marks.

    These are coordinate layouts, not camera views: +U/+V always increase from
    the stock minimum edges, including on negative faces. The axis key makes
    the rotation used to fit a narrow edge explicit.
    """
    output = []
    y = start_y
    for face in mortise_faces(part):
        swap = face.size[1] > face.size[0]
        horizontal, vertical = (1, 0) if swap else (0, 1)
        width, height = face.size[horizontal], face.size[vertical]
        scale = min(286 / width, 190 / height)
        specs = sorted({(c["length"], c["width"], c["depth"]) for c in face.cuts})
        left, top = 48.0, y + 97 + 18 * (len(specs) - 1)
        right, bottom = left + width * scale, top + height * scale
        xname, yname = ("U", "V")[horizontal], ("U", "V")[vertical]
        output.append(
            f'<g class="mortise-stock-layout" data-face="{face.selector}" '
            f'data-horizontal="{xname}" data-vertical="{yname}">'
        )
        output += [
            _text(12, y + 17, face.label, 14),
            _text(12, y + 35, "Stock-face layout · all dimensions in mm", 11),
            _text(
                12,
                y + 52,
                f"Right: +{xname} ({face.axes[horizontal]}) · "
                f"Up: +{yname} ({face.axes[vertical]})",
                12,
            ),
        ]
        for spec_index, (length, width_mm, depth) in enumerate(specs):
            count = sum(
                (c["length"], c["width"], c["depth"]) == (length, width_mm, depth)
                for c in face.cuts
            )
            output.append(
                _text(
                    12,
                    y + 70 + spec_index * 18,
                    f"{count} slots: {length:g} × {width_mm:g} · {depth:g} mm deep",
                    13,
                )
            )
        # A separate scale for each stock face makes the edge's true narrow
        # surface visible. The slot dimensions use exactly that same scale.
        output.append(
            f'<rect class="stock-face" x="{left:.3f}" y="{top:.3f}" '
            f'width="{width * scale:.3f}" height="{height * scale:.3f}" '
            'fill="#f2f5f7" stroke="#465c68" stroke-width="1.2"/>'
        )
        output.append(
            f'<path d="M{left:.3f} {top - 8:.3f} H{right:.3f} '
            f"M{left:.3f} {top - 12:.3f} v8 "
            f'M{right:.3f} {top - 12:.3f} v8" '
            'stroke="#465c68" fill="none"/>'
        )
        output.append(
            _text((left + right) / 2, top - 14, f"{xname}: {width:g}", 11, "middle")
        )
        mid = (top + bottom) / 2
        output.append(
            f'<text x="31" y="{mid:.3f}" font-size="11" '
            f'text-anchor="middle" fill="#163e50" '
            f'transform="rotate(-90 31 {mid:.3f})">'
            f"{yname}: {height:g}</text>"
        )
        for cut in face.cuts:
            uv = (cut["u"], cut["v"])
            x = left + uv[horizontal] * scale
            cy = bottom - uv[vertical] * scale
            long_horizontal = (cut["axis"] == "u") != swap
            w, h = (
                (cut["length"], cut["width"])
                if long_horizontal
                else (cut["width"], cut["length"])
            )
            output.append(
                f'<rect class="mortise-rim" data-u="{cut["u"]:g}" '
                f'data-v="{cut["v"]:g}" x="{x - w * scale / 2:.3f}" '
                f'y="{cy - h * scale / 2:.3f}" width="{w * scale:.3f}" '
                f'height="{h * scale:.3f}" rx="{cut["width"] * scale / 2:.3f}" '
                'fill="#ffc66d" stroke="#8c3600" stroke-width="1.5"/>'
                f'<path class="mortise-center" d="M{x - 3:.3f} {cy:.3f} h6 '
                f'M{x:.3f} {cy - 3:.3f} v6" stroke="#3f1a00" '
                'stroke-width="1" fill="none"/>'
            )
        output.append(
            f'<circle class="stock-datum" cx="{left:.3f}" '
            f'cy="{bottom:.3f}" r="3" fill="#163e50"/>'
        )
        row_y = bottom + 20
        output.append(_text(12, row_y, "Datum ●: U=0 / V=0 at stock min edges", 11))
        output.append(_text(12, row_y + 17, "Centre stations from datum (U/V):", 12))
        lines = _center_rows(face.cuts)
        for index, line in enumerate(lines):
            output.append(_text(20, row_y + 35 + index * 15, line, 12))
        output.append("</g>")
        y = row_y + 49 + len(lines) * 15
    return "".join(output), y

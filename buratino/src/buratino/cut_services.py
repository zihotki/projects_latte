"""Pure conversion of captured stock records to cut-service CSV files."""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from hashlib import sha256
from io import StringIO


@dataclass(frozen=True)
class ExportPlan:
    files: dict[str, str]
    summary: dict
    status: str


@dataclass(frozen=True)
class PanelOrder:
    source_id: str
    label: str
    material: str
    panel_type: str
    provider_material: str | None
    purchase_type: str | None
    quantity: int
    length: int
    width: int
    thickness: int | float
    original_blank: dict
    stock_length: int | float
    stock_width: int | float
    grain: str
    grain_status: str
    basis: dict | None
    frame_world: dict | None
    edges: dict[str, dict]


_AXES = "xyz"
_SIGNED_EDGES = {f"{axis}{side}" for axis in _AXES for side in "-+"}
_ZAGEN_FIELDS = ("Naam", "Aantal", "Lengte", "Breedte", "LV", "LA", "BL", "BR")
_OP_FIELDS = (
    "Aantal",
    "Lengte (mm)",
    "Breedte (mm)",
    "Eigen kenmerk",
    "Afwerking zijdes",
    "Afwerking type",
)


def _issue(
    issues: list[dict],
    code: str,
    message: str,
    part_id: str | None = None,
    severity: str = "review",
) -> None:
    issue = {"code": code, "message": message, "severity": severity}
    if part_id is not None:
        issue["part_id"] = part_id
    issues.append(issue)


def _finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _positive_finite(value: object, name: str) -> int | float:
    if not _finite_number(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return value


def _positive_quantity(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("quantity must be a positive integer")
    return value


def _round_up_mm(value: int | float) -> int:
    # Values within 1e-6 mm above a whole number are float noise.
    return math.ceil(value - 1e-6)


def _validate_config(config: dict | None, parts: list[dict]) -> dict:
    if config is None:
        return {"materials": {}, "parts": {}}
    if not isinstance(config, dict) or set(config) - {"materials", "parts"}:
        raise ValueError("config must contain only materials and parts maps")
    materials = config.get("materials", {})
    overrides = config.get("parts", {})
    if not isinstance(materials, dict) or not isinstance(overrides, dict):
        raise ValueError("config materials and parts must be maps")
    ids = {
        part["id"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("id"), str)
    }
    for material, entry in materials.items():
        if not isinstance(material, str) or not material or not isinstance(entry, dict):
            raise ValueError("each material config entry must be a named map")
        if set(entry) - {
            "panel_type",
            "provider_material",
            "purchase_type",
            "grain_required",
        }:
            raise ValueError(f"material {material!r}: unknown config field")
        for key in ("panel_type", "provider_material", "purchase_type"):
            if key in entry and (
                not isinstance(entry[key], str) or not entry[key].strip()
            ):
                raise ValueError(f"material {material!r}: {key} must be nonempty text")
        if "grain_required" in entry and not isinstance(entry["grain_required"], bool):
            raise ValueError(f"material {material!r}: grain_required must be boolean")
    for part_id, entry in overrides.items():
        if not isinstance(part_id, str) or part_id not in ids:
            raise ValueError(f"unknown source part ID in config: {part_id!r}")
        if not isinstance(entry, dict) or set(entry) - {
            "grain_axis",
            "show_face",
            "edge_finishes",
        }:
            raise ValueError(f"part {part_id!r}: unknown or invalid config field")
        if "grain_axis" in entry and entry["grain_axis"] not in (*_AXES, "none"):
            raise ValueError(f"part {part_id!r}: grain_axis must be x, y, z, or none")
        if "show_face" in entry and entry["show_face"] not in (
            *_SIGNED_EDGES,
            "a",
            "b",
        ):
            raise ValueError(
                f"part {part_id!r}: show_face must be a or b or signed stock face"
            )
        finishes = entry.get("edge_finishes", {})
        if not isinstance(finishes, dict):
            raise ValueError(f"part {part_id!r}: edge_finishes must be a map")
        for edge, finish in finishes.items():
            if edge not in _SIGNED_EDGES or not isinstance(finish, dict):
                raise ValueError(f"part {part_id!r}: invalid signed edge finish")
            if set(finish) - {"kind", "face", "size_mm"}:
                raise ValueError(f"part {part_id!r} {edge}: unknown finish field")
            kind = finish.get("kind")
            if not isinstance(kind, str) or kind not in {
                "band",
                "chamfer",
                "roundover",
                "mitre",
            }:
                raise ValueError(f"part {part_id!r} {edge}: invalid finish kind")
            face = finish.get("face", "a")
            if not isinstance(face, str) or face not in {"a", "b", "both"}:
                raise ValueError(f"part {part_id!r} {edge}: invalid finish face")
            if kind == "band":
                if "size_mm" in finish or "face" in finish:
                    raise ValueError(
                        f"part {part_id!r} {edge}: band has no size or face"
                    )
            elif kind in {"chamfer", "roundover"}:
                size = finish.get("size_mm")
                if not _finite_number(size) or size <= 0:
                    raise ValueError(
                        f"part {part_id!r} {edge}: size_mm must be positive"
                    )
            elif "size_mm" in finish:
                raise ValueError(f"part {part_id!r} {edge}: mitre has no size_mm")
    return {"materials": materials, "parts": overrides}


def _label(part_id: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9_-]+", "-", part_id).strip("-")[-42:] or "part"
    return f"{readable}-{sha256(part_id.encode()).hexdigest()[:10]}"


def _filename_hint(material: str, panel_type: str, thickness: int | float) -> str:
    def token(value: str, limit: int) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:limit].strip("-")

    material_hint = token(material, 24) or "material"
    panel_hint = token(panel_type, 16) if len(panel_type) <= 16 else ""
    thickness_hint = str(thickness).replace("+", "plus")
    thickness_hint = re.sub(r"[^A-Za-z0-9.]+", "-", thickness_hint)[:20]
    hints = [material_hint]
    if panel_hint:
        hints.append(panel_hint)
    hints.append(f"{thickness_hint}mm")
    return "-".join(hints)


def _basis(a: str, length_axis: str) -> dict:
    # Signed unit vectors, in the source's local stock XYZ frame.
    unit = {
        axis + sign: tuple(
            (1 if axis == dim else 0) * (1 if sign == "+" else -1) for dim in _AXES
        )
        for axis in _AXES
        for sign in "+-"
    }
    av, lv = unit[a], unit[length_axis]
    wv = (
        av[1] * lv[2] - av[2] * lv[1],
        av[2] * lv[0] - av[0] * lv[2],
        av[0] * lv[1] - av[1] * lv[0],
    )
    if wv == (0, 0, 0):
        raise ValueError("grain axis is the stock thickness axis")

    def signed(vector: tuple[int, int, int]) -> str:
        index = next(i for i, value in enumerate(vector) if value)
        return _AXES[index] + ("+" if vector[index] > 0 else "-")

    w = signed(wv)
    return {
        "L": length_axis,
        "W": w,
        "A": a,
        "origin_sides": {
            length_axis[0]: "min" if length_axis[1] == "+" else "max",
            w[0]: "min" if w[1] == "+" else "max",
        },
    }


def _edge_map(basis: dict) -> dict[str, str]:
    def other(signed_axis: str) -> str:
        return signed_axis[0] + ("-" if signed_axis[1] == "+" else "+")

    return {
        "v0": other(basis["W"]),
        "vW": basis["W"],
        "u0": other(basis["L"]),
        "uL": basis["L"],
    }


def _convert(
    part: dict, material_config: dict, override: dict, issues: list[dict]
) -> PanelOrder:
    source_id = part.get("id")
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("part has no source ID")
    material = part.get("material")
    if not isinstance(material, str) or not material:
        raise ValueError("part has no material ID")
    quantity = _positive_quantity(part.get("quantity", 1))
    stock = part.get("stock")
    native = isinstance(part.get("local_frame"), dict)
    space = isinstance(stock, dict) and "dimensions" in stock
    blank = part.get("blank_mm") or part.get("stock_mm") or part.get("finished_mm")
    if not isinstance(blank, dict):
        raise ValueError("part has no ordered stock blank")
    original = {
        key: _positive_finite(blank.get(key), f"blank {key}")
        for key in ("length", "width", "thickness")
    }
    frame_world = part["local_frame"] if native else None
    axis_dimensions = None
    a = None
    if space:
        raw_dimensions = stock["dimensions"]
        thickness_axis = stock.get("thickness_axis")
        if (
            not isinstance(raw_dimensions, list | tuple)
            or len(raw_dimensions) != 3
            or type(thickness_axis) is not int
            or thickness_axis not in (0, 1, 2)
        ):
            raise ValueError("invalid Space stock axes")
        axis_dimensions = {
            axis: _positive_finite(raw_dimensions[i], f"stock {axis}")
            for i, axis in enumerate(_AXES)
        }
        a = _AXES[thickness_axis] + "+"
        if abs(axis_dimensions[a[0]] - original["thickness"]) > 1e-6:
            raise ValueError("Space stock thickness differs from blank")
        stock_planar = sorted(axis_dimensions[axis] for axis in _AXES if axis != a[0])
        blank_planar = sorted((original["length"], original["width"]))
        if any(
            abs(left - right) > 1e-6
            for left, right in zip(stock_planar, blank_planar, strict=True)
        ):
            raise ValueError("Space stock planar sizes differ from blank")
    elif native:
        for key in ("origin_mm", "length_axis", "width_axis", "thickness_axis"):
            vector = frame_world.get(key)
            if (
                not isinstance(vector, list | tuple)
                or len(vector) != 3
                or any(not _finite_number(value) for value in vector)
            ):
                raise ValueError("invalid native local frame")
        length_vector = frame_world["length_axis"]
        width_vector = frame_world["width_axis"]
        normal_vector = frame_world["thickness_axis"]
        cross = (
            length_vector[1] * width_vector[2] - length_vector[2] * width_vector[1],
            length_vector[2] * width_vector[0] - length_vector[0] * width_vector[2],
            length_vector[0] * width_vector[1] - length_vector[1] * width_vector[0],
        )
        if any(abs(cross[i] - normal_vector[i]) > 1e-5 for i in range(3)):
            raise ValueError("native local frame is not right-handed")
        if any(
            abs(sum(value * value for value in vector) - 1) > 1e-5
            for vector in (length_vector, width_vector, normal_vector)
        ):
            raise ValueError("native local frame axes must have unit length")
        axis_dimensions = dict(zip(_AXES, original.values(), strict=True))
        a = "z+"
    else:
        # General records preserve ordered blanks, but have no verified stock-edge axes.
        axis_dimensions = None
    grain = override.get("grain_axis")
    if grain is None:
        if (
            part.get("grain_status") == "nondirectional"
            or part.get("grain_direction") == "none"
        ):
            grain = "none"
        elif (part.get("grain_status") == "confirmed" or native) and part.get(
            "grain_axis_local"
        ) in tuple(_AXES):
            grain = part["grain_axis_local"]
        elif (
            not space
            and not native
            and part.get("grain_direction") in {"length", "width"}
        ):
            grain = part["grain_direction"]
        else:
            grain = "unknown"
    grain_status = (
        "configured"
        if "grain_axis" in override
        else part.get("grain_status", "unverified")
    )
    if not isinstance(grain_status, str):
        grain_status = "unverified"
    if grain == "unknown":
        _issue(
            issues,
            "unknown_grain",
            "Grain axis is not confirmed; check direction before ordering.",
            source_id,
        )
    elif grain in {"length", "width"} and grain_status != "confirmed":
        _issue(
            issues,
            "grain_unconfirmed",
            "Ordered blank grain direction needs confirmation before ordering.",
            source_id,
        )
    if material_config.get("grain_required") and not (
        grain in _AXES and grain_status in {"confirmed", "configured"}
    ):
        raise ValueError("required grain axis is not confirmed")
    basis = None
    if a is not None:
        if grain in _AXES and grain == a[0]:
            raise ValueError("grain axis is the stock thickness axis")
        show = override.get("show_face", "a")
        if show == "b":
            a = a[0] + "-"
        elif show not in {"a", "b"}:
            if show[0] != a[0]:
                raise ValueError("show_face does not select a thickness face")
            a = show
        l_axis = (
            grain if grain in _AXES else next(axis for axis in _AXES if axis != a[0])
        )
        basis = _basis(a, l_axis + "+")
        stock_length = axis_dimensions[basis["L"][0]]
        stock_width = axis_dimensions[basis["W"][0]]
    else:
        if grain in _AXES:
            raise ValueError(
                "grain axis cannot be mapped to a blank without stock axes"
            )
        if override.get("show_face") is not None:
            _issue(
                issues,
                "missing_stock_axes",
                "Show face cannot be mapped without stock axes.",
                source_id,
            )
        stock_length, stock_width = original["length"], original["width"]
        if grain == "width":
            stock_length, stock_width = stock_width, stock_length
    length, width = _round_up_mm(stock_length), _round_up_mm(stock_width)
    if length <= 0 or width <= 0:
        raise ValueError("stock blank is too small for whole-mm ordering")
    if length - stock_length > 1e-6 or width - stock_width > 1e-6:
        _issue(
            issues,
            "stock_rounded_up",
            "Stock Length or Width was rounded up to a whole millimetre for ordering.",
            source_id,
        )
    edges = {}
    bands = part.get("edge_banding", [])
    if not isinstance(bands, list):
        raise ValueError("edge_banding must be a list")
    for band in bands:
        edge = band.get("edge") if isinstance(band, dict) else None
        if edge not in _SIGNED_EDGES:
            _issue(
                issues,
                "invalid_declared_band",
                "Declared band has no valid signed stock edge.",
                source_id,
            )
        else:
            edges[edge] = {"kind": "band"}
    edges.update(override.get("edge_finishes", {}))
    panel_type = material_config.get("panel_type", part.get("panel_type", "panel"))
    if not isinstance(panel_type, str) or not panel_type:
        raise ValueError("part has no valid panel type")
    return PanelOrder(
        source_id,
        _label(source_id),
        material,
        panel_type,
        material_config.get("provider_material"),
        material_config.get("purchase_type"),
        quantity,
        length,
        width,
        original["thickness"],
        original,
        stock_length,
        stock_width,
        grain,
        grain_status,
        basis,
        frame_world,
        edges,
    )


def _finish_zagen(finish: dict) -> str | None:
    kind, face = finish["kind"], finish.get("face", "a")
    if kind == "band":
        return "7"
    if kind == "chamfer" and finish.get("size_mm") == 2:
        return {"a": "1", "b": "2", "both": "3"}[face]
    if kind == "roundover" and finish.get("size_mm") == 3:
        return {"a": "4", "b": "5", "both": "6"}[face]
    if kind == "mitre":
        return {"a": "8", "b": "9"}.get(face)
    return None


def _finish_op(finish: dict) -> str | None:
    kind, face = finish["kind"], finish.get("face", "a")
    if kind == "band":
        return "Edge band matching - 1mm"
    size = finish.get("size_mm")
    side = {"a": "top", "b": "bottom", "both": "top and bottom"}[face]
    if kind == "chamfer" and size in {2, 3, 4}:
        return f"Bevelling {side} - {int(size)}mm"
    if kind == "roundover" and size in {2, 4, 6}:
        return f"Rounding off {side} - {int(size)}mm"
    return None


def _row(order: PanelOrder, provider: str, issues: list[dict]) -> list:
    if provider == "zagenzagen":
        blank = [order.label, order.quantity, order.length, order.width, "", "", "", ""]
    else:
        blank = [order.quantity, order.length, order.width, order.label, "", ""]
    if not order.edges:
        return blank
    if order.basis is None:
        _issue(
            issues,
            "missing_stock_axes",
            "Finishes need signed stock axes; export the blank for manual selection.",
            order.source_id,
        )
        return blank
    mapping = _edge_map(order.basis)
    if any(edge not in mapping.values() for edge in order.edges):
        _issue(
            issues,
            "invalid_finish_edge",
            "A finish selects a thickness face; export the blank for manual selection.",
            order.source_id,
        )
        return blank
    bands = {edge for edge, finish in order.edges.items() if finish["kind"] == "band"}
    if (
        provider == "zagenzagen"
        and len(bands) > 1
        and bands
        not in ({mapping["v0"], mapping["vW"]}, {mapping["u0"], mapping["uL"]})
    ):
        _issue(
            issues,
            "zagenzagen_band_eligibility",
            "Bands are not one opposing pair; export the blank for manual selection.",
            order.source_id,
        )
        return blank
    if provider == "zagenzagen":
        positions = ("v0", "vW", "u0", "uL")
        values = [
            _finish_zagen(order.edges[mapping[position]])
            if mapping[position] in order.edges
            else ""
            for position in positions
        ]
        if any(value is None for value in values):
            _issue(
                issues,
                "unsupported_finish",
                "No ZAGENZAGEN code for finish; select the finish manually.",
                order.source_id,
            )
            return blank
        if bands:
            _issue(
                issues,
                "zagenzagen_product_eligibility_unverified",
                "Confirm band product eligibility in the provider UI.",
                order.source_id,
            )
        return blank[:4] + values
    positions = {
        "vW": "Long side 1",
        "v0": "Long side 2",
        "u0": "Short side 1",
        "uL": "Short side 2",
    }
    selections = [
        (label, _finish_op(order.edges[mapping[position]]))
        for position, label in positions.items()
        if mapping[position] in order.edges
    ]
    if any(value is None for _, value in selections):
        _issue(
            issues,
            "unsupported_finish",
            "A finish has no OPMAATZAGEN type; export the blank for manual selection.",
            order.source_id,
        )
        return blank
    if len({value for _, value in selections}) > 1:
        _issue(
            issues,
            "opmaatzagen_mixed_finishes",
            "Mixed finish types need manual selection; export the blank.",
            order.source_id,
        )
        return blank
    if order.length < order.width:
        _issue(
            issues,
            "opmaatzagen_long_short_unverified",
            "Confirm Long and Short side labels when Length is less than Width.",
            order.source_id,
        )
    if len(selections) > 1:
        _issue(
            issues,
            "opmaatzagen_multi_edge_unverified",
            "Confirm the comma-separated multi-edge CSV syntax with the provider.",
            order.source_id,
        )
    return blank[:4] + [", ".join(label for label, _ in selections), selections[0][1]]


def _csv_text(provider: str, rows: list[list]) -> str:
    output = StringIO(newline="")
    writer = csv.writer(
        output, delimiter=";" if provider == "zagenzagen" else ",", lineterminator="\n"
    )
    writer.writerow(_ZAGEN_FIELDS if provider == "zagenzagen" else _OP_FIELDS)
    writer.writerows(rows)
    return output.getvalue()


def plan_export(result: dict, provider: str, config: dict | None = None) -> ExportPlan:
    """Plan provider CSVs from a captured result without I/O or CAD work."""
    if provider not in {"zagenzagen", "opmaatzagen"}:
        raise ValueError("provider must be zagenzagen or opmaatzagen")
    if not isinstance(result, dict) or not isinstance(result.get("parts"), list):
        raise ValueError("result must contain a parts list")
    parts = result["parts"]
    settings = _validate_config(config, parts)
    issues: list[dict] = []
    trace: list[dict] = []
    grouped: dict[tuple, list[tuple[PanelOrder, list]]] = {}
    seen_ids: set[str] = set()
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            _issue(
                issues,
                "invalid_part",
                "Part record must be a map.",
                f"#{index}",
                "partial",
            )
            trace.append({"source_id": f"#{index}", "outcome": "omitted"})
            continue
        source_id = part.get("id")
        if not isinstance(source_id, str) or not source_id:
            source_id = f"#{index}"
        if source_id in seen_ids:
            _issue(
                issues,
                "duplicate_source_id",
                "Source part ID occurs more than once.",
                source_id,
                "partial",
            )
            trace.append({"source_id": source_id, "outcome": "omitted"})
            continue
        seen_ids.add(source_id)
        try:
            material = part.get("material")
            order = _convert(
                part,
                settings["materials"].get(material, {}),
                settings["parts"].get(source_id, {}),
                issues,
            )
        except (ValueError, TypeError, KeyError) as error:
            _issue(issues, "invalid_part", str(error), source_id, "partial")
            trace.append({"source_id": source_id, "outcome": "omitted"})
            continue
        row = _row(order, provider, issues)
        key = (
            order.material,
            order.panel_type,
            order.thickness,
            order.provider_material,
            order.purchase_type,
        )
        grouped.setdefault(key, []).append((order, row))
        trace.append(
            {
                "source_id": source_id,
                "label": order.label,
                "outcome": "exported",
                "material": order.material,
                "quantity": order.quantity,
                "original_stock_mm": order.original_blank,
                "order_dimensions_mm": {
                    "length": order.length,
                    "width": order.width,
                    "thickness": order.thickness,
                },
                "rounding_allowance_mm": {
                    "length": max(0, round(order.length - order.stock_length, 6)),
                    "width": max(0, round(order.width - order.stock_width, 6)),
                },
                "grain": order.grain,
                "grain_status": order.grain_status,
                "basis": order.basis,
                "frame_world": order.frame_world,
                "edges": order.edges,
            }
        )
    files: dict[str, str] = {}
    groups: list[dict] = []
    for key in sorted(
        grouped,
        key=lambda item: tuple("" if value is None else str(value) for value in item),
    ):
        group_id = sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest()[
            :12
        ]
        chunks: list[list[tuple[str, list]]] = [[]]
        remaining = 500 if provider == "zagenzagen" else None
        for order, row in grouped[key]:
            quantity = order.quantity
            while quantity:
                take = min(quantity, remaining) if remaining is not None else quantity
                chunk_row = list(row)
                chunk_row[1 if provider == "zagenzagen" else 0] = take
                chunks[-1].append((order.source_id, chunk_row))
                quantity -= take
                if remaining is not None:
                    remaining -= take
                    if remaining == 0 and quantity:
                        chunks.append([])
                        remaining = 500
            if remaining == 0:
                chunks.append([])
                remaining = 500
        if not chunks[-1]:
            chunks.pop()
        hint = _filename_hint(key[0], key[1], key[2])
        for number, chunk in enumerate(chunks, 1):
            filename = f"{provider}-{hint}-{group_id}-{number:03d}.csv"
            files[filename] = _csv_text(provider, [row for _, row in chunk])
            groups.append(
                {
                    "file": filename,
                    "material": key[0],
                    "panel_type": key[1],
                    "thickness_mm": key[2],
                    "provider_material": key[3],
                    "purchase_type": key[4],
                    "quantity": sum(
                        row[1 if provider == "zagenzagen" else 0] for _, row in chunk
                    ),
                    "source_ids": [source_id for source_id, _ in chunk],
                }
            )
    status = (
        "partial"
        if any(item["severity"] == "partial" for item in issues)
        else "review"
        if issues
        else "complete"
    )
    summary = {
        "provider": provider,
        "provider_product_selection_required": True,
        "source_revision": result.get("source_revision"),
        "status": status,
        "groups": groups,
        "trace": trace,
        "issues": issues,
        "row_count": sum(len(content.splitlines()) - 1 for content in files.values()),
    }
    return ExportPlan(files, summary, status)

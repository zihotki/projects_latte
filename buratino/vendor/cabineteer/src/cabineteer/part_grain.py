"""Authored grain direction for resolved Space stock parts."""

from __future__ import annotations

from dataclasses import dataclass

_AXES = {"x", "y", "z", "none"}


def grain_direction_for_stock(part: dict) -> str:
    """Map authored local grain to the reported blank length or width.

    The longest planar stock dimension is reported as blank length. For a
    square panel, the first planar local axis in X/Y/Z order is the stable
    length tie-breaker.
    """
    if part.get("grain_status") == "nondirectional":
        return "none"
    axis = part.get("grain_axis_local")
    stock = part.get("stock")
    if axis in {"x", "y", "z"} and isinstance(stock, dict):
        dimensions = stock.get("dimensions")
        thickness_axis = stock.get("thickness_axis")
        if (
            isinstance(dimensions, list | tuple)
            and len(dimensions) == 3
            and thickness_axis in (0, 1, 2)
        ):
            planar_axes = [index for index in range(3) if index != thickness_axis]
            ordered_axes = sorted(
                planar_axes, key=lambda index: (-float(dimensions[index]), index)
            )
            grain_index = "xyz".index(axis)
            if grain_index == ordered_axes[0]:
                return "length"
            if grain_index == ordered_axes[1]:
                return "width"
    direction = part.get("grain_direction", "unknown")
    return direction if direction in {"length", "width", "none"} else "unknown"


@dataclass(frozen=True)
class PartGrain:
    """Record stock-local grain intent for one exact resolved part."""

    id: str
    part_id: str
    axis: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("part grain id must be a non-empty string")
        if not isinstance(self.part_id, str) or not self.part_id.startswith("/"):
            raise ValueError(
                "part grain part_id must be an exact qualified Space part id"
            )
        if not isinstance(self.axis, str) or self.axis not in _AXES:
            raise ValueError(f"part grain {self.id!r}: axis must be x, y, z, or none")


def resolve_part_grain(parts: list[dict], records: tuple[PartGrain, ...]) -> None:
    """Attach authored grain metadata after all part IDs and stock axes resolve."""
    by_id = {part["id"]: part for part in parts}
    seen_ids: set[str] = set()
    seen_parts: set[str] = set()
    for record in records:
        if not isinstance(record, PartGrain):
            raise ValueError("part_grain must contain PartGrain inputs")
        if record.id in seen_ids:
            raise ValueError(f"duplicate part grain id {record.id!r}")
        seen_ids.add(record.id)
        part = by_id.get(record.part_id)
        if part is None:
            raise ValueError(
                f"part grain {record.id!r}: unknown resolved Space part "
                f"{record.part_id!r}"
            )
        if record.part_id in seen_parts:
            raise ValueError(f"duplicate part grain for {record.part_id!r}")
        seen_parts.add(record.part_id)
        axis = record.axis
        thickness_axis = part["stock"].get("thickness_axis")
        if axis != "none" and "xyz".index(axis) == thickness_axis:
            raise ValueError(
                f"part grain {record.id!r}: {axis!r} is the stock thickness axis"
            )
        part.update(
            grain_axis_local=None if axis == "none" else axis,
            grain_direction=axis,
            grain_status="nondirectional" if axis == "none" else "confirmed",
            surface_normal_axis_local="xyz"[thickness_axis],
        )
    for part in parts:
        part.setdefault("grain_axis_local", None)
        part.setdefault("grain_direction", "unknown")
        part.setdefault("grain_status", "unverified")
        thickness_axis = part["stock"].get("thickness_axis")
        if thickness_axis in (0, 1, 2):
            part.setdefault("surface_normal_axis_local", "xyz"[thickness_axis])

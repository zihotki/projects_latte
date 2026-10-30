"""Authored grain direction in each part's local stock frame."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase

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
    if isinstance(part.get("local_frame"), dict) and axis in {"x", "y"}:
        return {"x": "length", "y": "width"}[axis]
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
        if not isinstance(self.part_id, str) or not self.part_id or any(
            char in self.part_id for char in "*?[]"
        ):
            raise ValueError(
                "part grain part_id must be an exact resolved part id"
            )
        if not isinstance(self.axis, str) or self.axis not in _AXES:
            raise ValueError(f"part grain {self.id!r}: axis must be x, y, z, or none")


@dataclass(frozen=True)
class GrainRule:
    """Apply grain to IDs matched by one anchored fnmatch pattern.

    Rules run in declaration order; later rules override earlier rules.
    Exact PartGrain records run last and override rules.
    """

    id: str
    pattern: str
    axis: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("grain rule id must be a non-empty string")
        if not isinstance(self.pattern, str) or not self.pattern.strip():
            raise ValueError("grain rule pattern must be a non-empty string")
        if not isinstance(self.axis, str) or self.axis not in _AXES:
            raise ValueError(f"grain rule {self.id!r}: axis must be x, y, z, or none")


def resolve_part_grain(parts: list[dict], records: tuple[PartGrain | GrainRule, ...]) -> None:
    """Attach authored grain metadata after all part IDs and stock axes resolve."""
    by_id = {part["id"]: part for part in parts}
    seen_ids: set[str] = set()
    seen_parts: set[str] = set()
    ordered = [item for item in records if isinstance(item, GrainRule)] + [
        item for item in records if not isinstance(item, GrainRule)
    ]
    for record in ordered:
        if not isinstance(record, (PartGrain, GrainRule)):
            raise ValueError("part_grain must contain PartGrain or GrainRule inputs")
        if record.id in seen_ids:
            raise ValueError(f"duplicate part grain id {record.id!r}")
        seen_ids.add(record.id)
        matches = (
            [part for part in parts if fnmatchcase(part["id"], record.pattern)]
            if isinstance(record, GrainRule)
            else [by_id[record.part_id]] if record.part_id in by_id else []
        )
        if not matches:
            if isinstance(record, PartGrain):
                kind = "Space" if record.part_id.startswith("/") else "native"
                raise ValueError(
                    f"part grain {record.id!r}: unknown resolved {kind} part "
                    f"{record.part_id!r}"
                )
            raise ValueError(
                f"part grain {record.id!r}: no resolved part matches "
                f"{record.pattern!r}"
            )
        for part in matches:
            if isinstance(record, PartGrain):
                if record.part_id in seen_parts:
                    raise ValueError(f"duplicate part grain for {record.part_id!r}")
                seen_parts.add(record.part_id)
            axis = record.axis
            thickness_axis = (
                2 if isinstance(part.get("local_frame"), dict)
                else part["stock"].get("thickness_axis")
            )
            if axis != "none" and "xyz".index(axis) == thickness_axis:
                raise ValueError(
                    f"part grain {record.id!r}: {axis!r} is the stock thickness axis"
                )
            part.update(
                grain_axis_local=None if axis == "none" else axis,
                grain_direction=(
                    {"x": "length", "y": "width"}.get(axis, axis)
                    if isinstance(part.get("local_frame"), dict)
                    else axis
                ),
                grain_status="nondirectional" if axis == "none" else "confirmed",
                surface_normal_axis_local="xyz"[thickness_axis],
            )
    for part in parts:
        part.setdefault("grain_axis_local", None)
        part.setdefault("grain_direction", "unknown")
        part.setdefault("grain_status", "unverified")
        thickness_axis = (
            2 if isinstance(part.get("local_frame"), dict)
            else part["stock"].get("thickness_axis")
        )
        if thickness_axis in (0, 1, 2):
            part.setdefault("surface_normal_axis_local", "xyz"[thickness_axis])

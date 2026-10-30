"""Zero-thickness full-edge color bands for resolved Space parts."""

from __future__ import annotations

import re
from dataclasses import dataclass


_EDGES = {f"{axis}{side}" for axis in "xyz" for side in "-+"}
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")


def _cad_color(value: str):
    import cadquery as cq

    rgb = tuple(int(value[index : index + 2], 16) / 255 for index in (1, 3, 5))
    return cq.Color(*rgb, 1)


@dataclass(frozen=True)
class EdgeBand:
    """Color one complete narrow edge face on an original stock part."""

    id: str
    part_id: str
    edge: str
    color: str = "#b78b5b"

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("edge band id must be a non-empty string")
        if not isinstance(self.part_id, str) or not self.part_id.startswith("/"):
            raise ValueError(
                "edge band part_id must be an exact qualified Space part id"
            )
        if not isinstance(self.edge, str) or self.edge not in _EDGES:
            raise ValueError(f"edge band {self.id!r}: invalid edge {self.edge!r}")
        if not isinstance(self.color, str) or not _COLOR.fullmatch(self.color):
            raise ValueError(f"edge band {self.id!r}: color must be #RRGGBB")


def resolve_edge_bands(parts: list[dict], bands: tuple[EdgeBand, ...]) -> None:
    """Validate bands and attach resolved display metadata to Space parts."""
    by_id = {part["id"]: part for part in parts}
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str]] = set()
    for band in bands:
        if not isinstance(band, EdgeBand):
            raise ValueError("edge_banding must contain EdgeBand inputs")
        if band.id in seen_ids:
            raise ValueError(f"duplicate edge band id {band.id!r}")
        seen_ids.add(band.id)
        part = by_id.get(band.part_id)
        if part is None:
            raise ValueError(
                f"edge band {band.id!r}: unknown resolved Space part {band.part_id!r}"
            )
        pair = (band.part_id, band.edge)
        if pair in seen_edges:
            raise ValueError(f"duplicate edge band for {band.part_id!r} {band.edge!r}")
        seen_edges.add(pair)
        normal_axis = "xyz".index(band.edge[0])
        thickness_axis = part["stock"].get("thickness_axis")
        if normal_axis == thickness_axis:
            raise ValueError(
                f"edge band {band.id!r}: {band.edge!r} selects a thickness face, not a narrow edge face"
            )
        other_axis = next(
            axis for axis in range(3) if axis not in (normal_axis, thickness_axis)
        )
        dims = part["stock"]["dimensions"]
        origin = part["origin"]
        plane = origin[normal_axis] + (dims[normal_axis] if band.edge[1] == "+" else 0)
        part.setdefault("edge_banding", []).append(
            {
                "id": band.id,
                "edge": band.edge,
                "color": band.color,
                "thickness_mm": 0,
                "length_mm": dims[other_axis],
                "stock_plane": {"axis": "xyz"[normal_axis], "coordinate_mm": plane},
            }
        )
    for part in parts:
        if part.get("edge_banding"):
            part["edge_banding"].sort(key=lambda band: band["id"])


def make_view_assembly(model, shapes: dict, name: str = "space"):
    """Build a viewer assembly, partitioning banded parts by face material."""
    import cadquery as cq

    assembly = cq.Assembly(name=name)
    by_id = {part["id"]: part for part in model.part_plan.parts}
    for ident, shape in shapes.items():
        part = by_id[ident]
        bands = part.get("edge_banding", [])
        if not bands:
            assembly.add(shape, name=ident, color=cq.Color(0.91, 0.92, 0.90, 1))
            continue
        grouped: dict[str, list] = {}
        band_faces = {band["id"]: [] for band in bands}
        normal_axes = {band["id"]: "xyz".index(band["edge"][0]) for band in bands}
        for face in shape.val().Faces():
            center = face.Center()
            assigned = None
            for band in bands:
                axis = normal_axes[band["id"]]
                coordinate = band["stock_plane"]["coordinate_mm"]
                normal = face.normalAt()
                normal_components = (normal.x, normal.y, normal.z)
                center_components = (center.x, center.y, center.z)
                if (
                    abs(abs(normal_components[axis]) - 1.0) < 1e-6
                    and abs(center_components[axis] - coordinate) < 1e-6
                ):
                    assigned = band["id"]
                    break
            if assigned is None:
                grouped.setdefault("#e8ebe6", []).append(face)
            else:
                band_faces[assigned].append(face)
        for band in bands:
            faces = band_faces[band["id"]]
            if not faces:
                raise ValueError(
                    f"{ident}: edge band {band['id']!r} has no remaining finished face on {band['edge']!r}"
                )
            grouped.setdefault(band["color"], []).extend(faces)
        # Empty named part parent preserves one stable viewer role. Surface
        # children carry no material volume and never enter physical geometry.
        parent = cq.Assembly(name=ident)
        for index, (color, faces) in enumerate(grouped.items()):
            compound = cq.Compound.makeCompound(faces)
            parent.add(compound, name=f"surface-{index}", color=_cad_color(color))
        assembly.add(parent, name=ident)
    return assembly

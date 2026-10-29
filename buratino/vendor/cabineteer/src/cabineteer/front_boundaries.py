"""Resolve rectangular overlay fronts from structural coverage boundaries."""
from __future__ import annotations

from .profiles import face_boundary_gap

_TOL = 1e-6


def resolve_front_boundaries(fronts: list[dict]) -> dict[str, tuple[float, float, float, float]]:
    """Return inset bounds for overlay fronts sharing a mounting back plane.

    Each entry has id, coverage (x0, x1, z0, z1), plane, kind, reveal,
    door_gap, drawer_front_gap and optional boundary_gap. Positive authored
    separation is represented by distinct coverage coordinates.
    """
    result = {}
    for face in fronts:
        x0, x1, z0, z1 = face["coverage"]
        limits = [x0, x1, z0, z1]
        matches = [[], [], [], []]
        for other in fronts:
            if other is face or abs(face["plane"] - other["plane"]) > _TOL:
                continue
            a, b, c, d = other["coverage"]
            if min(x1, b) - max(x0, a) > _TOL and min(z1, d) - max(z0, c) > _TOL:
                raise ValueError(f"overlapping front coverage: {face['id']} and {other['id']}")
            for edge, coordinate, peer, overlap in (
                (0, x0, b, min(z1, d) - max(z0, c)),
                (1, x1, a, min(z1, d) - max(z0, c)),
                (2, z0, d, min(x1, b) - max(x0, a)),
                (3, z1, c, min(x1, b) - max(x0, a)),
            ):
                if overlap <= _TOL or abs(coordinate - peer) > _TOL:
                    continue
                # Any declared positive body gap must stay exposed, even below tolerance.
                if face.get("instance") != other.get("instance") and coordinate != peer:
                    continue
                explicit = [v for v in (face.get("boundary_gap"), other.get("boundary_gap")) if v is not None]
                if len(explicit) == 2 and explicit[0] != explicit[1]:
                    raise ValueError(f"conflicting front gaps: {face['id']} and {other['id']}")
                gap = face_boundary_gap(face["kind"], other["kind"],
                    door_gap_mm=max(face["door_gap"], other["door_gap"]),
                    drawer_front_gap_mm=max(face["drawer_front_gap"], other["drawer_front_gap"]),
                    explicit_gap_mm=explicit[0] if explicit else (max(face["reveal"], other["reveal"]) if face["kind"] == other["kind"] == "applied_faceboard" else None))
                matches[edge].append((peer, gap, other["id"]))
        for edge, found in enumerate(matches):
            inset = face["reveal"]
            if edge == 3 and face.get("top_reveal") is not None:
                inset = face["top_reveal"]
            if found:
                coord, gap, name = found[0]
                for next_coord, next_gap, next_name in found[1:]:
                    if abs(coord - next_coord) > _TOL or abs(gap - next_gap) > _TOL:
                        raise ValueError(f"conflicting front boundaries: {name} and {next_name} (for {face['id']})")
                inset = gap / 2
            limits[edge] += inset if edge in (0, 2) else -inset
        if limits[1] <= limits[0] or limits[3] <= limits[2]:
            raise ValueError(f"{face['id']}: front dimensions are not positive")
        result[face["id"]] = tuple(limits)
    return result

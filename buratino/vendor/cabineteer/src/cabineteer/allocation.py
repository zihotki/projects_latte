"""Pure numeric allocation shared by spaces and assemblies."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Fixed:
    mm: float


@dataclass(frozen=True)
class Fr:
    weight: int = 1


@dataclass(frozen=True)
class Natural:
    pass


@dataclass(frozen=True)
class Allocation:
    lengths: tuple[float, ...]
    slack: float


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def allocate_tracks(available, tracks, reserved=0):
    """Allocate ordered fixed and weighted tracks, retaining any remainder."""
    available = finite(available, "available span")
    reserved = finite(reserved, "reserved span")
    if available < 0 or reserved < 0:
        raise ValueError("available and reserved spans must be non-negative")
    fixed = 0.0
    weight = 0
    for track in tracks:
        if isinstance(track, Fr):
            if isinstance(track.weight, bool) or not isinstance(track.weight, int) or track.weight <= 0:
                raise ValueError("Fr weight must be a positive integer")
            weight += track.weight
        else:
            value = finite(track.mm if isinstance(track, Fixed) else track, "fixed track")
            if value < 0:
                raise ValueError("fixed track must be non-negative")
            fixed = finite(fixed + value, "fixed tracks")
    remaining = finite(available - reserved - fixed, "remaining span")
    if remaining < 0:
        raise ValueError("fixed tracks and reservations exceed available span")
    if weight and not remaining.is_integer():
        raise ValueError("weighted tracks require an integral remaining span")
    lengths = tuple(
        (int(remaining) * t.weight) // weight if isinstance(t, Fr)
        else finite(t.mm if isinstance(t, Fixed) else t, "fixed track")
        for t in tracks
    )
    if any(length <= 0 for t, length in zip(tracks, lengths) if isinstance(t, Fr)):
        raise ValueError("flexible track has zero size")
    slack = finite(available - reserved - sum(lengths), "allocation slack")
    return Allocation(lengths, slack)

"""Checkpoint placement and arrival-time estimation along a route (spec §3, §6)."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from .geometry import cumulative_distances, point_at_distance
from .models import LonLat, TimelinePoint

__all__ = [
    "CheckpointPosition",
    "TimelinePoint",
    "checkpoint_miles",
    "elapsed_at",
    "sample_checkpoints",
]

# A regular checkpoint this close to the destination is dropped; the destination covers it.
MIN_FINAL_SEGMENT_MI = 0.5


@dataclass(frozen=True, slots=True)
class CheckpointPosition:
    """Where and when the truck is at one checkpoint.

    ``covers_mi`` is how much road this checkpoint's weather is applied to: every mile is
    scored by its nearest checkpoint, so a checkpoint covers from halfway back to the previous
    one to halfway on to the next. The origin covers the first half-interval (so the weather
    at departure counts) and the destination the last. The coverages add up to the route length.
    """

    index: int
    mile: float
    covers_mi: float
    coord: LonLat
    eta: int  # Unix seconds, UTC


def elapsed_at(timeline: Sequence[TimelinePoint], fraction: float) -> float:
    """Elapsed seconds at ``fraction`` (0-1) of the route, interpolated between timeline points.

    The timeline is positioned by fraction of its own total distance, so a small difference
    between the routing API's reported length and our polyline length does not skew ETAs.
    """
    if len(timeline) < 2:
        raise ValueError("A timeline needs at least a start and an end point")
    total = timeline[-1].distance_mi
    if total <= 0:
        raise ValueError("Timeline distance must be positive")

    d = min(max(fraction, 0.0), 1.0) * total
    distances = [p.distance_mi for p in timeline]
    i = min(bisect_right(distances, d) - 1, len(timeline) - 2)
    a, b = timeline[i], timeline[i + 1]
    span = b.distance_mi - a.distance_mi
    t = 0.0 if span == 0 else (d - a.distance_mi) / span
    return a.elapsed_s + (b.elapsed_s - a.elapsed_s) * t


def checkpoint_miles(total_mi: float, interval_mi: float) -> list[float]:
    """Mile 0, every ``interval_mi``, and the destination.

    A regular checkpoint within ``MIN_FINAL_SEGMENT_MI`` of the destination is dropped.
    """
    if interval_mi <= 0:
        raise ValueError("interval_mi must be positive")
    miles = [0.0]
    m = interval_mi
    while m < total_mi - MIN_FINAL_SEGMENT_MI:
        miles.append(m)
        m += interval_mi
    if total_mi > 0:
        miles.append(total_mi)
    return miles


def sample_checkpoints(
    polyline: Sequence[LonLat],
    timeline: Sequence[TimelinePoint],
    interval_mi: float,
    departure_ts: int,
) -> list[CheckpointPosition]:
    """Place checkpoints along the route and estimate when the truck reaches each one."""
    cumdist = cumulative_distances(polyline)
    total = cumdist[-1]

    miles = checkpoint_miles(total, interval_mi)
    # Boundaries halfway between neighbouring checkpoints; the route's ends close the first and
    # last stretches.
    bounds = [0.0] + [(a + b) / 2 for a, b in zip(miles, miles[1:], strict=False)] + [total]

    out: list[CheckpointPosition] = []
    for i, mile in enumerate(miles):
        fraction = mile / total if total else 0.0
        out.append(
            CheckpointPosition(
                index=i,
                mile=mile,
                covers_mi=bounds[i + 1] - bounds[i],
                coord=point_at_distance(polyline, cumdist, mile),
                eta=departure_ts + round(elapsed_at(timeline, fraction)),
            )
        )
    return out

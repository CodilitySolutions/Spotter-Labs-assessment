import pytest

from routing.domain.checkpoints import (
    TimelinePoint,
    checkpoint_miles,
    elapsed_at,
    sample_checkpoints,
)
from routing.domain.geometry import MI_PER_DEG_LAT, haversine_mi

DEPART = 1_800_000_000  # an arbitrary Unix timestamp


def north_line(miles: float, steps: int = 10):
    return [(-100.0, 35.0 + miles * k / steps / MI_PER_DEG_LAT) for k in range(steps + 1)]


def uniform_timeline(miles: float, seconds: float) -> list[TimelinePoint]:
    return [TimelinePoint(0, 0), TimelinePoint(miles, seconds)]


# --- Which miles get a checkpoint -----------------------------------------------------------


@pytest.mark.parametrize(
    ("total", "interval", "expected"),
    [
        (100, 25, [0, 25, 50, 75, 100]),
        (100, 50, [0, 50, 100]),
        (60, 25, [0, 25, 50, 60]),
        (100.3, 10, [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100.3]),  # 100 dropped: 0.3 mi left
        (100.6, 10, [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 100.6]),  # 0.6 mi left: kept
        (8, 10, [0, 8]),  # shorter than one interval
    ],
)
def test_checkpoint_miles(total: float, interval: float, expected: list[float]) -> None:
    assert checkpoint_miles(total, interval) == pytest.approx(expected)


def test_checkpoint_interval_must_be_positive() -> None:
    with pytest.raises(ValueError):
        checkpoint_miles(100, 0)


# --- Elapsed time ------------------------------------------------------------------------


def test_elapsed_time_uniform_speed() -> None:
    timeline = uniform_timeline(100, 7200)  # 100 miles in 2 hours

    assert elapsed_at(timeline, 0) == 0
    assert elapsed_at(timeline, 0.25) == pytest.approx(1800)
    assert elapsed_at(timeline, 1) == pytest.approx(7200)


def test_elapsed_time_follows_slow_and_fast_stretches() -> None:
    # The first 50 miles take an hour (city); the next 50 take 30 minutes (highway).
    timeline = [TimelinePoint(0, 0), TimelinePoint(50, 3600), TimelinePoint(100, 5400)]

    assert elapsed_at(timeline, 0.25) == pytest.approx(1800)
    assert elapsed_at(timeline, 0.75) == pytest.approx(4500)


def test_elapsed_time_clamps_fraction() -> None:
    timeline = uniform_timeline(10, 600)

    assert elapsed_at(timeline, -1) == 0
    assert elapsed_at(timeline, 2) == 600


def test_timeline_needs_two_points() -> None:
    with pytest.raises(ValueError):
        elapsed_at([TimelinePoint(0, 0)], 0.5)


# --- Full sampling ---------------------------------------------------------------------------


def test_sample_checkpoints_positions_etas_and_segments() -> None:
    line = north_line(100)
    cps = sample_checkpoints(line, uniform_timeline(100, 7200), interval_mi=25, departure_ts=DEPART)

    assert [c.index for c in cps] == [0, 1, 2, 3, 4]
    assert [c.mile for c in cps] == pytest.approx([0, 25, 50, 75, 100], abs=0.01)
    assert [c.segment_mi for c in cps] == pytest.approx([0, 25, 25, 25, 25], abs=0.01)
    assert [c.eta - DEPART for c in cps] == pytest.approx([0, 1800, 3600, 5400, 7200], abs=2)
    assert haversine_mi(line[0], cps[2].coord) == pytest.approx(50, abs=0.01)
    assert cps[0].coord == line[0]
    assert cps[-1].coord == line[-1]


def test_segments_add_up_to_route_length() -> None:
    line = north_line(137.4)
    cps = sample_checkpoints(line, uniform_timeline(137.4, 9000), interval_mi=10, departure_ts=0)

    assert sum(c.segment_mi for c in cps) == pytest.approx(137.4, abs=0.01)


def test_etas_use_route_fraction_when_api_length_differs() -> None:
    # Our polyline measures 100 mi but the routing API says 102 mi; the halfway checkpoint
    # should still get the halfway elapsed time.
    line = north_line(100)
    timeline = uniform_timeline(102, 7344)

    cps = sample_checkpoints(line, timeline, interval_mi=50, departure_ts=DEPART)

    assert cps[1].eta - DEPART == pytest.approx(3672, abs=2)
    assert cps[-1].eta - DEPART == 7344

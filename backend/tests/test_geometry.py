import pytest

from routing.domain.geometry import (
    MI_PER_DEG_LAT,
    corridor_grid,
    cumulative_distances,
    detour_waypoint,
    haversine_mi,
    overlap_fraction,
    point_at_distance,
    resample,
    route_similarity,
    simplify,
)


def north_line(miles: float, lon: float = -100.0, start_lat: float = 35.0, steps: int = 10):
    """A straight northbound line of the given length, split into ``steps`` segments."""
    return [(lon, start_lat + miles * k / steps / MI_PER_DEG_LAT) for k in range(steps + 1)]


def east_offset(line, miles: float):
    """Shift a line east by roughly ``miles`` (near 35 degrees N)."""
    from math import cos, radians

    dlon = miles / (MI_PER_DEG_LAT * cos(radians(line[0][1])))
    return [(lon + dlon, lat) for lon, lat in line]


# --- Distances ---------------------------------------------------------------------------


def test_haversine_one_degree_of_latitude() -> None:
    assert haversine_mi((0, 0), (0, 1)) == pytest.approx(69.09, abs=0.01)


def test_haversine_chicago_to_denver() -> None:
    # Great-circle distance is about 920 miles.
    assert haversine_mi((-87.6298, 41.8781), (-104.9903, 39.7392)) == pytest.approx(920, rel=0.01)


def test_cumulative_distances() -> None:
    cum = cumulative_distances(north_line(100, steps=4))

    assert cum[0] == 0
    assert cum == pytest.approx([0, 25, 50, 75, 100], abs=0.01)


def test_polyline_needs_two_points() -> None:
    with pytest.raises(ValueError):
        cumulative_distances([(0, 0)])


# --- Walking along a line -------------------------------------------------------------------


def test_point_at_distance_interpolates_within_segment() -> None:
    line = north_line(100, steps=1)  # one long segment
    cum = cumulative_distances(line)

    lon, lat = point_at_distance(line, cum, 30)

    assert lon == pytest.approx(-100)
    assert haversine_mi(line[0], (lon, lat)) == pytest.approx(30, abs=0.01)


def test_point_at_distance_clamps() -> None:
    line = north_line(10)
    cum = cumulative_distances(line)

    assert point_at_distance(line, cum, -5) == line[0]
    assert point_at_distance(line, cum, 999) == line[-1]


def test_point_at_distance_turns_corners() -> None:
    # An L shape: 10 miles north, then 10 miles east.
    north = north_line(10, steps=1)
    corner = north[-1]
    east = east_offset([corner], 10)[0]
    line = [north[0], corner, east]
    cum = cumulative_distances(line)

    assert point_at_distance(line, cum, 10) == pytest.approx(corner, abs=1e-3)
    assert haversine_mi(corner, point_at_distance(line, cum, 15)) == pytest.approx(5, abs=0.05)


def test_resample_includes_both_ends_and_even_spacing() -> None:
    line = north_line(100, steps=3)
    points = resample(line, 10)

    assert len(points) == 11
    assert points[0] == line[0]
    assert points[-1] == line[-1]
    gaps = [haversine_mi(a, b) for a, b in zip(points, points[1:], strict=False)]
    assert gaps == pytest.approx([10] * 10, abs=0.01)


# --- Route similarity ----------------------------------------------------------------------


def test_identical_routes_fully_overlap() -> None:
    line = north_line(50)
    assert route_similarity(line, line) == pytest.approx(1.0)


def test_parallel_routes_do_not_overlap() -> None:
    line = north_line(50)
    assert route_similarity(line, east_offset(line, 10)) == 0


def test_overlap_tolerates_small_offsets() -> None:
    line = north_line(50)
    # 0.05 mi (~80 m) apart: the same road drawn with slightly different vertices.
    assert route_similarity(line, east_offset(line, 0.05)) == pytest.approx(1.0)


def test_overlap_is_directional() -> None:
    long = north_line(100, steps=20)
    short = long[:11]  # the first 50 miles of the same road

    assert overlap_fraction(short, long) == pytest.approx(1.0)
    assert overlap_fraction(long, short) == pytest.approx(0.5, abs=0.02)
    assert route_similarity(long, short) == pytest.approx(0.5, abs=0.02)


# --- Detours ---------------------------------------------------------------------------------


@pytest.mark.parametrize(("side", "west"), [("left", True), ("right", False)])
def test_detour_waypoint_is_offset_sideways_from_midpoint(side: str, west: bool) -> None:
    line = north_line(200, steps=1)
    origin, dest = line[0], line[-1]
    mid = ((origin[0] + dest[0]) / 2, (origin[1] + dest[1]) / 2)

    wp = detour_waypoint(origin, dest, side, ratio=0.15)  # type: ignore[arg-type]

    # Going north, "left" is west.
    assert (wp[0] < mid[0]) is west
    assert wp[1] == pytest.approx(mid[1], abs=1e-6)
    assert haversine_mi(mid, wp) == pytest.approx(30, rel=0.01)


def test_detour_rejects_same_point() -> None:
    with pytest.raises(ValueError):
        detour_waypoint((0, 0), (0, 0), "left", 0.1)


# --- Corridor grid -------------------------------------------------------------------------


def _distance_to_line(p, line) -> float:
    return min(haversine_mi(p, q) for q in resample(line, 0.5))


def test_corridor_grid_stays_within_corridor_and_near_target_size() -> None:
    route = north_line(500, steps=20)
    result = corridor_grid([route], corridor_mi=40, target_points=300)
    grid = result.points

    assert 150 <= len(grid) <= 450
    assert all(_distance_to_line(p, route) <= 40.5 for p in grid)
    # The reported spacing is the real distance between neighbouring grid points.
    nearest = sorted(haversine_mi(grid[0], q) for q in grid[1:])[0]
    assert nearest == pytest.approx(result.spacing_mi, rel=0.05)


def test_corridor_grid_covers_every_route() -> None:
    a = north_line(300, steps=10)
    b = east_offset(a, 150)  # a second route far to the east
    grid = corridor_grid([a, b], corridor_mi=30, target_points=300).points

    near_a = [p for p in grid if _distance_to_line(p, a) <= 30.5]
    near_b = [p for p in grid if _distance_to_line(p, b) <= 30.5]
    assert near_a and near_b
    assert len(near_a) + len(near_b) == len(grid)  # nothing in the gap between them


def test_corridor_grid_requires_routes() -> None:
    with pytest.raises(ValueError):
        corridor_grid([])


# --- Simplification ----------------------------------------------------------------------


def test_simplify_drops_collinear_points_and_keeps_corners() -> None:
    north = north_line(10, steps=50)
    corner = north[-1]
    east = [(lon, lat) for lon, lat in east_offset(north_line(10, steps=50), 0)]
    east = [(corner[0] + k * 0.003, corner[1]) for k in range(1, 51)]
    line = north + east

    simplified = simplify(line, tolerance_mi=0.01)

    assert simplified[0] == line[0]
    assert simplified[-1] == line[-1]
    assert corner in simplified
    assert len(simplified) <= 4


def test_simplify_keeps_detail_above_tolerance() -> None:
    zigzag = [(-100 + k * 0.01, 35 + (0.01 if k % 2 else 0)) for k in range(20)]  # ~0.7 mi wiggles

    assert simplify(zigzag, tolerance_mi=0.1) == zigzag

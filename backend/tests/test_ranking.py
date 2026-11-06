"""Route summaries and the recommendation order (spec §5)."""

import pytest

from routing.domain.models import RiskLevel
from routing.domain.ranking import RankInput, explain, rank, summarize

L, M, H, S, NT = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)
HOUR = 3600


def route(name: str, segments, hours: float = 10) -> RankInput:
    return RankInput(id=name, name=name, summary=summarize(segments), duration_s=hours * HOUR)


# --- Summaries -------------------------------------------------------------------------------


def test_summary_counts_miles_per_level() -> None:
    s = summarize([(0, L), (25, L), (25, H), (25, S), (10, NT), (15, None)])

    assert s.miles_by_level == {
        "low": 25,
        "moderate": 0,
        "high": 25,
        "severe": 25,
        "no_travel": 10,
        "unknown": 15,
    }
    assert s.severe_miles == 35  # Severe + No Travel
    assert s.high_miles == 25
    assert s.has_no_travel
    assert s.unknown_miles == 15
    assert s.worst_level == NT


def test_average_risk_is_distance_weighted_over_known_miles() -> None:
    # 30 mi Low (0) + 10 mi Severe (3) = 30 / 40; the unknown 50 mi are excluded.
    s = summarize([(30, L), (10, S), (50, None)])

    assert s.avg_risk == pytest.approx(0.75)


def test_all_unknown_route_has_no_average() -> None:
    s = summarize([(0, None), (40, None)])

    assert s.avg_risk is None
    assert s.worst_level is None


def test_checkpoint_covering_no_road_does_not_set_worst_level() -> None:
    # Only possible on degenerate input; a level that applies to no miles isn't "worst".
    s = summarize([(0, S), (25, L)])

    assert s.worst_level == L
    assert s.severe_miles == 0


# --- Ranking: one test per criterion ---------------------------------------------------------


def test_no_travel_ranks_last_even_with_fewer_severe_miles() -> None:
    a = route("A", [(5, NT), (95, L)])  # 5 severe-or-worse miles, but No Travel
    b = route("B", [(50, S), (50, L)])  # 50 severe miles, no No Travel

    assert [r.id for r in rank([a, b])] == ["B", "A"]
    assert explain(rank([a, b])) == "B avoids No Travel conditions; A does not."


def test_fewest_severe_miles_wins_over_travel_time() -> None:
    a = route("A", [(42, S), (58, L)], hours=8)
    b = route("B", [(0, L), (100, H)], hours=12)

    assert [r.id for r in rank([a, b])] == ["B", "A"]
    assert explain(rank([a, b])) == "Fewest severe-or-worse miles: 0 mi vs 42 mi on A."


def test_fewest_high_miles_breaks_severe_tie() -> None:
    a = route("A", [(10, S), (30, H), (60, L)], hours=8)
    b = route("B", [(10, S), (5, H), (85, L)], hours=12)

    assert [r.id for r in rank([a, b])] == ["B", "A"]
    assert explain(rank([a, b])).startswith("Equal severe miles; fewest high-risk miles: 5.0 mi")


def test_lowest_average_risk_breaks_high_tie() -> None:
    a = route("A", [(20, H), (80, M)], hours=8)  # avg 1.2
    b = route("B", [(20, H), (80, L)], hours=12)  # avg 0.4

    assert [r.id for r in rank([a, b])] == ["B", "A"]
    assert "lowest average risk: 0.40 vs 1.20" in explain(rank([a, b]))


def test_shortest_time_breaks_full_risk_tie() -> None:
    a = route("A", [(100, L)], hours=12)
    b = route("B", [(100, L)], hours=10.5)

    assert [r.id for r in rank([a, b])] == ["B", "A"]
    assert explain(rank([a, b])) == "Equal weather risk; fastest: 10 h 30 min vs 12 h 00 min on A."


def test_complete_tie_keeps_router_order() -> None:
    a = route("A", [(100, L)])
    b = route("B", [(100, L)])

    assert [r.id for r in rank([a, b])] == ["A", "B"]
    assert explain(rank([a, b])) == "Routes are equal on every criterion; A is listed first."


def test_float_noise_does_not_decide_ranking() -> None:
    a = route("A", [(10.000001, S), (90, L)], hours=8)
    b = route("B", [(10.0, S), (90, L)], hours=9)

    assert rank([a, b])[0].id == "A"  # equal severe miles at 0.1 mi -> faster wins


def test_unknown_average_ranks_after_known() -> None:
    a = route("A", [(100, None)], hours=8)
    b = route("B", [(100, M)], hours=12)

    assert rank([a, b])[0].id == "B"


def test_single_route_explanation() -> None:
    assert explain([route("A", [(10, L)])]) == "Only one route was available."

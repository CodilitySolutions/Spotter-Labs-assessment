"""Risk rules, tested at every threshold edge (docs/PROJECT_SPEC.md §4)."""

import math

import pytest

from routing.domain.models import RiskLevel, Weather
from routing.domain.risk import (
    apply_load_rules,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
)

L, M, H, S, NT = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)


def wx(wind: float = 0, rain: float = 0, snow: float = 0) -> Weather:
    return Weather(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow, source="test")


# --- Weather thresholds --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mph", "expected"),
    [
        (0, L),
        (24.9, L),
        (25, M),
        (34.9, M),
        (35, H),
        (44.9, H),
        (45, S),
        (54.9, S),
        (55, NT),
        (80, NT),
    ],
)
def test_classify_wind(mph: float, expected: RiskLevel) -> None:
    assert classify_wind(mph) == expected


@pytest.mark.parametrize(
    ("in_hr", "expected"),
    [
        (0, L),
        (0.099, L),
        (0.10, M),
        (0.249, M),
        (0.25, H),
        (0.499, H),
        (0.50, S),
        (1.00, S),  # "0.50-1.00" is Severe; No Travel is strictly "> 1.00"
        (1.001, NT),
        (2.5, NT),
    ],
)
def test_classify_rain(in_hr: float, expected: RiskLevel) -> None:
    assert classify_rain(in_hr) == expected


@pytest.mark.parametrize(
    ("in_hr", "expected"),
    [
        (0, L),
        (0.49, L),
        (0.5, M),
        (0.99, M),
        (1.0, H),
        (1.99, H),
        (2.0, S),
        (3.0, S),  # "2.0-3.0" is Severe; No Travel is strictly "> 3.0"
        (3.01, NT),
    ],
)
def test_classify_snow(in_hr: float, expected: RiskLevel) -> None:
    assert classify_snow(in_hr) == expected


# --- Load rules ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mph", "load_lb", "expected"),
    [
        # 45-54 mph + > 30,000 lb -> No Travel
        (45, 30_001, NT),
        (54.9, 30_001, NT),
        (45, 30_000, None),  # load must be strictly above 30,000
        (44.9, 30_001, None),  # below the 45 mph band (and not > 40,000)
        # 35-44 mph + > 40,000 lb -> Severe
        (35, 40_001, S),
        (44.9, 40_001, S),
        (35, 40_000, None),  # load must be strictly above 40,000
        (34.9, 80_000, None),  # below the 35 mph band
        # >= 55 mph is handled by the wind thresholds, not by a load rule
        (55, 80_000, None),
    ],
)
def test_apply_load_rules(mph: float, load_lb: float, expected: RiskLevel | None) -> None:
    assert apply_load_rules(mph, load_lb) == expected


# --- Combined assessment ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("weather", "load_lb", "expected"),
    [
        (wx(), 0, L),
        # The worst of the three conditions wins
        (wx(wind=26, rain=0.3, snow=0.6), 0, H),
        (wx(wind=10, snow=2.5), 0, S),
        # Load rules raise the level
        (wx(wind=47), 30_001, NT),
        (wx(wind=47), 30_000, S),
        (wx(wind=40), 40_001, S),
        (wx(wind=40), 40_000, H),
        (wx(wind=55), 0, NT),
        # Load rules never lower the level
        (wx(wind=40, rain=1.5), 40_001, NT),
        (wx(wind=34.9), 80_000, M),
    ],
)
def test_assess_final_level(weather: Weather, load_lb: float, expected: RiskLevel) -> None:
    assert assess(weather, load_lb).final == expected


def test_assess_reports_each_condition_level() -> None:
    result = assess(wx(wind=47, rain=0.12, snow=1.5), 35_000)

    assert (result.wind, result.rain, result.snow) == (S, M, H)
    assert result.load_override == NT
    assert result.final == NT


@pytest.mark.parametrize(
    "weather",
    [
        None,
        Weather(wind_mph=None, rain_in_hr=0, snow_in_hr=0),
        Weather(wind_mph=10, rain_in_hr=None, snow_in_hr=0),
        Weather(wind_mph=10, rain_in_hr=0, snow_in_hr=math.nan),
    ],
)
def test_missing_weather_is_unknown_not_low(weather: Weather | None) -> None:
    result = assess(weather, 10_000)

    assert result.final is None
    assert result.is_unknown
    assert result.reason == "Weather data unavailable"


def test_negative_load_is_rejected() -> None:
    with pytest.raises(ValueError):
        assess(wx(), -1)


# --- Explanations ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("weather", "load_lb", "reason"),
    [
        (wx(), 0, "All conditions low"),
        (wx(wind=30), 0, "Moderate: Wind 30 mph"),
        (wx(rain=0.3), 0, "High: Rain 0.30 in/hr"),
        (wx(wind=47), 35_000, "No Travel: Wind 47 mph with load 35,000 lb > 30,000 lb"),
        (wx(wind=40), 45_000, "Severe: Wind 40 mph with load 45,000 lb > 40,000 lb"),
        (
            wx(wind=40, snow=2.5),
            45_000,
            "Severe: Wind 40 mph with load 45,000 lb > 40,000 lb; Snow 2.50 in/hr",
        ),
        (wx(wind=40, rain=1.5), 45_000, "No Travel: Rain 1.50 in/hr"),
    ],
)
def test_reason_names_the_deciding_factors(weather: Weather, load_lb: float, reason: str) -> None:
    assert assess(weather, load_lb).reason == reason


def test_level_labels() -> None:
    assert NT.label == "no_travel"
    assert NT.display == "No Travel"
    assert [int(level) for level in RiskLevel] == [0, 1, 2, 3, 4]

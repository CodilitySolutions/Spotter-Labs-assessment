"""Weather risk rules (docs/PROJECT_SPEC.md §4).

The thresholds are data, not branching code, so they can be checked line by line against the
spec table:

| Level      | Wind (mph) | Rain (in/hr)  | Snow (in/hr) |
|------------|------------|---------------|--------------|
| Low        | < 25       | < 0.10        | < 0.5        |
| Moderate   | >= 25      | >= 0.10       | >= 0.5       |
| High       | >= 35      | >= 0.25       | >= 1.0       |
| Severe     | >= 45      | >= 0.50       | >= 2.0       |
| No Travel  | >= 55      | >  1.00       | >  3.0       |

The brief's ranges share their edges (e.g. rain "0.10-0.25" and "0.25-0.50"). Each shared edge
belongs to the *higher* level, except the top of Severe for rain/snow, where the brief says
No Travel starts strictly *above* 1.00 / 3.0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Assessment, RiskLevel, Weather


@dataclass(frozen=True, slots=True)
class Threshold:
    """The value at which ``level`` starts."""

    level: RiskLevel
    value: float
    inclusive: bool = True

    def is_met(self, x: float) -> bool:
        return x >= self.value if self.inclusive else x > self.value


# Listed from the most to the least severe; the first threshold met wins.
WIND_THRESHOLDS = (
    Threshold(RiskLevel.NO_TRAVEL, 55),
    Threshold(RiskLevel.SEVERE, 45),
    Threshold(RiskLevel.HIGH, 35),
    Threshold(RiskLevel.MODERATE, 25),
)
RAIN_THRESHOLDS = (
    Threshold(RiskLevel.NO_TRAVEL, 1.00, inclusive=False),
    Threshold(RiskLevel.SEVERE, 0.50),
    Threshold(RiskLevel.HIGH, 0.25),
    Threshold(RiskLevel.MODERATE, 0.10),
)
SNOW_THRESHOLDS = (
    Threshold(RiskLevel.NO_TRAVEL, 3.0, inclusive=False),
    Threshold(RiskLevel.SEVERE, 2.0),
    Threshold(RiskLevel.HIGH, 1.0),
    Threshold(RiskLevel.MODERATE, 0.5),
)


@dataclass(frozen=True, slots=True)
class LoadRule:
    """Wind in ``[min_wind_mph, max_wind_mph)`` with a load strictly above ``min_load_lb``."""

    min_wind_mph: float
    max_wind_mph: float
    min_load_lb: float
    result: RiskLevel

    def applies(self, wind_mph: float, load_lb: float) -> bool:
        return self.min_wind_mph <= wind_mph < self.max_wind_mph and load_lb > self.min_load_lb


# ">= 55 mph -> No Travel for any load" is already covered by WIND_THRESHOLDS.
LOAD_RULES = (
    LoadRule(min_wind_mph=45, max_wind_mph=55, min_load_lb=30_000, result=RiskLevel.NO_TRAVEL),
    LoadRule(min_wind_mph=35, max_wind_mph=45, min_load_lb=40_000, result=RiskLevel.SEVERE),
)


def _classify(value: float, thresholds: tuple[Threshold, ...]) -> RiskLevel:
    for threshold in thresholds:
        if threshold.is_met(value):
            return threshold.level
    return RiskLevel.LOW


def classify_wind(mph: float) -> RiskLevel:
    return _classify(mph, WIND_THRESHOLDS)


def classify_rain(in_per_hr: float) -> RiskLevel:
    return _classify(in_per_hr, RAIN_THRESHOLDS)


def classify_snow(in_per_hr: float) -> RiskLevel:
    return _classify(in_per_hr, SNOW_THRESHOLDS)


def apply_load_rules(wind_mph: float, load_lb: float) -> RiskLevel | None:
    """The level the load rules force, or ``None`` when no rule applies."""
    for rule in LOAD_RULES:
        if rule.applies(wind_mph, load_lb):
            return rule.result
    return None


def _has_nan(*values: float) -> bool:
    return any(math.isnan(v) for v in values)


def assess(weather: Weather | None, load_lb: float) -> Assessment:
    """Apply the weather thresholds, then the load rules, to one checkpoint.

    The final level is the worst of wind, rain and snow, raised (never lowered) by the load
    rules. If any of the three measurements is missing the result is Unknown.
    """
    if load_lb < 0:
        raise ValueError(f"load_lb must be >= 0, got {load_lb}")

    wind_mph = weather.wind_mph if weather else None
    rain = weather.rain_in_hr if weather else None
    snow = weather.snow_in_hr if weather else None
    if wind_mph is None or rain is None or snow is None or _has_nan(wind_mph, rain, snow):
        return Assessment(
            wind=None,
            rain=None,
            snow=None,
            load_override=None,
            final=None,
            reason="Weather data unavailable",
        )

    wind_level = classify_wind(wind_mph)
    rain_level = classify_rain(rain)
    snow_level = classify_snow(snow)
    load_override = apply_load_rules(wind_mph, load_lb)

    weather_level = max(wind_level, rain_level, snow_level)
    final = max(weather_level, load_override) if load_override is not None else weather_level

    return Assessment(
        wind=wind_level,
        rain=rain_level,
        snow=snow_level,
        load_override=load_override,
        final=final,
        reason=_explain(
            final, wind_mph, rain, snow, wind_level, rain_level, snow_level, load_override, load_lb
        ),
    )


def _explain(
    final: RiskLevel,
    wind_mph: float,
    rain: float,
    snow: float,
    wind_level: RiskLevel,
    rain_level: RiskLevel,
    snow_level: RiskLevel,
    load_override: RiskLevel | None,
    load_lb: float,
) -> str:
    """Name every factor that produced the final level, e.g. ``"Wind 47 mph + load ..."``."""
    if final == RiskLevel.LOW:
        return "All conditions low"

    causes: list[str] = []
    if load_override == final and load_override > wind_level:
        rule = next(r for r in LOAD_RULES if r.applies(wind_mph, load_lb))
        causes.append(
            f"Wind {wind_mph:.0f} mph with load {load_lb:,.0f} lb > {rule.min_load_lb:,.0f} lb"
        )
    elif wind_level == final:
        causes.append(f"Wind {wind_mph:.0f} mph")
    if rain_level == final:
        causes.append(f"Rain {rain:.2f} in/hr")
    if snow_level == final:
        causes.append(f"Snow {snow:.2f} in/hr")

    return f"{final.display}: " + "; ".join(causes)

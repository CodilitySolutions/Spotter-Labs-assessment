"""Request validation (DRF serializers) and response shaping (plain functions)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from ..domain.models import Place
from ..services.heatmap_service import Heatmap
from ..services.plan_service import AssessedCheckpoint, Plan, PlannedRoute, TripRequest

# --- Requests --------------------------------------------------------------------------------


class PlaceSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(max_length=300, allow_blank=True, default="")


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure_time = serializers.DateTimeField()
    load_weight_lb = serializers.IntegerField(min_value=0, max_value=80_000)
    checkpoint_interval_mi = serializers.ChoiceField(choices=[10, 25, 50], default=25)

    def to_trip(self) -> TripRequest:
        data = self.validated_data
        return TripRequest(
            origin=Place(data["origin"]["label"], data["origin"]["lon"], data["origin"]["lat"]),
            destination=Place(
                data["destination"]["label"],
                data["destination"]["lon"],
                data["destination"]["lat"],
            ),
            departure_ts=int(data["departure_time"].timestamp()),
            load_lb=data["load_weight_lb"],
            interval_mi=data["checkpoint_interval_mi"],
        )


class GeocodeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=200, trim_whitespace=True)
    # Optional point to rank nearby results first (the frontend sends the map's centre).
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False)
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False)

    def validate(self, attrs):
        if ("lat" in attrs) != ("lon" in attrs):
            raise serializers.ValidationError("Send both lat and lon, or neither.")
        return attrs

    @property
    def near(self) -> tuple[float, float] | None:
        data = self.validated_data
        return (data["lon"], data["lat"]) if "lat" in data else None


# --- Responses -------------------------------------------------------------------------------


def place_json(place: Place) -> dict[str, Any]:
    return {"label": place.label, "lat": round(place.lat, 6), "lon": round(place.lon, 6)}


def plan_json(plan: Plan) -> dict[str, Any]:
    return {
        "plan_id": plan.id,
        "generated_at": plan.generated_at,
        "forecast_window": {"start": plan.window.start, "end": plan.window.end},
        "origin": place_json(plan.request.origin),
        "destination": place_json(plan.request.destination),
        "load_weight_lb": plan.request.load_lb,
        "checkpoint_interval_mi": plan.request.interval_mi,
        "recommended_route_id": plan.recommended_route_id,
        "recommendation_reason": plan.recommendation_reason,
        "warnings": plan.warnings,
        "routes": [_route_json(r) for r in plan.routes],
    }


def _route_json(route: PlannedRoute) -> dict[str, Any]:
    s = route.summary
    return {
        "id": route.id,
        "name": route.name,
        "source": route.candidate.source,
        "is_fallback_profile": route.candidate.is_fallback_profile,
        "geometry": [[round(lon, 5), round(lat, 5)] for lon, lat in route.display_geometry],
        "distance_mi": round(route.candidate.distance_mi, 1),
        "duration_s": round(route.candidate.duration_s),
        "departure_time": route.departure_ts,
        "arrival_time": route.arrival_ts,
        "summary": {
            "rank": route.rank,
            "miles_by_level": {k: round(v, 1) for k, v in s.miles_by_level.items()},
            "severe_miles": round(s.severe_miles, 1),
            "high_miles": round(s.high_miles, 1),
            "avg_risk": round(s.avg_risk, 3) if s.avg_risk is not None else None,
            "worst_level": s.worst_level.label if s.worst_level is not None else None,
        },
        "checkpoints": [_checkpoint_json(c) for c in route.checkpoints],
    }


def _checkpoint_json(c: AssessedCheckpoint) -> dict[str, Any]:
    p, a, w = c.position, c.assessment, c.weather
    return {
        "index": p.index,
        "mile": round(p.mile, 1),
        "segment_mi": round(p.segment_mi, 2),
        "lon": round(p.coord[0], 5),
        "lat": round(p.coord[1], 5),
        "eta": p.eta,
        "weather": None
        if w is None
        else {
            "wind_mph": _r(w.wind_mph, 1),
            "gust_mph": _r(w.gust_mph, 1),
            "rain_in_hr": _r(w.rain_in_hr, 3),
            "snow_in_hr": _r(w.snow_in_hr, 3),
            "source": w.source,
        },
        "levels": {
            "wind": _label(a.wind),
            "rain": _label(a.rain),
            "snow": _label(a.snow),
            "load_override": _label(a.load_override),
        },
        "risk": a.final.label if a.final is not None else "unknown",
        "risk_score": int(a.final) if a.final is not None else None,
        "reason": a.reason,
    }


def heatmap_json(heatmap: Heatmap) -> dict[str, Any]:
    return {
        "plan_id": heatmap.plan_id,
        "start_hour": heatmap.start_hour,
        "hours": heatmap.hours,
        "step_s": 3600,
        "spacing_mi": round(heatmap.spacing_mi, 2),
        "points": [[round(lon, 4), round(lat, 4)] for lon, lat in heatmap.points],
        "scores": heatmap.scores,
    }


def _r(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None


def _label(level: Any) -> str | None:
    return level.label if level is not None else None

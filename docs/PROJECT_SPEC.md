# Project Spec — Weather-Aware Truck Routing

## 1. Goal

Help a truck driver choose the **safest route** for a trip. The app weighs the forecast weather at the truck's expected position along each route, the load weight, and the travel time.

The brief says to prioritize correctness and clarity over extra features.

## 2. User inputs

| Field | Type | Validation |
|---|---|---|
| Origin | Address or place (autocomplete) | Must resolve to coordinates |
| Destination | Address or place (autocomplete) | Must resolve to coordinates and differ from the origin |
| Departure date/time | Local date and time, stored in UTC | Not in the past, and the whole trip must arrive within 48 h of now (see §6) |
| Load weight | Integer, lb | 0 – 80,000 lb |
| Checkpoint interval | 10 / 25 / 50 miles | Defaults to 25 |

The load weight is the **cargo** weight. The risk rules use it as entered. TomTom's truck routing needs the **gross** vehicle weight, so we send cargo + 35,000 lb (a typical empty tractor-trailer).

## 3. What the app produces

1. **3 route options** from the routing API (see §7 for how we guarantee 3).
2. **Checkpoints** on each route at every N miles (N = 10, 25 or 50), plus the origin (mile 0) and the destination.
3. At each checkpoint: its **ETA**, wind, rain, snow, the risk level from each condition, the final risk level, and which rule set that final level.
4. A **risk summary for each route**: distance, duration, ETA at the destination, miles at each risk level, average risk, and the worst level on the route.
5. **One recommended route**, with a short explanation of why it was chosen.
6. A **map** showing all routes (the recommended one highlighted), checkpoint markers colored by risk, and popups with checkpoint details.
7. A **weather risk heatmap** over the trip corridor with a **0–48 h forecast slider**.

## 4. Risk rules

### 4.1 Weather thresholds

Each range includes its lower bound and excludes its upper bound, unless the brief says otherwise. The brief's ranges overlap at the edges (for example, 0.10–0.25 and 0.25–0.50 both contain 0.25), so we settle each edge as follows:

| Level (score) | Wind (mph, sustained) | Rain (in/hr) | Snow (in/hr) |
|---|---|---|---|
| Low (0) | < 25 | < 0.10 | < 0.5 |
| Moderate (1) | 25 – < 35 | 0.10 – < 0.25 | 0.5 – < 1.0 |
| High (2) | 35 – < 45 | 0.25 – < 0.50 | 1.0 – < 2.0 |
| Severe (3) | 45 – < 55 | 0.50 – ≤ 1.00 | 2.0 – ≤ 3.0 |
| No Travel (4) | ≥ 55 | > 1.00 | > 3.0 |

- **Wind** is Open-Meteo `wind_speed_10m` (sustained wind). Gusts are shown for information but are not scored.
- **Rain rate** is `rain + showers`. Open-Meteo reports large-scale rain and convective showers separately, and both are liquid. Each value is the total for that hour, so it equals inches per hour.
- **Snow rate** is `snowfall` for that hour, in inches.

### 4.2 Load rules (applied after the weather levels)

| Condition | Result |
|---|---|
| Wind ≥ 55 mph | No Travel (any load) — already covered by the threshold table |
| 45 ≤ wind < 55 mph **and** load > 30,000 lb | No Travel |
| 35 ≤ wind < 45 mph **and** load > 40,000 lb | Severe |

### 4.3 Final checkpoint risk

```
level = max(wind_level, rain_level, snow_level)
level = max(level, load_override)          # load rules can only raise the level
```

We store the rule that produced the final level, for example `"wind 47 mph + load 35,000 lb > 30,000 lb"`, so the UI can explain it.

If weather is missing for a checkpoint after all fallbacks, its level is **Unknown**. Unknown is never treated as Low. Unknown miles are reported separately.

## 5. Route metrics and recommendation

### 5.1 Miles at each risk level
Every mile is scored by its **nearest checkpoint**. A checkpoint covers the road from halfway back to the previous checkpoint to halfway on to the next (`covers_mi`). The origin covers the first half-interval and the destination the last, so the weather **at departure and arrival counts**. The per-level miles still add up exactly to the route distance.

*Why not "each checkpoint covers the road since the previous one"?* That was the first version. It gives the origin zero miles, so a truck departing into heavy rain was summarised as all Low (seen on a real New York → New Jersey plan, where the origin was High at 0.40 in/hr and every route card showed Low as its highest risk). The nearest-checkpoint rule fixes that without double-counting any checkpoint.

### 5.2 Average risk
Average risk is weighted by distance: `Σ(score_k × covers_mi_k) / known_miles` (unknown miles are left out).

### 5.3 Ranking (lowest wins), compared left to right

1. `has_no_travel` — any route with a No Travel segment ranks below every route without one.
2. `severe_miles` — miles at **Severe or worse**.
3. `high_miles`
4. `avg_risk`
5. `duration_s`

The brief's ranking only mentions Severe miles. We count No Travel as part of Severe and also put it ahead in the sort, because a No Travel segment should never lose out just because the route is shorter. If **every** route has No Travel segments, the app still ranks them but shows a "No safe route in this window — consider a later departure" warning.

The explanation names the first comparison in the ranking that decided the winner, for example *"Route B: 0 severe miles vs 42 on Route A."*

## 6. Time handling

- All backend times are **UTC Unix seconds**. The frontend shows them in the browser's time zone.
- Checkpoint ETA = departure + the interpolated travel time at that checkpoint's distance along the route (see the implementation plan).
- The weather for a checkpoint is the forecast for the **hour that contains its ETA**.
- The forecast window is **the current UTC hour to +48 h**, the same window as the heatmap.
- The departure must fall inside it, and the **fastest** route must arrive inside it. Otherwise the API returns a `400` explaining why. Checkpoints on slower alternatives that fall past the window are **Unknown** ("Arrival is beyond the 48-hour forecast"), and their miles are reported as unknown rather than scored.
- Weather is looked up by snapping each checkpoint to a **0.1° cell** (at most ~4 mi away, about the forecast models' own resolution). Each cell's full 49-hour forecast is cached for an hour and shared by all routes, repeat plans and the heatmap.

## 7. Guaranteeing 3 routes

1. Request TomTom with `maxAlternatives=2` (3 routes). Measured on a ~1,000-mile trip: 2 alternatives take about 4–5 s, while 5 take about 12 s and send 4 MB, so we ask for fewer and fill gaps with detours. Drop near-duplicates: two routes are duplicates when **each** has over 85% of its length (sampled every 0.5 mi) within 200 m of the other and keep the 3 fastest distinct routes.
2. If we still have fewer than 3, generate **detour routes**: take a point offset sideways by 10–15% of the trip distance from the midpoint, on the left and on the right, and send it to TomTom as a waypoint.
3. If TomTom fails, use **OSRM** with `alternatives=3`. These routes are labeled `source: "osrm"` (car profile), and the UI says so.
4. If fewer than 3 distinct routes exist at all (for example, a very short trip), return what we have and say so. We never make up a route.

## 8. Heatmap

- **Area:** a regular grid covering every place within **40 miles** of any of the routes. Its spacing is tuned so the grid has about **300 points** (±25%), whatever the trip length.
- **Time:** forecast hours **0–48 from now** (hour 0 = the current hour). The departure time and the checkpoint ETAs are marked on the slider.
- **Value:** the checkpoint risk score from §4, with the trip's load weight applied, for each point and each hour. `null` where weather is unknown.
- **Why an area is risky:** each point and hour also carries the level from wind, rain and snow on their own (wind including the load rules) and the raw values, all from the same `assess()` call as the checkpoints. The map can show one condition at a time, name the cause ("Severe: wind up to 48 mph with 42,000 lb load"), explain any spot on hover or tap, and draw wind-direction arrows.
- **Weather source:** Open-Meteo only. NWS needs a request per point, too slow for ~300 points, so if Open-Meteo is down the heatmap returns `502` while the plan itself still works.
- **Performance:** the whole 49-hour grid is fetched once. Moving the slider only changes what is drawn and makes **no network requests**.

## 9. API contract

### `GET /api/geocode?q=<text>`
`→ [{ label, lat, lon }]` (up to 5 results)

### `POST /api/plan`
```json
{
  "origin": { "lat": 41.88, "lon": -87.63, "label": "Chicago, IL" },
  "destination": { "lat": 39.74, "lon": -104.99, "label": "Denver, CO" },
  "departure_time": "2026-11-07T14:00:00Z",
  "load_weight_lb": 42000,
  "checkpoint_interval_mi": 25
}
```
```json
{
  "plan_id": "uuid",
  "generated_at": 1762437600,
  "forecast_window": { "start": 1762434000, "end": 1762606800 },
  "recommended_route_id": "r2",
  "recommendation_reason": "Fewest severe miles (0 vs 42).",
  "warnings": [],
  "routes": [
    {
      "id": "r1",
      "name": "Route A",
      "source": "tomtom",
      "is_fallback_profile": false,
      "geometry": [[lon, lat], ...],   // simplified for display (~30 m tolerance)
      "distance_mi": 1003.2,
      "duration_s": 54000,
      "arrival_time": 1762491600,
      "summary": {
        "miles_by_level": { "low": 800, "moderate": 120, "high": 41, "severe": 42, "no_travel": 0, "unknown": 0 },
        "severe_miles": 42,
        "high_miles": 41,
        "avg_risk": 0.41,
        "worst_level": "severe",
        "rank": 2
      },
      "checkpoints": [
        {
          "index": 0, "mile": 0, "covers_mi": 12.5, "lat": 41.88, "lon": -87.63, "eta": 1762437600,
          "weather": { "wind_mph": 12, "gust_mph": 20, "rain_in_hr": 0.0, "snow_in_hr": 0.0, "source": "open-meteo" },
          "levels": { "wind": "low", "rain": "low", "snow": "low", "load_override": null },
          "risk": "low", "risk_score": 0, "reason": "All conditions low"
        }
      ]
    }
  ]
}
```

### `GET /api/plan/{plan_id}/heatmap`
```json
{
  "plan_id": "uuid",
  "start_hour": 1762434000,
  "hours": 49,
  "step_s": 3600,
  "points": [[lon, lat], ...],
  "spacing_mi": 7.1,
  "scores": [[0,0,1,...49 values], ...],  // overall level 0-4, or null when unknown
  "wind_levels": [[...]], "rain_levels": [[...]], "snow_levels": [[...]],  // each condition alone; wind includes load rules
  "load_raised": [[0,1,...]],             // 1 where the load rules raised the wind level
  "wind_mph": [[...]], "wind_dir_deg": [[...]],  // direction the wind comes FROM
  "rain_in_hr": [[...]], "snow_in_hr": [[...]]
}
```
Scores are stored as numbers rather than level names to keep the response small. It is served separately so the routes can appear on the map before the heatmap finishes loading.

### Errors
Errors use the shape `{ "error": { "code", "message", "details"? } }`.

| Status | Codes |
|---|---|
| 400 | `invalid_request` (field errors in `details`), `departure_in_past`, `departure_beyond_forecast`, `trip_beyond_forecast`, `same_place` |
| 404 | `plan_not_found` (the plan expired from the cache after 1 h) |
| 422 | `no_route` (no road route exists) |
| 502 | `routing_unavailable`, `weather_unavailable`, `geocoding_unavailable` (every provider failed) |

## 10. Non-functional requirements

- **Reliability:** every external call has a timeout (8 s; 20 s for TomTom routing), one retry with backoff for timeouts, network errors, 429 and 5xx, and then the fallback provider. Request URLs (which carry API keys) are never logged.
- **Performance:** `POST /api/plan` should finish in under about 8 s with an empty cache (TomTom truck routing alone takes ~5 s on long trips) and under 1 s when cached. The heatmap slider should run at 60 fps.
- **Quotas:** every response is cached (geocoding 24 h, routes 10 min, weather 1 h). One plan uses about 15 external calls when nothing is cached.
- **Correctness:** the risk engine and the ranking are pure functions with unit tests covering every threshold edge.

## 11. Out of scope

User accounts, saved trips, live traffic re-routing, hosting/CI (for now), mobile apps, and route segments outside the forecast providers' coverage.

# Implementation Plan

The phases run in order, and each one ends with something you can check. The logic work (phases 1–4) comes first because it carries the most marks (40%) and is the easiest to test without a UI.

See [PROJECT_SPEC.md](PROJECT_SPEC.md) for the rules and [TECH_STACK.md](TECH_STACK.md) for the libraries.

## Repository layout

```
assessment-trucks/
├── docs/
├── backend/
│   ├── config/                 # Django settings, urls
│   ├── routing/                # Django app
│   │   ├── api/                # DRF views + serializers
│   │   ├── providers/          # external services, one module each
│   │   │   ├── base.py         # http client, retry, cache helpers
│   │   │   ├── tomtom.py       # routing + geocoding
│   │   │   ├── osrm.py
│   │   │   ├── photon.py
│   │   │   ├── open_meteo.py
│   │   │   └── nws.py
│   │   ├── domain/             # pure logic, no I/O
│   │   │   ├── models.py       # dataclasses: Route, Checkpoint, Weather, RiskLevel
│   │   │   ├── risk.py         # thresholds + load rules
│   │   │   ├── geometry.py     # haversine, polyline walking, dedupe, detours, grid
│   │   │   ├── checkpoints.py  # sample points + ETA interpolation
│   │   │   └── ranking.py      # route metrics + recommendation
│   │   └── services/           # assembles providers + domain into a plan
│   │       ├── route_service.py
│   │       ├── weather_service.py
│   │       ├── plan_service.py
│   │       └── heatmap_service.py
│   └── tests/
│       ├── fixtures/           # recorded API responses
│       ├── test_risk.py
│       ├── test_ranking.py
│       ├── test_checkpoints.py
│       ├── test_geometry.py
│       ├── test_providers.py
│       └── test_api.py
└── frontend/
    └── src/
        ├── api/                # typed client + TanStack Query hooks
        ├── components/
        │   ├── TripForm.tsx
        │   ├── PlaceAutocomplete.tsx
        │   ├── RouteList.tsx
        │   ├── RouteCard.tsx
        │   ├── CheckpointTable.tsx
        │   ├── ForecastSlider.tsx
        │   └── map/
        │       ├── TripMap.tsx
        │       ├── RouteLayers.tsx
        │       ├── CheckpointLayer.tsx
        │       └── HeatmapLayer.tsx
        ├── lib/                # risk colors, formatting
        └── types.ts
```

`domain/` never imports from `providers/`. That separation keeps the logic testable and easy to read.

---

## Phase 0 — Scaffolding

- [x] `backend/`: Django project, DRF, CORS, `django-environ`, `ruff`, `pytest-django`, `.env.example`
- [x] `frontend/`: Vite React + TypeScript, Tailwind, MapLibre, TanStack Query, ESLint/Prettier, Vite proxy for `/api`
- [x] Root `README.md` with setup steps and a `.gitignore`
- [ ] `git init` and a first commit

**Done when:** `GET /api/health` returns 200, and the frontend renders an OpenFreeMap base map.

## Phase 1 — Risk engine (pure)

- [x] `RiskLevel` IntEnum: `LOW=0 … NO_TRAVEL=4`; Unknown is `final=None`, so it can never be mistaken for a level in `max()` or averages
- [x] `classify_wind`, `classify_rain`, `classify_snow` with the boundaries exactly as in spec §4.1
- [x] `apply_load_rules(wind_mph, load_lb) -> RiskLevel | None`
- [x] `assess(weather, load_lb) -> Assessment(levels, final, reason)`
- [x] Tests with a table of cases for **every boundary**: 24.9/25/34.9/35/44.9/45/54.9/55 mph; 0.0999/0.10/0.25/0.50/1.00/1.0001 in; 0.49/0.5/1.0/2.0/3.0/3.01 in. Load cases: 30,000 vs 30,001 lb, 40,000 vs 40,001 lb, combined with wind just inside and just outside each band.

**Done when:** all tests pass and the spec table can be checked line by line against the code.

## Phase 2 — Geometry and checkpoints (pure)

- [x] `haversine_mi`, `cumulative_distances(polyline)`
- [x] `point_at_distance(polyline, cumdist, d)` using linear interpolation along the segment that contains distance `d`
- [x] `sample_checkpoints(polyline, timeline, interval_mi, departure_ts)` → mile 0, every interval, and the destination (dropping the last regular checkpoint if it falls within 0.5 mi of the destination)
- [x] `elapsed_at(timeline, fraction)`, where `timeline` is a list of `TimelinePoint(distance_mi, elapsed_s)` built from TomTom's guidance instructions. It interpolates linearly by fraction of the route, so a small length mismatch between the API and our polyline doesn't skew ETAs. For OSRM, build the timeline from the per-step `distance`/`duration` values.
- [x] `route_similarity(a, b)` for dropping duplicate routes, and `detour_waypoint(origin, dest, side, ratio)` for generating detours
- [x] `corridor_grid(polylines, corridor_mi, target_points)` for the heatmap

**Done when:** tests pass on synthetic routes, such as a straight 100-mile line and an L-shaped line with known answers.

## Phase 3 — Providers

- [x] `base.py`: a shared `httpx.Client` with an 8 s timeout, a `tenacity` retry on timeouts, network errors, 429 and 5xx (2 attempts, exponential backoff), a per-call timeout override (20 s for TomTom routing), and httpx request logging silenced because URLs carry the API key, and a `cached(key, ttl)` helper
- [x] `tomtom.py`: `geocode(q)` and `calculate_route(origin, dest, depart_at, weight_kg, max_alternatives, waypoints=None)`, normalized into a `Route` with geometry, distance, duration and timeline
- [x] `osrm.py`: `route(origin, dest, alternatives=3)` normalized into the same `Route` shape with `source="osrm"`
- [x] `photon.py`: geocoding fallback
- [x] `open_meteo.py`: `hourly(points, start, end)` that sends chunks of about 100 coordinates per request and returns `{(lat, lon): {hour_ts: Weather}}`, with `rain_in_hr = rain + showers`
- [x] `nws.py`: a US-only fallback that converts its units to mph and inches per hour
- [x] Record real responses once into `tests/fixtures/`, and test the parsers against them using `respx`
- [x] **Checked:** Open-Meteo returns `snowfall` in inches when `precipitation_unit=inch` (its `hourly_units` say `"inch"`). One location comes back as an object, several as a list.
- [x] `scripts/record_fixtures.py` re-records all fixtures through the real provider functions

**Done when:** provider tests pass offline, and a manual script prints 3 routes and the weather for a real trip.

## Phase 4 — Plan service and recommendation

- [x] `route_service.get_routes()`: TomTom with 2 alternatives, then duplicate removal, then detour routes (left and right in parallel, 15% then 30% offsets, rejected if over 1.5× the fastest time), then the OSRM fallback (spec §7). Cached 10 min.
- [x] `weather_service.get_weather()`: snap points to 0.1° cells, cache each cell's whole 0–48 h window, fetch missing cells from Open-Meteo in parallel batches of 100, fall back to NWS per cell
- [x] `ranking.summarize(route)` → miles at each level, average risk, worst level
- [x] `ranking.recommend(routes)` → a sort by the five keys in spec §5.3, plus the reason text
- [x] Route lines simplified for display (Douglas–Peucker, ~30 m): ~15k → ~1k points per route
- [x] `plan_service.create_plan()` puts the pieces together, caches the plan by `plan_id` (it is needed for the heatmap), and adds warnings
- [x] `POST /api/plan` and `GET /api/geocode` with DRF serializers and input validation
- [x] Ranking tests: one test per tie-breaker, the "all routes have No Travel" warning, and Unknown miles

**Done when:** `POST /api/plan` returns the JSON in spec §9 for a real trip. Measured on Chicago→Denver: 6.8 s with an empty cache, 0.7 s cached, 107 KB.

## Phase 5 — Heatmap endpoint

- [x] `heatmap_service.build(plan)`: build the corridor grid, fetch 49 hours of weather in batches, score each cell and hour with `assess()` using the trip's load, and return compact arrays
- [x] `GET /api/plan/{id}/heatmap`, cached for 1 h

- [x] GZip on API responses (Django middleware; `gzip_proxied any` in the prod nginx)

**Done when:** the response is under about 150 KB for a cross-country trip and the scores match a spot check. Measured on Chicago→Denver: 306 points × 49 h, 1.35 s with an empty cache, 34 ms cached, 36 KB raw / 1.4 KB gzipped.

## Phase 6 — Frontend: form and results panel

- [x] `TripForm`: two `PlaceAutocomplete` fields (debounced 300 ms), a date/time picker, a load weight field, and a 10/25/50 toggle. Validation matches the backend.
- [x] `usePlan` mutation, with loading and error states that show the backend's error message
- [x] `RouteList` / `RouteCard`: distance, duration, arrival time, a stacked bar of miles at each risk level, a "Recommended" badge, the recommendation reason, and a fallback-source label
- [x] `CheckpointTable` for the selected route: mile, ETA, wind/rain/snow, risk chip, and reason

## Phase 7 — Map: routes and checkpoints

- [x] Draw all routes as one GeoJSON source with data-driven styling: the recommended route thick and opaque, the others thin. Clicking a route selects it.
- [x] Draw checkpoints as one source and a circle layer colored by `risk_score`, with a popup showing the details
- [x] Fit the map to the routes' bounds, and keep the map and the list selection in sync
- [x] Add a legend for the risk colors

**Performance rule:** use one source per feature type, and update it with `setData` instead of creating React components for each marker.

**Decisions made while building Phases 6–7:**
- Risk levels use the reserved *status* palette (Low `#0ca30c`, Moderate `#fab219`, High `#ec835a`, Severe `#d03b3b`, No Travel `#7a1f1f` plus a ⊘ icon, Unknown gray), and always appear with a text label.
- Routes are told apart by **letter (A/B/C) and line weight**: the selected route is blue, the others gray. No route takes an orange or red hue that could be mistaken for a risk level.
- Basemap: OpenFreeMap *Positron*, a quiet low-contrast style. Route lines are drawn **beneath** its place labels; checkpoints are drawn above.
- MapLibre v6's worker is bundled with `?worker&url` and passed to `setWorkerUrl` ([lib/maplibre.ts](../frontend/src/lib/maplibre.ts)). Without this the map stays blank, because Vite's pre-bundling breaks MapLibre's default worker lookup.
- Checked by driving the real app in headless Chrome (desktop 1440×900 and phone 390×844) with no console errors.

## Phase 8 — Heatmap and slider

- [x] Heatmap: one GeoJSON source with every grid point carrying all 49 hourly scores (`h0`..`h48`), drawn as **one MapLibre heatmap layer per risk level** (Moderate..No Travel). Each layer weights only points at exactly its level, so density decides where a band's soft edge falls but never which level it shows.
- [x] `ForecastSlider` for hours 0–48, showing the local time label and markers for the departure and arrival times
- [x] Changing the slider only swaps the property each layer's weight expression reads (`['get', 'h13']`): no `setData`, no new data and no network request. MapLibre still re-evaluates the points and redraws each heatmap layer (measured ~10 ms per change).
- [x] Optional play button that steps through the hours
- [x] Show/hide toggle for the heatmap (routes stay visible; a route toggle was not needed)

**Done when:** dragging the slider stays smooth (check with the Chrome Performance panel) on a cross-country trip.
- [x] Truck marker showing where the truck is on the selected route at the slider's time (interpolated between checkpoint ETAs); the selected route's driving window is highlighted on the slider track.

- [x] **Risk timeline** above the slider: 49 bars, one per hour, coloured by the worst level anywhere in the corridor (click a bar to jump there). It makes the slider useful even when the weather is calm, because all-green confirms the whole 48 hours are clear.
- [x] **Status line**: the corridor's worst level at the chosen hour plus where the truck is ("Truck near mile 312 on Route A", "Route A has arrived"), announced to screen readers.
- [x] **Driving window** drawn as its own labelled band ("Route A on the road") instead of a tint under the slider's fill, which hid it.

- [x] **What causes the risk:** a view switch (Overall · Wind · Rain · Snow); the cause in the status line and timeline tooltips ("No Travel: rain up to 1.84 in/hr", "wind up to 48 mph with 42,000 lb load"); and a hover/tap card at any spot with the level from each condition, wind speed and direction, and whether the load rule applied. The backend returns per-condition levels and raw values from the same `assess()` call as the checkpoints.
- [x] **Wind arrows:** Open-Meteo `wind_direction_10m` (NWS `windDirection` as fallback), drawn on a quarter of the grid points, pointing where the wind blows and sized by speed; they move with the slider.
- [x] The heatmap stays visible to zoom 10 and fades out by 12, so short trips (which frame at ~zoom 9) still show it. The map follows the slider through `useDeferredValue`, so a fast drag skips in-between hours instead of lagging (normal drag 60 fps with no slow frames, fast drag 58–59 fps).

**Decisions and measurements:**
- **Why one layer per level.** The first version used one heatmap whose density represented score/4. In a corridor only ~5 grid points wide, the summed density never reaches its full value, so High areas rendered as Moderate: a safety display understating risk. Per-level layers fix that by construction.
- **Kernel sizing.** The radius is 2× the grid spacing at every zoom (the backend returns `spacing_mi`), with intensity `1 / (0.2785 × 4)` so a solid area reaches density ~1. The heatmap fades out past zoom 8, where checkpoints are more informative.
- **Smoothness by drag speed** (headless Chrome, 240 frames each): ~15 hour changes/sec → 60 fps, no slow frames; ~30/sec → 59 fps, 3 slow frames; an artificial 60/sec → 52 fps. Profiling showed React's share is small (60 fps with the heatmap hidden); the cost is MapLibre redrawing the four visible heatmap layers. The 49-bar timeline is memoised so its tooltips aren't re-formatted on every change.
- **Verified** in headless Chrome with fabricated five-band scores swapped into the real heatmap response. Each band rendered in its own level's colour and moved correctly with the slider. Stepping the slider every animation frame for 179 frames averaged **16.7–17.1 ms per frame (~60 fps)**, p95 16.8 ms.


## Phase 9 — Polish and documentation

- [x] Empty, loading and error states. Warnings for fallback-provider routes and for "No safe route".
- [x] Layout that works at laptop width and stays usable on mobile
- [x] README: architecture diagram, how to run, the risk rules and the decisions made at their boundaries (copied from the spec), known limitations
- [x] Run `ruff` and `eslint` cleanly, and make sure all tests pass
- [x] Attribution for Open-Meteo (required by CC BY 4.0) and TomTom in the map credits
- [x] Error boundary around the map: without WebGL, the panel (routes, checkpoints, recommendation) still works
- [x] Map lazy-loaded as its own chunk: main bundle 398 KB → 94 KB gzipped
- [x] Frontend unit tests (Vitest) for the heatmap, timeline and truck-position logic and the formatting helpers, run by `make test`
- [x] Phones: the forecast slider sits below the map instead of covering it
- [x] Checked in headless Chrome: no-route error (Honolulu → Los Angeles), phone layout, desktop results


## Phase 10 — Loom walkthrough (5–10 min)

1. The problem and the architecture (1 min)
2. Live demo: enter a trip, compare the routes, explain the recommendation, inspect checkpoints, drag the heatmap slider (3–4 min)
3. Code tour: the risk engine and its tests, the ranking, the provider fallbacks (2–3 min)
4. Trade-offs and what I'd do next (1 min)

The free Loom plan stops recordings at 5 minutes, so either keep the video short or use the Business trial.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| TomTom returns fewer than 3 alternatives | Generated detour routes, then the OSRM fallback (spec §7) |
| Hitting the free API limits during development | Aggressive caching plus recorded fixtures in tests |
| Open-Meteo unit surprises (snowfall unit) | Verified in Phase 3 with a fixture and a test |
| The heatmap slider stutters | All 49 hours precomputed and loaded once; the slider only swaps a style expression; the timeline is memoised. Measured 60 fps at normal drag speeds |
| Trip ETAs extend past the forecast window | Rejected during validation with a clear message |

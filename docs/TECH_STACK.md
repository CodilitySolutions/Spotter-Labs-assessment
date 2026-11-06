# Tech Stack

Every service listed here is free, and none of them needs a credit card. Each external dependency that the app needs to work has a **fallback**, so one provider going down or throttling us does not break a trip plan.

## Overview

```
React (Vite + TS) ──HTTP/JSON──▶ Django + DRF ──▶ TomTom (routing, geocoding)
   MapLibre GL                      │  cache       ├─▶ OSRM (routing fallback)
   OpenFreeMap tiles                │              ├─▶ Photon / Nominatim (geocoding fallback)
                                    │              ├─▶ Open-Meteo (weather)
                                    ▼              └─▶ NWS api.weather.gov (weather fallback, US only)
                              risk engine (pure Python)
```

The browser only talks to our Django API. API keys and calls to third-party services stay on the server.

## Backend

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Current stable release with good typing support |
| Framework | Django 5.x + Django REST Framework | Required by the brief. DRF serializers validate requests and responses. |
| HTTP client | `httpx` | Timeouts on every call. Async-capable, so the batched weather fetches can run concurrently. |
| Retries | `tenacity` | Exponential backoff that only retries on timeouts and 5xx/429 responses |
| Cache | Django cache framework (`FileBasedCache` in dev, Redis optional) | Caches geocoding, routes and weather to stay well inside the free quotas |
| Geometry | Plain Python (haversine, polyline walking) | Splitting a route by distance and building the corridor grid don't need heavy GIS libraries |
| Polyline decoding | `polyline` | OSRM returns an encoded polyline |
| Config | `django-environ` | API keys and settings from `.env` |
| Tests | `pytest`, `pytest-django`, `respx` | `respx` mocks `httpx`, so tests run on recorded fixtures and never call live APIs |
| Lint/format | `ruff` | One fast tool for both linting and formatting |
| CORS | `django-cors-headers` | Lets the Vite dev server call the API |

## Frontend

| Concern | Choice | Why |
|---|---|---|
| Build | Vite | Fast dev server, simple configuration |
| Language | React 18 + TypeScript | Typed API contract shared with the backend's response shapes |
| Map | MapLibre GL JS (via `react-map-gl/maplibre`) | WebGL rendering with a **built-in heatmap layer**, so the forecast slider stays smooth |
| Base tiles | OpenFreeMap | Free vector tiles with no API key |
| Server state | TanStack Query | Caching, loading and error states, and request deduplication |
| Styling | Tailwind CSS | Quick, consistent UI without a component library |
| Date/time | `date-fns` + `date-fns-tz` | Formats UTC timestamps in the user's local time |
| Lint/format | ESLint + Prettier | Standard setup |

## External services

### Routing — TomTom Routing API (primary)
- Endpoint: `GET /routing/1/calculateRoute/{origin}:{destination}/json`
- Parameters: `travelMode=truck`, `vehicleWeight` (kg), `departAt`, `maxAlternatives=5`, `routeType=fastest`, `instructionsType=coded`.
- The guidance instructions give a distance from the start (`routeOffsetInMeters`) and the elapsed time (`travelTimeInSeconds`) at each maneuver. We interpolate between them to get **realistic arrival times at each checkpoint**.
- Free tier: 2,500 non-tile requests per day, shared across all TomTom APIs. No credit card is required.

### Routing — OSRM public server (fallback)
- `router.project-osrm.org` / `routing.openstreetmap.de`, with `alternatives=3`.
- It only has a **car profile** and is limited to 1 request per second with no uptime guarantee. We use it only when TomTom fails, and the UI labels those routes as fallback routes.

### Geocoding — Photon (primary), TomTom Search (fallback)
- Photon (`photon.komoot.io`) is free, needs no key and is built on OpenStreetMap data, with worldwide coverage. Requests use `lang=en` (otherwise names come back in the local script, e.g. Urdu) and the map's centre as a location bias once the user has zoomed into a region.
- TomTom Fuzzy Search is the fallback. It was the original primary, but its index misses major cities in some regions; for example, a search for "Lahore" returns a neighbourhood of Islamabad and not the city itself.
- Search is **worldwide**. Routing (TomTom truck) and weather (Open-Meteo) are global too; only the NWS weather fallback is US-only, and it is skipped for points outside the US.

### Weather — Open-Meteo (primary)
- Endpoint: `GET https://api.open-meteo.com/v1/forecast`
- Parameters: `hourly=wind_speed_10m,wind_gusts_10m,rain,showers,snowfall`, `wind_speed_unit=mph`, `precipitation_unit=inch`, `timeformat=unixtime`, `timezone=GMT`, `forecast_days=3`, plus several comma-separated latitudes and longitudes per request.
- Free for non-commercial use: 600 calls per minute, 5,000 per hour and 10,000 per day. A request for many locations counts as several calls.

### Weather — National Weather Service (fallback, US only)
- `api.weather.gov/points/{lat},{lon}` → gridpoint forecast data, which includes `windSpeed`, `quantitativePrecipitation` and `snowfallAmount`.
- Free with no key. It only needs a `User-Agent` header. It only covers the US, so points elsewhere skip it and stay Unknown if Open-Meteo is down.

### Rejected options
- **OpenRouteService:** its public API refuses alternative routes for trips over 100 km, which rules it out for trucking.
- **HERE:** excellent truck routing, but we couldn't confirm the free plan from an official HERE source.
- **OpenWeatherMap:** its forecast map tiles are paid, and the free tier is less generous than Open-Meteo's.

## Local development

- `backend/` — `python -m venv .venv && pip install -r requirements.txt && python manage.py runserver`
- `frontend/` — `npm install && npm run dev` (Vite proxies `/api` to `localhost:8000`)
- Environment variables: `TOMTOM_API_KEY`, `NWS_USER_AGENT`, `DJANGO_SECRET_KEY`, `DEBUG`, `CACHE_URL` (optional)

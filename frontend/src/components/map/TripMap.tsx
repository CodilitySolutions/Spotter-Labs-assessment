import type { FeatureCollection, LineString, Point } from 'geojson';
import 'maplibre-gl/dist/maplibre-gl.css';
import '../../lib/maplibre';
import { LngLatBounds, type ExpressionSpecification } from 'maplibre-gl';
import { useEffect, useMemo, useRef, useState } from 'react';
import MapGL, {
  Layer,
  Marker,
  NavigationControl,
  Popup,
  Source,
  type MapLayerMouseEvent,
  type MapRef,
} from 'react-map-gl/maplibre';
import { Truck } from 'lucide-react';
import { useHeatmap } from '../../api/plan';
import {
  HEATMAP_INTENSITY,
  HEATMAP_LEVELS,
  heatmapGeoJSON,
  hourIndex,
  levelColorExpression,
  levelWeightExpression,
  meanLatitude,
  radiusExpression,
  truckPosition,
  worstScorePerHour,
} from '../../lib/heatmap';
import { formatTime } from '../../lib/format';
import { RISK_COLOR, RISK_SCORE_COLOR_EXPRESSION } from '../../lib/risk';
import { ROUTE_LETTERS } from '../../lib/routes';
import type { LonLat, Plan } from '../../types';
import { CheckpointPopup } from './CheckpointPopup';
import { ForecastSlider } from './ForecastSlider';
import { MapLegend } from './MapLegend';

// Positron: a quiet, low-contrast basemap that keeps routes and risk colors legible.
const MAP_STYLE = 'https://tiles.openfreemap.org/styles/positron';
const ACCENT = '#2a78d6';
const ROUTE_IDLE = '#9a988f';
const ROUTE_HOVER = '#5f5d57';
const INTERACTIVE_LAYERS = ['checkpoints', 'route-hit'];
// Below this zoom the view spans continents, so its centre says nothing about where to search.
const REGION_ZOOM = 3;

interface TripMapProps {
  plan: Plan | null;
  loading: boolean;
  selectedRouteId: string | null;
  focusedIndex: number | null;
  onSelectRoute: (id: string) => void;
  onFocusCheckpoint: (index: number | null) => void;
  /** Reports the map centre when zoomed into a region (null at world/continent zoom). */
  onFocusAreaChange: (center: LonLat | null) => void;
}

export function TripMap({
  plan,
  loading,
  selectedRouteId,
  focusedIndex,
  onSelectRoute,
  onFocusCheckpoint,
  onFocusAreaChange,
}: TripMapProps) {
  const mapRef = useRef<MapRef>(null);
  const [hoveredRoute, setHoveredRoute] = useState<string | null>(null);
  const [pointer, setPointer] = useState(false);
  const [labelLayerId, setLabelLayerId] = useState<string | undefined>();

  // Forecast slider state. Hour 0 is the start of the plan's forecast window.
  const heatmapQuery = useHeatmap(plan?.plan_id ?? null);
  const heatmap = heatmapQuery.data ?? null;
  const [hour, setHour] = useState(0);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [syncedHeatmap, setSyncedHeatmap] = useState<string | null>(null);

  const selectedRoute = plan?.routes.find((r) => r.id === selectedRouteId) ?? null;
  const focused = selectedRoute?.checkpoints.find((c) => c.index === focusedIndex) ?? null;

  // When a new heatmap arrives, start the slider at the selected route's departure hour.
  if (heatmap && heatmap.plan_id !== syncedHeatmap) {
    setSyncedHeatmap(heatmap.plan_id);
    setPlaying(false);
    setHour(
      selectedRoute
        ? hourIndex(heatmap.start_hour, heatmap.hours, selectedRoute.departure_time)
        : 0,
    );
  }

  const heatmapData = useMemo(() => (heatmap ? heatmapGeoJSON(heatmap) : null), [heatmap]);
  const worstByHour = useMemo(() => (heatmap ? worstScorePerHour(heatmap) : null), [heatmap]);
  const heatmapRadius = useMemo(
    () => (heatmap ? radiusExpression(heatmap.spacing_mi, meanLatitude(heatmap.points)) : null),
    [heatmap],
  );
  const sliderTime = heatmap ? heatmap.start_hour + hour * 3600 : null;
  // Mid-hour, so the marker sits where the truck is during the hour the heatmap shows.
  const truck =
    selectedRoute && sliderTime !== null ? truckPosition(selectedRoute, sliderTime + 1800) : null;

  const routesData = useMemo<FeatureCollection<LineString>>(
    () => ({
      type: 'FeatureCollection',
      features: (plan?.routes ?? []).map((route) => ({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: route.geometry },
        properties: {
          id: route.id,
          selected: route.id === selectedRouteId,
          hovered: route.id === hoveredRoute,
        },
      })),
    }),
    [plan, selectedRouteId, hoveredRoute],
  );

  const checkpointsData = useMemo<FeatureCollection<Point>>(
    () => ({
      type: 'FeatureCollection',
      features: (selectedRoute?.checkpoints ?? []).map((cp) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [cp.lon, cp.lat] },
        properties: {
          index: cp.index,
          risk_score: cp.risk_score,
          focused: cp.index === focusedIndex,
        },
      })),
    }),
    [selectedRoute, focusedIndex],
  );

  // Frame every route whenever a new plan arrives.
  useEffect(() => {
    const map = mapRef.current;
    if (!plan || !map) return;
    const bounds = new LngLatBounds();
    plan.routes.forEach((route) => route.geometry.forEach((p) => bounds.extend(p)));
    // Keep routes clear of the legend (top-left on wider maps) and the forecast slider (bottom).
    const width = map.getContainer().clientWidth;
    const legendSpace = width >= 900 ? 300 : 48;
    // On phones the slider sits below the map rather than over it.
    const sliderSpace = width >= 640 ? 180 : 40;
    map.fitBounds(bounds, {
      padding: { top: 72, bottom: sliderSpace, left: legendSpace, right: 48 },
      duration: 900,
    });
  }, [plan]);

  // Bring a checkpoint chosen from the table into view.
  useEffect(() => {
    const map = mapRef.current;
    if (!focused || !map) return;
    map.easeTo({
      center: [focused.lon, focused.lat],
      zoom: Math.max(map.getZoom(), 7),
      duration: 600,
    });
  }, [focused]);

  function handleClick(event: MapLayerMouseEvent) {
    const feature = event.features?.[0];
    if (feature?.layer.id === 'checkpoints') {
      onFocusCheckpoint(Number(feature.properties.index));
    } else if (feature?.layer.id === 'route-hit') {
      onSelectRoute(String(feature.properties.id));
    } else {
      onFocusCheckpoint(null);
    }
  }

  function handleMouseMove(event: MapLayerMouseEvent) {
    const feature = event.features?.[0];
    setPointer(Boolean(feature));
    const routeId = feature?.layer.id === 'route-hit' ? String(feature.properties.id) : null;
    if (routeId !== hoveredRoute) setHoveredRoute(routeId);
  }

  return (
    <div className="relative flex h-full w-full flex-col">
      <div className="relative min-h-0 flex-1">
        <MapGL
          ref={mapRef}
          initialViewState={{ longitude: 20, latitude: 25, zoom: 1.6 }}
          onMoveEnd={(event) => {
            const { longitude, latitude, zoom } = event.viewState;
            onFocusAreaChange(zoom >= REGION_ZOOM ? [longitude, latitude] : null);
          }}
          mapStyle={MAP_STYLE}
          interactiveLayerIds={INTERACTIVE_LAYERS}
          onLoad={(event) => {
            const firstLabel = event.target.getStyle().layers.find((l) => l.type === 'symbol');
            setLabelLayerId(firstLabel?.id);
          }}
          onClick={handleClick}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => {
            setPointer(false);
            setHoveredRoute(null);
          }}
          cursor={pointer ? 'pointer' : undefined}
          style={{ position: 'absolute', inset: 0 }}
          attributionControl={{
            compact: true,
            customAttribution:
              'Weather <a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo</a> (CC BY 4.0) · Routing © TomTom',
          }}
        >
          <NavigationControl position="top-right" showCompass={false} />

          {heatmapData && heatmapRadius && plan && (
            <Source id="heatmap" type="geojson" data={heatmapData}>
              {/* Lowest level first, so more severe bands draw on top. */}
              {HEATMAP_LEVELS.map(({ score, level }) => (
                <Layer
                  key={level}
                  id={`weather-heatmap-${level}`}
                  type="heatmap"
                  beforeId="route-casing"
                  layout={{ visibility: showHeatmap ? 'visible' : 'none' }}
                  paint={{
                    'heatmap-weight': levelWeightExpression(hour, score),
                    'heatmap-radius': heatmapRadius,
                    'heatmap-intensity': HEATMAP_INTENSITY,
                    'heatmap-color': levelColorExpression(RISK_COLOR[level]),
                    // Fade out when zoomed in close, where checkpoints say more than a regional field.
                    'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 7, 1, 9, 0],
                  }}
                />
              ))}
            </Source>
          )}

          <Source id="routes" type="geojson" data={routesData}>
            <Layer
              id="route-casing"
              beforeId={labelLayerId}
              type="line"
              layout={{ 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': SORT_KEY }}
              paint={{
                'line-color': '#ffffff',
                'line-width': ['case', ['get', 'selected'], 10, 7],
              }}
            />
            <Layer
              id="route-line"
              beforeId={labelLayerId}
              type="line"
              layout={{ 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': SORT_KEY }}
              paint={{
                'line-color': [
                  'case',
                  ['get', 'selected'],
                  ACCENT,
                  ['get', 'hovered'],
                  ROUTE_HOVER,
                  ROUTE_IDLE,
                ],
                'line-width': ['case', ['get', 'selected'], 5.5, 3.5],
              }}
            />
            {/* Invisible, wide line so routes are easy to hover and click. */}
            <Layer
              id="route-hit"
              beforeId={labelLayerId}
              type="line"
              layout={{ 'line-join': 'round', 'line-cap': 'round' }}
              paint={{ 'line-color': '#000000', 'line-width': 18, 'line-opacity': 0 }}
            />
          </Source>

          <Source id="checkpoints" type="geojson" data={checkpointsData}>
            <Layer
              id="checkpoints"
              type="circle"
              paint={{
                'circle-color': RISK_SCORE_COLOR_EXPRESSION as unknown as ExpressionSpecification,
                'circle-radius': ['case', ['get', 'focused'], 8, 5.5],
                'circle-stroke-color': '#ffffff',
                'circle-stroke-width': 2,
              }}
            />
          </Source>

          {plan?.routes.map((route, i) => {
            const mid = route.geometry[Math.floor(route.geometry.length / 2)];
            if (!mid) return null;
            const selected = route.id === selectedRouteId;
            return (
              <Marker key={route.id} longitude={mid[0]} latitude={mid[1]} anchor="center">
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelectRoute(route.id);
                  }}
                  aria-label={`Select ${route.name}`}
                  className={`grid size-7 place-items-center rounded-full text-xs font-semibold shadow-md ring-2 ring-white ${
                    selected ? 'bg-accent text-white' : 'bg-surface text-ink-2 hover:text-ink'
                  }`}
                >
                  {ROUTE_LETTERS[i]}
                </button>
              </Marker>
            );
          })}

          {plan && (
            <>
              <Marker longitude={plan.origin.lon} latitude={plan.origin.lat} anchor="center">
                <span
                  title={plan.origin.label}
                  className="block size-4 rounded-full bg-ink ring-4 ring-white shadow-md"
                />
              </Marker>
              <Marker
                longitude={plan.destination.lon}
                latitude={plan.destination.lat}
                anchor="center"
              >
                <span
                  title={plan.destination.label}
                  className="block size-4 rounded-sm bg-ink ring-4 ring-white shadow-md"
                />
              </Marker>
            </>
          )}

          {truck && sliderTime !== null && (
            <Marker longitude={truck.coord[0]} latitude={truck.coord[1]} anchor="center">
              <span
                title={`Truck at ${formatTime(sliderTime)}`}
                className="grid size-7 place-items-center rounded-full bg-ink text-white shadow-md ring-2 ring-white"
              >
                <Truck aria-hidden className="size-3.5" />
              </span>
            </Marker>
          )}

          {focused && selectedRoute && (
            <Popup
              longitude={focused.lon}
              latitude={focused.lat}
              anchor="bottom"
              offset={14}
              closeButton={false}
              closeOnClick={false}
              maxWidth="300px"
              onClose={() => onFocusCheckpoint(null)}
            >
              <CheckpointPopup
                checkpoint={focused}
                routeName={selectedRoute.name}
                onClose={() => onFocusCheckpoint(null)}
              />
            </Popup>
          )}
        </MapGL>

        {loading && (
          <div
            className="absolute inset-x-0 top-0 h-0.5 overflow-hidden bg-accent/15"
            role="progressbar"
            aria-label="Loading routes"
          >
            <div className="progress-bar h-full w-2/5 bg-accent" />
          </div>
        )}

        {plan && <MapLegend showHeatmap={showHeatmap && heatmap !== null} />}

        {!plan && !loading && (
          <div className="pointer-events-none absolute inset-x-0 bottom-6 hidden justify-center px-4 sm:flex">
            <p className="rounded-full border border-line bg-surface/95 px-4 py-2 text-sm text-ink-2 shadow-sm">
              Plan a trip to compare routes and weather along the way
            </p>
          </div>
        )}
      </div>

      {plan && (
        // Phones: below the map, so it never covers the small map or its attribution.
        // Wider screens: floating over the bottom of the map.
        <div className="border-t border-line bg-page px-3 py-3 sm:pointer-events-none sm:absolute sm:inset-x-0 sm:bottom-8 sm:flex sm:justify-center sm:border-0 sm:bg-transparent sm:px-4 sm:py-0">
          <div className="w-full sm:pointer-events-auto sm:max-w-xl">
            <ForecastSlider
              startHour={heatmap?.start_hour ?? plan.forecast_window.start}
              hours={heatmap?.hours ?? 49}
              hour={hour}
              onHourChange={setHour}
              worstByHour={worstByHour}
              routeName={selectedRoute?.name ?? null}
              truckMile={truck?.mile ?? null}
              tripStart={selectedRoute?.departure_time ?? null}
              tripEnd={selectedRoute?.arrival_time ?? null}
              visible={showHeatmap}
              onVisibleChange={setShowHeatmap}
              playing={playing}
              onPlayingChange={setPlaying}
              status={heatmapQuery.isError ? 'error' : heatmap ? 'ready' : 'loading'}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// Draw the selected route above hovered, and hovered above the rest.
const SORT_KEY: ExpressionSpecification = [
  'case',
  ['get', 'selected'],
  2,
  ['get', 'hovered'],
  1,
  0,
];

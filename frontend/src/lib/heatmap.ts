import type { ExpressionSpecification } from 'maplibre-gl';
import type { FeatureCollection, Point } from 'geojson';
import type { Heatmap, LonLat, Route } from '../types';

/**
 * Heatmap rendering for the 0-48 h forecast slider.
 *
 * Every grid point carries all 49 hourly scores as properties `h0`..`h48`. Moving the slider
 * only swaps which property the weight expressions read: no new data and no network request.
 * (MapLibre still re-evaluates the ~300 points and redraws each heatmap layer, roughly 10 ms per
 * change in headless Chrome. That holds 60 fps at normal drag speeds.)
 */

/** One GeoJSON feature per grid point, with its score for every hour. Built once per heatmap. */
export function heatmapGeoJSON(heatmap: Heatmap): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: heatmap.points.map((coordinates, i) => {
      const properties: Record<string, number> = {};
      heatmap.scores[i]?.forEach((score, h) => {
        if (score !== null) properties[`h${h}`] = score;
      });
      return { type: 'Feature', geometry: { type: 'Point', coordinates }, properties };
    }),
  };
}

/**
 * One heatmap layer per risk level (Moderate..No Travel). Each layer gives weight 1 only to
 * points at exactly its level in the chosen hour, so a layer's density is "how much of the
 * neighbourhood is at this level", never a sum of scores. Density therefore controls only
 * where a band's soft edge falls, never which level it shows: a narrow corridor can't make
 * a High area render as Moderate. Low draws nothing, so calm weather leaves the map clean.
 */
export const HEATMAP_LEVELS = [
  { score: 1, level: 'moderate' },
  { score: 2, level: 'high' },
  { score: 3, level: 'severe' },
  { score: 4, level: 'no_travel' },
] as const;

/** 1 for points at exactly `score` in the chosen hour, else 0 (unknown scores weigh nothing). */
export function levelWeightExpression(hour: number, score: number): ExpressionSpecification {
  return ['case', ['==', ['coalesce', ['get', `h${hour}`], -1], score], 1, 0];
}

/*
 * Kernel sizing. MapLibre's heatmap kernel is  w * intensity * 0.3989 * exp(-4.5 * (d / r)^2).
 * On a regular grid with spacing s it sums to about  w * intensity * 0.2785 * (r / s)^2  inside
 * an area, so with r = 2s and the intensity below an all-one area reaches density ~1, and its
 * edge (half the neighbours) ~0.5. The color ramp switches on between 0.25 and 0.4, which puts
 * each band's edge at roughly the boundary between grid cells.
 */
const RADIUS_PER_SPACING = 2;
export const HEATMAP_INTENSITY = 1 / (0.2785 * RADIUS_PER_SPACING ** 2);

const EARTH_CIRCUMFERENCE_MI = 24_901.46;
const TILE_SIZE = 512;

/** Radius in pixels that keeps the blur at 2x grid spacing at every zoom level. */
export function radiusExpression(spacingMi: number, latitude: number): ExpressionSpecification {
  const pxPerMileAtZoom0 =
    TILE_SIZE / (EARTH_CIRCUMFERENCE_MI * Math.cos((latitude * Math.PI) / 180));
  const r0 = RADIUS_PER_SPACING * spacingMi * pxPerMileAtZoom0;
  // Doubling per zoom level; past zoom 9 the layer has faded out (see opacity).
  return ['interpolate', ['exponential', 2], ['zoom'], 0, r0, 9, r0 * 2 ** 9];
}

/** Translucent fill in one status color, with a short soft edge. */
export function levelColorExpression(hex: string): ExpressionSpecification {
  const n = parseInt(hex.slice(1), 16);
  const rgb = `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`;
  return [
    'interpolate',
    ['linear'],
    ['heatmap-density'],
    0.25,
    `rgba(${rgb}, 0)`,
    0.4,
    `rgba(${rgb}, ${HEATMAP_FILL_ALPHA})`,
  ];
}

export const HEATMAP_FILL_ALPHA = 0.5;

export function meanLatitude(points: LonLat[]): number {
  return points.length ? points.reduce((sum, p) => sum + p[1], 0) / points.length : 0;
}

/** Index of the forecast hour containing `ts`, clamped to the slider range. */
export function hourIndex(heatmapStart: number, hours: number, ts: number): number {
  return Math.min(Math.max(Math.floor((ts - heatmapStart) / 3600), 0), hours - 1);
}

/** The worst risk score anywhere in the corridor for each hour; null if all unknown. */
export function worstScorePerHour(heatmap: Heatmap): (number | null)[] {
  const worst: (number | null)[] = Array.from({ length: heatmap.hours }, () => null);
  for (const row of heatmap.scores) {
    row.forEach((score, h) => {
      if (score !== null && (worst[h] === null || score > worst[h]!)) worst[h] = score;
    });
  }
  return worst;
}

export interface TruckPosition {
  coord: LonLat;
  mile: number;
}

/**
 * Where the truck is on `route` at time `ts`, interpolated between the checkpoints around it
 * (their ETAs come from the routing API's own timeline). Null outside the trip.
 */
export function truckPosition(route: Route, ts: number): TruckPosition | null {
  const cps = route.checkpoints;
  const first = cps[0];
  const last = cps[cps.length - 1];
  if (!first || !last || ts < first.eta || ts > last.eta) return null;
  for (let i = 1; i < cps.length; i++) {
    const a = cps[i - 1]!;
    const b = cps[i]!;
    if (ts <= b.eta) {
      const t = b.eta === a.eta ? 0 : (ts - a.eta) / (b.eta - a.eta);
      return {
        coord: [a.lon + (b.lon - a.lon) * t, a.lat + (b.lat - a.lat) * t],
        mile: a.mile + (b.mile - a.mile) * t,
      };
    }
  }
  return { coord: [last.lon, last.lat], mile: last.mile };
}

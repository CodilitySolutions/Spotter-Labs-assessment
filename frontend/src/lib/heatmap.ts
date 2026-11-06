import type { ExpressionSpecification } from 'maplibre-gl';
import type { FeatureCollection, Point } from 'geojson';
import type { Heatmap, LonLat, Route } from '../types';

/**
 * Heatmap rendering for the 0-48 h forecast slider.
 *
 * Every grid point carries all 49 hourly levels for each view as properties: `o0`..`o48`
 * (overall), `w*` (wind, incl. load rules), `r*` (rain) and `s*` (snow). Moving the slider or
 * switching the view only swaps which property the weight expressions read: no new data and no
 * network request.
 * (MapLibre still re-evaluates the ~300 points and redraws each heatmap layer, roughly 10 ms per
 * change in headless Chrome. That holds 60 fps at normal drag speeds.)
 */

/** What the heatmap shows: the overall risk, or the risk from one condition on its own. */
export type HeatmapView = 'overall' | 'wind' | 'rain' | 'snow';

export const HEATMAP_VIEWS: readonly { value: HeatmapView; label: string }[] = [
  { value: 'overall', label: 'Overall' },
  { value: 'wind', label: 'Wind' },
  { value: 'rain', label: 'Rain' },
  { value: 'snow', label: 'Snow' },
];

const VIEW_PREFIX: Record<HeatmapView, string> = { overall: 'o', wind: 'w', rain: 'r', snow: 's' };

/** Level (0-4) at grid point `i` in hour `h` for a view, or null when unknown. */
export function levelAt(heatmap: Heatmap, view: HeatmapView, i: number, h: number): number | null {
  return viewMatrix(heatmap, view)[i]?.[h] ?? null;
}

function viewMatrix(heatmap: Heatmap, view: HeatmapView): (number | null)[][] {
  switch (view) {
    case 'overall':
      return heatmap.scores;
    case 'wind':
      return heatmap.wind_levels;
    case 'rain':
      return heatmap.rain_levels;
    case 'snow':
      return heatmap.snow_levels;
  }
}

/** One GeoJSON feature per grid point with its level for every view and hour. Built once. */
export function heatmapGeoJSON(heatmap: Heatmap): FeatureCollection<Point> {
  const views = HEATMAP_VIEWS.map(
    ({ value }) => [VIEW_PREFIX[value], viewMatrix(heatmap, value)] as const,
  );
  return {
    type: 'FeatureCollection',
    features: heatmap.points.map((coordinates, i) => {
      const properties: Record<string, number> = {};
      for (const [prefix, matrix] of views) {
        matrix[i]?.forEach((level, h) => {
          if (level !== null) properties[`${prefix}${h}`] = level;
        });
      }
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

/** 1 for points at exactly `score` in the chosen view and hour, else 0 (unknown weighs 0). */
export function levelWeightExpression(
  hour: number,
  score: number,
  view: HeatmapView = 'overall',
): ExpressionSpecification {
  return ['case', ['==', ['coalesce', ['get', `${VIEW_PREFIX[view]}${hour}`], -1], score], 1, 0];
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
  // Doubling per zoom level, up to zoom 12 where the layer has faded out (see opacity).
  return ['interpolate', ['exponential', 2], ['zoom'], 0, r0, 12, r0 * 2 ** 12];
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

export type Condition = 'wind' | 'rain' | 'snow';

/** The worst level in the corridor for one hour, and what causes it. */
export interface HourSummary {
  score: number | null; // null when every point is unknown
  causes: Condition[]; // conditions at that level somewhere in the corridor (overall view)
  loadRaised: boolean; // the load rules raised wind to this level somewhere
  maxWindMph: number | null; // strongest value among the worst points, for the cause text
  maxRainInHr: number | null;
  maxSnowInHr: number | null;
}

/** Per-hour summary of the worst level in the chosen view, with its causes and peak values. */
export function summarizeHours(heatmap: Heatmap, view: HeatmapView = 'overall'): HourSummary[] {
  const matrix = viewMatrix(heatmap, view);
  return Array.from({ length: heatmap.hours }, (_, h) => {
    let score: number | null = null;
    for (const row of matrix) {
      const v = row[h];
      if (v !== null && v !== undefined && (score === null || v > score)) score = v;
    }
    const summary: HourSummary = {
      score,
      causes: [],
      loadRaised: false,
      maxWindMph: null,
      maxRainInHr: null,
      maxSnowInHr: null,
    };
    if (score === null || score === 0) return summary;

    const causes = new Set<Condition>();
    matrix.forEach((row, i) => {
      if (row[h] !== score) return;
      const levels: [Condition, number | null | undefined][] = [
        ['wind', heatmap.wind_levels[i]?.[h]],
        ['rain', heatmap.rain_levels[i]?.[h]],
        ['snow', heatmap.snow_levels[i]?.[h]],
      ];
      for (const [condition, level] of levels) {
        // In a single-condition view, only that condition is the cause.
        if (level !== score || (view !== 'overall' && condition !== view)) continue;
        causes.add(condition);
        if (condition === 'wind') {
          summary.maxWindMph = max(summary.maxWindMph, heatmap.wind_mph[i]?.[h]);
          if (heatmap.load_raised[i]?.[h] === 1) summary.loadRaised = true;
        } else if (condition === 'rain') {
          summary.maxRainInHr = max(summary.maxRainInHr, heatmap.rain_in_hr[i]?.[h]);
        } else {
          summary.maxSnowInHr = max(summary.maxSnowInHr, heatmap.snow_in_hr[i]?.[h]);
        }
      }
    });
    summary.causes = (['wind', 'rain', 'snow'] as const).filter((c) => causes.has(c));
    return summary;
  });
}

function max(current: number | null, value: number | null | undefined): number | null {
  if (value === null || value === undefined) return current;
  return current === null || value > current ? value : current;
}

/** "wind up to 52 mph (with 42,000 lb load) and rain up to 0.31 in/hr" */
export function describeCauses(summary: HourSummary, loadLb: number): string {
  const parts = summary.causes.map((c) => {
    if (c === 'wind') {
      const speed =
        summary.maxWindMph !== null ? ` up to ${Math.round(summary.maxWindMph)} mph` : '';
      const load = summary.loadRaised ? ` with ${loadLb.toLocaleString()} lb load` : '';
      return `wind${speed}${load}`;
    }
    const v = c === 'rain' ? summary.maxRainInHr : summary.maxSnowInHr;
    return `${c}${v !== null ? ` up to ${v.toFixed(2)} in/hr` : ''}`;
  });
  return parts.join(' and ');
}

/** Index of the grid point nearest to `at`, if it is within `maxMi`. */
export function nearestPoint(heatmap: Heatmap, at: LonLat, maxMi: number): number | null {
  const kx = 69.09 * Math.cos((at[1] * Math.PI) / 180);
  let best: number | null = null;
  let bestD2 = maxMi * maxMi;
  heatmap.points.forEach(([lon, lat], i) => {
    const dx = (lon - at[0]) * kx;
    const dy = (lat - at[1]) * 69.09;
    const d2 = dx * dx + dy * dy;
    if (d2 <= bestD2) {
      bestD2 = d2;
      best = i;
    }
  });
  return best;
}

/** 8-point compass name for the direction the wind comes from: 290 -> "W". */
export function compass(fromDeg: number): string {
  const names = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  return names[Math.round((((fromDeg % 360) + 360) % 360) / 45) % 8]!;
}

/**
 * Wind arrows on every other grid row and column (a quarter of the points), so they stay
 * readable at regional zoom. Properties per hour: `d*` = direction the wind blows TOWARDS (for
 * the arrow's rotation) and `v*` = speed in mph.
 */
export function windArrowGeoJSON(heatmap: Heatmap): FeatureCollection<Point> {
  const lat0 = meanLatitude(heatmap.points);
  const stepLat = heatmap.spacing_mi / 69.09;
  const stepLon = heatmap.spacing_mi / (69.09 * Math.cos((lat0 * Math.PI) / 180));
  return {
    type: 'FeatureCollection',
    features: heatmap.points.flatMap((coordinates, i) => {
      const row = Math.round(coordinates[1] / stepLat);
      const col = Math.round(coordinates[0] / stepLon);
      if (row % 2 !== 0 || col % 2 !== 0) return [];
      const properties: Record<string, number> = {};
      for (let h = 0; h < heatmap.hours; h++) {
        const from = heatmap.wind_dir_deg[i]?.[h];
        const speed = heatmap.wind_mph[i]?.[h];
        if (from === null || from === undefined || speed === null || speed === undefined) continue;
        properties[`d${h}`] = (from + 180) % 360;
        properties[`v${h}`] = speed;
      }
      return [
        { type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates }, properties },
      ];
    }),
  };
}

export interface TruckPosition {
  coord: LonLat;
  mile: number;
}

/**
 * Where the truck is on `route` at time `ts`. The distance travelled is interpolated between
 * the checkpoints around `ts` (their ETAs come from the routing API's own timeline); the
 * position is then found by walking that far along the route line, so the marker stays on the
 * road even where it curves between checkpoints. Null outside the trip.
 */
export function truckPosition(route: Route, ts: number): TruckPosition | null {
  const cps = route.checkpoints;
  const first = cps[0];
  const last = cps[cps.length - 1];
  if (!first || !last || ts < first.eta || ts > last.eta) return null;

  let mile = last.mile;
  for (let i = 1; i < cps.length; i++) {
    const a = cps[i - 1]!;
    const b = cps[i]!;
    if (ts <= b.eta) {
      const t = b.eta === a.eta ? 0 : (ts - a.eta) / (b.eta - a.eta);
      mile = a.mile + (b.mile - a.mile) * t;
      break;
    }
  }
  // The display line is slightly simplified, so position by share of the trip, not raw miles.
  const fraction = last.mile > 0 ? mile / last.mile : 0;
  return { coord: pointAlong(route.geometry, fraction), mile };
}

const cumulativeCache = new WeakMap<LonLat[], number[]>();

/** Distance from the start to each vertex (flat approximation; only ratios are used). */
function cumulative(line: LonLat[]): number[] {
  let cum = cumulativeCache.get(line);
  if (!cum) {
    cum = [0];
    for (let i = 1; i < line.length; i++) {
      const [x0, y0] = line[i - 1]!;
      const [x1, y1] = line[i]!;
      const kx = Math.cos((((y0 + y1) / 2) * Math.PI) / 180);
      cum.push(cum[i - 1]! + Math.hypot((x1 - x0) * kx, y1 - y0));
    }
    cumulativeCache.set(line, cum);
  }
  return cum;
}

/** The point `fraction` (0-1) of the way along a polyline. */
export function pointAlong(line: LonLat[], fraction: number): LonLat {
  if (line.length === 0) return [0, 0];
  if (line.length === 1 || fraction <= 0) return line[0]!;
  if (fraction >= 1) return line[line.length - 1]!;
  const cum = cumulative(line);
  const target = fraction * cum[cum.length - 1]!;
  // Binary search for the segment containing the target distance.
  let lo = 0;
  let hi = cum.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (cum[mid]! <= target) lo = mid;
    else hi = mid;
  }
  const span = cum[hi]! - cum[lo]!;
  const t = span === 0 ? 0 : (target - cum[lo]!) / span;
  const [x0, y0] = line[lo]!;
  const [x1, y1] = line[hi]!;
  return [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t];
}

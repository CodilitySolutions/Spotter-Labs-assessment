import { describe, expect, it } from 'vitest';
import type { Checkpoint, Heatmap, Route } from '../types';
import {
  compass,
  describeCauses,
  HEATMAP_INTENSITY,
  heatmapGeoJSON,
  hourIndex,
  levelWeightExpression,
  nearestPoint,
  radiusExpression,
  summarizeHours,
  truckPosition,
  windArrowGeoJSON,
} from './heatmap';

const START = 1_800_000_000 - (1_800_000_000 % 3600);

type M = (number | null)[][];

/** A heatmap where every matrix not given is filled with `fill` (same shape as `scores`). */
function heatmap(scores: M, over: Partial<Record<keyof Heatmap, M>> = {}, spacing = 10): Heatmap {
  const like = (fill: number | null) => scores.map((row) => row.map(() => fill));
  return {
    plan_id: 'p1',
    start_hour: START,
    hours: scores[0]?.length ?? 0,
    step_s: 3600,
    spacing_mi: spacing,
    points: scores.map((_, i) => [-100 + i, 40]),
    scores,
    wind_levels: over.wind_levels ?? like(0),
    rain_levels: over.rain_levels ?? like(0),
    snow_levels: over.snow_levels ?? like(0),
    load_raised: over.load_raised ?? like(0),
    wind_mph: over.wind_mph ?? like(5),
    wind_dir_deg: over.wind_dir_deg ?? like(270),
    rain_in_hr: over.rain_in_hr ?? like(0),
    snow_in_hr: over.snow_in_hr ?? like(0),
  };
}

function checkpoint(index: number, mile: number, eta: number, lon: number): Checkpoint {
  return {
    index,
    mile,
    covers_mi: 0,
    lon,
    lat: 40,
    eta,
    weather: null,
    levels: { wind: null, rain: null, snow: null, load_override: null },
    risk: 'low',
    risk_score: 0,
    reason: '',
  };
}

const route = {
  id: 'r1',
  name: 'Route A',
  // Straight along latitude 40 from -100 to -98, so positions are easy to check.
  geometry: [
    [-100, 40],
    [-99, 40],
    [-98, 40],
  ],
  checkpoints: [
    checkpoint(0, 0, START + 3600, -100),
    checkpoint(1, 50, START + 2 * 3600, -99),
    checkpoint(2, 100, START + 4 * 3600, -98), // slower stretch: 50 mi in 2 h
  ],
} as unknown as Route;

describe('heatmapGeoJSON', () => {
  it('stores each view per hour (o/w/r/s) and omits unknown hours', () => {
    const fc = heatmapGeoJSON(
      heatmap([[0, 2, null]], {
        wind_levels: [[0, 2, null]],
        rain_levels: [[0, 1, null]],
        snow_levels: [[0, 0, null]],
      }),
    );

    expect(fc.features).toHaveLength(1);
    expect(fc.features[0]!.properties).toEqual({
      o0: 0,
      o1: 2,
      w0: 0,
      w1: 2,
      r0: 0,
      r1: 1,
      s0: 0,
      s1: 0,
    });
    expect(fc.features[0]!.geometry.coordinates).toEqual([-100, 40]);
  });
});

describe('levelWeightExpression', () => {
  it('reads the chosen view and hour and matches one exact level', () => {
    expect(levelWeightExpression(13, 3)).toEqual([
      'case',
      ['==', ['coalesce', ['get', 'o13'], -1], 3],
      1,
      0,
    ]);
    expect(JSON.stringify(levelWeightExpression(2, 1, 'rain'))).toContain('"r2"');
  });
});

describe('kernel sizing', () => {
  it('makes a solid area reach density ~1 with a radius of twice the spacing', () => {
    // Summed kernel inside an area ~= intensity * 0.2785 * (r / s)^2 with r = 2s.
    expect(HEATMAP_INTENSITY * 0.2785 * 4).toBeCloseTo(1, 6);
  });

  it('doubles the radius every zoom level and grows with spacing', () => {
    const [, , , z0, r0, z12, r12] = radiusExpression(10, 0) as unknown as number[];
    expect([z0, z12]).toEqual([0, 12]);
    expect(r12! / r0!).toBeCloseTo(4096);
    // 2 x 10 mi at the equator, at 512 px per world width.
    expect(r0).toBeCloseTo((2 * 10 * 512) / 24_901.46, 6);
  });
});

describe('hourIndex', () => {
  it('finds the hour containing a time and clamps to the slider', () => {
    expect(hourIndex(START, 49, START + 3599)).toBe(0);
    expect(hourIndex(START, 49, START + 3600 * 5 + 10)).toBe(5);
    expect(hourIndex(START, 49, START - 100)).toBe(0);
    expect(hourIndex(START, 49, START + 3600 * 100)).toBe(48);
  });
});

describe('summarizeHours', () => {
  it('takes the worst known level per hour across all points', () => {
    const hm = heatmap([
      [0, 1, null, 0],
      [0, 3, null, null],
      [2, 0, null, 0],
    ]);

    expect(summarizeHours(hm).map((h) => h.score)).toEqual([2, 3, null, 0]);
  });

  it('names the conditions behind the worst level, with peak values and the load rule', () => {
    // Hour 0: point 0 is Severe from wind (raised by load), point 1 is Severe from rain.
    const hm = heatmap([[3], [3], [1]], {
      wind_levels: [[3], [0], [1]],
      rain_levels: [[0], [3], [0]],
      load_raised: [[1], [0], [0]],
      wind_mph: [[48], [10], [30]],
      rain_in_hr: [[0], [0.62], [0]],
    });

    const [hour0] = summarizeHours(hm);
    expect(hour0).toMatchObject({
      score: 3,
      causes: ['wind', 'rain'],
      loadRaised: true,
      maxWindMph: 48, // only points at the worst level count, not the 30 mph one
      maxRainInHr: 0.62,
    });
    expect(describeCauses(hour0!, 42000)).toBe(
      'wind up to 48 mph with 42,000 lb load and rain up to 0.62 in/hr',
    );
  });

  it('in a single-condition view, the cause is only that condition', () => {
    const hm = heatmap([[3]], { wind_levels: [[2]], rain_levels: [[2]], rain_in_hr: [[0.3]] });

    const [rainView] = summarizeHours(hm, 'rain');
    expect(rainView).toMatchObject({ score: 2, causes: ['rain'] });
  });

  it('has no causes when the corridor is clear', () => {
    expect(summarizeHours(heatmap([[0], [0]]))[0]).toMatchObject({ score: 0, causes: [] });
  });
});

describe('nearestPoint', () => {
  const hm = heatmap([[0], [0], [0]]); // points at lon -100, -99, -98; lat 40

  it('finds the closest grid point within range', () => {
    expect(nearestPoint(hm, [-99.1, 40.05], 20)).toBe(1);
  });

  it('returns null outside the corridor', () => {
    expect(nearestPoint(hm, [-99.1, 42], 20)).toBeNull();
  });
});

describe('wind helpers', () => {
  it.each([
    [0, 'N'],
    [44, 'NE'],
    [180, 'S'],
    [290, 'W'],
    [350, 'N'],
    [-90, 'W'],
  ])('compass(%i) = %s', (deg, name) => {
    expect(compass(deg)).toBe(name);
  });

  it('points arrows where the wind blows towards, on a thinned grid', () => {
    // Spacing 69.09 mi = 1 degree of latitude; points sit 1 degree of longitude apart.
    const scores = [[0], [0], [0], [0]];
    const hm = heatmap(scores, { wind_dir_deg: [[270], [270], [90], [null]] }, 69.09);
    hm.points = [
      [0, 0],
      [1, 0],
      [2, 0],
      [4, 0],
    ];

    const fc = windArrowGeoJSON(hm);

    // Every other column: x = 0, 2 and 4 (x = 1 is skipped).
    expect(fc.features.map((f) => f.geometry.coordinates[0])).toEqual([0, 2, 4]);
    // Wind from the west (270) blows east (90); from the east (90) blows west (270).
    expect(fc.features[0]!.properties).toEqual({ d0: 90, v0: 5 });
    expect(fc.features[1]!.properties).toEqual({ d0: 270, v0: 5 });
    expect(fc.features[2]!.properties).toEqual({}); // no direction: no arrow this hour
  });
});

describe('truckPosition', () => {
  it('is null before departure and after arrival', () => {
    expect(truckPosition(route, START)).toBeNull();
    expect(truckPosition(route, START + 4 * 3600 + 1)).toBeNull();
  });

  it('interpolates the mile between checkpoint ETAs', () => {
    // Halfway between checkpoint 0 (1 h) and 1 (2 h).
    const p = truckPosition(route, START + 1.5 * 3600)!;
    expect(p.mile).toBeCloseTo(25);
    expect(p.coord[0]).toBeCloseTo(-99.5);
  });

  it('follows the slower stretch at the right pace', () => {
    // 1 h into the 2 h stretch from mile 50 to 100.
    expect(truckPosition(route, START + 3 * 3600)!.mile).toBeCloseTo(75);
  });

  it('is exactly at the destination on arrival', () => {
    const p = truckPosition(route, START + 4 * 3600)!;
    expect(p.mile).toBe(100);
    expect(p.coord).toEqual([-98, 40]);
  });

  it('stays on the road where it bends between checkpoints', () => {
    // An L-shaped road: 1 degree north, then 1 degree east. Checkpoints only at the ends, so a
    // straight line between them would cut the corner; the truck must follow the road instead.
    const bent = {
      ...route,
      geometry: [
        [0, 0],
        [0, 1],
        [1, 1],
      ],
      checkpoints: [checkpoint(0, 0, START, 0), checkpoint(1, 138, START + 3600, 1)],
    } as unknown as Route;
    bent.checkpoints[1]!.lat = 1;

    const quarter = truckPosition(bent, START + 900)!.coord; // 25% of the way
    const atCorner = truckPosition(bent, START + 1800)!.coord; // 50%: the corner
    expect(quarter[0]).toBeCloseTo(0); // still on the northbound leg
    expect(quarter[1]).toBeCloseTo(0.5, 1);
    expect(atCorner[0]).toBeCloseTo(0, 1);
    expect(atCorner[1]).toBeCloseTo(1, 1);
  });
});

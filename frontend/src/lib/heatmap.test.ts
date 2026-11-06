import { describe, expect, it } from 'vitest';
import type { Checkpoint, Heatmap, Route } from '../types';
import {
  HEATMAP_INTENSITY,
  heatmapGeoJSON,
  hourIndex,
  levelWeightExpression,
  radiusExpression,
  truckPosition,
  worstScorePerHour,
} from './heatmap';

const START = 1_800_000_000 - (1_800_000_000 % 3600);

function heatmap(scores: (number | null)[][]): Heatmap {
  return {
    plan_id: 'p1',
    start_hour: START,
    hours: scores[0]?.length ?? 0,
    step_s: 3600,
    spacing_mi: 10,
    points: scores.map((_, i) => [-100 + i, 40]),
    scores,
  };
}

function checkpoint(index: number, mile: number, eta: number, lon: number): Checkpoint {
  return {
    index,
    mile,
    segment_mi: 0,
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
  checkpoints: [
    checkpoint(0, 0, START + 3600, -100),
    checkpoint(1, 50, START + 2 * 3600, -99),
    checkpoint(2, 100, START + 4 * 3600, -98), // slower stretch: 50 mi in 2 h
  ],
} as unknown as Route;

describe('heatmapGeoJSON', () => {
  it('stores every hourly score as h0..hN and omits unknown hours', () => {
    const fc = heatmapGeoJSON(heatmap([[0, 2, null]]));

    expect(fc.features).toHaveLength(1);
    expect(fc.features[0]!.properties).toEqual({ h0: 0, h1: 2 });
    expect(fc.features[0]!.geometry.coordinates).toEqual([-100, 40]);
  });
});

describe('levelWeightExpression', () => {
  it('reads the chosen hour and matches one exact level', () => {
    expect(levelWeightExpression(13, 3)).toEqual([
      'case',
      ['==', ['coalesce', ['get', 'h13'], -1], 3],
      1,
      0,
    ]);
  });
});

describe('kernel sizing', () => {
  it('makes a solid area reach density ~1 with a radius of twice the spacing', () => {
    // Summed kernel inside an area ~= intensity * 0.2785 * (r / s)^2 with r = 2s.
    expect(HEATMAP_INTENSITY * 0.2785 * 4).toBeCloseTo(1, 6);
  });

  it('doubles the radius every zoom level and grows with spacing', () => {
    const [, , , z0, r0, z9, r9] = radiusExpression(10, 0) as unknown as number[];
    expect([z0, z9]).toEqual([0, 9]);
    expect(r9! / r0!).toBeCloseTo(512);
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

describe('worstScorePerHour', () => {
  it('takes the maximum known score per hour across all points', () => {
    const hm = heatmap([
      [0, 1, null, 0],
      [0, 3, null, null],
      [2, 0, null, 0],
    ]);

    expect(worstScorePerHour(hm)).toEqual([2, 3, null, 0]);
  });
});

describe('truckPosition', () => {
  it('is null before departure and after arrival', () => {
    expect(truckPosition(route, START)).toBeNull();
    expect(truckPosition(route, START + 4 * 3600 + 1)).toBeNull();
  });

  it('interpolates position and mile between checkpoint ETAs', () => {
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
});

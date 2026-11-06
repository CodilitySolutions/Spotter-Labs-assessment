import type { RiskOrUnknown } from '../types';

/**
 * Risk levels use the reserved *status* scale (good -> critical), never a categorical
 * series color, and are always shown with a text label so color is never the only cue.
 * Low..Severe are the documented status steps; No Travel is a darker step of critical.
 */
export const RISK_LEVELS: readonly RiskOrUnknown[] = [
  'low',
  'moderate',
  'high',
  'severe',
  'no_travel',
  'unknown',
];

export const RISK_COLOR: Record<RiskOrUnknown, string> = {
  low: '#0ca30c',
  moderate: '#fab219',
  high: '#ec835a',
  severe: '#d03b3b',
  no_travel: '#7a1f1f',
  unknown: '#b5b3ab',
};

export const RISK_LABEL: Record<RiskOrUnknown, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
  unknown: 'Unknown',
};

/** MapLibre expression: color a feature by its numeric `risk_score` (null -> unknown). */
export const RISK_SCORE_COLOR_EXPRESSION = [
  'match',
  ['coalesce', ['get', 'risk_score'], -1],
  0,
  RISK_COLOR.low,
  1,
  RISK_COLOR.moderate,
  2,
  RISK_COLOR.high,
  3,
  RISK_COLOR.severe,
  4,
  RISK_COLOR.no_travel,
  RISK_COLOR.unknown,
] as const;

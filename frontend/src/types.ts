/** Types mirroring the backend API (docs/PROJECT_SPEC.md §9). Times are Unix seconds, UTC. */

export type LonLat = [number, number];

export type RiskLevel = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel';
export type RiskOrUnknown = RiskLevel | 'unknown';

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface PlanRequest {
  origin: Place;
  destination: Place;
  departure_time: string; // ISO 8601
  load_weight_lb: number;
  checkpoint_interval_mi: 10 | 25 | 50;
}

export interface CheckpointWeather {
  wind_mph: number | null;
  gust_mph: number | null;
  rain_in_hr: number | null;
  snow_in_hr: number | null;
  source: string;
}

export interface Checkpoint {
  index: number;
  mile: number;
  /** Miles of road scored by this checkpoint (it covers halfway to each neighbour). */
  covers_mi: number;
  lon: number;
  lat: number;
  eta: number;
  weather: CheckpointWeather | null;
  levels: {
    wind: RiskLevel | null;
    rain: RiskLevel | null;
    snow: RiskLevel | null;
    load_override: RiskLevel | null;
  };
  risk: RiskOrUnknown;
  risk_score: number | null;
  reason: string;
}

export interface RouteSummary {
  rank: number;
  miles_by_level: Record<RiskOrUnknown, number>;
  severe_miles: number;
  high_miles: number;
  avg_risk: number | null;
  worst_level: RiskLevel | null;
}

export interface Route {
  id: string;
  name: string;
  source: string;
  is_fallback_profile: boolean;
  geometry: LonLat[];
  distance_mi: number;
  duration_s: number;
  departure_time: number;
  arrival_time: number;
  summary: RouteSummary;
  checkpoints: Checkpoint[];
}

export interface Plan {
  plan_id: string;
  generated_at: number;
  forecast_window: { start: number; end: number };
  origin: Place;
  destination: Place;
  load_weight_lb: number;
  checkpoint_interval_mi: number;
  recommended_route_id: string;
  recommendation_reason: string;
  warnings: string[];
  routes: Route[];
}

export interface Heatmap {
  plan_id: string;
  start_hour: number;
  hours: number;
  step_s: number;
  spacing_mi: number;
  points: LonLat[];
  /** All matrices are [point][hour]; null = unknown. scores = overall risk score 0-4. */
  scores: (number | null)[][];
  /** Level each condition produces on its own. Wind includes the load rules. */
  wind_levels: (number | null)[][];
  rain_levels: (number | null)[][];
  snow_levels: (number | null)[][];
  /** 1 where the load rules raised the wind level. */
  load_raised: (number | null)[][];
  wind_mph: (number | null)[][];
  /** Direction the wind comes FROM, degrees clockwise from north. */
  wind_dir_deg: (number | null)[][];
  rain_in_hr: (number | null)[][];
  snow_in_hr: (number | null)[][];
}

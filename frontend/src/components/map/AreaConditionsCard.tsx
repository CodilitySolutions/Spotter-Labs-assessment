import { Navigation2 } from 'lucide-react';
import { formatDateTime } from '../../lib/format';
import { compass } from '../../lib/heatmap';
import type { Heatmap, RiskOrUnknown } from '../../types';
import { RiskChip } from '../RiskChip';

const LEVEL_BY_SCORE: RiskOrUnknown[] = ['low', 'moderate', 'high', 'severe', 'no_travel'];
const levelOf = (score: number | null | undefined): RiskOrUnknown =>
  score === null || score === undefined ? 'unknown' : (LEVEL_BY_SCORE[score] ?? 'unknown');

interface AreaConditionsCardProps {
  heatmap: Heatmap;
  index: number; // grid point
  hour: number;
  loadLb: number;
}

/** The forecast at one heatmap grid point and hour: overall level and what each condition adds. */
export function AreaConditionsCard({
  heatmap: hm,
  index: i,
  hour: h,
  loadLb,
}: AreaConditionsCardProps) {
  const overall = levelOf(hm.scores[i]?.[h]);
  const windMph = hm.wind_mph[i]?.[h] ?? null;
  const windFrom = hm.wind_dir_deg[i]?.[h] ?? null;
  const rain = hm.rain_in_hr[i]?.[h] ?? null;
  const snow = hm.snow_in_hr[i]?.[h] ?? null;
  const loadRaised = hm.load_raised[i]?.[h] === 1;

  return (
    <div className="w-64 p-3.5 text-ink">
      <p className="text-[11px] tracking-wide text-muted uppercase">Forecast area</p>
      <p className="mt-0.5 text-sm font-semibold">{formatDateTime(hm.start_hour + h * 3600)}</p>
      <div className="mt-2">
        <RiskChip level={overall} size="md" />
      </div>

      <dl className="mt-3 space-y-1.5 border-t border-line pt-3 text-sm tabular-nums">
        <Row label="Wind" level={levelOf(hm.wind_levels[i]?.[h])}>
          {windMph === null ? (
            '—'
          ) : (
            <span className="inline-flex items-center gap-1">
              {windFrom !== null && (
                <Navigation2
                  aria-hidden
                  className="size-3 text-ink-2"
                  // The icon points north; rotate it to where the wind blows towards.
                  style={{ transform: `rotate(${(windFrom + 180) % 360}deg)` }}
                />
              )}
              {Math.round(windMph)} mph{windFrom !== null && ` from ${compass(windFrom)}`}
            </span>
          )}
        </Row>
        <Row label="Rain" level={levelOf(hm.rain_levels[i]?.[h])}>
          {rain === null ? '—' : `${rain.toFixed(2)} in/hr`}
        </Row>
        <Row label="Snow" level={levelOf(hm.snow_levels[i]?.[h])}>
          {snow === null ? '—' : `${snow.toFixed(2)} in/hr`}
        </Row>
      </dl>

      {loadRaised && (
        <p className="mt-2.5 rounded-md bg-surface-2 px-2 py-1.5 text-xs leading-snug text-ink-2">
          The {loadLb.toLocaleString()} lb load raises the wind risk to this level.
        </p>
      )}
      <p className="mt-2 text-[11px] text-muted">
        Nearest forecast point · about {Math.round(hm.spacing_mi)} mi apart
      </p>
    </div>
  );
}

function Row({
  label,
  level,
  children,
}: {
  label: string;
  level: RiskOrUnknown;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="w-10 text-xs text-muted">{label}</dt>
      <dd className="flex-1 text-ink">{children}</dd>
      <dd>
        <RiskChip level={level} />
      </dd>
    </div>
  );
}

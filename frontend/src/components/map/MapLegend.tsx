import { HEATMAP_FILL_ALPHA } from '../../lib/heatmap';
import { RISK_COLOR, RISK_LABEL } from '../../lib/risk';
import type { RiskOrUnknown } from '../../types';
import { RiskMark } from '../RiskChip';

const LEVELS: RiskOrUnknown[] = ['low', 'moderate', 'high', 'severe', 'no_travel'];
const AREA_LEVELS: RiskOrUnknown[] = ['moderate', 'high', 'severe', 'no_travel'];

export function MapLegend({ showHeatmap }: { showHeatmap: boolean }) {
  return (
    <div className="absolute top-4 left-4 hidden rounded-xl border border-line bg-surface/95 p-3 text-xs text-ink-2 shadow-sm sm:block">
      <div className="space-y-1.5">
        <LineKey color="#2a78d6" width={4} label="Selected route" />
        <LineKey color="#9a988f" width={3} label="Other routes" />
      </div>
      <p className="mt-3 mb-1.5 text-[11px] tracking-wide text-muted uppercase">Checkpoint risk</p>
      <ul className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {LEVELS.map((level) => (
          <li key={level} className="flex items-center gap-1.5">
            <RiskMark level={level} />
            {RISK_LABEL[level]}
          </li>
        ))}
      </ul>
      {showHeatmap && (
        <>
          <p className="mt-3 mb-1.5 text-[11px] tracking-wide text-muted uppercase">
            Forecast risk area
          </p>
          <ul className="flex gap-1" aria-label="Forecast risk area colors">
            {AREA_LEVELS.map((level) => (
              <li key={level} className="flex flex-col items-center gap-1">
                <span
                  aria-hidden
                  className="block h-2.5 w-12 rounded-sm"
                  style={{ backgroundColor: RISK_COLOR[level], opacity: HEATMAP_FILL_ALPHA }}
                />
                <span className="text-[10px] text-muted">{RISK_LABEL[level]}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function LineKey({ color, width, label }: { color: string; width: number; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="block w-5 rounded-full" style={{ height: width, backgroundColor: color }} />
      {label}
    </div>
  );
}

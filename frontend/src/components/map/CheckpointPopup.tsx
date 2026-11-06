import { X } from 'lucide-react';
import { formatDateTime, formatNumber } from '../../lib/format';
import type { Checkpoint } from '../../types';
import { RiskChip } from '../RiskChip';

interface CheckpointPopupProps {
  checkpoint: Checkpoint;
  routeName: string;
  onClose: () => void;
}

export function CheckpointPopup({ checkpoint: cp, routeName, onClose }: CheckpointPopupProps) {
  const w = cp.weather;
  return (
    <div className="w-64 p-4 text-ink">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-muted">
            {routeName} · mile {Math.round(cp.mile)}
          </p>
          <p className="mt-0.5 text-sm font-semibold">{formatDateTime(cp.eta)}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="-mt-1 -mr-1 grid size-7 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-ink"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="mt-3">
        <RiskChip level={cp.risk} size="md" />
        <p className="mt-2 text-sm leading-snug text-ink-2">{cp.reason}</p>
      </div>

      {w && (
        <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-line pt-3 text-center tabular-nums">
          <Stat label="Wind" value={formatNumber(w.wind_mph, 0, 'mph')} />
          <Stat label="Rain" value={formatNumber(w.rain_in_hr, 2, 'in/h')} />
          <Stat label="Snow" value={formatNumber(w.snow_in_hr, 2, 'in/h')} />
        </dl>
      )}
      {w && (
        <p className="mt-2 text-[11px] text-muted">
          {w.gust_mph !== null && `Gusts ${Math.round(w.gust_mph)} mph · `}
          Forecast: {w.source === 'nws' ? 'National Weather Service' : 'Open-Meteo'}
        </p>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] tracking-wide text-muted uppercase">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium whitespace-nowrap">{value}</dd>
    </div>
  );
}

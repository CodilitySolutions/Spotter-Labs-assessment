import { formatNumber, formatTime } from '../lib/format';
import type { Checkpoint } from '../types';
import { RiskChip } from './RiskChip';

interface CheckpointTableProps {
  checkpoints: Checkpoint[];
  focusedIndex: number | null;
  onFocus: (index: number) => void;
}

/** Every checkpoint of the selected route; also the accessible table view of the map markers. */
export function CheckpointTable({ checkpoints, focusedIndex, onFocus }: CheckpointTableProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-left text-[11px] tracking-wide text-muted uppercase">
            <tr>
              <th scope="col" className="px-2 py-2 pl-4 font-medium">
                Mile · ETA
              </th>
              <th scope="col" className="px-2 py-2 font-medium">
                Wind
              </th>
              <th scope="col" className="px-2 py-2 font-medium">
                Rain / Snow
              </th>
              <th scope="col" className="px-2 py-2 pr-4 text-right font-medium">
                Risk
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line tabular-nums">
            {checkpoints.map((cp) => {
              const w = cp.weather;
              const focused = cp.index === focusedIndex;
              return (
                <tr
                  key={cp.index}
                  onClick={() => onFocus(cp.index)}
                  title={cp.reason}
                  aria-selected={focused}
                  className={`cursor-pointer transition-colors ${
                    focused ? 'bg-accent-soft' : 'hover:bg-surface-2'
                  }`}
                >
                  <td className="px-2 py-2 pl-4 whitespace-nowrap">
                    <span className="block font-medium text-ink">{Math.round(cp.mile)} mi</span>
                    <span className="block text-xs text-muted">{formatTime(cp.eta)}</span>
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap text-ink-2">
                    {formatNumber(w?.wind_mph ?? null, 0, 'mph')}
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap text-ink-2">
                    {w ? `${rate(w.rain_in_hr)} / ${rate(w.snow_in_hr)}` : '—'}
                  </td>
                  <td className="px-2 py-2 pr-4 text-right">
                    <RiskChip level={cp.risk} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t border-line px-4 py-2 text-xs text-muted">
        Rain and snow in inches per hour, at each checkpoint's estimated arrival time.
      </p>
    </div>
  );
}

function rate(value: number | null): string {
  return value === null ? '—' : value.toFixed(2);
}

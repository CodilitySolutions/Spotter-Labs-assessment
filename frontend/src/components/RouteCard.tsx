import { Check, TriangleAlert } from 'lucide-react';
import { formatDuration, formatMiles, formatTime } from '../lib/format';
import type { Route } from '../types';
import { RiskBar } from './RiskBar';
import { RiskChip } from './RiskChip';

interface RouteCardProps {
  route: Route;
  letter: string;
  recommended: boolean;
  selected: boolean;
  onSelect: () => void;
}

export function RouteCard({ route, letter, recommended, selected, onSelect }: RouteCardProps) {
  const { summary } = route;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`w-full rounded-xl border bg-surface p-4 text-left transition-colors ${
        selected ? 'border-accent ring-1 ring-accent' : 'border-line hover:border-line-strong'
      }`}
    >
      <div className="flex items-start gap-3">
        <RouteLetter letter={letter} selected={selected} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-ink">{route.name}</h3>
            {recommended && (
              <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent-hover">
                <Check aria-hidden className="size-3" strokeWidth={3} />
                Recommended
              </span>
            )}
          </div>
          <p className="mt-0.5 text-sm text-ink-2 tabular-nums">
            {formatDuration(route.duration_s)} · {formatMiles(route.distance_mi)} · arrives{' '}
            {formatTime(route.arrival_time)}
          </p>
        </div>
        {summary.worst_level && (
          <div className="shrink-0 text-right">
            <p className="mb-1 text-[11px] tracking-wide text-muted uppercase">Worst</p>
            <RiskChip level={summary.worst_level} />
          </div>
        )}
      </div>

      <div className="mt-4">
        <RiskBar milesByLevel={summary.miles_by_level} />
      </div>

      {route.is_fallback_profile && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-warn-ink">
          <TriangleAlert aria-hidden className="size-3.5" />
          Car-routing fallback — truck restrictions not applied
        </p>
      )}
    </button>
  );
}

export function RouteLetter({ letter, selected }: { letter: string; selected: boolean }) {
  return (
    <span
      aria-hidden
      className={`grid size-8 shrink-0 place-items-center rounded-lg text-sm font-semibold ${
        selected ? 'bg-accent text-white' : 'bg-surface-2 text-ink-2 ring-1 ring-line'
      }`}
    >
      {letter}
    </span>
  );
}

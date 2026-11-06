import { ArrowRight, Route as RouteIcon, TriangleAlert } from 'lucide-react';
import { formatDateTime, formatWeight } from '../lib/format';
import type { Plan } from '../types';
import { CheckpointTable } from './CheckpointTable';
import { ROUTE_LETTERS } from '../lib/routes';
import { RouteCard } from './RouteCard';

interface ResultsProps {
  plan: Plan;
  selectedRouteId: string;
  focusedIndex: number | null;
  onSelectRoute: (id: string) => void;
  onFocusCheckpoint: (index: number) => void;
}

export function Results({
  plan,
  selectedRouteId,
  focusedIndex,
  onSelectRoute,
  onFocusCheckpoint,
}: ResultsProps) {
  const recommended = plan.routes.find((r) => r.id === plan.recommended_route_id);
  const selected = plan.routes.find((r) => r.id === selectedRouteId) ?? plan.routes[0];

  return (
    <div className="space-y-6">
      <section aria-label="Trip">
        <p className="flex items-center gap-1.5 text-sm font-semibold text-ink">
          <span className="truncate">{plan.origin.label}</span>
          <ArrowRight aria-hidden className="size-3.5 shrink-0 text-muted" />
          <span className="truncate">{plan.destination.label}</span>
        </p>
        <p className="mt-0.5 text-sm text-ink-2">
          Departs {formatDateTime(plan.routes[0]?.departure_time ?? plan.generated_at)} ·{' '}
          {formatWeight(plan.load_weight_lb)}
        </p>
      </section>

      {recommended && (
        <section aria-label="Recommendation" className="rounded-xl bg-accent-soft p-4">
          <p className="text-xs font-medium tracking-wide text-accent-hover uppercase">
            Recommended
          </p>
          <p className="mt-1 text-base font-semibold text-ink">{recommended.name}</p>
          <p className="mt-1 text-sm leading-snug text-ink-2">{plan.recommendation_reason}</p>
        </section>
      )}

      {plan.warnings.length > 0 && (
        <ul aria-label="Warnings" className="space-y-2">
          {plan.warnings.map((warning) => (
            <li
              key={warning}
              className="flex gap-2.5 rounded-xl bg-warn-soft px-4 py-3 text-sm leading-snug text-warn-ink"
            >
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
              {warning}
            </li>
          ))}
        </ul>
      )}

      <section aria-labelledby="routes-heading">
        <h2
          id="routes-heading"
          className="mb-3 text-xs font-medium tracking-wide text-muted uppercase"
        >
          Routes
        </h2>
        <div className="space-y-2.5">
          {plan.routes.map((route, i) => (
            <RouteCard
              key={route.id}
              route={route}
              letter={ROUTE_LETTERS[i] ?? String(i + 1)}
              recommended={route.id === plan.recommended_route_id}
              selected={route.id === selected?.id}
              onSelect={() => onSelectRoute(route.id)}
            />
          ))}
        </div>
      </section>

      {selected && (
        <section aria-labelledby="checkpoints-heading">
          <div className="mb-3 flex items-baseline justify-between">
            <h2
              id="checkpoints-heading"
              className="text-xs font-medium tracking-wide text-muted uppercase"
            >
              Checkpoints · {selected.name}
            </h2>
            <span className="text-xs text-muted">
              every {plan.checkpoint_interval_mi} mi · {selected.checkpoints.length} stops
            </span>
          </div>
          <CheckpointTable
            checkpoints={selected.checkpoints}
            focusedIndex={focusedIndex}
            onFocus={onFocusCheckpoint}
          />
        </section>
      )}
    </div>
  );
}

export function ResultsSkeleton() {
  return (
    <div className="space-y-3" aria-hidden>
      <div className="h-10 w-3/4 animate-pulse rounded-lg bg-line/70" />
      <div className="h-24 animate-pulse rounded-xl bg-line/70" />
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-28 animate-pulse rounded-xl bg-line/70" />
      ))}
    </div>
  );
}

export function EmptyResults() {
  return (
    <div className="rounded-xl border border-dashed border-line-strong px-5 py-8 text-center">
      <RouteIcon aria-hidden className="mx-auto size-5 text-muted" />
      <p className="mt-2 text-sm font-medium text-ink">Compare three routes</p>
      <p className="mt-1 text-sm leading-snug text-ink-2">
        We check the forecast where your truck will be at each checkpoint, apply load limits, and
        recommend the safest option.
      </p>
    </div>
  );
}

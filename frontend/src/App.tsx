import { Truck } from 'lucide-react';
import { lazy, Suspense, useState } from 'react';
import { usePlanMutation } from './api/plan';
import { ErrorBoundary } from './components/ErrorBoundary';
import { EmptyResults, Results, ResultsSkeleton } from './components/Results';
import { TripForm } from './components/TripForm';
import type { LonLat, PlanRequest } from './types';

// The map (MapLibre + its worker) is the heaviest part of the app; load it as its own chunk.
const TripMap = lazy(() =>
  import('./components/map/TripMap').then((module) => ({ default: module.TripMap })),
);

export default function App() {
  const planMutation = usePlanMutation();
  const plan = planMutation.data ?? null;
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
  const [searchNear, setSearchNear] = useState<LonLat | null>(null);

  function submit(request: PlanRequest) {
    setFocusedIndex(null);
    planMutation.mutate(request, {
      onSuccess: (result) => setSelectedRouteId(result.recommended_route_id),
    });
  }

  function selectRoute(id: string) {
    setSelectedRouteId(id);
    setFocusedIndex(null);
  }

  return (
    <div className="flex min-h-full flex-col lg:h-full lg:flex-row">
      <aside className="order-2 flex flex-col border-line bg-page lg:order-1 lg:h-full lg:w-[440px] lg:shrink-0 lg:border-r">
        <header className="flex items-center gap-3 border-b border-line bg-surface px-5 py-4">
          <span className="grid size-9 place-items-center rounded-lg bg-ink text-white">
            <Truck aria-hidden className="size-5" />
          </span>
          <div>
            <h1 className="text-[15px] leading-tight font-semibold text-ink">
              Truck Route Planner
            </h1>
            <p className="text-xs text-ink-2">Weather-aware routing for heavy loads</p>
          </div>
        </header>

        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
          <div className="rounded-xl border border-line bg-surface p-4">
            <TripForm
              submitting={planMutation.isPending}
              onSubmit={submit}
              searchNear={searchNear}
            />
          </div>

          {planMutation.isError && (
            <p role="alert" className="rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">
              {planMutation.error.message}
            </p>
          )}

          {planMutation.isPending ? (
            <ResultsSkeleton />
          ) : plan && selectedRouteId ? (
            <Results
              plan={plan}
              selectedRouteId={selectedRouteId}
              focusedIndex={focusedIndex}
              onSelectRoute={selectRoute}
              onFocusCheckpoint={setFocusedIndex}
            />
          ) : (
            !planMutation.isError && <EmptyResults />
          )}
        </div>
      </aside>

      <main className="relative order-1 h-[78vh] sm:h-[60vh] lg:order-2 lg:h-full lg:flex-1">
        <ErrorBoundary fallback={<MapUnavailable />}>
          <Suspense fallback={<div className="h-full w-full bg-[#f2f2ef]" aria-hidden />}>
            <TripMap
              plan={planMutation.isPending ? null : plan}
              loading={planMutation.isPending}
              selectedRouteId={selectedRouteId}
              focusedIndex={focusedIndex}
              onSelectRoute={selectRoute}
              onFocusCheckpoint={setFocusedIndex}
              onFocusAreaChange={setSearchNear}
            />
          </Suspense>
        </ErrorBoundary>
      </main>
    </div>
  );
}

function MapUnavailable() {
  return (
    <div className="grid h-full place-items-center bg-surface-2 p-6 text-center">
      <div className="max-w-sm">
        <p className="text-sm font-medium text-ink">The map couldn't load</p>
        <p className="mt-1 text-sm text-ink-2">
          Your browser may not support WebGL. Routes, checkpoints and the recommendation are still
          available in the panel.
        </p>
      </div>
    </div>
  );
}

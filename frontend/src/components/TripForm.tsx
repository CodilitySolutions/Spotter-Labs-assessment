import { ArrowUpDown, Circle, Loader2, MapPin } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { defaultDeparture, toDateTimeLocal } from '../lib/format';
import type { LonLat, Place, PlanRequest } from '../types';
import { PlaceAutocomplete } from './PlaceAutocomplete';
import { SegmentedControl } from './SegmentedControl';

const FORECAST_HOURS = 48;
const MAX_LOAD_LB = 80_000;
const INTERVALS = [
  { value: 10, label: '10' },
  { value: 25, label: '25' },
  { value: 50, label: '50' },
] as const;

interface TripFormProps {
  submitting: boolean;
  onSubmit: (request: PlanRequest) => void;
  /** The map's centre when zoomed into a region; biases place search towards it. */
  searchNear: LonLat | null;
}

export function TripForm({ submitting, onSubmit, searchNear }: TripFormProps) {
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [departure, setDeparture] = useState(() => toDateTimeLocal(defaultDeparture()));
  const [load, setLoad] = useState('42000');
  const [interval, setCheckpointInterval] = useState<10 | 25 | 50>(25);
  const [error, setError] = useState<string | null>(null);

  const now = new Date();
  const minDeparture = toDateTimeLocal(now);
  const maxDeparture = toDateTimeLocal(new Date(now.getTime() + FORECAST_HOURS * 3_600_000));

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const loadLb = Number(load);
    const departureDate = new Date(departure);

    if (!origin || !destination) {
      return setError('Choose an origin and a destination from the suggestions.');
    }
    if (!load.trim() || !Number.isInteger(loadLb) || loadLb < 0 || loadLb > MAX_LOAD_LB) {
      return setError(
        `Load weight must be a whole number from 0 to ${MAX_LOAD_LB.toLocaleString()} lb.`,
      );
    }
    if (Number.isNaN(departureDate.getTime())) {
      return setError('Choose a departure date and time.');
    }
    setError(null);
    onSubmit({
      origin,
      destination,
      departure_time: departureDate.toISOString(),
      load_weight_lb: loadLb,
      checkpoint_interval_mi: interval,
    });
  }

  function swap() {
    setOrigin(destination);
    setDestination(origin);
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      <fieldset className="space-y-2">
        <legend className="mb-2 text-xs font-medium tracking-wide text-muted uppercase">
          Trip
        </legend>
        <div className="relative space-y-2">
          <PlaceAutocomplete
            label="Origin"
            placeholder="Origin — city or address"
            icon={<Circle className="size-3.5" strokeWidth={3} />}
            value={origin}
            onChange={setOrigin}
            near={searchNear}
          />
          <PlaceAutocomplete
            label="Destination"
            placeholder="Destination — city or address"
            icon={<MapPin className="size-4" />}
            value={destination}
            onChange={setDestination}
            near={searchNear}
          />
          <button
            type="button"
            onClick={swap}
            aria-label="Swap origin and destination"
            title="Swap origin and destination"
            className="absolute top-1/2 right-2 z-10 grid size-7 -translate-y-1/2 place-items-center rounded-full border border-line bg-surface text-ink-2 shadow-sm hover:text-ink"
          >
            <ArrowUpDown className="size-3.5" />
          </button>
        </div>
      </fieldset>

      <Field label="Departure" htmlFor="departure">
        <input
          id="departure"
          type="datetime-local"
          value={departure}
          min={minDeparture}
          max={maxDeparture}
          onChange={(event) => setDeparture(event.target.value)}
          className="h-11 w-full rounded-lg bg-surface px-3 text-sm text-ink ring-1 ring-line outline-none focus:ring-2 focus:ring-accent"
        />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Load weight" htmlFor="load">
          <div className="flex h-11 items-center rounded-lg bg-surface pr-3 ring-1 ring-line focus-within:ring-2 focus-within:ring-accent">
            <input
              id="load"
              inputMode="numeric"
              value={load}
              onChange={(event) => setLoad(event.target.value.replace(/[^\d]/g, ''))}
              className="h-full w-full min-w-0 bg-transparent px-3 text-sm text-ink tabular-nums outline-none"
            />
            <span className="text-sm text-muted">lb</span>
          </div>
        </Field>
        <Field label="Checkpoint every (mi)">
          <SegmentedControl
            label="Weather checkpoint interval in miles"
            value={interval}
            options={INTERVALS}
            onChange={setCheckpointInterval}
          />
        </Field>
      </div>

      {error && (
        <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-ink text-sm font-medium text-white transition-colors hover:bg-ink/85 disabled:cursor-wait disabled:bg-ink/70"
      >
        {submitting && <Loader2 aria-hidden className="size-4 animate-spin" />}
        {submitting ? 'Checking routes and weather…' : 'Plan routes'}
      </button>
    </form>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={htmlFor}
        className="block text-xs font-medium tracking-wide text-muted uppercase"
      >
        {label}
      </label>
      {children}
    </div>
  );
}

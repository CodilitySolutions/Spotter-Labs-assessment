import { Eye, EyeOff, Loader2, Pause, Play } from 'lucide-react';
import { memo, useCallback, useEffect, useId, useMemo } from 'react';
import { formatDateTime, formatTime } from '../../lib/format';
import { RISK_COLOR, RISK_LABEL } from '../../lib/risk';
import type { RiskOrUnknown } from '../../types';

interface ForecastSliderProps {
  startHour: number; // Unix seconds of hour 0
  hours: number; // slider positions (49 = 0..48 h)
  hour: number;
  onHourChange: (hour: number) => void;
  /** Worst risk score anywhere in the corridor for each hour (null = unknown). */
  worstByHour: (number | null)[] | null;
  routeName: string | null;
  tripStart: number | null; // selected route departure (Unix seconds)
  tripEnd: number | null; // selected route arrival
  truckMile: number | null; // where the truck is at the slider's time, if on the road
  visible: boolean;
  onVisibleChange: (visible: boolean) => void;
  playing: boolean;
  onPlayingChange: (playing: boolean) => void;
  status: 'loading' | 'error' | 'ready';
}

const PLAY_STEP_MS = 450;
const TICKS = [0, 12, 24, 36, 48];
const LEVEL_BY_SCORE: RiskOrUnknown[] = ['low', 'moderate', 'high', 'severe', 'no_travel'];

const levelOf = (score: number | null | undefined): RiskOrUnknown =>
  score === null || score === undefined ? 'unknown' : (LEVEL_BY_SCORE[score] ?? 'unknown');

export function ForecastSlider({
  startHour,
  hours,
  hour,
  onHourChange,
  worstByHour,
  routeName,
  tripStart,
  tripEnd,
  truckMile,
  visible,
  onVisibleChange,
  playing,
  onPlayingChange,
  status,
}: ForecastSliderProps) {
  const id = useId();
  const max = hours - 1;
  const ready = status === 'ready';
  const hourStart = startHour + hour * 3600;
  // Position (0-100%) of a time on the slider; matches the thumb's centre for whole hours.
  const pct = (ts: number) => Math.min(Math.max(((ts - startHour) / 3600 / max) * 100, 0), 100);

  const selectHour = useCallback(
    (h: number) => {
      onPlayingChange(false);
      onHourChange(h);
    },
    [onHourChange, onPlayingChange],
  );

  // Step through the hours while playing; stop at the end.
  useEffect(() => {
    if (!playing) return;
    if (hour >= max) {
      onPlayingChange(false);
      return;
    }
    const timer = window.setTimeout(() => onHourChange(hour + 1), PLAY_STEP_MS);
    return () => window.clearTimeout(timer);
  }, [playing, hour, max, onHourChange, onPlayingChange]);

  return (
    <div className="rounded-xl border border-line bg-surface/95 px-4 py-3 shadow-sm backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => {
            if (!playing && hour >= max) onHourChange(0);
            onPlayingChange(!playing);
          }}
          disabled={!ready}
          aria-label={playing ? 'Pause forecast animation' : 'Play forecast animation'}
          className="grid size-8 shrink-0 place-items-center rounded-full bg-ink text-white transition-colors hover:bg-ink/85 disabled:bg-ink/30"
        >
          {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5 translate-x-px" />}
        </button>

        <div className="min-w-0 flex-1">
          <label htmlFor={id} className="block text-sm font-medium text-ink tabular-nums">
            {formatDateTime(hourStart)}
            <span className="ml-1.5 font-normal text-muted">+{hour} h</span>
          </label>
          <p aria-live="polite" className="truncate text-xs text-ink-2">
            {status === 'loading' && 'Loading the 48-hour forecast…'}
            {status === 'error' && <span className="text-danger">Weather layer unavailable</span>}
            {ready && (
              <StatusText
                worst={worstByHour?.[hour]}
                routeName={routeName}
                hourStart={hourStart}
                tripStart={tripStart}
                tripEnd={tripEnd}
                truckMile={truckMile}
              />
            )}
          </p>
        </div>

        {status === 'loading' && (
          <Loader2 aria-hidden className="size-4 shrink-0 animate-spin text-muted" />
        )}
        <button
          type="button"
          onClick={() => onVisibleChange(!visible)}
          aria-pressed={visible}
          disabled={!ready}
          className="flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium text-ink-2 ring-1 ring-line transition-colors hover:text-ink disabled:opacity-50"
        >
          {visible ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
          {visible ? 'Hide' : 'Show'}
          <span className="sr-only">weather layer</span>
        </button>
      </div>

      {/*
        Every row below sits inside an 8px inset (half the thumb), so hour h lines up with the
        thumb's centre: bars, the driving window and tick labels share one coordinate system.
      */}
      <div className="mt-3">
        {/* Risk timeline: the worst level in the corridor, hour by hour. */}
        <RiskTimeline
          startHour={startHour}
          hours={hours}
          worstByHour={worstByHour}
          current={hour}
          ready={ready}
          onSelect={selectHour}
        />

        {/* Slider: neutral track; the native input supplies the thumb and keyboard support. */}
        <div className="relative mt-1 h-5">
          <div className="absolute inset-x-2 top-1/2 h-1 -translate-y-1/2 rounded-full bg-line" />
          <input
            id={id}
            type="range"
            min={0}
            max={max}
            step={1}
            value={hour}
            disabled={!ready}
            onChange={(event) => {
              onPlayingChange(false);
              onHourChange(Number(event.target.value));
            }}
            aria-valuetext={`${formatDateTime(hourStart)}, ${hour} hours from now`}
            className="forecast-range absolute inset-0 w-full"
          />
        </div>

        {/* The selected route's time on the road, as its own labelled band. */}
        {routeName && tripStart !== null && tripEnd !== null && (
          <div className="mt-1 h-4 px-2">
            <div className="relative h-full">
              <div
                className="absolute top-0 flex h-full min-w-0 items-center"
                style={{ left: `${pct(tripStart)}%`, width: `${pct(tripEnd) - pct(tripStart)}%` }}
                title={`${routeName}: departs ${formatTime(tripStart)}, arrives ${formatTime(tripEnd)}`}
              >
                <div className="absolute inset-x-0 top-0 h-1 rounded-full bg-accent" />
                <span className="mt-2 truncate text-[11px] font-medium text-accent-hover">
                  {routeName} on the road
                </span>
              </div>
            </div>
          </div>
        )}

        <div className="mt-1 h-4 px-2 text-[11px] text-muted tabular-nums">
          <div className="relative h-full">
            {TICKS.filter((t) => t <= max).map((t) => (
              <span
                key={t}
                className="absolute -translate-x-1/2 whitespace-nowrap first:translate-x-0 last:-translate-x-full"
                style={{ left: `${(t / max) * 100}%` }}
              >
                {t === 0 ? 'Now' : `+${t} h`}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusText({
  worst,
  routeName,
  hourStart,
  tripStart,
  tripEnd,
  truckMile,
}: {
  worst: number | null | undefined;
  routeName: string | null;
  hourStart: number;
  tripStart: number | null;
  tripEnd: number | null;
  truckMile: number | null;
}) {
  const level = levelOf(worst);
  const corridor =
    level === 'low'
      ? 'Clear: no risk areas in the corridor'
      : level === 'unknown'
        ? 'Weather unknown in the corridor'
        : `${RISK_LABEL[level]} weather in parts of the corridor`;

  let truck: string | null = null;
  if (routeName && tripStart !== null && tripEnd !== null) {
    if (hourStart + 3600 <= tripStart) truck = `${routeName} departs ${formatTime(tripStart)}`;
    else if (hourStart > tripEnd) truck = `${routeName} has arrived`;
    else if (truckMile !== null) truck = `Truck near mile ${Math.round(truckMile)} on ${routeName}`;
  }

  return (
    <>
      <span
        aria-hidden
        className="mr-1.5 inline-block size-2 rounded-full align-middle"
        style={{ backgroundColor: RISK_COLOR[level] }}
      />
      {corridor}
      {truck && <span className="text-muted"> · {truck}</span>}
    </>
  );
}

interface RiskTimelineProps {
  startHour: number;
  hours: number;
  worstByHour: (number | null)[] | null;
  current: number;
  ready: boolean;
  onSelect: (hour: number) => void;
}

/**
 * One bar per hour, coloured by the worst level in the corridor. Memoised, with tooltips
 * computed once per heatmap, so moving the slider re-renders only cheap style changes.
 */
const RiskTimeline = memo(function RiskTimeline({
  startHour,
  hours,
  worstByHour,
  current,
  ready,
  onSelect,
}: RiskTimelineProps) {
  const bars = useMemo(
    () =>
      Array.from({ length: hours }, (_, h) => {
        const level = levelOf(worstByHour?.[h]);
        return {
          color: RISK_COLOR[level],
          title: `${formatDateTime(startHour + h * 3600)} · worst in corridor: ${RISK_LABEL[level]}`,
        };
      }),
    [startHour, hours, worstByHour],
  );

  return (
    <div className="px-2">
      <div aria-hidden className="flex h-3 items-end gap-px">
        {bars.map((bar, h) => {
          const isCurrent = h === current;
          return (
            <div
              key={h}
              title={bar.title}
              onClick={() => ready && onSelect(h)}
              className={`flex-1 cursor-pointer rounded-[1px] ${isCurrent ? 'h-3' : 'h-2'}`}
              style={{
                backgroundColor: ready ? bar.color : 'var(--color-line)',
                opacity: ready && !isCurrent ? 0.75 : 1,
              }}
            />
          );
        })}
      </div>
    </div>
  );
});

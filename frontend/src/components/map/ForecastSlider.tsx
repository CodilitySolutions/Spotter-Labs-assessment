import { Eye, EyeOff, Loader2, Navigation2, Pause, Play } from 'lucide-react';
import { memo, useCallback, useEffect, useId, useMemo } from 'react';
import { formatDateTime, formatTime } from '../../lib/format';
import {
  describeCauses,
  HEATMAP_VIEWS,
  type HeatmapView,
  type HourSummary,
} from '../../lib/heatmap';
import { RISK_COLOR, RISK_LABEL } from '../../lib/risk';
import type { RiskOrUnknown } from '../../types';

interface ForecastSliderProps {
  startHour: number; // Unix seconds of hour 0
  hours: number; // slider positions (49 = 0..48 h)
  hour: number;
  onHourChange: (hour: number) => void;
  /** Worst level in the corridor and its causes, per hour, for the current view. */
  summaries: HourSummary[] | null;
  view: HeatmapView;
  onViewChange: (view: HeatmapView) => void;
  arrows: boolean;
  onArrowsChange: (arrows: boolean) => void;
  loadLb: number;
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
  summaries,
  view,
  onViewChange,
  arrows,
  onArrowsChange,
  loadLb,
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

  const tripStartPct = tripStart !== null ? pct(tripStart) : 0;
  const tripEndPct = tripEnd !== null ? pct(tripEnd) : 0;

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
            {ready && <CorridorStatus summary={summaries?.[hour]} view={view} loadLb={loadLb} />}
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

      {/* What to show: the overall risk or one condition, and the wind arrows. */}
      <div className="mt-3 flex items-center gap-2">
        <div
          role="radiogroup"
          aria-label="Heatmap shows"
          className="flex rounded-lg bg-surface-2 p-0.5 ring-1 ring-line"
        >
          {HEATMAP_VIEWS.map((option) => {
            const selected = option.value === view;
            return (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={selected}
                disabled={!ready}
                onClick={() => onViewChange(option.value)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  selected
                    ? 'bg-surface text-ink shadow-sm ring-1 ring-line'
                    : 'text-ink-2 hover:text-ink'
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>
        <button
          type="button"
          onClick={() => onArrowsChange(!arrows)}
          aria-pressed={arrows}
          disabled={!ready}
          className={`ml-auto flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium ring-1 transition-colors disabled:opacity-50 ${
            arrows ? 'bg-ink text-white ring-ink' : 'text-ink-2 ring-line hover:text-ink'
          }`}
        >
          <Navigation2 aria-hidden className="size-3.5 rotate-45" />
          Wind arrows
        </button>
      </div>

      {/*
        Every row below sits inside an 8px inset (half the thumb), so hour h lines up with the
        thumb's centre: bars, the driving window and tick labels share one coordinate system.
      */}
      <div className="mt-3">
        <RiskTimeline
          startHour={startHour}
          hours={hours}
          summaries={summaries}
          view={view}
          loadLb={loadLb}
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
            onChange={(event) => selectHour(Number(event.target.value))}
            aria-valuetext={`${formatDateTime(hourStart)}, ${hour} hours from now`}
            className="forecast-range absolute inset-0 w-full"
          />
        </div>

        {/* The selected route's time on the road, as its own labelled band. */}
        {routeName && tripStart !== null && tripEnd !== null && (
          <div className="mt-1 h-4 px-2">
            <div className="relative h-full">
              <div
                className="absolute top-0 h-1 rounded-full bg-accent"
                style={{ left: `${tripStartPct}%`, width: `${tripEndPct - tripStartPct}%` }}
                title={`${routeName}: departs ${formatTime(tripStart)}, arrives ${formatTime(tripEnd)}`}
              />
              {/* Not clipped to the band: short trips would otherwise show "Ro…". */}
              <span
                className={`absolute top-1.5 text-[11px] font-medium whitespace-nowrap text-accent-hover ${
                  tripStartPct > 60 ? '-translate-x-full' : ''
                }`}
                style={{ left: `${tripStartPct > 60 ? tripEndPct : tripStartPct}%` }}
              >
                {routeName} on the road
              </span>
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

      {ready && (
        <TruckStatus
          routeName={routeName}
          hourStart={hourStart}
          tripStart={tripStart}
          tripEnd={tripEnd}
          truckMile={truckMile}
        />
      )}
    </div>
  );
}

const VIEW_NOUN: Record<HeatmapView, string> = {
  overall: 'weather',
  wind: 'wind',
  rain: 'rain',
  snow: 'snow',
};

function CorridorStatus({
  summary,
  view,
  loadLb,
}: {
  summary: HourSummary | undefined;
  view: HeatmapView;
  loadLb: number;
}) {
  const level = levelOf(summary?.score);
  const noun = VIEW_NOUN[view];
  let text: string;
  if (level === 'unknown')
    text = `${noun[0]!.toUpperCase()}${noun.slice(1)} unknown in the corridor`;
  else if (level === 'low')
    text = `Clear: no ${view === 'overall' ? 'risk areas' : `${noun} risk`} in the corridor`;
  else text = `${RISK_LABEL[level]}: ${summary ? describeCauses(summary, loadLb) : noun}`;
  return (
    <>
      <span
        aria-hidden
        className="mr-1.5 inline-block size-2 rounded-full align-middle"
        style={{ backgroundColor: RISK_COLOR[level] }}
      />
      {text}
    </>
  );
}

function TruckStatus({
  routeName,
  hourStart,
  tripStart,
  tripEnd,
  truckMile,
}: {
  routeName: string | null;
  hourStart: number;
  tripStart: number | null;
  tripEnd: number | null;
  truckMile: number | null;
}) {
  if (!routeName || tripStart === null || tripEnd === null) return null;
  let text: string;
  if (hourStart + 3600 <= tripStart) text = `${routeName} departs ${formatTime(tripStart)}`;
  else if (hourStart > tripEnd) text = `${routeName} arrived at ${formatTime(tripEnd)}`;
  else if (truckMile !== null) text = `Truck near mile ${Math.round(truckMile)} on ${routeName}`;
  else return null;
  return <p className="mt-1 text-[11px] text-muted">{text}</p>;
}

interface RiskTimelineProps {
  startHour: number;
  hours: number;
  summaries: HourSummary[] | null;
  view: HeatmapView;
  loadLb: number;
  current: number;
  ready: boolean;
  onSelect: (hour: number) => void;
}

/**
 * One bar per hour, coloured by the worst level in the corridor for the current view, with the
 * cause in its tooltip. Memoised with tooltips computed once per heatmap/view, so moving the
 * slider re-renders only cheap style changes.
 */
const RiskTimeline = memo(function RiskTimeline({
  startHour,
  hours,
  summaries,
  view,
  loadLb,
  current,
  ready,
  onSelect,
}: RiskTimelineProps) {
  const bars = useMemo(
    () =>
      Array.from({ length: hours }, (_, h) => {
        const summary = summaries?.[h];
        const level = levelOf(summary?.score);
        const cause =
          summary && summary.causes.length ? ` (${describeCauses(summary, loadLb)})` : '';
        const scope = view === 'overall' ? 'worst in corridor' : `worst ${view} risk`;
        return {
          color: RISK_COLOR[level],
          title: `${formatDateTime(startHour + h * 3600)} · ${scope}: ${RISK_LABEL[level]}${cause}`,
        };
      }),
    [startHour, hours, summaries, view, loadLb],
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

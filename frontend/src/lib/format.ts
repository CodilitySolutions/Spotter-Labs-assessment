import { format, isSameDay } from 'date-fns';

export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

export function formatMiles(miles: number): string {
  if (miles > 0 && miles < 10) return `${miles.toFixed(1)} mi`;
  return `${Math.round(miles).toLocaleString()} mi`;
}

export function formatWeight(lb: number): string {
  return `${lb.toLocaleString()} lb`;
}

/** "2:30 PM", or "Thu 2:30 PM" when the time is not today. */
export function formatTime(unixSeconds: number, now: Date = new Date()): string {
  const date = new Date(unixSeconds * 1000);
  return isSameDay(date, now) ? format(date, 'h:mm a') : format(date, 'EEE h:mm a');
}

export function formatDateTime(unixSeconds: number): string {
  return format(new Date(unixSeconds * 1000), 'EEE, MMM d · h:mm a');
}

export function formatNumber(value: number | null, digits: number, unit: string): string {
  return value === null ? '—' : `${value.toFixed(digits)} ${unit}`;
}

/** Value for an <input type="datetime-local"> in the browser's time zone. */
export function toDateTimeLocal(date: Date): string {
  return format(date, "yyyy-MM-dd'T'HH:mm");
}

/** A sensible default departure: the next quarter hour, at least 10 minutes from now. */
export function defaultDeparture(now: Date = new Date()): Date {
  const d = new Date(now.getTime() + 10 * 60_000);
  d.setSeconds(0, 0);
  d.setMinutes(Math.ceil(d.getMinutes() / 15) * 15);
  return d;
}

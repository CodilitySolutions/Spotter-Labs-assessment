import { describe, expect, it } from 'vitest';
import { defaultDeparture, formatDuration, formatMiles, formatNumber } from './format';

describe('formatDuration', () => {
  it.each([
    [45 * 60, '45 min'],
    [3600, '1 h'],
    [13 * 3600 + 51 * 60, '13 h 51 min'],
    [3600 + 29, '1 h'], // rounds to whole minutes
  ])('%i s -> %s', (seconds, text) => {
    expect(formatDuration(seconds)).toBe(text);
  });
});

describe('formatMiles', () => {
  it('keeps one decimal below 10 miles and groups thousands above', () => {
    expect(formatMiles(4.25)).toBe('4.3 mi');
    expect(formatMiles(0)).toBe('0 mi');
    expect(formatMiles(1336.4)).toBe('1,336 mi');
  });
});

describe('formatNumber', () => {
  it('shows a dash for missing values instead of a misleading zero', () => {
    expect(formatNumber(null, 2, 'in/h')).toBe('—');
    expect(formatNumber(0, 2, 'in/h')).toBe('0.00 in/h');
  });
});

describe('defaultDeparture', () => {
  it('rounds up to the next quarter hour at least 10 minutes ahead', () => {
    const now = new Date(2026, 10, 6, 16, 52, 30);
    const d = defaultDeparture(now);

    expect(d.getHours()).toBe(17);
    expect(d.getMinutes()).toBe(15);
    expect(d.getSeconds()).toBe(0);
  });
});

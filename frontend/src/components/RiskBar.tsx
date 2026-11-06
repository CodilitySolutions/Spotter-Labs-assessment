import { formatMiles } from '../lib/format';
import { RISK_COLOR, RISK_LABEL, RISK_LEVELS } from '../lib/risk';
import type { RiskOrUnknown } from '../types';
import { RiskMark } from './RiskChip';

interface RiskBarProps {
  milesByLevel: Record<RiskOrUnknown, number>;
}

/**
 * Miles at each risk level as one stacked bar, with a direct-labelled legend underneath so
 * no level is identified by color alone. Segments are separated by 2px gaps.
 */
export function RiskBar({ milesByLevel }: RiskBarProps) {
  const levels = RISK_LEVELS.filter((level) => milesByLevel[level] > 0.05);
  const total = levels.reduce((sum, level) => sum + milesByLevel[level], 0);
  if (total === 0) return null;

  return (
    <div>
      <div
        className="flex h-2 gap-0.5 overflow-hidden rounded"
        role="img"
        aria-label={levels
          .map((l) => `${RISK_LABEL[l]} ${formatMiles(milesByLevel[l])}`)
          .join(', ')}
      >
        {levels.map((level) => (
          <div
            key={level}
            title={`${RISK_LABEL[level]} · ${formatMiles(milesByLevel[level])}`}
            className="h-full min-w-1"
            style={{
              flexGrow: milesByLevel[level],
              flexBasis: 0,
              backgroundColor: RISK_COLOR[level],
            }}
          />
        ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-2">
        {levels.map((level) => (
          <li key={level} className="inline-flex items-center gap-1.5">
            <RiskMark level={level} />
            <span>{RISK_LABEL[level]}</span>
            <span className="text-muted tabular-nums">{formatMiles(milesByLevel[level])}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

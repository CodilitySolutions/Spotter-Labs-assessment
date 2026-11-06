import { Ban } from 'lucide-react';
import { RISK_COLOR, RISK_LABEL } from '../lib/risk';
import type { RiskOrUnknown } from '../types';

interface RiskChipProps {
  level: RiskOrUnknown;
  size?: 'sm' | 'md';
}

/** A risk level as a colored mark plus its name. The text stays in ink, never the status color. */
export function RiskChip({ level, size = 'sm' }: RiskChipProps) {
  const text = size === 'sm' ? 'text-xs' : 'text-sm';
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2 py-0.5 font-medium whitespace-nowrap text-ink ${text}`}
    >
      <RiskMark level={level} />
      {RISK_LABEL[level]}
    </span>
  );
}

export function RiskMark({ level }: { level: RiskOrUnknown }) {
  if (level === 'no_travel') {
    return (
      <Ban
        aria-hidden
        className="size-3.5 shrink-0"
        color={RISK_COLOR.no_travel}
        strokeWidth={2.5}
      />
    );
  }
  return (
    <span
      aria-hidden
      className="size-2.5 shrink-0 rounded-full"
      style={{ backgroundColor: RISK_COLOR[level] }}
    />
  );
}

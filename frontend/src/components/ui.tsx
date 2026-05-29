// Small presentational helpers shared across dashboard views.

export function ConfidenceBadge({ value }: { value: number }) {
  const tone =
    value >= 70 ? "text-accent bg-accent/10 border-accent/30"
    : value >= 45 ? "text-warn bg-warn/10 border-warn/30"
    : "text-danger bg-danger/10 border-danger/30";
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums ${tone}`}>
      {value.toFixed(0)}
    </span>
  );
}

// Visualises how far the verified floor clears the sportsbook line.
export function GapBar({ floor, line }: { floor: number; line: number }) {
  const span = Math.max(floor, line) || 1;
  const linePct = (line / span) * 100;
  const floorPct = (floor / span) * 100;
  return (
    <div className="relative h-2 w-full rounded-full bg-surface-2">
      <div
        className="absolute inset-y-0 left-0 rounded-full bg-accent/70"
        style={{ width: `${floorPct}%` }}
      />
      <div
        className="absolute inset-y-[-3px] w-0.5 bg-foreground"
        style={{ left: `${linePct}%` }}
        title={`line ${line}`}
      />
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted">{label}</div>
      <div className="text-sm font-semibold tabular-nums">{value}</div>
    </div>
  );
}

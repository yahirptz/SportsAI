"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type UnpricedMarket } from "@/lib/api";

// Operator-supplied odds workflow (SRS §01 bridge). Lists slate markets that
// still need a line and lets you add one inline; the next slate prices it.
export default function OddsPanel({
  sport,
  onPriced,
}: {
  sport: string;
  onPriced: () => void;
}) {
  const [unpriced, setUnpriced] = useState<UnpricedMarket[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setUnpriced((await api.unpriced(sport)).unpriced);
    } catch {
      setUnpriced([]);
    }
  }, [sport]);

  useEffect(() => {
    load();
  }, [load]);

  const addLine = async (m: UnpricedMarket, line: number) => {
    const key = `${m.player}-${m.market}`;
    setBusy(key);
    try {
      await api.addLine(sport, m.player, m.market, line, -110);
      await load();
      onPriced();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
          Unpriced Markets
        </h2>
        <span className="text-xs text-muted">{unpriced.length}</span>
      </div>
      <p className="mt-1 text-[10px] text-muted">
        Players on the slate with no line yet. Add your book&apos;s line to price them.
      </p>

      {unpriced.length === 0 ? (
        <p className="mt-3 text-xs text-muted">All slate markets are priced. ✓</p>
      ) : (
        <ul className="mt-3 max-h-72 space-y-1.5 overflow-y-auto pr-1">
          {unpriced.slice(0, 30).map((m) => (
            <UnpricedRow
              key={`${m.player}-${m.market}`}
              market={m}
              busy={busy === `${m.player}-${m.market}`}
              onAdd={(line) => addLine(m, line)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function UnpricedRow({
  market,
  busy,
  onAdd,
}: {
  market: UnpricedMarket;
  busy: boolean;
  onAdd: (line: number) => void;
}) {
  // Pre-fill a sensible suggestion just below the floor hint.
  const [line, setLine] = useState(Math.max(0, market.floor_hint - 0.5));
  return (
    <li className="flex items-center justify-between gap-2 rounded-md bg-surface-2 px-2 py-1.5 text-xs">
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{market.player}</div>
        <div className="text-[10px] text-muted">
          {market.market_label} · floor≈{market.floor_hint}
        </div>
      </div>
      <input
        type="number"
        step="0.5"
        value={line}
        onChange={(e) => setLine(parseFloat(e.target.value))}
        className="w-16 rounded border border-border bg-background px-1.5 py-1 text-right tabular-nums"
      />
      <button
        onClick={() => onAdd(line)}
        disabled={busy}
        className="rounded bg-accent px-2 py-1 font-semibold text-background disabled:opacity-50"
      >
        {busy ? "…" : "add"}
      </button>
    </li>
  );
}

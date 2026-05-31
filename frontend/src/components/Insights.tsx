"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Patterns } from "@/lib/api";

// The Obsidian "second brain": learned patterns from graded bets + an AI debrief.
export default function Insights() {
  const [p, setP] = useState<Patterns | null>(null);
  const [debrief, setDebrief] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    api.vaultPatterns().then(setP).catch(() => setP(null));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const runDebrief = async () => {
    setLoading(true);
    try {
      const r = await api.vaultDebrief();
      setDebrief(r.debrief);
      setP(r.patterns);
    } finally {
      setLoading(false);
    }
  };

  const rows = (m?: Record<string, { n: number; hit_rate: number | null }>) =>
    Object.entries(m ?? {}).sort((a, b) => b[1].n - a[1].n);

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
          Vault — Learned Patterns
        </h2>
        <button
          onClick={runDebrief}
          disabled={loading || !p || p.total_graded === 0}
          className="rounded-lg border border-border px-2.5 py-1 text-xs font-medium hover:border-accent/40 disabled:opacity-50"
        >
          {loading ? "Thinking…" : "AI debrief"}
        </button>
      </div>

      {!p || p.total_graded === 0 ? (
        <p className="mt-3 text-xs text-muted">
          No graded bets yet. Patterns build as you grade picks — they get meaningful around
          ~30+ per bucket.
        </p>
      ) : (
        <>
          <div className="mt-2 text-[11px] text-muted">
            {p.total_graded} graded · overall {p.overall.hit_rate}%
            <span className="ml-1">(small sample — directional only)</span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-4 text-xs">
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wider text-muted">By cushion</div>
              {rows(p.by_cushion).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span>{k}</span>
                  <span className="tabular-nums text-muted">{v.hit_rate}% · n={v.n}</span>
                </div>
              ))}
            </div>
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wider text-muted">By market</div>
              {rows(p.by_market).slice(0, 5).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-2">
                  <span className="truncate">{k}</span>
                  <span className="tabular-nums text-muted">{v.hit_rate}% · n={v.n}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {debrief && (
        <div className="mt-3 whitespace-pre-wrap border-l-2 border-accent/40 pl-3 text-xs text-foreground/85">
          {debrief}
        </div>
      )}
    </div>
  );
}

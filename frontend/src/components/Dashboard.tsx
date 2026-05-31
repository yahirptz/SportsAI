"use client";

import { useEffect, useState } from "react";
import { api, type SportInfo } from "@/lib/api";
import Assistant from "./Assistant";
import TrackRecord from "./TrackRecord";
import Insights from "./Insights";

export default function Dashboard() {
  const [sports, setSports] = useState<SportInfo[]>([]);
  const [sport, setSport] = useState("mlb");
  const [bankroll, setBankroll] = useState<number | null>(null);

  useEffect(() => {
    api.sports().then(setSports).catch(() => {});
    api.bankroll().then((b) => setBankroll(b.balance)).catch(() => {});
  }, []);

  return (
    <div className="mx-auto w-full max-w-5xl flex-1 px-5 py-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Edge<span className="text-accent">IQ</span>
          </h1>
          <p className="text-xs text-muted">Paste a board. Ask. Bet smarter.</p>
        </div>
        {bankroll != null && (
          <div className="rounded-lg border border-border bg-surface px-4 py-2 text-right">
            <div className="text-[10px] uppercase tracking-wider text-muted">Bankroll</div>
            <div className="text-lg font-bold tabular-nums">${bankroll.toFixed(2)}</div>
          </div>
        )}
      </header>

      <nav className="mt-5 flex flex-wrap gap-2">
        {sports.filter((s) => s.active).map((s) => (
          <button
            key={s.sport}
            onClick={() => setSport(s.sport)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
              sport === s.sport
                ? "border-accent bg-accent/10 text-accent"
                : "border-border bg-surface text-foreground hover:border-accent/40"
            }`}
          >
            {s.label}
          </button>
        ))}
      </nav>

      <main className="mt-5">
        <Assistant key={sport} sport={sport} />
      </main>

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <TrackRecord sport={sport} />
        <Insights />
      </div>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type FeedHealth, type Parlay, type Pick, type SportInfo } from "@/lib/api";
import PickCard from "./PickCard";
import ParlayPanel from "./ParlayPanel";
import ModelHealth from "./ModelHealth";
import OddsPanel from "./OddsPanel";

export default function Dashboard() {
  const [sports, setSports] = useState<SportInfo[]>([]);
  const [sport, setSport] = useState("nba");
  const [picks, setPicks] = useState<Pick[]>([]);
  const [parlay, setParlay] = useState<Parlay | null>(null);
  const [health, setHealth] = useState<FeedHealth | null>(null);
  const [bankroll, setBankroll] = useState<number | null>(null);
  const [enriched, setEnriched] = useState(false);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.sports().then(setSports).catch((e) => setError(String(e)));
    api.bankroll().then((b) => setBankroll(b.balance)).catch(() => {});
  }, []);

  const loadSport = useCallback(async (s: string) => {
    setError(null);
    setParlay(null);
    try {
      const [p, h] = await Promise.all([api.picks(s), api.feedHealth()]);
      setPicks(p.picks);
      setEnriched(p.enriched);
      setHealth(h);
    } catch (e) {
      setError(String(e));
      setPicks([]);
    }
  }, []);

  useEffect(() => {
    loadSport(sport);
  }, [sport, loadSport]);

  const build = async () => {
    setBuilding(true);
    setError(null);
    try {
      setParlay(await api.buildParlay(sport));
    } catch (e) {
      setError(String(e));
    } finally {
      setBuilding(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-6xl flex-1 px-5 py-8">
      {/* Header */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Edge<span className="text-accent">IQ</span>
          </h1>
          <p className="text-xs text-muted">
            The Intelligent Edge · floor-verified same-game parlays
          </p>
        </div>
        {bankroll != null && (
          <div className="rounded-lg border border-border bg-surface px-4 py-2 text-right">
            <div className="text-[10px] uppercase tracking-wider text-muted">Bankroll</div>
            <div className="text-lg font-bold tabular-nums">${bankroll.toFixed(2)}</div>
          </div>
        )}
      </header>

      {/* Sport tabs */}
      <nav className="mt-6 flex flex-wrap gap-2">
        {sports.map((s) => (
          <button
            key={s.sport}
            onClick={() => s.active && setSport(s.sport)}
            disabled={!s.active}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
              sport === s.sport
                ? "border-accent bg-accent/10 text-accent"
                : s.active
                  ? "border-border bg-surface text-foreground hover:border-accent/40"
                  : "border-border bg-surface/50 text-muted/50 cursor-not-allowed"
            }`}
            title={s.active ? s.primary_source : "Coming soon"}
          >
            {s.label}
            {!s.active && <span className="ml-1 text-[9px]">soon</span>}
          </button>
        ))}
      </nav>

      {error && (
        <div className="mt-4 rounded-lg border border-danger/30 bg-danger/10 p-3 text-xs text-danger">
          {error} — is the backend running on :8000?
        </div>
      )}

      {/* Main grid */}
      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Agent Feed */}
        <section className="lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
              Agent Feed
            </h2>
            <div className="flex items-center gap-2">
              {enriched && (
                <span className="rounded border border-accent/30 bg-accent/10 px-2 py-0.5 text-[10px] text-accent">
                  enriched
                </span>
              )}
              <span className="text-xs text-muted">{picks.length} eligible</span>
            </div>
          </div>
          {picks.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted">
              No eligible picks — every prop failed the floor model.
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {picks.map((p) => (
                <PickCard key={p.id} pick={p} />
              ))}
            </div>
          )}
        </section>

        {/* Right rail */}
        <aside className="space-y-5">
          <ParlayPanel parlay={parlay} loading={building} onBuild={build} />
          <OddsPanel sport={sport} onPriced={() => loadSport(sport)} />
          <ModelHealth health={health} />
        </aside>
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import { api, type FloorboardResponse } from "@/lib/api";
import GameLines from "./GameLines";

// Paste FanDuel's tiered board → floor board → pick the bet shape you want.
export default function FloorBoard({ sport }: { sport: string }) {
  const [paste, setPaste] = useState("");
  const [mode, setMode] = useState<"single" | "parlay" | "moneyline">("parlay");
  const [legs, setLegs] = useState(3);
  const [res, setRes] = useState<FloorboardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [glReload, setGlReload] = useState(0);
  const [importMsg, setImportMsg] = useState<string | null>(null);

  const importLines = async () => {
    setImportMsg(null);
    try {
      const r = await api.importGameLines(sport, paste);
      setImportMsg(`Imported ${r.imported} game line(s).`);
      setGlReload((k) => k + 1);
    } catch (e) {
      setImportMsg(String(e));
    }
  };

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      setRes(await api.floorboard(sport, paste, mode, legs));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const bet = res?.bet;
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">Floor Board</h2>
        <p className="mt-1 text-[11px] text-muted">
          Paste FanDuel&apos;s player-prop board. The floor model keeps only tiers a player
          cleared in <em>every</em> recent game, then builds the bet you choose.
        </p>
        {mode !== "moneyline" && (
          <textarea
            value={paste}
            onChange={(e) => setPaste(e.target.value)}
            placeholder="Paste FanDuel props here (To Score 20+ Points, 2+ Made Threes, …)"
            className="mt-3 h-28 w-full rounded-lg border border-border bg-background p-2 font-mono text-[11px]"
          />
        )}
        {mode === "moneyline" && (
          <div className="mt-3">
            <textarea
              value={paste}
              onChange={(e) => setPaste(e.target.value)}
              placeholder="Paste FanDuel's game line (Spread / Money / Total block) here, then Import."
              className="h-28 w-full rounded-lg border border-border bg-background p-2 font-mono text-[11px]"
            />
            <div className="mt-2 flex items-center gap-3">
              <button
                onClick={importLines}
                disabled={!paste.trim()}
                className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-background disabled:opacity-50"
              >
                Import game line
              </button>
              {importMsg && <span className="text-[11px] text-muted">{importMsg}</span>}
            </div>
          </div>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <div className="flex gap-1 rounded-lg border border-border bg-surface-2 p-0.5 text-xs">
            {(["single", "parlay", "moneyline"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`rounded-md px-2.5 py-1 capitalize ${
                  mode === m ? "bg-accent/15 text-accent" : "text-muted"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
          {mode === "parlay" && (
            <label className="flex items-center gap-2 text-xs text-muted">
              Legs
              <input
                type="number" min={2} max={8} value={legs}
                onChange={(e) => setLegs(Math.max(2, Math.min(8, +e.target.value)))}
                className="w-14 rounded border border-border bg-background px-1.5 py-1 text-right"
              />
            </label>
          )}
          {mode !== "moneyline" && (
            <button
              onClick={run}
              disabled={loading || !paste.trim()}
              className="ml-auto rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-background disabled:opacity-50"
            >
              {loading ? "Building…" : "Build"}
            </button>
          )}
        </div>
        {error && <div className="mt-2 text-xs text-danger">{error}</div>}
      </div>

      {mode === "moneyline" && <GameLines key={glReload} sport={sport} />}

      {bet && !bet.no_bet && (
        <div className="rounded-xl border border-accent/30 bg-accent/5 p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-accent">
              {bet.leg_count}-leg {mode} · {bet.combined_odds! > 0 ? `+${bet.combined_odds}` : bet.combined_odds}
            </span>
            <span className="text-xs text-muted">
              model {bet.model_hit_prob}% · stake ${bet.recommended_stake}
            </span>
          </div>
          <ul className="mt-3 divide-y divide-border">
            {bet.legs.map((l) => (
              <li key={`${l.player}-${l.market}`} className="flex items-center justify-between py-2 text-sm">
                <span>
                  {l.player} <span className="text-muted">· {l.market_label}</span>
                </span>
                <span className="text-xs tabular-nums text-muted">
                  floor {l.floor} (+{l.cushion}) · {l.odds > 0 ? `+${l.odds}` : l.odds}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {bet?.no_bet && <div className="rounded-lg border border-danger/30 bg-danger/10 p-3 text-xs text-danger">{bet.reason}</div>}

      {res?.board && res.board.length > 0 && (
        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="mb-2 text-xs text-muted">
            {res.board_size} qualifying floor plays (cleared every recent game)
          </div>
          <ul className="space-y-1 text-xs">
            {res.board.map((p) => (
              <li key={`${p.player}-${p.market}`} className="flex justify-between">
                <span>{p.player} <span className="text-muted">{p.market_label}</span></span>
                <span className="tabular-nums text-muted">
                  floor {p.floor} (+{p.cushion}) · {p.odds > 0 ? `+${p.odds}` : p.odds}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

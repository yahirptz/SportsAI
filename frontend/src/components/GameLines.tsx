"use client";

import { useEffect, useState } from "react";
import { api, type GamesResponse } from "@/lib/api";

// Game-line value model (moneyline). Deliberately framed with a loud caveat:
// this is a naive record-only model that ignores starting pitchers, so it is a
// reference, not a betting signal.
export default function GameLines({ sport }: { sport: string }) {
  const [data, setData] = useState<GamesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .games(sport)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [sport]);

  if (loading) return <p className="text-sm text-muted">Loading game lines…</p>;
  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!data || data.games.length === 0)
    return (
      <p className="text-sm text-muted">
        No game lines for {sport.toUpperCase()}. {data?.note ?? ""}
      </p>
    );

  return (
    <div>
      <div className="mb-4 rounded-lg border border-warn/40 bg-warn/10 p-3 text-xs text-warn">
        ⚠️ {data.warning}
      </div>
      <div className="mb-3 flex items-center justify-between text-xs text-muted">
        <span>{data.count} games · model: {data.model}</span>
        <span>{data.leans} record-model leans</span>
      </div>

      <ul className="space-y-2">
        {data.games.map((g) => (
          <li
            key={g.game_id}
            className={`rounded-xl border bg-surface p-3 ${
              g.best ? "border-warn/40" : "border-border"
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="text-sm">
                <span className="font-medium">{g.away}</span>
                <span className="text-muted"> ({g.away_record}) @ </span>
                <span className="font-medium">{g.home}</span>
                <span className="text-muted"> ({g.home_record})</span>
              </div>
              {g.total != null && (
                <span className="text-[10px] text-muted">O/U {g.total}</span>
              )}
            </div>

            <div className="mt-2 grid grid-cols-2 gap-2">
              {g.edges.map((e) => (
                <div
                  key={e.side}
                  className={`rounded-md px-2 py-1.5 text-xs ${
                    g.best && g.best.side === e.side
                      ? "bg-warn/10 ring-1 ring-warn/40"
                      : "bg-surface-2"
                  }`}
                >
                  <div className="flex justify-between">
                    <span className="font-medium">{e.team}</span>
                    <span className="tabular-nums text-muted">
                      {e.odds > 0 ? `+${e.odds}` : e.odds}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[10px] text-muted tabular-nums">
                    model {(e.model_prob * 100).toFixed(0)}% · mkt{" "}
                    {(e.implied_prob * 100).toFixed(0)}%
                    {e.edge > 0 && (
                      <span className={g.best?.side === e.side ? "text-warn" : ""}>
                        {" "}
                        (+{(e.edge * 100).toFixed(1)})
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {g.note && <div className="mt-1.5 text-[10px] text-muted">{g.note}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type MoneylineForm, type MoneylinePrediction } from "@/lib/api";

// Moneyline panel — team form scores + a form-model prediction (win prob, EV,
// Kelly) once you enter the odds. Win prob comes only from our form model.
export default function OddsPanel({ sport }: { sport: string }) {
  const [form, setForm] = useState<MoneylineForm | null>(null);
  const [pred, setPred] = useState<MoneylinePrediction | null>(null);
  const [homeOdds, setHomeOdds] = useState(-130);
  const [awayOdds, setAwayOdds] = useState(110);
  const [loading, setLoading] = useState(false);

  const loadForm = useCallback(() => {
    setPred(null);
    api.moneylineForm(sport).then(setForm).catch(() => setForm(null));
  }, [sport]);
  useEffect(() => {
    loadForm();
  }, [loadForm]);

  const predict = async () => {
    setLoading(true);
    try {
      setPred(await api.moneylinePredict(sport, homeOdds, awayOdds));
    } finally {
      setLoading(false);
    }
  };

  const noGame = !form?.home || !form?.away;

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">Moneyline (form model)</h2>

      {noGame ? (
        <p className="mt-3 text-xs text-muted">{form?.note ?? "No upcoming game for this sport."}</p>
      ) : (
        <>
          <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
            {[form.away, form.home].map((t, i) => (
              <div key={i} className="rounded-md bg-surface-2 p-2">
                <div className="flex justify-between">
                  <span className="font-medium">{t!.team}</span>
                  <span className="tabular-nums text-accent">{t!.form_score}</span>
                </div>
                <div className="mt-1 text-[10px] text-muted">
                  {t!.last5.join(" ")} · margin {t!.avg_margin > 0 ? "+" : ""}{t!.avg_margin}
                  {t!.rest_days != null && ` · ${t!.rest_days}d rest`}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 flex items-center gap-2 text-xs">
            <label className="flex items-center gap-1 text-muted">
              Away ML
              <input type="number" value={awayOdds} onChange={(e) => setAwayOdds(+e.target.value)}
                className="w-16 rounded border border-border bg-background px-1.5 py-1 text-right" />
            </label>
            <label className="flex items-center gap-1 text-muted">
              Home ML
              <input type="number" value={homeOdds} onChange={(e) => setHomeOdds(+e.target.value)}
                className="w-16 rounded border border-border bg-background px-1.5 py-1 text-right" />
            </label>
            <button onClick={predict} disabled={loading}
              className="ml-auto rounded-lg bg-accent px-3 py-1.5 font-semibold text-background disabled:opacity-50">
              {loading ? "…" : "Predict"}
            </button>
          </div>

          {pred && (
            <div className="mt-3 rounded-lg border border-accent/30 bg-accent/5 p-3 text-xs">
              <div className="flex justify-between">
                <span>{pred.away_team} {pred.away_win_prob != null && `${(pred.away_win_prob * 100).toFixed(0)}%`}</span>
                <span>{pred.home_team} {pred.home_win_prob != null && `${(pred.home_win_prob * 100).toFixed(0)}%`}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
                <span>Lean: <span className="text-foreground">{pred.lean}</span></span>
                <span>Conf: {pred.confidence}</span>
                <span>EV: <span className={(pred.expected_value ?? 0) >= 0 ? "text-accent" : "text-danger"}>
                  {pred.expected_value}</span></span>
                <span>Kelly: {pred.kelly_fraction != null ? `${(pred.kelly_fraction * 100).toFixed(1)}%` : "—"}</span>
              </div>
              {pred.honest_note && <div className="mt-2 text-[10px] text-muted">⚠️ {pred.honest_note}</div>}
            </div>
          )}
        </>
      )}
    </div>
  );
}

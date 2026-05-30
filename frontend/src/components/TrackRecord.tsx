"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Performance } from "@/lib/api";
import { Stat } from "./ui";

// Track Record: real graded results so you can see if the model has edge.
export default function TrackRecord({ sport }: { sport: string }) {
  const [perf, setPerf] = useState<Performance | null>(null);
  const [grading, setGrading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    api.performance().then(setPerf).catch(() => setPerf(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const gradeNow = async () => {
    setGrading(true);
    setMsg(null);
    try {
      const r = await api.gradeRun(sport);
      setMsg(`Graded ${r.graded}, skipped ${r.skipped} (unfinished/no data).`);
      load();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setGrading(false);
    }
  };

  const o = perf?.overall;
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
          Track Record
        </h2>
        <button
          onClick={gradeNow}
          disabled={grading}
          className="rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-foreground transition hover:border-accent/40 disabled:opacity-50"
        >
          {grading ? "Grading…" : "Grade finished games"}
        </button>
      </div>

      {!o || o.graded === 0 ? (
        <p className="mt-3 text-xs text-muted">
          {perf?.open_picks ?? 0} picks tracked, none graded yet. Run grading after games finish.
        </p>
      ) : (
        <>
          <div className="mt-3 grid grid-cols-3 gap-3">
            <Stat label="Record" value={`${o.wins}-${o.losses}${o.pushes ? `-${o.pushes}` : ""}`} />
            <Stat label="Hit rate" value={o.hit_rate != null ? `${o.hit_rate}%` : "—"} />
            <Stat
              label="ROI"
              value={
                o.roi != null ? (
                  <span className={o.roi >= 0 ? "text-accent" : "text-danger"}>
                    {o.roi >= 0 ? "+" : ""}
                    {o.roi}%
                  </span>
                ) : "—"
              }
            />
            <Stat
              label="Units"
              value={
                <span className={o.units >= 0 ? "text-accent" : "text-danger"}>
                  {o.units >= 0 ? "+" : ""}
                  {o.units}u
                </span>
              }
            />
            <Stat label="Avg CLV" value={o.avg_clv != null ? `${o.avg_clv}%` : "—"} />
            <Stat label="Open" value={perf?.open_picks ?? 0} />
          </div>
          {perf && Object.keys(perf.by_sport).length > 1 && (
            <div className="mt-3 space-y-1 border-t border-border pt-2 text-[11px] text-muted">
              {Object.entries(perf.by_sport).map(([s, b]) => (
                <div key={s} className="flex justify-between">
                  <span className="uppercase">{s}</span>
                  <span className="tabular-nums">
                    {b.wins}-{b.losses} · {b.hit_rate ?? "—"}% · {b.units >= 0 ? "+" : ""}
                    {b.units}u
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
      {msg && <div className="mt-2 text-[10px] text-muted">{msg}</div>}
      <p className="mt-2 text-[10px] text-muted">
        Paper-traded: every surfaced pick is graded vs the real box score. CLV needs a
        closing line (entered at grade time).
      </p>
    </div>
  );
}

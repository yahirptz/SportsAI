import type { Parlay } from "@/lib/api";
import { ConfidenceBadge } from "./ui";

// The SGP Builder output — 8 legs or an explicit NO BET (SRS §04/§07).
export default function ParlayPanel({
  parlay,
  loading,
  onBuild,
}: {
  parlay: Parlay | null;
  loading: boolean;
  onBuild: () => void;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
          Parlay Builder
        </h2>
        <button
          onClick={onBuild}
          disabled={loading}
          className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-background transition hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "Building…" : "Build SGP"}
        </button>
      </div>

      {!parlay && !loading && (
        <p className="mt-4 text-sm text-muted">
          Build a same-game parlay from the floor-verified slate.
        </p>
      )}

      {parlay?.no_bet && (
        <div className="mt-4 rounded-lg border border-danger/30 bg-danger/10 p-3">
          <div className="text-sm font-semibold text-danger">NO BET</div>
          <p className="mt-1 text-xs text-muted">{parlay.reason}</p>
        </div>
      )}

      {parlay && !parlay.no_bet && (
        <div className="mt-4">
          <div className="mb-3 flex items-center justify-between rounded-lg border border-accent/30 bg-accent/5 px-3 py-2">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted">
                Combined win prob
              </div>
              <div className="text-lg font-bold text-accent tabular-nums">
                {parlay.combined_confidence}%
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] uppercase tracking-wider text-muted">
                Recommended stake
              </div>
              <div className="text-lg font-bold tabular-nums">
                ${parlay.recommended_stake.toFixed(2)}
              </div>
            </div>
          </div>

          <ul className="divide-y divide-border">
            {parlay.legs.map((leg) => (
              <li key={leg.pick_id} className="flex items-center justify-between py-2">
                <div>
                  <div className="text-sm font-medium">{leg.player_name}</div>
                  <div className="text-xs text-muted">
                    {leg.market_label} o{leg.line} · floor {leg.floor}
                  </div>
                </div>
                <ConfidenceBadge value={leg.confidence} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

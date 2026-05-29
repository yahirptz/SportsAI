import type { Pick } from "@/lib/api";
import { ConfidenceBadge, GapBar, Stat } from "./ui";

// One floor-verified pick in the Agent Feed (SRS §07).
export default function PickCard({ pick }: { pick: Pick }) {
  const e = pick.enrichment;
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold">{pick.player_name}</div>
          <div className="text-xs text-muted">
            {pick.market_label} · o{pick.line}
            {pick.odds != null && (
              <span className="ml-1 text-muted">
                ({pick.odds > 0 ? `+${pick.odds}` : pick.odds})
              </span>
            )}
          </div>
        </div>
        <ConfidenceBadge value={pick.confidence} />
      </div>

      <div className="mt-3">
        <GapBar floor={pick.floor} line={pick.line} />
        <div className="mt-1 flex justify-between text-[10px] text-muted">
          <span>line {pick.line}</span>
          <span className="text-accent">floor {pick.floor} (+{pick.gap})</span>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        <Stat label="Avg (last-N)" value={pick.sample_average ?? "—"} />
        <Stat label="Kelly stake" value={`$${pick.kelly_stake.toFixed(2)}`} />
        <Stat
          label="Sentiment"
          value={
            <span className={e.reddit_sentiment >= 0 ? "text-accent" : "text-danger"}>
              {e.reddit_sentiment >= 0 ? "+" : ""}
              {e.reddit_sentiment.toFixed(2)}
            </span>
          }
        />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
        {e.reverse_line_movement && (
          <span className="rounded border border-accent/30 bg-accent/10 px-1.5 py-0.5 text-accent">
            sharp RLM
          </span>
        )}
        {e.public_bet_pct != null && (
          <span className="rounded border border-border bg-surface-2 px-1.5 py-0.5 text-muted">
            public {e.public_bet_pct}%
          </span>
        )}
        {!e.injury_flag && (
          <span className="rounded border border-border bg-surface-2 px-1.5 py-0.5 text-muted">
            injury check ✓
          </span>
        )}
      </div>
    </div>
  );
}

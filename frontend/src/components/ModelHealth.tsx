import type { FeedHealth } from "@/lib/api";

// Circuit-breaker status per feed (SRS §07 Model Health view).
export default function ModelHealth({ health }: { health: FeedHealth | null }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
          Model Health
        </h2>
        {health && (
          <span className="rounded border border-border bg-surface-2 px-2 py-0.5 text-[10px] text-muted">
            feed: {health.active_provider}
          </span>
        )}
      </div>

      {!health || health.feeds.length === 0 ? (
        <p className="mt-3 text-xs text-muted">No feed activity yet.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {health.feeds.map((f) => {
            const ok = f.status === "ok";
            return (
              <li key={f.source} className="flex items-center justify-between text-xs">
                <span className="text-foreground">{f.source}</span>
                <span
                  className={`inline-flex items-center gap-1.5 ${
                    ok ? "text-accent" : "text-danger"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      ok ? "bg-accent" : "bg-danger"
                    }`}
                  />
                  {f.status}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

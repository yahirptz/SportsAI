"use client";

import { useEffect, useRef, useState } from "react";
import { api, type ChatMessage, type AssistantSlip } from "@/lib/api";

const GREETING: Record<string, ChatMessage> = {
  base: {
    role: "assistant",
    content:
      "Paste a FanDuel board above, then tell me what you want — “build a 3-leg”, “is this good?”, “who's most likely?” I'll build it on the floor model and give you the honest read.",
  },
};

export default function Assistant({ sport }: { sport: string }) {
  const [board, setBoard] = useState("");
  const [showBoard, setShowBoard] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING.base]);
  const [input, setInput] = useState("");
  const [slip, setSlip] = useState<AssistantSlip | null>(null);
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const send = async (text: string) => {
    if (!text.trim() || loading) return;
    const next = [...messages, { role: "user" as const, content: text }];
    setMessages(next);
    setInput("");
    setLoading(true);
    try {
      const r = await api.assistant(
        next.filter((m) => m !== GREETING.base),
        sport,
        board,
      );
      setMessages([...next, { role: "assistant", content: r.reply }]);
      if (r.slip?.bet && !r.slip.bet.no_bet) setSlip(r.slip);
    } catch (e) {
      setMessages([...next, { role: "assistant", content: `Error: ${String(e)}` }]);
    } finally {
      setLoading(false);
    }
  };

  const quick = ["Build me a 3-leg parlay", "Give me the single safest play", "Who's most likely to hit?"];

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
      {/* Chat */}
      <div className="lg:col-span-2">
        {/* Board paste */}
        <div className="mb-3 rounded-xl border border-border bg-surface p-3">
          <button
            onClick={() => setShowBoard((s) => !s)}
            className="flex w-full items-center justify-between text-xs font-semibold uppercase tracking-wider text-muted"
          >
            <span>FanDuel board {board ? "✓" : ""}</span>
            <span>{showBoard ? "–" : "+"}</span>
          </button>
          {showBoard && (
            <textarea
              value={board}
              onChange={(e) => setBoard(e.target.value)}
              placeholder="Paste FanDuel's prop board here (any sport). Then chat below."
              className="mt-2 h-24 w-full rounded-lg border border-border bg-background p-2 font-mono text-[11px]"
            />
          )}
        </div>

        <div className="flex h-[26rem] flex-col rounded-xl border border-border bg-surface">
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "text-right" : ""}>
                <div
                  className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${
                    m.role === "user"
                      ? "bg-accent/15 text-foreground"
                      : "bg-surface-2 text-foreground/90"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {loading && <div className="text-xs text-muted">EdgeIQ is thinking…</div>}
            <div ref={endRef} />
          </div>

          <div className="border-t border-border p-2">
            <div className="mb-2 flex flex-wrap gap-1.5">
              {quick.map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  disabled={loading}
                  className="rounded-full border border-border px-2.5 py-1 text-[11px] text-muted hover:border-accent/40 disabled:opacity-50"
                >
                  {q}
                </button>
              ))}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
              className="flex gap-2"
            >
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask EdgeIQ…"
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm"
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-background disabled:opacity-50"
              >
                Send
              </button>
            </form>
          </div>
        </div>
      </div>

      {/* Slip card */}
      <aside>
        <SlipCard slip={slip} />
      </aside>
    </div>
  );
}

function SlipCard({ slip }: { slip: AssistantSlip | null }) {
  const bet = slip?.bet;
  if (!bet || bet.no_bet) {
    return (
      <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted">
        Your slip will appear here once EdgeIQ builds one.
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-accent/30 bg-accent/5 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-accent">
          {bet.leg_count}-leg slip ·{" "}
          {bet.combined_odds != null && (bet.combined_odds > 0 ? `+${bet.combined_odds}` : bet.combined_odds)}
        </h2>
        <span className="text-xs text-muted">
          model {bet.model_hit_prob}% · ${bet.recommended_stake}
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
  );
}

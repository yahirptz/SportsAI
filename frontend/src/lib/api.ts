// Typed client for the EdgeIQ FastAPI backend (SRS §06).

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Enrichment {
  injury_flag: boolean;
  perplexity_summary: string | null;
  reddit_sentiment: number;
  public_bet_pct: number | null;
  public_money_pct: number | null;
  reverse_line_movement: boolean;
}

export interface Pick {
  id: string;
  sport: string;
  game_id: string;
  player_id: string;
  player_name: string;
  market: string;
  market_label: string;
  floor: number;
  line: number;
  gap: number;
  sample_average: number | null;
  confidence: number;
  kelly_stake: number;
  odds: number | null;
  status: string;
  enrichment: Enrichment;
}

export interface ParlayLeg {
  pick_id: string;
  player_name: string;
  market_label: string;
  floor: number;
  line: number;
  confidence: number;
}

export interface Parlay {
  id: string;
  sport: string;
  game_id: string;
  legs: ParlayLeg[];
  combined_confidence: number;
  recommended_stake: number;
  no_bet: boolean;
  reason: string | null;
}

export interface SportInfo {
  sport: string;
  label: string;
  sample_window: number;
  active: boolean;
  stats: string[];
  primary_source: string;
}

export interface FeedHealthEntry {
  source: string;
  status: string;
  last_updated: number | null;
  circuit_broken_at: number | null;
  detail: string | null;
}

export interface FeedHealth {
  active_provider: string;
  feeds: FeedHealthEntry[];
}

async function getJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  sports: () => getJSON<SportInfo[]>("/api/sports"),
  picks: (sport: string) =>
    getJSON<{ sport: string; count: number; picks: Pick[] }>(`/api/picks/${sport}`),
  buildParlay: (sport: string, gameId?: string) =>
    getJSON<Parlay>("/api/parlay/build", {
      method: "POST",
      body: JSON.stringify({ sport, game_id: gameId ?? null }),
    }),
  bankroll: () => getJSON<{ balance: number; risk_profile: string }>("/api/bankroll"),
  feedHealth: () => getJSON<FeedHealth>("/api/feed/health"),
};

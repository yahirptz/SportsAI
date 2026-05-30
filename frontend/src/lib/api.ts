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
  reasoning: string | null;
}

export interface ParlayLeg {
  pick_id: string;
  player_name: string;
  market_label: string;
  floor: number;
  line: number;
  confidence: number;
  reasoning: string | null;
}

export interface UnpricedMarket {
  player: string;
  market: string;
  market_label: string;
  floor_hint: number;
}

export interface MoneylineEdge {
  side: string;
  team: string;
  odds: number;
  model_prob: number;
  implied_prob: number;
  edge: number;
  kelly_stake: number;
}

export interface Starter {
  name: string;
  era: number;
  record: string;
}

export interface TotalLean {
  pick: string;
  line: number;
  projected: number;
  diff: number;
}

export interface GameValue {
  game_id: string;
  home: string;
  away: string;
  scheduled: string | null;
  form_note: string | null;
  home_record: string;
  away_record: string;
  home_starter: Starter | null;
  away_starter: Starter | null;
  proj_home_runs: number | null;
  proj_away_runs: number | null;
  proj_total: number | null;
  proj_margin: number | null;
  total: number | null;
  total_lean: TotalLean | null;
  best: MoneylineEdge | null;
  edges: MoneylineEdge[];
  injury_notes: string[];
  note: string | null;
}

export interface GamesResponse {
  sport: string;
  count?: number;
  ml_leans?: number;
  total_leans?: number;
  model?: string;
  warning?: string;
  note?: string;
  games: GameValue[];
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
    getJSON<{ sport: string; count: number; enriched: boolean; picks: Pick[] }>(
      `/api/picks/${sport}`,
    ),
  unpriced: (sport: string) =>
    getJSON<{ sport: string; count: number; unpriced: UnpricedMarket[] }>(
      `/api/odds/unpriced/${sport}`,
    ),
  addLine: (sport: string, player: string, market: string, line: number, odds: number) =>
    getJSON<{ ok: boolean }>("/api/odds/lines", {
      method: "POST",
      body: JSON.stringify({ sport, player, market, line, odds }),
    }),
  buildParlay: (sport: string, gameId?: string) =>
    getJSON<Parlay>("/api/parlay/build", {
      method: "POST",
      body: JSON.stringify({ sport, game_id: gameId ?? null }),
    }),
  bankroll: () => getJSON<{ balance: number; risk_profile: string }>("/api/bankroll"),
  feedHealth: () => getJSON<FeedHealth>("/api/feed/health"),
  games: (sport: string) => getJSON<GamesResponse>(`/api/games/${sport}`),
  performance: () => getJSON<Performance>("/api/performance"),
  importGameLines: (sport: string, paste: string) =>
    getJSON<{ ok: boolean; imported: number }>("/api/games/lines/import", {
      method: "POST",
      body: JSON.stringify({ sport, paste }),
    }),
  floorboard: (sport: string, paste: string, mode: string, legs: number, minCushion = 0) =>
    getJSON<FloorboardResponse>("/api/floorboard", {
      method: "POST",
      body: JSON.stringify({ sport, paste, mode, legs, min_cushion: minCushion }),
    }),
  gradeRun: (sport: string) =>
    getJSON<{ graded: number; skipped: number }>("/api/grade/run", {
      method: "POST",
      body: JSON.stringify({ sport }),
    }),
};

export interface PerfBucket {
  graded: number;
  wins: number;
  losses: number;
  pushes: number;
  hit_rate: number | null;
  units: number;
  roi: number | null;
  avg_clv: number | null;
}

export interface Performance {
  open_picks: number;
  overall: PerfBucket | null;
  by_sport: Record<string, PerfBucket>;
}

export interface FloorPlay {
  player: string;
  market: string;
  market_label: string;
  threshold: number;
  line: number;
  odds: number;
  floor: number;
  hit_count: number;
  n: number;
  hit_prob: number;
  cushion: number;
}

export interface AssembledBet {
  no_bet: boolean;
  reason?: string;
  legs: FloorPlay[];
  leg_count?: number;
  combined_odds?: number;
  combined_decimal?: number;
  model_hit_prob?: number;
  recommended_stake?: number;
}

export interface FloorboardResponse {
  mode: string;
  parsed_props?: number;
  board_size?: number;
  board?: FloorPlay[];
  bet?: AssembledBet;
}

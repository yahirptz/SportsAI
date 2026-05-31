"""SportRadar feed adapter (SRS §01 — primary structured source).

Multi-sport: SportRadar issues a separate key and endpoint per sport, so the
provider builds a per-sport client lazily from settings. NBA is verified against
the live API; MLB plumbing is in place and activates as soon as an MLB key is
supplied (its stat field-paths are marked for verification against a real
response — the same care taken for NBA, where summary.json carries player stats
and boxscore.json does not).

Flow per sport:
  1. Walk back recent daily schedules to collect closed games (the window).
  2. Pick target games (today's slate; else the most recent completed matchup).
  3. For each team, read its last-N closed games' summaries and accumulate each
     player's per-stat values into a last-N log.
  4. Price each (player, stat) against the odds book; skip anything unpriced.

Responses are disk-cached (immutable history) with 429 backoff for the trial
tier. Selecting the SportRadar provider with no key for a given sport yields an
empty slate for that sport rather than an error.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Callable

import httpx

from app.config import settings
from app.feeds.base import FeedError
from app.feeds.cache import DiskCache
from app.feeds.circuit import CircuitBreaker
from app.feeds.odds import OddsBook, StaticOddsBook
from app.floor.engine import GameLog
from app.models.schemas import EnrichmentContext
from app.pipeline import PropInput
from app.sports.registry import Sport, get_config

_RATE_LIMIT_SLEEP = 1.3  # seconds between live calls (trial tier ~1 req/sec)

# SportRadar URL path segment + API version per sport (NHL is on v7).
_SPORT_PATH = {Sport.NBA: ("nba", "v8"), Sport.MLB: ("mlb", "v8"), Sport.NHL: ("nhl", "v7")}


def _endpoint_for(sport: Sport) -> tuple[str | None, str | None]:
    """Return (base_url, api_key) for a sport, or (None, None) if unsupported."""
    if sport not in _SPORT_PATH:
        return None, None
    path, version = _SPORT_PATH[sport]
    base = f"https://api.sportradar.com/{path}/{settings.sportradar_access}/{version}/en"
    key = {
        Sport.NBA: settings.sportradar_api_key,
        Sport.MLB: settings.sportradar_mlb_api_key,
        Sport.NHL: settings.sportradar_api_key,  # multi-sport trial key covers NHL
    }.get(sport)
    return base, key


# --- Per-sport stat extraction ----------------------------------------------
# Each extractor takes a player's full record (from summary.json) and returns a
# numeric stat value. NBA paths are verified live. MLB paths are best-effort and
# MUST be confirmed against a real MLB summary response before trusting live
# output (defensive .get chains mean an unverified path yields 0, not a crash).


def _nba(key: str) -> Callable[[dict], float]:
    return lambda p: float((p.get("statistics") or {}).get(key, 0) or 0)


def _nba_combo(*keys: str) -> Callable[[dict], float]:
    return lambda p: float(sum((p.get("statistics") or {}).get(k, 0) or 0 for k in keys))


def _mlb_hit(*path: str) -> Callable[[dict], float]:
    def extract(p: dict) -> float:
        node = (p.get("statistics") or {}).get("hitting", {}).get("overall", {})
        for seg in path:
            node = node.get(seg, {}) if isinstance(node, dict) else {}
        return float(node if isinstance(node, (int, float)) else 0)

    return extract


def _mlb_pitch(*path: str) -> Callable[[dict], float]:
    def extract(p: dict) -> float:
        node = (p.get("statistics") or {}).get("pitching", {}).get("overall", {})
        for seg in path:
            node = node.get(seg, {}) if isinstance(node, dict) else {}
        return float(node if isinstance(node, (int, float)) else 0)

    return extract


def _nhl(key: str) -> Callable[[dict], float]:
    # NHL skater stats live under statistics.total. (Goalie saves are elsewhere
    # and not wired yet.)
    return lambda p: float((p.get("statistics") or {}).get("total", {}).get(key, 0) or 0)


EXTRACTORS: dict[Sport, dict[str, Callable[[dict], float]]] = {
    Sport.NBA: {
        "pts": _nba("points"),
        "reb": _nba("rebounds"),
        "ast": _nba("assists"),
        "fg3m": _nba("three_points_made"),
        "pra": _nba_combo("points", "rebounds", "assists"),
        "pa": _nba_combo("points", "assists"),
        "ra": _nba_combo("rebounds", "assists"),
    },
    # MLB field-paths are provisional — verify against a live MLB summary.json.
    Sport.MLB: {
        "hits": _mlb_hit("onbase", "h"),
        "rbi": _mlb_hit("rbi"),
        "runs": _mlb_hit("runs", "total"),
        "tb": _mlb_hit("onbase", "tb"),
        "bb": _mlb_hit("onbase", "bb"),
        "k_pitcher": _mlb_pitch("outs", "ktotal"),
    },
    Sport.NHL: {
        "shots": _nhl("shots"),   # shots on goal
        "pts": _nhl("points"),    # goals + assists
        "goals": _nhl("goals"),
        "ast": _nhl("assists"),
        # "saves" (goalie) is not wired — it lives outside statistics.total.
    },
}


class SportRadarStats:
    """Client over the SportRadar endpoints for one sport, with disk caching."""

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(timeout=timeout)
        self._cache = DiskCache()

    def _get(self, path: str, *, max_retries: int = 4, fresh: bool = False) -> dict:
        cache_key = f"{self.base_url}/{path}"
        if not fresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        url = f"{self.base_url}/{path.lstrip('/')}"
        backoff = 2.0
        for _ in range(max_retries):
            resp = self._client.get(url, params={"api_key": self.api_key})
            if resp.status_code == 429:
                time.sleep(float(resp.headers.get("Retry-After", backoff)))
                backoff = min(backoff * 2, 30)
                continue
            resp.raise_for_status()
            data = resp.json()
            self._cache.set(cache_key, data)
            time.sleep(_RATE_LIMIT_SLEEP)
            return data
        raise FeedError(f"SportRadar rate-limited after {max_retries} retries: {path}")

    def schedule(self, day: date) -> dict:
        return self._get(f"games/{day.year}/{day.month:02d}/{day.day:02d}/schedule.json")

    def summary(self, game_id: str, *, fresh: bool = False) -> dict:
        return self._get(f"games/{game_id}/summary.json", fresh=fresh)

    def recent_games(self, lookback_days: int) -> list[dict]:
        games: list[dict] = []
        day = date.today()
        for _ in range(lookback_days):
            for g in self.schedule(day).get("games", []):
                g["_date"] = str(day)
                games.append(g)
            day -= timedelta(days=1)
        return games


def _team_ids(game: dict, sport: Sport) -> tuple[str, str]:
    # MLB schedule uses home_team/away_team string ids; NBA uses home/away dicts.
    if sport is Sport.MLB:
        return game.get("home_team", ""), game.get("away_team", "")
    return game.get("home", {}).get("id", ""), game.get("away", {}).get("id", "")


def _player_name(p: dict) -> str:
    return p.get("full_name") or f"{p.get('preferred_name', '')} {p.get('last_name', '')}".strip()


def team_rest_days(window: list[dict], team_id: str, sport: Sport, ref_date: str) -> int | None:
    """Days since this team's last completed game before ``ref_date`` (fatigue).

    Adapted from kyleskom's Add_Days_Rest: clamp to [0, 9]; returns None if there
    is no prior game in the window.
    """
    if not ref_date:
        return None
    prior = sorted(
        (g["_date"] for g in window
         if g.get("status") == "closed" and team_id in _team_ids(g, sport) and g["_date"] < ref_date),
        reverse=True,
    )
    if not prior:
        return None
    last, ref = date.fromisoformat(prior[0]), date.fromisoformat(ref_date)
    return max(0, min((ref - last).days, 9))


def _player_lines(summary: dict, team_id: str, sport: Sport) -> list[dict]:
    # MLB nests teams under a top-level "game" key; NBA keeps them at the root.
    root = summary.get("game", summary) if sport is Sport.MLB else summary
    for side in ("home", "away"):
        if root.get(side, {}).get("id") == team_id:
            return root[side].get("players", [])
    return []


class SportRadarFeedProvider:
    """Builds the prop slate for any supported sport from real logs + odds book."""

    name = "sportradar"

    def __init__(self, odds: OddsBook) -> None:
        self._odds = odds
        self._clients: dict[Sport, SportRadarStats] = {}
        self._breaker = CircuitBreaker("sportradar")

    def _client(self, sport: Sport) -> SportRadarStats | None:
        if sport in self._clients:
            return self._clients[sport]
        base, key = _endpoint_for(sport)
        if not base or not key:
            return None
        client = SportRadarStats(base, key)
        self._clients[sport] = client
        return client

    def slate(self, sport: Sport) -> list[PropInput]:
        client = self._client(sport)
        if client is None:
            return []  # no key for this sport
        return self._breaker.call(lambda: self._build_slate(sport, client))

    def candidates(self, sport: Sport) -> list[dict]:
        client = self._client(sport)
        if client is None:
            return []
        config = get_config(sport)
        bettable = [s.key for s in config.stats if not s.ceiling_prop]
        window = client.recent_games(settings.sportradar_lookback_days)
        rows, seen = [], set()
        for game in self._target_games(window):
            for team_id in _team_ids(game, sport):
                if not team_id:
                    continue
                for rec in self._team_last_n_logs(sport, client, window, team_id, config.sample_window).values():
                    for stat_key in bettable:
                        vals = rec["stats"].get(stat_key, [])
                        if len(vals) < config.sample_window or (rec["name"], stat_key) in seen:
                            continue
                        seen.add((rec["name"], stat_key))
                        spec = config.stat(stat_key)
                        rows.append({
                            "player": rec["name"], "market": stat_key,
                            "market_label": spec.label if spec else stat_key,
                            "floor_hint": min(vals),
                        })
        return rows

    def _target_games(self, window: list[dict]) -> list[dict]:
        today = str(date.today())
        upcoming = [g for g in window if g["_date"] == today and g.get("status") != "closed"]
        if upcoming:
            return upcoming[:2]
        return [g for g in window if g.get("status") == "closed"][:1]

    def _team_last_n_logs(
        self, sport: Sport, client: SportRadarStats, window: list[dict], team_id: str, n: int
    ) -> dict[str, dict]:
        extractors = EXTRACTORS.get(sport, {})
        team_games = [
            g for g in window if g.get("status") == "closed" and team_id in _team_ids(g, sport)
        ]
        team_games.sort(key=lambda g: g["_date"], reverse=True)
        players: dict[str, dict] = {}
        for game in team_games[:n]:
            summary = client.summary(game["id"])
            for p in _player_lines(summary, team_id, sport):
                pid = p.get("id")
                if not pid:
                    continue
                rec = players.setdefault(pid, {"name": _player_name(p), "stats": {}})
                for stat_key, extract in extractors.items():
                    rec["stats"].setdefault(stat_key, []).append(extract(p))
        return players

    def _build_slate(self, sport: Sport, client: SportRadarStats) -> list[PropInput]:
        config = get_config(sport)
        bettable = [s.key for s in config.stats if not s.ceiling_prop]
        window = client.recent_games(settings.sportradar_lookback_days)
        props: list[PropInput] = []
        for game in self._target_games(window):
            for team_id in _team_ids(game, sport):
                if not team_id:
                    continue
                rest = team_rest_days(window, team_id, sport, game.get("_date", ""))
                logs_by_player = self._team_last_n_logs(
                    sport, client, window, team_id, config.sample_window
                )
                for pid, rec in logs_by_player.items():
                    name = rec["name"]
                    for stat_key in bettable:
                        priced = self._odds.line_for(sport.value, name, stat_key)
                        if priced is None:
                            continue
                        line, odds = priced
                        values = rec["stats"].get(stat_key, [])
                        if not values:
                            continue
                        logs = [
                            GameLog(game_id=f"{pid}-{i}", game_date="", value=v)
                            for i, v in enumerate(values)
                        ]
                        props.append(
                            PropInput(
                                game_id=game["id"], player_id=pid, player_name=name,
                                stat_key=stat_key, line=line, odds=odds, logs=logs,
                                enrichment=EnrichmentContext(rest_days=rest),
                            )
                        )
        return props


def build_sportradar_provider(odds: OddsBook | None = None) -> SportRadarFeedProvider:
    """Construct the multi-sport SportRadar provider.

    Raises ``FeedError`` only if no sport has a key configured at all, so the app
    can degrade to the sample feed. A sport without a key simply yields an empty
    slate.
    """
    if not (settings.sportradar_api_key or settings.sportradar_mlb_api_key):
        raise FeedError("SportRadar selected but no sport key is configured.")
    return SportRadarFeedProvider(odds or _load_default_odds())


def _load_default_odds() -> OddsBook:
    from pathlib import Path

    path = Path(settings.odds_lines_path)
    return StaticOddsBook.from_json(path) if path.exists() else StaticOddsBook()

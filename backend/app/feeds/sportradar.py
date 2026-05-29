"""SportRadar feed adapter (SRS §01 — primary structured source).

Pulls real NBA player game logs from the SportRadar NBA v8 API and pairs them
with an :class:`~app.feeds.odds.OddsBook` to build the prop slate. Every network
call runs under a :class:`~app.feeds.circuit.CircuitBreaker`, so a SportRadar
outage or staleness trips the breaker and hard-stops downstream agents (SRS §01).

Player game logs are assembled from the **game summary** endpoint (which carries
per-player statistics). The flow:

  1. Walk back recent daily schedules to collect closed games (the window).
  2. Pick target games (today's slate; else the most recent completed matchup).
  3. For each team, read its last-N closed games' summaries and accumulate each
     player's per-stat values into a last-N log.
  4. Price each (player, stat) against the odds book; skip anything unpriced.

Responses are disk-cached (historical data is immutable) to respect the trial
tier's rate limit. Requires ``EDGEIQ_SPORTRADAR_API_KEY``; without it,
:func:`build_sportradar_provider` raises ``FeedError`` and the app degrades to
the sample feed.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

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

# Map our stat keys → how to derive them from a SportRadar player statistics dict.
_STAT_EXTRACTORS = {
    "pts": lambda s: s.get("points", 0),
    "reb": lambda s: s.get("rebounds", 0),
    "ast": lambda s: s.get("assists", 0),
    "fg3m": lambda s: s.get("three_points_made", 0),
    "pra": lambda s: s.get("points", 0) + s.get("rebounds", 0) + s.get("assists", 0),
    "pa": lambda s: s.get("points", 0) + s.get("assists", 0),
    "ra": lambda s: s.get("rebounds", 0) + s.get("assists", 0),
}

_RATE_LIMIT_SLEEP = 1.3  # seconds between live calls (trial tier ~1 req/sec)


class SportRadarStats:
    """Client over the SportRadar NBA v8 endpoints, with disk caching."""

    def __init__(self, api_key: str, base_url: str, *, timeout: float = 15.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)
        self._cache = DiskCache()

    def _get(self, path: str, *, max_retries: int = 4) -> dict:
        cached = self._cache.get(path)
        if cached is not None:
            return cached  # immutable historical data — never refetch
        url = f"{self.base_url}/{path.lstrip('/')}"
        backoff = 2.0
        for attempt in range(max_retries):
            resp = self._client.get(url, params={"api_key": self.api_key})
            if resp.status_code == 429:  # trial rate cap — honor Retry-After
                wait = float(resp.headers.get("Retry-After", backoff))
                time.sleep(wait)
                backoff = min(backoff * 2, 30)
                continue
            resp.raise_for_status()
            data = resp.json()
            self._cache.set(path, data)
            time.sleep(_RATE_LIMIT_SLEEP)  # space out subsequent live calls
            return data
        raise FeedError(f"SportRadar rate-limited after {max_retries} retries: {path}")

    def schedule(self, day: date) -> dict:
        return self._get(f"games/{day.year}/{day.month:02d}/{day.day:02d}/schedule.json")

    def summary(self, game_id: str) -> dict:
        return self._get(f"games/{game_id}/summary.json")

    def recent_games(self, lookback_days: int) -> list[dict]:
        """Walk back daily schedules; return games (closed + upcoming) in window."""
        games: list[dict] = []
        day = date.today()
        for _ in range(lookback_days):
            for g in self.schedule(day).get("games", []):
                g["_date"] = str(day)
                games.append(g)
            day -= timedelta(days=1)
        return games

    def close(self) -> None:
        self._client.close()


def _team_ids(game: dict) -> tuple[str, str]:
    return game.get("home", {}).get("id", ""), game.get("away", {}).get("id", "")


def _player_lines(summary: dict, team_id: str) -> list[dict]:
    """Return the player stat lines for ``team_id`` from a game summary."""
    for side in ("home", "away"):
        if summary.get(side, {}).get("id") == team_id:
            return summary[side].get("players", [])
    return []


class SportRadarFeedProvider:
    """Builds the prop slate from real SportRadar logs + an odds book."""

    name = "sportradar"

    def __init__(self, stats: SportRadarStats, odds: OddsBook) -> None:
        self._stats = stats
        self._odds = odds
        self._breaker = CircuitBreaker("sportradar")

    def slate(self, sport: Sport) -> list[PropInput]:
        if sport is not Sport.NBA:
            return []  # this adapter currently covers NBA
        return self._breaker.call(lambda: self._build_slate(sport))

    def _target_games(self, window: list[dict]) -> list[dict]:
        """Prefer today's scheduled games; else the most recent completed game."""
        today = str(date.today())
        upcoming = [g for g in window if g["_date"] == today and g.get("status") != "closed"]
        if upcoming:
            return upcoming[:2]
        closed = [g for g in window if g.get("status") == "closed"]
        return closed[:1]

    def _team_last_n_logs(
        self, window: list[dict], team_id: str, n: int
    ) -> dict[str, dict]:
        """Accumulate each player's last-N per-stat values for one team.

        Returns ``{player_id: {"name": str, "stats": {stat_key: [values]}}}`` with
        values ordered most-recent-first.
        """
        team_games = [
            g for g in window
            if g.get("status") == "closed" and team_id in _team_ids(g)
        ]
        team_games.sort(key=lambda g: g["_date"], reverse=True)

        players: dict[str, dict] = {}
        for game in team_games[:n]:
            summary = self._stats.summary(game["id"])
            for p in _player_lines(summary, team_id):
                pid = p.get("id")
                stats = p.get("statistics") or {}
                if not pid or not stats:
                    continue
                rec = players.setdefault(pid, {"name": p.get("full_name", ""), "stats": {}})
                for stat_key, extract in _STAT_EXTRACTORS.items():
                    rec["stats"].setdefault(stat_key, []).append(float(extract(stats)))
        return players

    def _build_slate(self, sport: Sport) -> list[PropInput]:
        config = get_config(sport)
        bettable = [s.key for s in config.stats if not s.ceiling_prop]
        window = self._stats.recent_games(settings.sportradar_lookback_days)

        props: list[PropInput] = []
        for game in self._target_games(window):
            for team_id in _team_ids(game):
                if not team_id:
                    continue
                logs_by_player = self._team_last_n_logs(window, team_id, config.sample_window)
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
                                game_id=game["id"],
                                player_id=pid,
                                player_name=name,
                                stat_key=stat_key,
                                line=line,
                                odds=odds,
                                logs=logs,
                                enrichment=EnrichmentContext(),
                            )
                        )
        return props


def build_sportradar_provider(odds: OddsBook | None = None) -> SportRadarFeedProvider:
    """Construct the SportRadar provider, or raise ``FeedError`` if unconfigured."""
    if not settings.sportradar_api_key:
        raise FeedError("SportRadar selected but EDGEIQ_SPORTRADAR_API_KEY is not set.")
    stats = SportRadarStats(settings.sportradar_api_key, settings.sportradar_base_url)
    if odds is None:
        odds = _load_default_odds()
    return SportRadarFeedProvider(stats, odds)


def _load_default_odds() -> OddsBook:
    """Load operator-supplied lines from data/lines.json if present."""
    from pathlib import Path

    path = Path(settings.odds_lines_path)
    if path.exists():
        return StaticOddsBook.from_json(path)
    return StaticOddsBook()

"""SportRadar feed adapter (SRS §01 — primary structured source).

Pulls real NBA player game logs from the SportRadar NBA v8 API and pairs them
with an :class:`~app.feeds.odds.OddsBook` to build the prop slate. Every network
call runs under a :class:`~app.feeds.circuit.CircuitBreaker`, so a SportRadar
outage or staleness trips the breaker and hard-stops downstream agents (SRS §01).

Game logs are assembled by walking recent daily schedules and reading each
boxscore — SportRadar exposes per-game player lines via the boxscore endpoint.
The walk-back is bounded by ``EDGEIQ_SPORTRADAR_LOOKBACK_DAYS``.

Requires ``EDGEIQ_SPORTRADAR_API_KEY``. Without it, :func:`build_sportradar_provider`
raises ``FeedError`` and the app degrades to the sample feed.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx

from app.config import settings
from app.feeds.base import FeedError
from app.feeds.circuit import CircuitBreaker
from app.feeds.odds import OddsBook, StaticOddsBook
from app.floor.engine import GameLog
from app.models.schemas import EnrichmentContext
from app.pipeline import PropInput
from app.sports.registry import Sport, get_config

# Map our stat keys → how to derive them from a SportRadar boxscore stat line.
# Values are functions over the player's `statistics` dict.
_STAT_EXTRACTORS = {
    "pts": lambda s: s.get("points", 0),
    "reb": lambda s: s.get("rebounds", 0),
    "ast": lambda s: s.get("assists", 0),
    "fg3m": lambda s: s.get("three_points_made", 0),
    "pra": lambda s: s.get("points", 0) + s.get("rebounds", 0) + s.get("assists", 0),
    "pa": lambda s: s.get("points", 0) + s.get("assists", 0),
    "ra": lambda s: s.get("rebounds", 0) + s.get("assists", 0),
}


class SportRadarStats:
    """Thin client over the SportRadar NBA v8 endpoints used by EdgeIQ."""

    def __init__(self, api_key: str, base_url: str, *, timeout: float = 10.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = self._client.get(url, params={"api_key": self.api_key})
        resp.raise_for_status()
        return resp.json()

    def schedule(self, day: date) -> dict:
        return self._get(f"games/{day.year}/{day.month:02d}/{day.day:02d}/schedule.json")

    def boxscore(self, game_id: str) -> dict:
        return self._get(f"games/{game_id}/boxscore.json")

    def todays_games(self, day: date | None = None) -> list[dict]:
        day = day or date.today()
        return self.schedule(day).get("games", [])

    def last_n_logs(self, player_id: str, stat_key: str, n: int) -> list[GameLog]:
        """Walk recent daily schedules and collect a player's last-N stat values."""
        extractor = _STAT_EXTRACTORS.get(stat_key)
        if extractor is None:
            return []
        logs: list[GameLog] = []
        day = date.today()
        for _ in range(settings.sportradar_lookback_days):
            day -= timedelta(days=1)
            for game in self.schedule(day).get("games", []):
                if game.get("status") != "closed":
                    continue
                box = self.boxscore(game["id"])
                for team in (box.get("home", {}), box.get("away", {})):
                    for player in team.get("players", []):
                        if player.get("id") != player_id:
                            continue
                        stats = player.get("statistics", {})
                        logs.append(
                            GameLog(
                                game_id=game["id"],
                                game_date=str(day),
                                value=float(extractor(stats)),
                            )
                        )
            if len(logs) >= n:
                break
        return logs[:n]

    def close(self) -> None:
        self._client.close()


class SportRadarFeedProvider:
    """Builds the prop slate from real SportRadar logs + an odds book."""

    name = "sportradar"

    def __init__(self, stats: SportRadarStats, odds: OddsBook) -> None:
        self._stats = stats
        self._odds = odds
        self._breaker = CircuitBreaker("sportradar")

    def slate(self, sport: Sport) -> list[PropInput]:
        if sport is not Sport.NBA:
            # This adapter currently covers NBA; other sports use their own feeds.
            return []
        return self._breaker.call(lambda: self._build_slate(sport))

    def _build_slate(self, sport: Sport) -> list[PropInput]:
        config = get_config(sport)
        bettable = [s.key for s in config.stats if not s.ceiling_prop]
        props: list[PropInput] = []

        for game in self._stats.todays_games():
            game_id = game["id"]
            for team in (game.get("home", {}), game.get("away", {})):
                for player in team.get("players", []) or []:
                    pid, pname = player.get("id"), player.get("full_name", "")
                    if not pid:
                        continue
                    for stat_key in bettable:
                        priced = self._odds.line_for(sport.value, pid, stat_key)
                        if priced is None:
                            continue  # no line → can't bet this market
                        line, odds = priced
                        logs = self._stats.last_n_logs(pid, stat_key, config.sample_window)
                        if not logs:
                            continue
                        props.append(
                            PropInput(
                                game_id=game_id,
                                player_id=pid,
                                player_name=pname,
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
        raise FeedError(
            "SportRadar selected but EDGEIQ_SPORTRADAR_API_KEY is not set."
        )
    stats = SportRadarStats(settings.sportradar_api_key, settings.sportradar_base_url)
    return SportRadarFeedProvider(stats, odds or StaticOddsBook())

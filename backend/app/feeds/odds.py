"""Odds source (SRS §01 — FanDuel / DraftKings / OddsJam lines).

SportRadar supplies game logs, not betting lines, so a provider pairs it with an
odds source. The OddsJam / FanDuel adapters land in a later phase; until then a
:class:`StaticOddsBook` supplies operator-supplied lines (copied from a real
sportsbook) so the floor model can run against real game logs with real prices.

Lines are keyed by player **name** + market, because that is how an operator
reads them off a book — SportRadar's player ids are opaque UUIDs not known ahead
of time. Names are normalised (case/space-insensitive) on both sides.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


def _norm(name: str) -> str:
    return " ".join(name.lower().split())


class OddsBook(Protocol):
    """Returns the current line + American odds for a player/market."""

    name: str

    def line_for(self, sport: str, player_name: str, market: str) -> tuple[float, int] | None:
        ...


class StaticOddsBook:
    """A fixed line book keyed by (sport, normalised player name, market).

    Returns ``None`` for any market it has no line for, so the provider skips
    props it cannot price.
    """

    name = "static"

    def __init__(self, lines: dict[tuple[str, str, str], tuple[float, int]] | None = None) -> None:
        self._lines: dict[tuple[str, str, str], tuple[float, int]] = {}
        for (sport, player, market), val in (lines or {}).items():
            self._lines[(sport, _norm(player), market)] = val

    def set_line(self, sport: str, player_name: str, market: str, line: float, odds: int) -> None:
        self._lines[(sport, _norm(player_name), market)] = (line, odds)

    def line_for(self, sport: str, player_name: str, market: str) -> tuple[float, int] | None:
        return self._lines.get((sport, _norm(player_name), market))

    def __len__(self) -> int:
        return len(self._lines)

    @classmethod
    def from_json(cls, path: str | Path) -> "StaticOddsBook":
        """Load lines from a JSON file.

        Format:
            { "nba": { "Victor Wembanyama": { "pts": [22.5, -115], "reb": [10.5, -110] } } }
        """
        book = cls()
        data = json.loads(Path(path).read_text())
        for sport, players in data.items():
            if sport.startswith("_") or not isinstance(players, dict):
                continue  # skip comment / metadata keys
            for player, markets in players.items():
                if player.startswith("_") or not isinstance(markets, dict):
                    continue
                for market, (line, odds) in markets.items():
                    book.set_line(sport, player, market, float(line), int(odds))
        return book

"""Odds source (SRS §01 — FanDuel / DraftKings / OddsJam lines).

SportRadar supplies game logs, not betting lines, so a provider pairs it with an
odds source. The OddsJam / FanDuel adapters land in a later phase; until then a
:class:`StaticOddsBook` supplies operator-supplied lines so the floor model can
run against real game logs with realistic prices.
"""

from __future__ import annotations

from typing import Protocol


class OddsLine(Protocol):
    line: float
    odds: int


class OddsBook(Protocol):
    """Returns the current line + American odds for a player/market."""

    name: str

    def line_for(self, sport: str, player_id: str, market: str) -> tuple[float, int] | None:
        ...


class StaticOddsBook:
    """A fixed line book keyed by (sport, player_id, market).

    Use to bridge real SportRadar game logs with known lines before the live
    odds feed is wired. Returns ``None`` for any market it has no line for, so
    the provider can skip props it cannot price.
    """

    name = "static"

    def __init__(self, lines: dict[tuple[str, str, str], tuple[float, int]] | None = None) -> None:
        self._lines = lines or {}

    def set_line(self, sport: str, player_id: str, market: str, line: float, odds: int) -> None:
        self._lines[(sport, player_id, market)] = (line, odds)

    def line_for(self, sport: str, player_id: str, market: str) -> tuple[float, int] | None:
        return self._lines.get((sport, player_id, market))

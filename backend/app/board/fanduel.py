"""Parse a pasted FanDuel tiered player-prop board.

FanDuel lists props as threshold tiers ("To Score 20+ Points", "3+ Made
Threes", "To Record 6+ Rebounds/Assists"), each tier showing players + American
odds, grouped into per-game cards ended by a time stamp ("Sat 8:10pm ET").

A tier "X+" is an OVER on line X-0.5. We capture points / rebounds / assists /
made-threes and ignore non-floor markets (first basket, team to score, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# market header -> our stat key
_MARKET_PATTERNS = [
    (re.compile(r"To Score (\d+)\+ Points", re.I), "pts"),
    (re.compile(r"(\d+)\+ Made Threes", re.I), "fg3m"),
    (re.compile(r"To Record (\d+)\+ Rebounds", re.I), "reb"),
    (re.compile(r"To Record (\d+)\+ Assists", re.I), "ast"),
]
_TIME_RE = re.compile(r"^[A-Z][a-z]{2}\s+\d{1,2}:\d{2}(am|pm)\s+ET$")
_ODDS_RE = re.compile(r"^[+-]\d+$")
_NOISE = {"more wagers", "show more", "tap a player name or icon for stats and more betting options"}

_LABELS = {"pts": "Points", "reb": "Rebounds", "ast": "Assists", "fg3m": "Made Threes"}


@dataclass
class ParsedProp:
    player: str
    market: str       # pts | reb | ast | fg3m
    threshold: int    # e.g. 20  (the "X+")
    line: float       # threshold - 0.5 (over line)
    odds: int
    game_time: str | None

    @property
    def market_label(self) -> str:
        return f"{self.threshold}+ {_LABELS[self.market]}"


def parse_fanduel(text: str) -> list[ParsedProp]:
    props: list[ParsedProp] = []
    market: str | None = None
    threshold: int | None = None
    pending: list[tuple[str, str, int, int]] = []  # (player, market, threshold, odds)
    pending_player: str | None = None

    def flush(game_time: str | None) -> None:
        for player, mk, thr, odds in pending:
            props.append(ParsedProp(player, mk, thr, thr - 0.5, odds, game_time))
        pending.clear()

    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.lower() in _NOISE:
            continue

        matched_header = False
        for pat, mk in _MARKET_PATTERNS:
            m = pat.match(s)
            if m:
                market, threshold = mk, int(m.group(1))
                pending_player = None
                matched_header = True
                break
        if matched_header:
            continue

        if _TIME_RE.match(s):
            flush(s)
            pending_player = None
            continue

        if _ODDS_RE.match(s):
            if pending_player and market and threshold is not None:
                pending.append((pending_player, market, threshold, int(s)))
            pending_player = None
            continue

        # Otherwise it's a player name (or a category divider we don't track).
        # A divider resets market so its players aren't captured.
        if s in ("Quick Bets", "First Basket", "Method Of First Basket",
                 "Team to Score First", "Made 3s", "Rebounds", "Assists"):
            market = threshold = None
            pending_player = None
            continue
        pending_player = s

    flush(None)  # any trailing card without a parsed timestamp
    return props

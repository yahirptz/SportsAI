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

# market header phrase -> our stat key. Matched with re.search, so a "To
# Record"/"To Score" prefix is optional and both sports' boards are handled.
_MARKET_PATTERNS = [
    # NBA
    (re.compile(r"(\d+)\+ Points", re.I), "pts"),
    (re.compile(r"(\d+)\+ Made Threes", re.I), "fg3m"),
    (re.compile(r"(\d+)\+ Rebounds", re.I), "reb"),
    (re.compile(r"(\d+)\+ Assists", re.I), "ast"),
    # MLB (order matters: check Total Bases before a bare "Bases")
    (re.compile(r"(\d+)\+ Total Bases", re.I), "tb"),
    (re.compile(r"(\d+)\+ Hits", re.I), "hits"),
    (re.compile(r"(\d+)\+ RBI", re.I), "rbi"),
    (re.compile(r"(\d+)\+ Runs(?!\s+Bat)", re.I), "runs"),  # not "Runs Batted In"
    (re.compile(r"(\d+)\+ Strikeouts", re.I), "k_pitcher"),
    (re.compile(r"(\d+)\+ Walks", re.I), "bb"),
]
_TIME_RE = re.compile(r"^[A-Z][a-z]{2}\s+\d{1,2}:\d{2}(am|pm)\s+ET$")
_ODDS_RE = re.compile(r"^[+-]\d+$")
_NOISE = {"more wagers", "show more", "tap a player name or icon for stats and more betting options"}

_LABELS = {
    "pts": "Points", "reb": "Rebounds", "ast": "Assists", "fg3m": "Made Threes",
    "hits": "Hits", "tb": "Total Bases", "rbi": "RBI", "runs": "Runs",
    "k_pitcher": "Strikeouts", "bb": "Walks",
}


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
            m = pat.search(s)
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
                 "Team to Score First", "Made 3s", "Rebounds", "Assists",
                 "Hits", "Total Bases", "RBIs", "Runs", "Strikeouts",
                 "Pitcher Strikeouts", "Walks", "Stolen Bases", "Pitching", "Batting"):
            market = threshold = None
            pending_player = None
            continue
        pending_player = s

    flush(None)  # any trailing card without a parsed timestamp
    return props


_NUM_RE = re.compile(r"^[+-]\d+(\.\d+)?$")
_OU_RE = re.compile(r"^[OU]\s+([\d.]+)$")
_GAME_NOISE = {"spread", "money", "total", "stats", "more wagers", "show more", ""}


def parse_fanduel_games(text: str) -> list[dict]:
    """Parse FanDuel's game-line block (spread / moneyline / total).

    Per game the columns come as: away spread, away spread-odds, away ML,
    total(O), over-odds, home spread, home spread-odds, home ML, total(U),
    under-odds — preceded by the two team names and ended by a time stamp.
    Returns dicts with away/home + moneylines + total.
    """
    games: list[dict] = []
    teams: list[str] = []
    nums: list[str] = []

    def flush() -> None:
        # Need 2 teams and the full 10-token numeric sequence.
        if len(teams) >= 2 and len(nums) >= 8:
            total = None
            for tok in nums:
                m = _OU_RE.match(tok)
                if m:
                    total = float(m.group(1))
                    break
            try:
                away_ml, home_ml = int(float(nums[2])), int(float(nums[7]))
                # Teams are the two alpha lines immediately before the numbers
                # (skips page headers like "NBA").
                games.append({"away": teams[-2], "home": teams[-1],
                              "away_ml": away_ml, "home_ml": home_ml, "total": total})
            except (ValueError, IndexError):
                pass
        teams.clear()
        nums.clear()

    for raw in text.splitlines():
        s = raw.strip()
        low = s.lower()
        if not s or low in _GAME_NOISE:
            continue
        if _TIME_RE.match(s):
            flush()
            continue
        if _NUM_RE.match(s) or _OU_RE.match(s):
            nums.append(s)
        elif not s.startswith("+") and not s.startswith("-"):
            teams.append(s)  # a team name
    flush()
    return games


"""Floor board + configurable bet builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.board.fanduel import ParsedProp
from app.config import settings
from app.feeds.sportradar import EXTRACTORS, SportRadarStats, _endpoint_for, _team_ids
from app.games.model import american_to_decimal
from app.sports.registry import Sport

FORM_GAMES = 6
FORM_LOOKBACK = 20


@dataclass
class FloorPlay:
    player: str
    market: str
    market_label: str
    threshold: int
    line: float
    odds: int
    floor: float          # worst game in the window
    hit_count: int        # games clearing the threshold
    n: int                # games in sample
    hit_prob: float       # Laplace-smoothed hit rate
    cushion: float        # floor - line

    def as_dict(self) -> dict:
        return self.__dict__.copy()


_PLAYABLE = {"scheduled", "inprogress", "created", "halftime"}


def _find_target_game(stats: SportRadarStats) -> dict | None:
    # Skip "unnecessary"/"closed"/"cancelled" — we want a real upcoming game.
    for i in range(4):
        d = date.today() + timedelta(days=i)
        for g in stats.schedule(d).get("games", []):
            if g.get("status") in _PLAYABLE:
                return g
    return None


def get_game_floors(sport: Sport, n: int = FORM_GAMES) -> dict[str, dict[str, list[int]]]:
    """{player_name: {stat: [last-n values]}} for the next game's two rosters."""
    base, key = _endpoint_for(sport)
    if not base or not key:
        return {}
    stats = SportRadarStats(base, key)
    target = _find_target_game(stats)
    if not target:
        return {}
    window = stats.recent_games(FORM_LOOKBACK)
    ex = EXTRACTORS.get(sport, {})
    floors: dict[str, dict[str, list[int]]] = {}
    for team_id in _team_ids(target, sport):
        if not team_id:
            continue
        games = [g for g in window if g.get("status") == "closed" and team_id in _team_ids(g, sport)]
        games.sort(key=lambda g: g["_date"], reverse=True)
        for g in games[:n]:
            summary = stats.summary(g["id"])
            root = summary.get("game", summary) if sport is Sport.MLB else summary
            for side in ("home", "away"):
                if root.get(side, {}).get("id") != team_id:
                    continue
                for p in root[side].get("players", []) or []:
                    name = p.get("full_name") or f"{p.get('preferred_name','')} {p.get('last_name','')}".strip()
                    rec = floors.setdefault(name, {})
                    for stat, extract in ex.items():
                        rec.setdefault(stat, []).append(int(extract(p)))
    return floors


def build_floor_board(sport: Sport, props: list[ParsedProp], n: int = FORM_GAMES) -> list[FloorPlay]:
    """Keep only tiers the player cleared in ALL n recent games, ranked best-first."""
    floors = get_game_floors(sport, n)
    plays: list[FloorPlay] = []
    for prop in props:
        rec = floors.get(prop.player)
        if not rec or prop.market not in rec:
            continue
        vals = rec[prop.market]
        if len(vals) < n:
            continue
        hit = sum(1 for v in vals if v >= prop.threshold)
        if hit < n:  # floor model: must have cleared the tier in every game
            continue
        plays.append(FloorPlay(
            player=prop.player, market=prop.market, market_label=prop.market_label,
            threshold=prop.threshold, line=prop.line, odds=prop.odds,
            floor=min(vals), hit_count=hit, n=len(vals),
            # Add-one smoothing with 2 pseudo-counts: a 6/6 clear → ~0.88, not 1.0,
            # so stacked legs don't compound to false certainty.
            hit_prob=round((hit + 1) / (len(vals) + 2), 3),
            cushion=round(min(vals) - prop.line, 1),
        ))
    # Best play per (player, market); then rank by probability, then cushion.
    best: dict[tuple, FloorPlay] = {}
    for p in plays:
        k = (p.player, p.market)
        if k not in best or p.threshold > best[k].threshold:  # prefer the higher tier cleared
            best[k] = p
    ranked = sorted(best.values(), key=lambda p: (p.hit_prob, p.cushion, -p.odds), reverse=True)
    return ranked


def _decimal_to_american(decimal: float) -> int:
    if decimal >= 2:
        return round((decimal - 1) * 100)
    return round(-100 / (decimal - 1))


def assemble_bet(
    plays: list[FloorPlay], *, legs: int, markets: list[str] | None = None, bankroll: float = 1000.0
) -> dict:
    """Build a single (legs=1) or N-leg parlay from the ranked floor board."""
    pool = [p for p in plays if not markets or p.market in markets]
    # one leg per player to avoid stacking the same player
    seen: set[str] = set()
    unique = []
    for p in pool:
        if p.player in seen:
            continue
        seen.add(p.player)
        unique.append(p)

    legs = max(1, min(legs, 8))
    chosen = unique[:legs]
    if not chosen:
        return {"legs": [], "no_bet": True, "reason": "No qualifying floor plays for the filters."}

    decimal = 1.0
    prob = 1.0
    for p in chosen:
        decimal *= american_to_decimal(p.odds)
        prob *= p.hit_prob

    b = decimal - 1
    f = max(0.0, (b * prob - (1 - prob)) / b) if b > 0 else 0.0
    stake = round(min(bankroll * settings.kelly_fraction * f, bankroll * settings.max_stake_pct), 2)

    return {
        "no_bet": False,
        "legs": [p.as_dict() for p in chosen],
        "leg_count": len(chosen),
        "combined_odds": _decimal_to_american(decimal),
        "combined_decimal": round(decimal, 2),
        "model_hit_prob": round(prob * 100, 1),
        "recommended_stake": stake,
    }

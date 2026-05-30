"""Moneyline value math.

Pipeline per game:
  1. model win probability from team records (Bradley-Terry + home edge),
  2. de-vig the book's two-way moneyline into a fair implied probability,
  3. edge = model_prob - implied_prob (per side); surface positive edges,
  4. fractional-Kelly stake on the side with edge, at the book's price.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import settings

# MLB home teams win ~53% of the time; a small, fixed prior, not a fitted edge.
HOME_FIELD_EDGE = 0.03

# Single-game MLB outcomes are far closer to a coin flip than season records
# imply (even a .640 team beats a .380 team well under 65% of the time in one
# game, because the starting pitcher — which this model does NOT see — dominates
# the line). Compress the record-implied probability hard toward 0.5 to reflect
# that variance and to avoid manufacturing fake edges. This is a blunt
# correction, not a calibrated one.
SINGLE_GAME_COMPRESSION = 0.40

# Only flag a side as a "lean" past this divergence — and even then it is a
# record-model disagreement with the market, NOT a verified positive-EV edge.
LEAN_THRESHOLD = 0.06


def american_to_prob(odds: int) -> float:
    """American odds → implied probability (includes the vig)."""
    if odds < 0:
        return -odds / (-odds + 100)
    return 100 / (odds + 100)


def american_to_decimal(odds: int) -> float:
    return 1 + (odds / 100 if odds > 0 else 100 / -odds)


def win_pct(wins: int, losses: int) -> float:
    total = wins + losses
    return wins / total if total else 0.5


def matchup_prob(home_wp: float, away_wp: float) -> float:
    """Bradley-Terry home win probability with a small home-field prior."""
    # Bradley-Terry on win% (clamped away from 0/1 to stay defined).
    h = min(max(home_wp, 0.05), 0.95)
    a = min(max(away_wp, 0.05), 0.95)
    base = (h * (1 - a)) / (h * (1 - a) + a * (1 - h))
    base = base + HOME_FIELD_EDGE
    # Compress toward a coin flip to reflect single-game MLB variance.
    compressed = 0.5 + SINGLE_GAME_COMPRESSION * (base - 0.5)
    return min(0.99, max(0.01, compressed))


class MoneylineEdge(BaseModel):
    side: str  # "home" | "away"
    team: str
    odds: int
    model_prob: float = Field(..., ge=0, le=1)
    implied_prob: float = Field(..., ge=0, le=1)
    edge: float = Field(..., description="model_prob - de-vigged implied_prob")
    kelly_stake: float = 0.0


class GameValue(BaseModel):
    game_id: str
    home: str
    away: str
    home_record: str
    away_record: str
    total: float | None = None  # stored from the book; not yet modelled
    best: MoneylineEdge | None = None  # the positive-edge side, if any
    edges: list[MoneylineEdge] = Field(default_factory=list)
    note: str | None = None


def moneyline_value(
    *,
    game_id: str,
    home: str,
    away: str,
    home_record: tuple[int, int],
    away_record: tuple[int, int],
    home_ml: int,
    away_ml: int,
    bankroll: float,
    total: float | None = None,
) -> GameValue:
    home_wp = win_pct(*home_record)
    away_wp = win_pct(*away_record)
    p_home = matchup_prob(home_wp, away_wp)
    p_away = 1 - p_home

    # De-vig the two-way market into fair probabilities.
    ih, ia = american_to_prob(home_ml), american_to_prob(away_ml)
    overround = ih + ia
    fair_home, fair_away = ih / overround, ia / overround

    def _edge(side: str, team: str, odds: int, model_p: float, fair_p: float) -> MoneylineEdge:
        edge = round(model_p - fair_p, 4)
        stake = 0.0
        if edge > 0:
            b = american_to_decimal(odds) - 1
            f_star = max(0.0, (b * model_p - (1 - model_p)) / b) if b > 0 else 0.0
            stake = round(min(bankroll * settings.kelly_fraction * f_star,
                              bankroll * settings.max_stake_pct), 2)
        return MoneylineEdge(side=side, team=team, odds=odds, model_prob=round(model_p, 4),
                             implied_prob=round(fair_p, 4), edge=edge, kelly_stake=stake)

    edges = [
        _edge("home", home, home_ml, p_home, fair_home),
        _edge("away", away, away_ml, p_away, fair_away),
    ]
    leans = [e for e in edges if e.edge > LEAN_THRESHOLD]
    best = max(leans, key=lambda e: e.edge) if leans else None
    return GameValue(
        game_id=game_id, home=home, away=away,
        home_record=f"{home_record[0]}-{home_record[1]}",
        away_record=f"{away_record[0]}-{away_record[1]}",
        total=total, edges=edges, best=best,
        note=(
            f"Record-model lean (NOT verified edge — ignores tonight's pitchers)"
            if best else "Aligned with the market."
        ),
    )

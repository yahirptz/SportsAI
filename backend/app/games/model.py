"""Pitcher-aware game-line model (moneyline + totals).

The starting pitcher is the dominant factor in an MLB line, so this model is
built around it. For each game:

  1. Expected runs each side scores ≈ a blend of the OPPOSING starter's ERA
     (the share of the game the starter pitches) and league-average run scoring
     (the bullpen share), nudged by a weak team-offense proxy from records.
  2. Win probability from the Pythagorean expectation of those run estimates.
  3. Projected total = sum of expected runs → compared to the book total.
  4. Moneyline edge = model prob − de-vigged market prob.

Still simplified (no park factors, bullpen quality, lineups, weather, or
recent-form-vs-season-ERA), so leans are leans — not guaranteed edges. But it is
grounded in the single most important input, which the record-only model lacked.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import settings

LEAGUE_AVG_RUNS = 4.5          # approx MLB runs per team per game
LEAGUE_AVG_ERA = 4.10          # approx MLB starter ERA
STARTER_INNINGS_SHARE = 0.60   # share of the game the starter typically throws
PYTHAG_EXP = 1.83              # Pythagenpat-ish exponent for MLB
HOME_FIELD_RUNS = 1.03         # ~3% home run-scoring bump
OFFENSE_SWING = 0.25           # max ±25% offense adjustment from record
ERA_REGRESSION = 0.55          # weight on the raw ERA; rest pulls toward mean
ML_LEAN_THRESHOLD = 0.08       # min model-vs-market gap to flag a moneyline lean
TOTAL_LEAN_THRESHOLD = 1.0     # min projected-vs-book run gap to flag over/under


def _regress_era(era: float) -> float:
    """Regress a noisy in-season ERA toward the league mean. 0.0 = no data."""
    if era is None or era <= 0 or era > 12:
        return LEAGUE_AVG_ERA
    return ERA_REGRESSION * era + (1 - ERA_REGRESSION) * LEAGUE_AVG_ERA


def american_to_prob(odds: int) -> float:
    if odds < 0:
        return -odds / (-odds + 100)
    return 100 / (odds + 100)


def american_to_decimal(odds: int) -> float:
    return 1 + (odds / 100 if odds > 0 else 100 / -odds)


def win_pct(wins: int, losses: int) -> float:
    total = wins + losses
    return wins / total if total else 0.5


def _offense_factor(wp: float) -> float:
    return 1 + OFFENSE_SWING * (wp - 0.5) * 2


def _runs_allowed_profile(starter_era: float) -> float:
    """Runs the opposing offense is expected to score vs this starter + pen."""
    return STARTER_INNINGS_SHARE * starter_era + (1 - STARTER_INNINGS_SHARE) * LEAGUE_AVG_RUNS


def _pythagorean(home_runs: float, away_runs: float) -> float:
    h, a = home_runs ** PYTHAG_EXP, away_runs ** PYTHAG_EXP
    return h / (h + a) if (h + a) else 0.5


class Starter(BaseModel):
    name: str
    era: float
    record: str


class MoneylineEdge(BaseModel):
    side: str
    team: str
    odds: int
    model_prob: float
    implied_prob: float
    edge: float
    kelly_stake: float = 0.0


class TotalLean(BaseModel):
    pick: str  # "over" | "under"
    line: float
    projected: float
    diff: float


class GameValue(BaseModel):
    game_id: str
    home: str
    away: str
    home_record: str
    away_record: str
    home_starter: Starter | None = None
    away_starter: Starter | None = None
    proj_home_runs: float | None = None
    proj_away_runs: float | None = None
    proj_total: float | None = None
    total: float | None = None
    total_lean: TotalLean | None = None
    best: MoneylineEdge | None = None
    edges: list[MoneylineEdge] = Field(default_factory=list)
    note: str | None = None


def game_value(
    *,
    game_id: str,
    home: str,
    away: str,
    home_record: tuple[int, int],
    away_record: tuple[int, int],
    home_starter: Starter | None,
    away_starter: Starter | None,
    home_ml: int,
    away_ml: int,
    bankroll: float,
    total: float | None = None,
) -> GameValue:
    home_wp, away_wp = win_pct(*home_record), win_pct(*away_record)
    # Regress raw ERAs toward the mean (in-season ERAs are noisy; 0.0 = no data).
    home_era = _regress_era(home_starter.era) if home_starter else LEAGUE_AVG_ERA
    away_era = _regress_era(away_starter.era) if away_starter else LEAGUE_AVG_ERA

    # Expected runs: each side's offense vs the opposing starter, ± offense proxy.
    exp_home = _runs_allowed_profile(away_era) * _offense_factor(home_wp) * HOME_FIELD_RUNS
    exp_away = _runs_allowed_profile(home_era) * _offense_factor(away_wp)
    proj_total = round(exp_home + exp_away, 2)

    p_home = min(0.95, max(0.05, _pythagorean(exp_home, exp_away)))
    p_away = 1 - p_home

    ih, ia = american_to_prob(home_ml), american_to_prob(away_ml)
    overround = ih + ia
    fair_home, fair_away = ih / overround, ia / overround

    def _edge(side, team, odds, mp, fp) -> MoneylineEdge:
        edge = round(mp - fp, 4)
        stake = 0.0
        if edge > ML_LEAN_THRESHOLD:
            b = american_to_decimal(odds) - 1
            f = max(0.0, (b * mp - (1 - mp)) / b) if b > 0 else 0.0
            stake = round(min(bankroll * settings.kelly_fraction * f, bankroll * settings.max_stake_pct), 2)
        return MoneylineEdge(side=side, team=team, odds=odds, model_prob=round(mp, 4),
                             implied_prob=round(fp, 4), edge=edge, kelly_stake=stake)

    edges = [
        _edge("home", home, home_ml, p_home, fair_home),
        _edge("away", away, away_ml, p_away, fair_away),
    ]
    leans = [e for e in edges if e.edge > ML_LEAN_THRESHOLD]
    best = max(leans, key=lambda e: e.edge) if leans else None

    total_lean = None
    if total is not None:
        diff = round(proj_total - total, 2)
        if diff > TOTAL_LEAN_THRESHOLD:
            total_lean = TotalLean(pick="over", line=total, projected=proj_total, diff=diff)
        elif diff < -TOTAL_LEAN_THRESHOLD:
            total_lean = TotalLean(pick="under", line=total, projected=proj_total, diff=diff)

    return GameValue(
        game_id=game_id, home=home, away=away,
        home_record=f"{home_record[0]}-{home_record[1]}",
        away_record=f"{away_record[0]}-{away_record[1]}",
        home_starter=home_starter, away_starter=away_starter,
        proj_home_runs=round(exp_home, 2), proj_away_runs=round(exp_away, 2),
        proj_total=proj_total, total=total, total_lean=total_lean,
        edges=edges, best=best,
        note="Pitcher-aware model. Leans are model-vs-market gaps, not guaranteed edges.",
    )

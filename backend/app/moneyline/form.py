"""Team form model + moneyline prediction (form + EV + Kelly)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from app.config import settings
from app.feeds.sportradar import (
    SportRadarStats,
    _endpoint_for,
    _team_ids,
    team_rest_days,
)
from app.scoring.kelly import american_to_decimal, expected_value
from app.sports.registry import Sport, get_config

# The team-score field in a SportRadar summary, per sport.
_SCORE_KEY = {Sport.NBA: "points", Sport.NHL: "points", Sport.MLB: "runs"}
FORM_GAMES = 5
LOOKBACK = 25
HOME_EDGE = 3.0       # form points of home-court/field advantage
PROB_SCALE = 14.0     # logistic scale on the form differential
LEAN_EDGE = 0.04      # min model-vs-market prob gap to call a lean


@dataclass
class TeamForm:
    team: str
    last5: list[str]                 # "W"/"L", most recent first
    margins: list[int]
    avg_margin: float
    points_allowed_floor: int | None
    home_record: str                 # "W-L" in these games as home
    away_record: str                 # "W-L" as away
    rest_days: int | None
    pace: float | None               # avg combined score (scoring-environment proxy)
    form_score: float                # 0-100


def _form_score(win_rate: float, avg_margin: float, rest: int | None) -> float:
    margin_norm = max(0.0, min(1.0, (avg_margin + 15) / 30))  # ±15 spans the range
    rest_factor = 0.85 if (rest is not None and rest < 2) else 1.0
    return round(100 * (0.55 * win_rate + 0.35 * margin_norm + 0.10 * rest_factor), 1)


def _team_form(stats: SportRadarStats, window: list[dict], team_id: str,
               sport: Sport, ref_date: str) -> TeamForm | None:
    score_key = _SCORE_KEY.get(sport, "points")
    games = sorted(
        [g for g in window if g.get("status") == "closed"
         and team_id in _team_ids(g, sport) and g["_date"] < ref_date],
        key=lambda g: g["_date"], reverse=True,
    )[:FORM_GAMES]

    name, last5, margins, pa_list, totals = "", [], [], [], []
    hw = hl = aw = al = 0
    for g in games:
        summary = stats.summary(g["id"])
        root = summary.get("game", summary) if sport is Sport.MLB else summary
        home, away = root.get("home", {}), root.get("away", {})
        mine, opp, is_home = (home, away, True) if home.get("id") == team_id else (away, home, False)
        name = f"{mine.get('market','')} {mine.get('name','')}".strip() or mine.get("name", "")
        pf, pa = mine.get(score_key), opp.get(score_key)
        if pf is None or pa is None:
            continue
        won = pf > pa
        last5.append("W" if won else "L")
        margins.append(pf - pa)
        pa_list.append(pa)
        totals.append(pf + pa)
        if is_home:
            hw, hl = hw + won, hl + (not won)
        else:
            aw, al = aw + won, al + (not won)

    if not last5:
        return None
    win_rate = last5.count("W") / len(last5)
    avg_margin = round(sum(margins) / len(margins), 1)
    rest = team_rest_days(window, team_id, sport, ref_date)
    return TeamForm(
        team=name, last5=last5, margins=margins, avg_margin=avg_margin,
        points_allowed_floor=min(pa_list) if pa_list else None,
        home_record=f"{hw}-{hl}", away_record=f"{aw}-{al}", rest_days=rest,
        pace=round(sum(totals) / len(totals), 1) if totals else None,
        form_score=_form_score(win_rate, avg_margin, rest),
    )


def _target_game(stats: SportRadarStats) -> dict | None:
    from datetime import date, timedelta
    playable = {"scheduled", "inprogress", "created", "halftime"}
    for i in range(4):
        d = date.today() + timedelta(days=i)
        for g in stats.schedule(d).get("games", []):
            if g.get("status") in playable:
                g["_date"] = str(d)
                return g
    return None


def build_form(sport: Sport) -> dict:
    base, key = _endpoint_for(sport)
    if not base or not key:
        return {"sport": sport.value, "game": None, "note": f"No SportRadar key for {sport.value}."}
    stats = SportRadarStats(base, key)
    target = _target_game(stats)
    if not target:
        return {"sport": sport.value, "game": None, "note": "No upcoming game found."}
    window = stats.recent_games(LOOKBACK)
    home_id, away_id = _team_ids(target, sport)
    home = _team_form(stats, window, home_id, sport, target["_date"])
    away = _team_form(stats, window, away_id, sport, target["_date"])
    if not home or not away:
        return {"sport": sport.value, "game": None, "note": "Not enough recent games for both teams."}
    return {
        "sport": sport.value,
        "game": {"home": home.team, "away": away.team, "scheduled": target.get("scheduled")},
        "home": asdict(home), "away": asdict(away),
    }


def predict_moneyline(sport: Sport, home_odds: int, away_odds: int, bankroll: float = 1000.0) -> dict:
    form = build_form(sport)
    if not form.get("home"):
        return {"sport": sport.value, "lean": "no lean", "note": form.get("note", "No data."),
                "confidence": 0}

    hs, as_ = form["home"]["form_score"], form["away"]["form_score"]
    diff = (hs - as_) + HOME_EDGE
    p_home = 1 / (1 + math.exp(-diff / PROB_SCALE))
    p_home = min(0.95, max(0.05, p_home))
    p_away = 1 - p_home

    # De-vig the market to compare fairly.
    ih, ia = 1 / american_to_decimal(home_odds), 1 / american_to_decimal(away_odds)
    fair_home = ih / (ih + ia)

    def _kelly_fraction(p: float, odds: int) -> float:
        b = american_to_decimal(odds) - 1
        f = (b * p - (1 - p)) / b if b > 0 else 0.0
        return round(max(0.0, settings.kelly_fraction * f), 4)

    edge_home = p_home - fair_home
    if abs(edge_home) < LEAN_EDGE:
        lean = "no lean"
        side_p, side_odds = (p_home, home_odds)
    elif edge_home > 0:
        lean = form["home"]["team"]
        side_p, side_odds = (p_home, home_odds)
    else:
        lean = form["away"]["team"]
        side_p, side_odds = (p_away, away_odds)

    confidence = round(min(100.0, abs(hs - as_) * 2 + 50), 1) if lean != "no lean" else round(50 - abs(edge_home) * 100, 1)
    note = ("Form model on a 5-game sample — directional, not predictive. "
            "Moneylines are an efficient market; treat any lean as a look, not an edge.")
    if abs(hs - as_) < 8:
        note = "Close matchup — forms are near-even. " + note

    return {
        "sport": sport.value,
        "home_team": form["home"]["team"], "away_team": form["away"]["team"],
        "home_form_score": hs, "away_form_score": as_,
        "home_win_prob": round(p_home, 3), "away_win_prob": round(p_away, 3),
        "lean": lean, "confidence": confidence,
        "expected_value": expected_value(side_p, side_odds),
        "kelly_fraction": _kelly_fraction(side_p, side_odds),
        "honest_note": note,
    }

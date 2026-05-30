"""Build game-line values: match today's schedule to operator odds + model them.

Uses one cheap SportRadar schedule call (team records ride along in the schedule
team objects), then matches each game to a line in game_lines.json by team
nickname and runs the moneyline value model.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.config import settings
from app.feeds.sportradar import SportRadarStats, _endpoint_for
from app.games.model import GameValue, moneyline_value
from app.sports.registry import Sport

GAME_LINES_PATH = "data/game_lines.json"


def load_game_lines(sport: Sport) -> list[dict]:
    path = Path(GAME_LINES_PATH)
    if not path.exists():
        return []
    return json.loads(path.read_text()).get(sport.value, [])


def _match(odds: list[dict], away_nick: str, home_nick: str) -> dict | None:
    a, h = away_nick.lower(), home_nick.lower()
    for o in odds:
        if o.get("away", "").lower().endswith(a) and o.get("home", "").lower().endswith(h):
            return o
    return None


def build_game_values(sport: Sport, bankroll: float) -> dict:
    base, key = _endpoint_for(sport)
    if not base or not key:
        return {"sport": sport.value, "games": [], "note": f"No SportRadar key for {sport.value}."}

    odds = load_game_lines(sport)
    if not odds:
        return {"sport": sport.value, "games": [], "note": "No game lines entered for this sport."}

    stats = SportRadarStats(base, key)
    games = stats.schedule(date.today()).get("games", [])

    values: list[GameValue] = []
    for g in games:
        home, away = g.get("home"), g.get("away")
        if not isinstance(home, dict) or not isinstance(away, dict):
            continue  # need the team objects (records) to model
        o = _match(odds, away.get("name", ""), home.get("name", ""))
        if not o:
            continue
        values.append(
            moneyline_value(
                game_id=g["id"],
                home=f"{home.get('market','')} {home.get('name','')}".strip(),
                away=f"{away.get('market','')} {away.get('name','')}".strip(),
                home_record=(home.get("win", 0), home.get("loss", 0)),
                away_record=(away.get("win", 0), away.get("loss", 0)),
                home_ml=o["home_ml"],
                away_ml=o["away_ml"],
                total=o.get("total"),
                bankroll=bankroll,
            )
        )

    values.sort(key=lambda v: (v.best.edge if v.best else -1), reverse=True)
    leans = sum(1 for v in values if v.best)
    return {
        "sport": sport.value,
        "count": len(values),
        "leans": leans,
        "model": "naive season-record moneyline",
        "warning": (
            "Reference model only. It ignores starting pitchers (the dominant "
            "factor in MLB lines), so 'leans' are record-vs-market disagreements, "
            "NOT verified positive-EV bets. Do not bet these as edges."
        ),
        "games": values,
    }

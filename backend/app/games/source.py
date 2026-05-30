"""Build pitcher-aware game-line values.

Fetches tonight's schedule (1 call) for the slate, then each game's summary
(carries both probable starters with their season ERA, plus team records). All
responses are disk-cached, so a slate costs ~1 + N calls once per day.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.feeds.sportradar import SportRadarStats, _endpoint_for
from app.games.model import GameValue, Starter, game_value
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


def _starter(team: dict) -> Starter | None:
    pp = team.get("probable_pitcher")
    if not pp:
        return None
    try:
        era = float(pp.get("era"))
    except (TypeError, ValueError):
        return None
    return Starter(
        name=pp.get("full_name", "").strip(),
        era=era,
        record=f"{pp.get('win', 0)}-{pp.get('loss', 0)}",
    )


def build_game_values(sport: Sport, bankroll: float) -> dict:
    base, key = _endpoint_for(sport)
    if not base or not key:
        return {"sport": sport.value, "games": [], "note": f"No SportRadar key for {sport.value}."}
    odds = load_game_lines(sport)
    if not odds:
        return {"sport": sport.value, "games": [], "note": "No game lines entered for this sport."}

    stats = SportRadarStats(base, key)
    schedule = stats.schedule(date.today()).get("games", [])

    values: list[GameValue] = []
    for sg in schedule:
        home_s, away_s = sg.get("home"), sg.get("away")
        if not isinstance(home_s, dict) or not isinstance(away_s, dict):
            continue
        o = _match(odds, away_s.get("name", ""), home_s.get("name", ""))
        if not o:
            continue
        # Pull the summary for probable starters + records.
        summary = stats.summary(sg["id"]).get("game", {})
        home, away = summary.get("home", home_s), summary.get("away", away_s)
        values.append(
            game_value(
                game_id=sg["id"],
                home=f"{home.get('market','')} {home.get('name','')}".strip(),
                away=f"{away.get('market','')} {away.get('name','')}".strip(),
                home_record=(home.get("win", 0), home.get("loss", 0)),
                away_record=(away.get("win", 0), away.get("loss", 0)),
                home_starter=_starter(home),
                away_starter=_starter(away),
                home_ml=o["home_ml"],
                away_ml=o["away_ml"],
                total=o.get("total"),
                bankroll=bankroll,
            )
        )

    values.sort(key=lambda v: (v.best.edge if v.best else -1), reverse=True)
    return {
        "sport": sport.value,
        "count": len(values),
        "ml_leans": sum(1 for v in values if v.best),
        "total_leans": sum(1 for v in values if v.total_lean),
        "model": "pitcher-aware (starter ERA → expected runs → Pythagorean win prob + projected total)",
        "warning": (
            "Simplified model: no park factors, bullpen, lineups, or weather. "
            "Leans are model-vs-market gaps to investigate, not guaranteed edges."
        ),
        "games": values,
    }

"""Build game-line values per sport.

- MLB: pitcher-aware (each game's summary gives both probable starters + ERA).
- NBA: team-scoring (one standings call gives every team's points-for/against
  per game; win probability from the projected margin).

All responses are disk-cached.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.feeds.sportradar import SportRadarStats, _endpoint_for
from app.games.model import GameValue, Starter, game_value, nba_game_value
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
    return Starter(name=pp.get("full_name", "").strip(), era=era,
                   record=f"{pp.get('win', 0)}-{pp.get('loss', 0)}")


def _today_schedule(stats: SportRadarStats) -> list[dict]:
    d = date.today()
    return stats.schedule(d).get("games", [])


def build_game_values(sport: Sport, bankroll: float) -> dict:
    base, key = _endpoint_for(sport)
    if not base or not key:
        return {"sport": sport.value, "games": [], "note": f"No SportRadar key for {sport.value}."}
    odds = load_game_lines(sport)
    if not odds:
        return {"sport": sport.value, "games": [], "note": "No game lines entered for this sport."}

    stats = SportRadarStats(base, key)
    if sport is Sport.MLB:
        result = _build_mlb(stats, odds, bankroll)
    elif sport is Sport.NBA:
        result = _build_nba(stats, odds, bankroll)
    else:
        return {"sport": sport.value, "games": [], "note": "Game-line model not built for this sport."}

    result["games"].sort(key=lambda v: (v.best.edge if v.best else -1), reverse=True)
    return {
        "sport": sport.value,
        "count": len(result["games"]),
        "ml_leans": sum(1 for v in result["games"] if v.best),
        "total_leans": sum(1 for v in result["games"] if v.total_lean),
        "model": result["model"],
        "warning": result["warning"],
        "games": result["games"],
    }


def _build_mlb(stats: SportRadarStats, odds: list[dict], bankroll: float) -> dict:
    values: list[GameValue] = []
    for sg in _today_schedule(stats):
        home_s, away_s = sg.get("home"), sg.get("away")
        if not isinstance(home_s, dict) or not isinstance(away_s, dict):
            continue
        o = _match(odds, away_s.get("name", ""), home_s.get("name", ""))
        if not o:
            continue
        summary = stats.summary(sg["id"]).get("game", {})
        home, away = summary.get("home", home_s), summary.get("away", away_s)
        values.append(game_value(
            game_id=sg["id"],
            home=f"{home.get('market','')} {home.get('name','')}".strip(),
            away=f"{away.get('market','')} {away.get('name','')}".strip(),
            home_record=(home.get("win", 0), home.get("loss", 0)),
            away_record=(away.get("win", 0), away.get("loss", 0)),
            home_starter=_starter(home), away_starter=_starter(away),
            home_ml=o["home_ml"], away_ml=o["away_ml"], total=o.get("total"), bankroll=bankroll,
        ))
    return {
        "games": values,
        "model": "pitcher-aware (starter ERA → expected runs → Pythagorean + projected total)",
        "warning": ("Simplified: no park/bullpen/lineup/weather. Leans are gaps to "
                    "investigate, not guaranteed edges."),
    }


def _nba_season_year() -> int:
    today = date.today()
    return today.year if today.month >= 10 else today.year - 1


def _collect_teams(node, out: dict) -> None:
    if isinstance(node, dict):
        if "points_for" in node and node.get("id"):
            out[node["id"]] = node
        for v in node.values():
            _collect_teams(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_teams(v, out)


def _build_nba(stats: SportRadarStats, odds: list[dict], bankroll: float) -> dict:
    standings = stats._get(f"seasons/{_nba_season_year()}/REG/standings.json")
    teams: dict[str, dict] = {}
    _collect_teams(standings, teams)
    if not teams:
        return {"games": [], "model": "nba-scoring", "warning": "No standings data available."}
    league_avg = sum(t["points_for"] for t in teams.values()) / len(teams)

    values: list[GameValue] = []
    for sg in _today_schedule(stats):
        home_s, away_s = sg.get("home"), sg.get("away")
        if not isinstance(home_s, dict) or not isinstance(away_s, dict):
            continue
        o = _match(odds, away_s.get("name", ""), home_s.get("name", ""))
        if not o:
            continue
        ht, at = teams.get(home_s.get("id")), teams.get(away_s.get("id"))
        if not ht or not at:
            continue
        values.append(nba_game_value(
            game_id=sg["id"],
            home=f"{ht.get('market','')} {ht.get('name','')}".strip(),
            away=f"{at.get('market','')} {at.get('name','')}".strip(),
            home_record=(ht.get("wins", 0), ht.get("losses", 0)),
            away_record=(at.get("wins", 0), at.get("losses", 0)),
            home_off=ht["points_for"], home_def=ht["points_against"],
            away_off=at["points_for"], away_def=at["points_against"],
            league_avg=league_avg,
            home_ml=o["home_ml"], away_ml=o["away_ml"], total=o.get("total"), bankroll=bankroll,
        ))
    return {
        "games": values,
        "model": "NBA team-scoring (off/def ratings + home court → margin → win prob + total)",
        "warning": ("Simplified: season ratings, no injuries/rest/pace adjustments. "
                    "Leans are gaps to investigate, not guaranteed edges."),
    }

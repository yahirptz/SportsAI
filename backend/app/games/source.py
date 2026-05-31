"""Build game-line values per sport.

- MLB: pitcher-aware (each game's summary gives both probable starters + ERA).
- NBA: recent-form scoring — each team's last-N games' points for/against (so a
  Game 7 is modelled on the actual series/playoff games, at playoff pace, not
  the regular season).

Games are found by scanning an upcoming window (today .. +N days), so a game
scheduled tomorrow (e.g. a Finals Game 7) is picked up. All responses cached.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from app.feeds.sportradar import SportRadarStats, _endpoint_for
from app.games.model import GameValue, Starter, game_value, nba_game_value
from app.sports.registry import Sport

GAME_LINES_PATH = "data/game_lines.json"
UPCOMING_DAYS = 3       # how far ahead to look for a scheduled game
NBA_FORM_GAMES = 7      # last-N games for NBA recent-form ratings
NBA_FORM_LOOKBACK = 20  # days to walk back collecting those games


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


def _upcoming_games(stats: SportRadarStats, days: int = UPCOMING_DAYS) -> list[dict]:
    """Scheduled (not-yet-played) games from today through +days, earliest first."""
    out: list[dict] = []
    for i in range(days + 1):
        d = date.today() + timedelta(days=i)
        for g in stats.schedule(d).get("games", []):
            if g.get("status") != "closed":
                g["_date"] = str(d)
                out.append(g)
    return out


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

    _attach_injuries(result["games"], sport)
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


def save_game_lines(sport: Sport, parsed: list[dict]) -> int:
    """Upsert parsed game lines into game_lines.json (shared by API + assistant)."""
    path = Path(GAME_LINES_PATH)
    data = json.loads(path.read_text()) if path.exists() else {}
    rows = data.setdefault(sport.value, [])
    for g in parsed:
        rows[:] = [r for r in rows if not (r.get("away") == g["away"] and r.get("home") == g["home"])]
        rows.append(g)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return len(parsed)


def _attach_injuries(games: list[GameValue], sport: Sport) -> None:
    """Per team: injury note (Perplexity) + Reddit public-lean / fade read."""
    from app.enrichment import get_enrichment_service
    from app.sports.registry import get_config

    service = get_enrichment_service()
    if not service.enabled:
        return
    cfg = get_config(sport)
    for gv in games:
        for team in (gv.away, gv.home):
            news = service.team_news(team, cfg.label)
            if news.get("note"):
                gv.injury_notes.append(f"{team}: {news['note']}")
        # Reddit public lean → fade signal (context only, never overrides).
        gv.away_sentiment = service.team_sentiment(gv.away, cfg.subreddits)
        gv.home_sentiment = service.team_sentiment(gv.home, cfg.subreddits)
        diff = (gv.home_sentiment or 0) - (gv.away_sentiment or 0)
        if abs(diff) < 0.25:
            gv.public_note = "No strong public lean (Reddit)."
        elif diff > 0:
            gv.public_note = f"Public buzz on {gv.home} — fade value may be on {gv.away}."
        else:
            gv.public_note = f"Public buzz on {gv.away} — fade value may be on {gv.home}."


def _build_mlb(stats: SportRadarStats, odds: list[dict], bankroll: float) -> dict:
    values: list[GameValue] = []
    seen: set[str] = set()
    for sg in _upcoming_games(stats):
        home_s, away_s = sg.get("home"), sg.get("away")
        if not isinstance(home_s, dict) or not isinstance(away_s, dict):
            continue
        o = _match(odds, away_s.get("name", ""), home_s.get("name", ""))
        if not o or (key := f'{o["away"]}@{o["home"]}') in seen:
            continue
        seen.add(key)
        summary = stats.summary(sg["id"]).get("game", {})
        home, away = summary.get("home", home_s), summary.get("away", away_s)
        values.append(game_value(
            game_id=sg["id"], scheduled=sg.get("scheduled"),
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


# --- NBA recent-form -------------------------------------------------------


def _recent_closed(stats: SportRadarStats, lookback: int) -> list[dict]:
    games: list[dict] = []
    d = date.today()
    for _ in range(lookback):
        d -= timedelta(days=1)
        for g in stats.schedule(d).get("games", []):
            if g.get("status") == "closed":
                g["_date"] = str(d)
                games.append(g)
    return games  # newest-first (we decrement the date)


def _team_form(stats: SportRadarStats, team_id: str, closed: list[dict], n: int):
    """Return (avg_points_for, avg_points_against, games_used) over last-N games."""
    mine = [g for g in closed if team_id in (g.get("home", {}).get("id"), g.get("away", {}).get("id"))][:n]
    pf, pa = [], []
    for g in mine:
        s = stats.summary(g["id"])
        home, away = s.get("home", {}), s.get("away", {})
        if home.get("points") is None or away.get("points") is None:
            continue
        if home.get("id") == team_id:
            pf.append(home["points"]); pa.append(away["points"])
        else:
            pf.append(away["points"]); pa.append(home["points"])
    if not pf:
        return None
    return sum(pf) / len(pf), sum(pa) / len(pa), len(pf)


def _build_nba(stats: SportRadarStats, odds: list[dict], bankroll: float) -> dict:
    upcoming = _upcoming_games(stats)
    if not any(_match(odds, g.get("away", {}).get("name", ""), g.get("home", {}).get("name", "")) for g in upcoming):
        return {"games": [], "model": "nba-recent-form",
                "warning": "No upcoming game matched the entered NBA lines."}

    closed = _recent_closed(stats, NBA_FORM_LOOKBACK)
    values: list[GameValue] = []
    seen: set[str] = set()
    for sg in upcoming:
        home_s, away_s = sg.get("home"), sg.get("away")
        if not isinstance(home_s, dict) or not isinstance(away_s, dict):
            continue
        o = _match(odds, away_s.get("name", ""), home_s.get("name", ""))
        if not o or (mk := f'{o["away"]}@{o["home"]}') in seen:
            continue
        hf = _team_form(stats, home_s.get("id"), closed, NBA_FORM_GAMES)
        af = _team_form(stats, away_s.get("id"), closed, NBA_FORM_GAMES)
        if not hf or not af:
            continue
        seen.add(mk)
        values.append(nba_game_value(
            game_id=sg["id"], scheduled=sg.get("scheduled"),
            home=f"{home_s.get('market','')} {home_s.get('name','')}".strip(),
            away=f"{away_s.get('market','')} {away_s.get('name','')}".strip(),
            home_record=(home_s.get("win", 0), home_s.get("loss", 0)),
            away_record=(away_s.get("win", 0), away_s.get("loss", 0)),
            home_off=hf[0], home_def=hf[1], away_off=af[0], away_def=af[1],
            home_ml=o["home_ml"], away_ml=o["away_ml"], total=o.get("total"), bankroll=bankroll,
            form_note=f"last {min(hf[2], af[2])} games (recent/playoff form)",
        ))
    return {
        "games": values,
        "model": "NBA recent-form (last-N points for/against + home court → margin → win prob + total)",
        "warning": ("Recent-form ratings from the latest games (playoff pace). Still no "
                    "injury/rest/matchup adjustments — leans are gaps, not guaranteed edges."),
    }

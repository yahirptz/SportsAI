"""Auto-grade tracked player props against SportRadar box scores.

For each open pick whose game has finished, fetch the (fresh) game summary,
pull the player's actual stat with the same extractor used to build the pick,
and grade the OVER. Closing-line value still requires a closing line (no odds
feed yet), so CLV is left null unless supplied via the manual grade endpoint.
"""

from __future__ import annotations

from app.db.repository import open_picks, record_outcome
from app.feeds.sportradar import EXTRACTORS, SportRadarStats, _endpoint_for
from app.sports.registry import Sport


def autograde(sport_value: str) -> dict:
    sport = Sport(sport_value)
    base, key = _endpoint_for(sport)
    if not base or not key:
        return {"graded": 0, "skipped": 0, "note": f"No SportRadar key for {sport_value}."}

    extractors = EXTRACTORS.get(sport, {})
    if not extractors:
        return {"graded": 0, "skipped": 0, "note": "No stat extractors for this sport."}

    stats = SportRadarStats(base, key)
    picks = open_picks(sport_value)
    by_game: dict[str, list[dict]] = {}
    for p in picks:
        by_game.setdefault(p["game_id"], []).append(p)

    graded = skipped = 0
    for game_id, plist in by_game.items():
        try:
            summary = stats.summary(game_id, fresh=True)  # bypass cache for live status
        except Exception:
            skipped += len(plist)  # unknown/sample game id, network error, etc.
            continue
        root = summary.get("game", summary)
        status = root.get("status") or summary.get("status")
        if status != "closed":
            skipped += len(plist)
            continue
        players: dict[str, dict] = {}
        for side in ("home", "away"):
            for pl in root.get(side, {}).get("players", []) or []:
                if pl.get("id"):
                    players[pl["id"]] = pl
        # Final team scores for moneyline grading.
        score_key = {"nba": "points", "mlb": "runs", "nhl": "points"}.get(sport_value, "points")
        home_score = root.get("home", {}).get(score_key)
        away_score = root.get("away", {}).get(score_key)

        for p in plist:
            if p.get("bet_type") == "moneyline":
                if home_score is None or away_score is None:
                    skipped += 1
                    continue
                mine, opp = ((home_score, away_score) if p["player_id"] == "home"
                             else (away_score, home_score))
                record_outcome(p["id"], actual_value=float(mine - opp))  # margin > 0 => win
                graded += 1
                continue
            pl = players.get(p["player_id"])
            if pl is None or p["market"] not in extractors:
                skipped += 1
                continue
            actual = extractors[p["market"]](pl)
            record_outcome(p["id"], actual_value=actual)
            graded += 1

    return {"sport": sport_value, "graded": graded, "skipped": skipped}

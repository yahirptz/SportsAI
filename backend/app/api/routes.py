"""REST API routes (SRS §06 — Backend API).

Implements the FastAPI surface described in the SRS. Persistence is stubbed with
an in-memory bankroll and the sample feed; real DB/Obsidian adapters slot behind
these handlers in later phases. Routes that depend on unbuilt infrastructure
(shadow tester, Obsidian rule vault) return a clear "not yet wired" payload
rather than fabricating data.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from app.config import settings
from app.db.autograde import autograde
from app.db.repository import open_picks, performance_summary, record_outcome, save_picks
from app.enrichment import get_enrichment_service
from app.feeds import HEALTH_REGISTRY, get_provider
from app.parlay.builder import build_parlay
from app.pipeline import attach_reasoning, generate_picks
from app.sports.registry import SPORTS, Sport

router = APIRouter()

# In-memory state stand-ins (replaced by PostgreSQL adapters in a later phase).
_BANKROLL = {"balance": 1000.0, "risk_profile": "moderate"}
_PICK_INDEX: dict[str, object] = {}


def _resolve_sport(sport: str) -> Sport:
    try:
        return Sport(sport.lower())
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown sport: {sport!r}")


def _busiest_game(props) -> str:
    """Return the game_id with the most candidate props on the slate."""
    counts: dict[str, int] = {}
    for p in props:
        counts[p.game_id] = counts.get(p.game_id, 0) + 1
    return max(counts, key=counts.get)


@router.get("/sports", summary="List configured sports and their status")
def list_sports():
    return [
        {
            "sport": c.sport.value,
            "label": c.label,
            "sample_window": c.sample_window,
            "active": c.active,
            "stats": [s.key for s in c.stats if not s.ceiling_prop],
            "primary_source": c.primary_source,
        }
        for c in SPORTS.values()
    ]


@router.get("/picks/{sport}", summary="Floor-verified picks for a sport")
def get_picks(sport: str):
    s = _resolve_sport(sport)
    enrichment = get_enrichment_service()
    props = get_provider().slate(s)
    picks = generate_picks(s, props, _BANKROLL["balance"], enrichment=enrichment)
    picks.sort(key=lambda p: p.confidence, reverse=True)
    attach_reasoning(picks, enrichment, settings.reasoning_max_legs)
    for p in picks:
        _PICK_INDEX[p.id] = p
    # Persist surfaced picks so they can be graded later (paper trade).
    tracked = save_picks(picks)
    return {"sport": s.value, "count": len(picks), "enriched": enrichment.enabled,
            "newly_tracked": tracked, "picks": picks}


@router.post("/parlay/build", summary="Trigger the SGP builder for a game")
def build_parlay_route(
    sport: str = Body(...),
    game_id: str | None = Body(default=None),
):
    s = _resolve_sport(sport)
    enrichment = get_enrichment_service()
    props = get_provider().slate(s)
    if not props:
        raise HTTPException(status_code=400, detail=f"No props available for {s.value}.")
    # Default to the busiest game on the slate if no game_id is supplied.
    game = game_id or _busiest_game(props)
    candidates = [
        p for p in generate_picks(s, props, _BANKROLL["balance"], enrichment=enrichment)
        if p.game_id == game
    ]
    parlay = build_parlay(game, s, candidates, bankroll=_BANKROLL["balance"])
    # Decorate the chosen legs with Claude reasoning (bounded to the leg count).
    if not parlay.no_bet and enrichment.enabled:
        by_id = {p.id: p for p in candidates}
        attach_reasoning([by_id[leg.pick_id] for leg in parlay.legs], enrichment, settings.parlay_legs)
        for leg in parlay.legs:
            leg.reasoning = by_id[leg.pick_id].reasoning
    return parlay


@router.get("/bankroll", summary="Read current bankroll")
def get_bankroll():
    return _BANKROLL


@router.put("/bankroll", summary="Update current bankroll")
def update_bankroll(balance: float = Body(..., embed=True)):
    if balance < 0:
        raise HTTPException(status_code=400, detail="Bankroll cannot be negative.")
    _BANKROLL["balance"] = round(balance, 2)
    return _BANKROLL


@router.post("/picks/{pick_id}/grade", summary="Grade a tracked pick (manual + optional CLV)")
def grade_route(
    pick_id: str,
    actual_value: float = Body(...),
    closing_line: float | None = Body(default=None),
):
    result = record_outcome(pick_id, actual_value=actual_value, closing_line=closing_line)
    if result is None:
        raise HTTPException(status_code=404, detail="Tracked pick not found.")
    return result


@router.post("/grade/run", summary="Auto-grade tracked picks from final box scores")
def grade_run(sport: str = Body(..., embed=True)):
    """Grade every open pick whose game has finished, using SportRadar results."""
    s = _resolve_sport(sport)
    return autograde(s.value)


@router.get("/picks/tracked/open", summary="Open (ungraded) tracked picks")
def tracked_open(sport: str | None = None):
    return {"open": open_picks(sport)}


@router.get("/performance", summary="Hit rate, record, ROI, CLV by sport")
def performance():
    return performance_summary()


@router.get("/rules/{sport}", summary="Active agent rules from the Obsidian vault")
def rules(sport: str):
    s = _resolve_sport(sport)
    cfg = SPORTS[s]
    return {
        "sport": s.value,
        "sample_window": cfg.sample_window,
        "exclusion_rules": cfg.exclusion_rules,
        "source": "static_config",
        "note": "Obsidian-promoted ruleset overrides these once the vault loop is live.",
    }


@router.get("/shadow/status", summary="Shadow test progress and pending promotions")
def shadow_status():
    return {"status": "pending_data", "active_tests": [], "pending_promotions": []}


@router.get("/feed/health", summary="Circuit-breaker status per data source")
def feed_health():
    """Powers the Model Health view (SRS §07) from the feed_health registry."""
    return {"active_provider": get_provider().name, "feeds": HEALTH_REGISTRY.snapshot()}


@router.post("/games/lines/import", summary="Paste FanDuel game lines (spread/ML/total)")
def import_game_lines(sport: str = Body(...), paste: str = Body(...)):
    """Parse a pasted FanDuel game-line block and save the moneylines + totals."""
    from app.board import parse_fanduel_games

    s = _resolve_sport(sport)
    parsed = parse_fanduel_games(paste)
    if not parsed:
        raise HTTPException(status_code=400, detail="No game lines parsed from the paste.")
    path = Path("data/game_lines.json")
    data = json.loads(path.read_text()) if path.exists() else {}
    rows = data.setdefault(s.value, [])
    for g in parsed:
        rows[:] = [r for r in rows if not (r.get("away") == g["away"] and r.get("home") == g["home"])]
        rows.append(g)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return {"ok": True, "imported": len(parsed), "games": parsed}


@router.get("/games/{sport}", summary="Game-line value model (moneyline)")
def games(sport: str):
    """Season-record moneyline value detector vs operator-supplied game odds.

    Distinct from the player-prop floor model: this bets game outcomes, uses
    team records (not last-N floors), and only flags positive-edge sides.
    """
    from app.games.source import build_game_values

    s = _resolve_sport(sport)
    return build_game_values(s, _BANKROLL["balance"])


@router.post("/floorboard", summary="FanDuel board → floor board → chosen bet")
def floorboard(
    sport: str = Body(...),
    paste: str = Body(default=""),
    mode: str = Body(default="parlay"),   # single | parlay | moneyline
    legs: int = Body(default=3),
    markets: list[str] | None = Body(default=None),
):
    """Parse a pasted FanDuel tiered board, keep tiers cleared in ALL recent
    games (the floor plays), and assemble the bet shape you asked for."""
    from app.board import assemble_bet, build_floor_board, parse_fanduel
    from app.games.source import build_game_values

    s = _resolve_sport(sport)

    if mode == "moneyline":
        games = build_game_values(s, _BANKROLL["balance"]).get("games", [])
        leans = [g for g in games if g.best]
        return {"mode": "moneyline", "picks": [g.best for g in leans] or None,
                "games": games}

    props = parse_fanduel(paste)
    if not props:
        raise HTTPException(status_code=400, detail="No props parsed from the pasted board.")
    board = build_floor_board(s, props)
    bet = assemble_bet(board, legs=1 if mode == "single" else legs,
                       markets=markets, bankroll=_BANKROLL["balance"])
    return {"mode": mode, "parsed_props": len(props), "board_size": len(board),
            "board": [p.as_dict() for p in board], "bet": bet}


@router.post("/games/lines", summary="Add or update a game line (moneyline + total)")
def upsert_game_line(
    sport: str = Body(...),
    away: str = Body(...),
    home: str = Body(...),
    away_ml: int = Body(...),
    home_ml: int = Body(...),
    total: float | None = Body(default=None),
):
    """Persist a game-level line to game_lines.json (matched to the schedule by
    team name). Lets you add moneylines for any sport, e.g. tonight's NBA game."""
    s = _resolve_sport(sport)
    path = Path("data/game_lines.json")
    data = json.loads(path.read_text()) if path.exists() else {}
    rows = data.setdefault(s.value, [])
    entry = {"away": away, "home": home, "away_ml": away_ml, "home_ml": home_ml}
    if total is not None:
        entry["total"] = total
    # Replace an existing matchup, else append.
    rows[:] = [r for r in rows if not (r.get("away") == away and r.get("home") == home)]
    rows.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return {"ok": True, "sport": s.value, "entry": entry}


# --- Odds workflow (operator-supplied lines bridge, SRS §01) ----------------


@router.get("/odds/lines", summary="List all operator-supplied lines")
def list_lines():
    from app.feeds.odds import StaticOddsBook

    path = Path(settings.odds_lines_path)
    rows = StaticOddsBook.from_json(path).as_rows() if path.exists() else []
    return {"path": str(path), "count": len(rows), "lines": rows}


@router.post("/odds/lines", summary="Add or update a line (persists to lines.json)")
def upsert_line(
    sport: str = Body(...),
    player: str = Body(...),
    market: str = Body(...),
    line: float = Body(...),
    odds: int = Body(default=-110),
):
    from app.feeds.odds import upsert_line_file

    s = _resolve_sport(sport)
    if SPORTS[s].stat(market) is None:
        raise HTTPException(status_code=400, detail=f"Unknown market {market!r} for {s.value}.")
    upsert_line_file(settings.odds_lines_path, s.value, player, market, line, odds)
    return {"ok": True, "sport": s.value, "player": player, "market": market, "line": line, "odds": odds}


@router.get("/odds/unpriced/{sport}", summary="Slate markets that still need a line")
def unpriced(sport: str):
    """Players/markets on the current slate with full samples but no line yet."""
    from app.feeds.odds import StaticOddsBook

    s = _resolve_sport(sport)
    provider = get_provider()
    if not hasattr(provider, "candidates"):
        return {"sport": s.value, "unpriced": [], "note": "Provider exposes no candidates."}

    path = Path(settings.odds_lines_path)
    book = StaticOddsBook.from_json(path) if path.exists() else StaticOddsBook()
    missing = [
        c for c in provider.candidates(s)
        if book.line_for(s.value, c["player"], c["market"]) is None
    ]
    return {"sport": s.value, "count": len(missing), "unpriced": missing}

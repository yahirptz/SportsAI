"""REST API routes (SRS §06 — Backend API).

Implements the FastAPI surface described in the SRS. Persistence is stubbed with
an in-memory bankroll and the sample feed; real DB/Obsidian adapters slot behind
these handlers in later phases. Routes that depend on unbuilt infrastructure
(shadow tester, Obsidian rule vault) return a clear "not yet wired" payload
rather than fabricating data.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from app.config import settings
from app.grading import grade_pick
from app.pipeline import build_game_parlay, generate_picks
from app.sample_data import SAMPLE_GAMES, SAMPLE_PROPS
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
    props = SAMPLE_PROPS.get(s, [])
    picks = generate_picks(s, props, _BANKROLL["balance"])
    for p in picks:
        _PICK_INDEX[p.id] = p
    picks.sort(key=lambda p: p.confidence, reverse=True)
    return {"sport": s.value, "count": len(picks), "picks": picks}


@router.post("/parlay/build", summary="Trigger the SGP builder for a game")
def build_parlay_route(
    sport: str = Body(...),
    game_id: str | None = Body(default=None),
):
    s = _resolve_sport(sport)
    game = game_id or SAMPLE_GAMES.get(s)
    if not game:
        raise HTTPException(status_code=400, detail="No game_id provided and no sample game.")
    props = SAMPLE_PROPS.get(s, [])
    parlay = build_game_parlay(s, game, props, _BANKROLL["balance"])
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


@router.post("/picks/{pick_id}/grade", summary="Grade a pick (Result Grader)")
def grade_route(
    pick_id: str,
    actual_value: float = Body(...),
    closing_line: float = Body(...),
):
    pick = _PICK_INDEX.get(pick_id)
    if pick is None:
        raise HTTPException(
            status_code=404,
            detail="Pick not found. Fetch /picks/{sport} first to populate the index.",
        )
    return grade_pick(pick, actual_value, closing_line)  # type: ignore[arg-type]


@router.get("/performance", summary="CLV trend, hit rate, ROI by sport")
def performance():
    # Backed by the outcomes table + Obsidian model-drift notes in a later phase.
    return {
        "status": "pending_data",
        "detail": "Performance analytics populate once graded outcomes accumulate.",
    }


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

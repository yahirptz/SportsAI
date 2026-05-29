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
from app.enrichment import get_enrichment_service
from app.feeds import HEALTH_REGISTRY, get_provider
from app.grading import grade_pick
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
    return {"sport": s.value, "count": len(picks), "enriched": enrichment.enabled, "picks": picks}


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


@router.get("/feed/health", summary="Circuit-breaker status per data source")
def feed_health():
    """Powers the Model Health view (SRS §07) from the feed_health registry."""
    return {"active_provider": get_provider().name, "feeds": HEALTH_REGISTRY.snapshot()}

"""Vault learning-loop tests (offline): patterns + journal."""

import uuid

from app.db.repository import record_outcome, save_picks, set_closing_line
from app.models.schemas import EnrichmentContext, Pick
from app.sports.registry import Sport
from app.vault import compute_patterns, patterns_brief


def _pick(player: str, floor: float, line: float, rest: int | None = None) -> Pick:
    return Pick(
        id=str(uuid.uuid4()), sport=Sport.NBA, game_id="vault-test",
        player_id=player, player_name=player, market="pts", market_label="Points",
        floor=floor, line=line, gap=floor - line, confidence=60.0, odds=-110,
        enrichment=EnrichmentContext(rest_days=rest),
    )


def test_patterns_bucket_by_cushion_and_journal():
    thick = _pick("ThickGuy", floor=20, line=14)   # cushion 6 -> thick (>3)
    thin = _pick("ThinGuy", floor=10.5, line=10)    # cushion 0.5 -> thin (<1)
    save_picks([thick, thin])
    record_outcome(thick.id, actual_value=22)  # win
    record_outcome(thin.id, actual_value=8)    # loss

    p = compute_patterns()
    assert p["total_graded"] >= 2
    assert "thick (>3)" in p["by_cushion"]
    assert "thin (<1)" in p["by_cushion"]
    # the thick winner and thin loser must be reflected per player
    assert p["by_player"]["ThickGuy — Points"]["hit_rate"] == 100.0
    assert p["by_player"]["ThinGuy — Points"]["hit_rate"] == 0.0


def test_closing_line_populates_clv_and_patterns():
    p = _pick("ClvGuy", floor=20, line=14)
    save_picks([p])
    record_outcome(p.id, actual_value=22)  # win
    res = set_closing_line(p.id, 15.0)      # close moved up → beat the line
    assert res is not None and res["clv"] is not None
    pats = compute_patterns()
    assert pats["by_player"]["ClvGuy — Points"]["avg_clv"] is not None


def test_by_rest_bucket_splits_b2b_and_rested():
    save_picks([_pick("B2BGuy", 20, 14, rest=1), _pick("RestedGuy", 20, 14, rest=3)])
    record_outcome("any", actual_value=1)  # no-op for unknown id
    # grade both
    from app.db.repository import open_picks
    for o in open_picks("nba"):
        if o["player_name"] in ("B2BGuy", "RestedGuy"):
            record_outcome(o["id"], actual_value=22)
    rest = compute_patterns()["by_rest"]
    assert "back-to-back (<2)" in rest and "rested (2+)" in rest


def test_patterns_brief_is_text():
    brief = patterns_brief()
    assert isinstance(brief, str) and len(brief) > 0

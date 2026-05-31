"""Vault learning-loop tests (offline): patterns + journal."""

import uuid

from app.db.repository import record_outcome, save_picks
from app.models.schemas import Pick
from app.sports.registry import Sport
from app.vault import compute_patterns, patterns_brief


def _pick(player: str, floor: float, line: float) -> Pick:
    return Pick(
        id=str(uuid.uuid4()), sport=Sport.NBA, game_id="vault-test",
        player_id=player, player_name=player, market="pts", market_label="Points",
        floor=floor, line=line, gap=floor - line, confidence=60.0, odds=-110,
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


def test_patterns_brief_is_text():
    brief = patterns_brief()
    assert isinstance(brief, str) and len(brief) > 0

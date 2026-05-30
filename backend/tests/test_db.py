"""Persistence + grading + performance tests (offline, temp SQLite)."""

import uuid

from app.db.repository import (
    open_picks,
    performance_summary,
    record_outcome,
    save_picks,
)
from app.models.schemas import Pick
from app.sports.registry import Sport


def _pick(player: str, market: str, line: float, floor: float, odds: int = -110) -> Pick:
    return Pick(
        id=str(uuid.uuid4()), sport=Sport.NBA, game_id="game-db-test",
        player_id=player, player_name=player, market=market, market_label=market,
        floor=floor, line=line, gap=floor - line, confidence=60.0, odds=odds,
    )


def test_save_dedupes_and_grades_to_performance():
    p1 = _pick("PlayerA", "pts", 20.5, 24, odds=-110)
    p2 = _pick("PlayerB", "reb", 6.5, 8, odds=+100)
    # Saving twice must not duplicate (same game/player/market/line).
    assert save_picks([p1, p2]) == 2
    assert save_picks([p1, p2]) == 0

    open_before = {o["player_name"] for o in open_picks("nba")}
    assert {"PlayerA", "PlayerB"} <= open_before

    # Grade: A clears its line (win), B misses (loss). Provide a closing line for CLV.
    assert record_outcome(p1.id, actual_value=27, closing_line=21.5)["result"] == "win"
    assert record_outcome(p2.id, actual_value=5)["result"] == "loss"

    perf = performance_summary()
    overall = perf["overall"]
    assert overall["graded"] == 2
    assert overall["wins"] == 1 and overall["losses"] == 1
    assert overall["hit_rate"] == 50.0
    # Win at -110 (+0.91u) minus 1u loss => slightly negative units.
    assert overall["units"] < 0
    assert overall["avg_clv"] is not None  # one pick had a closing line
    assert "nba" in perf["by_sport"]


def test_grade_unknown_pick_returns_none():
    assert record_outcome("does-not-exist", actual_value=1) is None

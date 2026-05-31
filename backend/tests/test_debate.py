"""Debate agent tests (offline — exercises the no-key fallback path)."""

from app.assistant.debate import debate
from app.board.builder import FloorPlay
from app.config import settings


def _play(player, cushion, values):
    return FloorPlay(player=player, market="pts", market_label="Points", threshold=10,
                     line=9.5, odds=-150, floor=9.5 + cushion, hit_count=6, n=6,
                     hit_prob=0.85, cushion=cushion, values=values)


def test_debate_fallback_keeps_all_without_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    plays = [_play("A", 3.0, [13, 14, 12, 15, 13, 14]), _play("B", 0.5, [10, 10, 11, 10, 12, 10])]
    out = debate(plays)
    assert out["survivors"] == {("A", "pts"), ("B", "pts")}
    assert len(out["verdicts"]) == 2


def test_debate_empty():
    assert debate([])["survivors"] == set()

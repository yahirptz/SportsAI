"""Confidence scoring: missing-data signals are redistributed, not zeroed."""

from app.floor.engine import FloorResult
from app.models.schemas import EnrichmentContext
from app.scoring.confidence import score_confidence


def _result(floor=24.0, line=18.5, avg=26.0, lo=22.0, hi=30.0) -> FloorResult:
    return FloorResult(
        player_id="p", player_name="P", stat_key="pts", stat_label="Points",
        line=line, eligible=True, floor=floor, sample_average=avg,
        sample_min=lo, sample_max=hi, gap=floor - line,
    )


def test_missing_market_data_does_not_cap_score():
    # No public% / RLM (live-feed reality). Score should reflect only the signals
    # we have, renormalised — not be dragged down by the missing 15%.
    clean = EnrichmentContext(reddit_sentiment=0.0)  # nothing but the floor/consistency
    b = score_confidence(_result(), clean)
    # Strong floor gap + clean injury, redistributed over 4 signals → well above
    # the old ~70 cap that scoring missing data as zero would have produced.
    assert b.total > 75
    assert 0 <= b.total <= 100


def test_having_public_and_rlm_still_valid():
    enr = EnrichmentContext(reddit_sentiment=0.5, public_bet_pct=30, reverse_line_movement=True)
    b = score_confidence(enr and _result() or _result(), enr)
    assert 0 <= b.total <= 100


def test_ineligible_scores_zero():
    bad = FloorResult(player_id="p", player_name="P", stat_key="pts", stat_label="Points",
                      line=10, eligible=False, floor=None)
    assert score_confidence(bad, EnrichmentContext()).total == 0

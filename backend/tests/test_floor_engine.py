"""Tests for the Floor Model engine.

These tests encode the absolute, non-overridable rules from SRS §04 / §08.
If one of these fails, the floor model is no longer trustworthy — the whole
EdgeIQ premise rests on these invariants.
"""

import pytest

from app.floor.engine import Disqualifier, GameLog, PlayerStatInput, evaluate_stat
from app.sports.registry import Sport, get_config

NBA = get_config(Sport.NBA)
NFL = get_config(Sport.NFL)


def _logs(values: list[float]) -> list[GameLog]:
    return [
        GameLog(game_id=f"g{i}", game_date=f"2026-05-{20 + i:02d}", value=v)
        for i, v in enumerate(values)
    ]


def _input(stat_key: str, line: float, values: list[float], **kw) -> PlayerStatInput:
    return PlayerStatInput(
        player_id="p1",
        player_name="Test Player",
        stat_key=stat_key,
        line=line,
        logs=_logs(values),
        **kw,
    )


# --- Rule 1 & 2: complete N-of-N sample, no misses --------------------------


def test_eligible_counting_stat_clears_line():
    # NBA assists, last 5: min 7, avg 8.4, line 5.5 → floor floor(7)=7, gap 1.5
    result = evaluate_stat(_input("ast", 5.5, [7, 8, 9, 10, 8]), NBA)
    assert result.eligible
    assert result.floor == 7.0
    assert result.gap == 1.5
    assert result.disqualifiers == []


def test_incomplete_sample_is_disqualified():
    result = evaluate_stat(_input("pts", 10.0, [20, 22, 25, 30]), NBA)  # only 4 games
    assert not result.eligible
    assert Disqualifier.INCOMPLETE_SAMPLE in result.disqualifiers


def test_single_miss_in_window_discards_stat():
    # Made-threes: a zero in the window means it missed once → discard.
    result = evaluate_stat(_input("fg3m", 1.5, [3, 2, 0, 4, 3]), NBA)
    assert not result.eligible
    assert Disqualifier.MISSED_IN_WINDOW in result.disqualifiers


# --- Rule 3: yardage floor takes a 10% haircut ------------------------------


def test_yardage_floor_haircut():
    # NFL receiving yards, min 40 → floor 40 * 0.9 = 36.0, line 30 → gap 6.0
    result = evaluate_stat(_input("rec_yds", 30.0, [40, 55, 62, 48, 70]), NFL)
    assert result.eligible
    assert result.floor == 36.0
    assert result.gap == 6.0


# --- Rule 4: counting stats round DOWN --------------------------------------


def test_counting_stat_rounds_down():
    # Receptions min is 4 (already whole) but verify floor stays integer-valued.
    result = evaluate_stat(_input("rec", 2.5, [4, 5, 6, 4, 7]), NFL)
    assert result.eligible
    assert result.floor == 4.0


# --- Rule 5: TD / anytime-scorer eligible only if scored in ALL N -----------


def test_anytime_td_requires_all_games():
    # Scored in 4 of 5 games (one zero) → not eligible.
    miss = evaluate_stat(_input("tds", 0.5, [1, 1, 0, 2, 1]), NFL)
    assert not miss.eligible
    assert Disqualifier.MISSED_IN_WINDOW in miss.disqualifiers

    # Scored in all 5 → eligible, floor is a single occurrence.
    hit = evaluate_stat(_input("tds", 0.5, [1, 2, 1, 1, 1]), NFL)
    assert hit.eligible
    assert hit.floor == 1.0


# --- Rule 6: line above the last-N average is excluded ----------------------


def test_line_above_average_excluded():
    # avg = 8.0, line 9.5 is above average → excluded even though floor clears.
    result = evaluate_stat(_input("pts", 9.5, [8, 8, 8, 8, 8]), NBA)
    assert not result.eligible
    assert Disqualifier.LINE_ABOVE_AVERAGE in result.disqualifiers


# --- Rule 7: any injury flag discards the player ----------------------------


def test_injury_flag_discards():
    result = evaluate_stat(
        _input("pts", 10.0, [20, 22, 25, 30, 28], injury_flag=True), NBA
    )
    assert not result.eligible
    assert Disqualifier.INJURY_FLAG in result.disqualifiers


# --- Rule 8: ceiling props never eligible -----------------------------------


def test_ceiling_prop_never_eligible():
    result = evaluate_stat(_input("longest_rec", 5.0, [12, 20, 18, 25, 30]), NFL)
    assert not result.eligible
    assert Disqualifier.CEILING_PROP in result.disqualifiers


# --- Rule 9: floor must clear the line --------------------------------------


def test_floor_below_line_disqualified():
    # min 6 → floor 6, line 7.5 → floor does not clear line. Line also < avg(7.6)
    # so the only disqualifier is FLOOR_BELOW_LINE.
    result = evaluate_stat(_input("ast", 7.5, [6, 7, 8, 9, 8]), NBA)
    assert not result.eligible
    assert Disqualifier.FLOOR_BELOW_LINE in result.disqualifiers
    assert Disqualifier.LINE_ABOVE_AVERAGE not in result.disqualifiers


# --- Unknown stats are reported, not crashed --------------------------------


def test_unknown_stat_reported():
    result = evaluate_stat(_input("blocks", 1.5, [2, 3, 1, 2, 2]), NBA)
    assert not result.eligible
    assert Disqualifier.UNKNOWN_STAT in result.disqualifiers


# --- Multiple violations are all surfaced -----------------------------------


def test_multiple_disqualifiers_accumulate():
    result = evaluate_stat(
        _input("fg3m", 5.0, [3, 0, 2], injury_flag=True), NBA
    )
    assert not result.eligible
    assert Disqualifier.INJURY_FLAG in result.disqualifiers
    assert Disqualifier.INCOMPLETE_SAMPLE in result.disqualifiers
    assert Disqualifier.MISSED_IN_WINDOW in result.disqualifiers


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

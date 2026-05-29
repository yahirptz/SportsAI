"""Result Grader agent (SRS §04 / §05 learning loop).

Grades a pick against its actual result and computes Closing Line Value (CLV) —
the edge captured between the line we took and the closing line. CLV is tracked
on every single bet (a core differentiator in SRS §01) and is what the Weekly
Debrief Agent and Kelly Sizer read back from Obsidian.
"""

from __future__ import annotations

from app.models.schemas import Outcome, Pick


def compute_clv(line_taken: float, closing_line: float) -> float:
    """CLV as the percentage edge of our line vs the closing line.

    For an OVER bet, a *lower* closing line than the one we took is favorable
    (the market moved toward us). Positive CLV = we beat the close.
    """
    if closing_line <= 0:
        return 0.0
    return round((closing_line - line_taken) / closing_line * 100, 2)


def grade_pick(pick: Pick, actual_value: float, closing_line: float) -> Outcome:
    """Grade an OVER pick: win if the actual value cleared the line we took."""
    if actual_value > pick.line:
        result = "win"
    elif actual_value == pick.line:
        result = "push"
    else:
        result = "loss"

    return Outcome(
        pick_id=pick.id,
        result=result,
        closing_line=closing_line,
        clv=compute_clv(pick.line, closing_line),
    )

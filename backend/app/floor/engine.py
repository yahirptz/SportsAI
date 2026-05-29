"""Floor Model engine.

SRS §04 states: *"The floor model is the foundation of the entire system. These
rules are absolute and cannot be overridden by any enrichment signal, user
preference, or operator configuration."*

This module is intentionally pure: no I/O, no database, no network. It takes a
player's last-N game logs for a single stat plus the current sportsbook line,
and returns a :class:`FloorResult` describing whether the stat is eligible to
become a parlay leg and — if so — its verified floor and the floor/line gap.

The absolute rules (SRS §04 Floor Model Rules + §08 Hard Exclusions):

1. A stat is ELIGIBLE only if it occurred in N-of-N games for the sport's window.
2. If a stat missed once in the sample window — permanently discard it.
3. Floor = LOWEST value in the window, minus 10% for yardage stats.
4. Counting stats round DOWN to the nearest whole number.
5. TD / anytime-scorer props are eligible only if achieved in ALL N games.
6. Lines ABOVE the last-N average are automatically excluded.
7. Players with ANY injury tag or snap-limitation flag are discarded entirely.
8. Ceiling-based props (longest rush/reception) are never eligible.
9. The pick only qualifies if the floor clears the line (floor >= line).
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, Field

from app.sports.registry import SportConfig, StatKind, StatSpec

YARDAGE_FLOOR_HAIRCUT = 0.10  # 10% haircut applied to yardage floors (rule 3).


class Disqualifier(str, Enum):
    """Reasons a stat fails to become an eligible parlay leg."""

    INCOMPLETE_SAMPLE = "incomplete_sample"
    MISSED_IN_WINDOW = "missed_in_window"
    CEILING_PROP = "ceiling_prop"
    INJURY_FLAG = "injury_flag"
    LINE_ABOVE_AVERAGE = "line_above_average"
    FLOOR_BELOW_LINE = "floor_below_line"
    UNKNOWN_STAT = "unknown_stat"


class GameLog(BaseModel):
    """A single game's value for one stat, ordered most-recent-first by caller."""

    game_id: str
    game_date: str
    value: float


class PlayerStatInput(BaseModel):
    """Everything the floor model needs to evaluate one stat for one player."""

    player_id: str
    player_name: str
    stat_key: str
    line: float = Field(..., description="Current sportsbook over/under line.")
    logs: list[GameLog]
    injury_flag: bool = Field(
        default=False, description="Any injury tag or snap-limitation flag."
    )


class FloorResult(BaseModel):
    """The floor model's verdict on a single stat."""

    player_id: str
    player_name: str
    stat_key: str
    stat_label: str
    line: float
    eligible: bool
    floor: float | None = None
    sample_average: float | None = None
    sample_min: float | None = None
    sample_max: float | None = None
    gap: float | None = Field(
        default=None, description="floor - line; how far the floor clears the line."
    )
    disqualifiers: list[Disqualifier] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def _round_floor(value: float, kind: StatKind) -> float:
    """Apply the per-kind floor transform (rules 3 & 4)."""
    if kind is StatKind.YARDAGE:
        return round(value * (1 - YARDAGE_FLOOR_HAIRCUT), 2)
    if kind is StatKind.COUNTING:
        return float(math.floor(value))
    if kind is StatKind.SCORING:
        # Anytime-scorer floor is a single occurrence (eligibility already
        # guarantees value >= 1 in all N games).
        return 1.0
    return round(value, 2)


def evaluate_stat(stat_input: PlayerStatInput, config: SportConfig) -> FloorResult:
    """Evaluate one stat against the absolute floor model rules.

    The function never raises for ordinary disqualification; it returns a
    :class:`FloorResult` with ``eligible=False`` and the reasons. It only fails
    loudly for programmer error (a stat key that isn't in the sport schema is
    reported as a disqualifier rather than an exception).
    """
    spec: StatSpec | None = config.stat(stat_input.stat_key)
    if spec is None:
        return FloorResult(
            player_id=stat_input.player_id,
            player_name=stat_input.player_name,
            stat_key=stat_input.stat_key,
            stat_label=stat_input.stat_key,
            line=stat_input.line,
            eligible=False,
            disqualifiers=[Disqualifier.UNKNOWN_STAT],
            reasons=[f"Stat {stat_input.stat_key!r} is not in the {config.label} schema."],
        )

    disqualifiers: list[Disqualifier] = []
    reasons: list[str] = []
    values = [log.value for log in stat_input.logs]

    sample_average = sample_min = sample_max = None
    if values:
        sample_average = round(sum(values) / len(values), 2)
        sample_min = min(values)
        sample_max = max(values)

    # Rule 7 — any injury / snap-limitation flag discards the player entirely.
    if stat_input.injury_flag:
        disqualifiers.append(Disqualifier.INJURY_FLAG)
        reasons.append("Player carries an injury or snap-limitation flag — discarded.")

    # Rule 8 — ceiling props are never eligible.
    if spec.ceiling_prop:
        disqualifiers.append(Disqualifier.CEILING_PROP)
        reasons.append(f"{spec.label} is a ceiling-based prop — never eligible.")

    # Rule 1 — require a complete N-of-N sample.
    if len(values) < config.sample_window:
        disqualifiers.append(Disqualifier.INCOMPLETE_SAMPLE)
        reasons.append(
            f"Only {len(values)} of required {config.sample_window} games available."
        )

    # Rules 1, 2 & 5 — the stat must have occurred (value >= 1) in every game in
    # the window. A single miss permanently discards it. This also enforces the
    # all-N requirement for SCORING (TD / anytime-scorer) props.
    if values and any(v < 1 for v in values):
        disqualifiers.append(Disqualifier.MISSED_IN_WINDOW)
        if spec.kind is StatKind.SCORING:
            reasons.append(f"{spec.label} not achieved in all {config.sample_window} games.")
        else:
            reasons.append(f"{spec.label} missed at least one game in the window.")

    # Rule 6 — a line above the last-N average is automatically excluded.
    if sample_average is not None and stat_input.line > sample_average:
        disqualifiers.append(Disqualifier.LINE_ABOVE_AVERAGE)
        reasons.append(
            f"Line {stat_input.line} is above the last-{config.sample_window} "
            f"average {sample_average} — excluded."
        )

    floor: float | None = None
    gap: float | None = None
    if sample_min is not None:
        floor = _round_floor(sample_min, spec.kind)
        gap = round(floor - stat_input.line, 2)
        # Rule 9 — the floor must clear the line for the pick to qualify.
        if floor < stat_input.line:
            disqualifiers.append(Disqualifier.FLOOR_BELOW_LINE)
            reasons.append(
                f"Verified floor {floor} does not clear the line {stat_input.line}."
            )

    eligible = not disqualifiers
    if eligible:
        reasons.append(
            f"Eligible: floor {floor} clears line {stat_input.line} "
            f"(gap {gap}); occurred in all {config.sample_window} games."
        )

    return FloorResult(
        player_id=stat_input.player_id,
        player_name=stat_input.player_name,
        stat_key=stat_input.stat_key,
        stat_label=spec.label,
        line=stat_input.line,
        eligible=eligible,
        floor=floor if eligible else None,
        sample_average=sample_average,
        sample_min=sample_min,
        sample_max=sample_max,
        gap=gap,
        disqualifiers=disqualifiers,
        reasons=reasons,
    )

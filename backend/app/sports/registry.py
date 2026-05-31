"""Sport configuration registry.

Implements SRS §02 (Scope & Sports Coverage) and the Sport Router agent's
configuration injection (SRS §04). Every sport has its own sample window, stat
schema, primary data source, subreddit list, and exclusion rules. The Floor
Model engine consumes a :class:`SportConfig` to decide eligibility and floors.

v1.0 (Q3 2026 roadmap) ships NBA + NFL as the active sports; the remaining
sports are configured here so the router and floor model are multi-sport from
day one, but they are flagged ``active=False`` until their data feeds land.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Sport(str, Enum):
    """Canonical sport identifiers used across the platform."""

    NBA = "nba"
    NFL = "nfl"
    MLB = "mlb"
    NHL = "nhl"
    EPL = "epl"
    CFB = "cfb"
    TENNIS = "tennis"
    GOLF = "golf"
    MMA = "mma"
    NASCAR = "nascar"


class StatKind(str, Enum):
    """How a stat is treated by the floor model rules (SRS §04, Floor Model Rules).

    - ``YARDAGE``: floor is the sample minimum minus 10%.
    - ``COUNTING``: floor is the sample minimum rounded DOWN to a whole number.
    - ``SCORING``: TD / anytime-scorer style props. Eligible only if achieved
      (value >= 1) in ALL N sample games; floor is effectively 1 occurrence.
    - ``RATE``: everything else (e.g. saves%, speed) — floor is the raw minimum.
    """

    YARDAGE = "yardage"
    COUNTING = "counting"
    SCORING = "scoring"
    RATE = "rate"


class StatSpec(BaseModel):
    """A single bettable stat within a sport's schema."""

    key: str = Field(..., description="Stable stat key, e.g. 'rec_yds'.")
    label: str = Field(..., description="Human-readable label, e.g. 'Receiving Yards'.")
    kind: StatKind
    ceiling_prop: bool = Field(
        default=False,
        description="Ceiling-based props (longest rush/reception). Hard-excluded.",
    )

    model_config = {"frozen": True}


class SportConfig(BaseModel):
    """Per-sport agent configuration injected before the floor model runs."""

    sport: Sport
    label: str
    sample_window: int = Field(..., gt=0, description="N — the last-N game window.")
    same_context_required: bool = Field(
        default=False,
        description="If true, the N games must share context (surface/track/format).",
    )
    context_label: str | None = Field(
        default=None, description="What 'same context' means, e.g. 'surface'."
    )
    stats: list[StatSpec]
    primary_source: str
    subreddits: list[str]
    exclusion_rules: list[str] = Field(default_factory=list)
    active: bool = Field(default=False, description="Whether the sport is live in this release.")

    model_config = {"frozen": True}

    def stat(self, key: str) -> StatSpec | None:
        return next((s for s in self.stats if s.key == key), None)


# Shared exclusions enforced for every sport (SRS §08 Hard Exclusions).
_GLOBAL_EXCLUSIONS = [
    "Never use season averages, projections, or narrative context.",
    "Never surface a line above the last-N game average.",
    "Never use longest-rush / longest-reception or other ceiling props.",
    "Never include anytime-TD props unless scored in all N sample games.",
    "Never build a parlay with negatively correlated legs.",
]


def _yds(key: str, label: str) -> StatSpec:
    return StatSpec(key=key, label=label, kind=StatKind.YARDAGE)


def _count(key: str, label: str) -> StatSpec:
    return StatSpec(key=key, label=label, kind=StatKind.COUNTING)


def _score(key: str, label: str) -> StatSpec:
    return StatSpec(key=key, label=label, kind=StatKind.SCORING)


def _rate(key: str, label: str) -> StatSpec:
    return StatSpec(key=key, label=label, kind=StatKind.RATE)


SPORTS: dict[Sport, SportConfig] = {
    Sport.NBA: SportConfig(
        sport=Sport.NBA,
        label="NBA",
        sample_window=5,
        stats=[
            _count("pts", "Points"),
            _count("reb", "Rebounds"),
            _count("ast", "Assists"),
            _count("fg3m", "3-Pointers Made"),
            _count("pra", "Points + Rebounds + Assists"),
            _count("pa", "Points + Assists"),
            _count("ra", "Rebounds + Assists"),
        ],
        primary_source="SportRadar",
        subreddits=["r/sportsbook", "r/nbabetting", "r/nba"],
        exclusion_rules=_GLOBAL_EXCLUSIONS,
        active=True,
    ),
    Sport.NFL: SportConfig(
        sport=Sport.NFL,
        label="NFL",
        sample_window=5,
        stats=[
            _yds("pass_yds", "Passing Yards"),
            _yds("rush_yds", "Rushing Yards"),
            _yds("rec_yds", "Receiving Yards"),
            _count("rec", "Receptions"),
            _score("tds", "Anytime Touchdown"),
            StatSpec(
                key="longest_rush",
                label="Longest Rush",
                kind=StatKind.YARDAGE,
                ceiling_prop=True,
            ),
            StatSpec(
                key="longest_rec",
                label="Longest Reception",
                kind=StatKind.YARDAGE,
                ceiling_prop=True,
            ),
        ],
        primary_source="SportRadar",
        subreddits=["r/sportsbook", "r/nflbetting", "r/nfl"],
        exclusion_rules=_GLOBAL_EXCLUSIONS,
        active=True,
    ),
    Sport.MLB: SportConfig(
        sport=Sport.MLB,
        label="MLB",
        sample_window=10,
        stats=[
            _count("hits", "Hits"),
            _count("rbi", "RBI"),
            _count("runs", "Runs"),
            _count("tb", "Total Bases"),
            _count("k_pitcher", "Strikeouts (Pitcher)"),
            _count("bb", "Walks"),
        ],
        primary_source="SportRadar",
        subreddits=["r/sportsbook", "r/mlbbetting", "r/baseball"],
        exclusion_rules=_GLOBAL_EXCLUSIONS,
        active=True,
    ),
    Sport.NHL: SportConfig(
        sport=Sport.NHL,
        label="NHL",
        sample_window=5,
        stats=[
            _count("shots", "Shots on Goal"),
            _count("pts", "Points"),
            _score("goals", "Goals"),
            _count("ast", "Assists"),
            _count("saves", "Saves"),
        ],
        primary_source="SportRadar",
        subreddits=["r/sportsbook", "r/hockey"],
        exclusion_rules=_GLOBAL_EXCLUSIONS,
        active=True,
    ),
    Sport.EPL: SportConfig(
        sport=Sport.EPL,
        label="Soccer / EPL",
        sample_window=5,
        stats=[
            _count("shots", "Shots"),
            _count("sot", "Shots on Target"),
            _count("passes", "Passes"),
            _score("goals", "Goals"),
            _count("ast", "Assists"),
        ],
        primary_source="Opta / Stats Perform",
        subreddits=["r/sportsbook", "r/soccerbetting", "r/soccer"],
        exclusion_rules=_GLOBAL_EXCLUSIONS,
    ),
    Sport.CFB: SportConfig(
        sport=Sport.CFB,
        label="College Football",
        sample_window=3,
        stats=[
            _yds("pass_yds", "Passing Yards"),
            _yds("rush_yds", "Rushing Yards"),
            _yds("rec_yds", "Receiving Yards"),
        ],
        primary_source="SportRadar College",
        subreddits=["r/sportsbook", "r/CFB"],
        exclusion_rules=_GLOBAL_EXCLUSIONS,
    ),
    Sport.TENNIS: SportConfig(
        sport=Sport.TENNIS,
        label="Tennis",
        sample_window=5,
        same_context_required=True,
        context_label="surface",
        stats=[
            _count("aces", "Aces"),
            _count("dfs", "Double Faults"),
            _count("games_won", "Games Won"),
            _count("sets_won", "Sets Won"),
        ],
        primary_source="ATP/WTA / SportRadar",
        subreddits=["r/sportsbook", "r/tennis"],
        exclusion_rules=_GLOBAL_EXCLUSIONS,
    ),
    Sport.GOLF: SportConfig(
        sport=Sport.GOLF,
        label="Golf",
        sample_window=6,
        stats=[
            _count("birdies", "Birdies"),
            _count("bogeys", "Bogeys"),
            _rate("fir", "Fairways in Regulation"),
            _rate("gir", "Greens in Regulation"),
        ],
        primary_source="PGA ShotLink",
        subreddits=["r/sportsbook", "r/golf"],
        exclusion_rules=_GLOBAL_EXCLUSIONS,
    ),
    Sport.MMA: SportConfig(
        sport=Sport.MMA,
        label="MMA / UFC",
        sample_window=3,
        same_context_required=True,
        context_label="format",
        stats=[
            _count("strikes", "Significant Strikes"),
            _count("td", "Takedowns"),
            _count("sub_attempts", "Submission Attempts"),
        ],
        primary_source="UFC Stats API",
        subreddits=["r/sportsbook", "r/MMA", "r/ufc"],
        exclusion_rules=_GLOBAL_EXCLUSIONS,
    ),
    Sport.NASCAR: SportConfig(
        sport=Sport.NASCAR,
        label="NASCAR",
        sample_window=5,
        same_context_required=True,
        context_label="track type",
        stats=[
            _count("laps_led", "Laps Led"),
            _count("finish_pos", "Finish Position"),
            _rate("speed", "Average Speed"),
        ],
        primary_source="NASCAR Official API",
        subreddits=["r/sportsbook", "r/NASCAR"],
        exclusion_rules=_GLOBAL_EXCLUSIONS,
    ),
}


def get_config(sport: Sport | str) -> SportConfig:
    """Return the config for a sport, raising ``KeyError`` if unknown."""
    if isinstance(sport, str):
        sport = Sport(sport.lower())
    return SPORTS[sport]


def route_sport(sport: Sport | str) -> SportConfig:
    """Sport Router agent entry point (SRS §04).

    Resolves the sport and returns its fully-loaded config (stat schema +
    exclusion rules) ready for injection into the agent context. Raises
    ``ValueError`` for an unknown or inactive sport so the pipeline hard-stops
    before the floor model runs.
    """
    try:
        config = get_config(sport)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Unknown sport: {sport!r}") from exc
    if not config.active:
        raise ValueError(
            f"Sport {config.label!r} is configured but not active in this release."
        )
    return config

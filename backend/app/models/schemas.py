"""Core domain models shared across agents, the API, and persistence.

These mirror the PostgreSQL schema in SRS §06 but live as Pydantic models so the
in-memory pipeline and the REST layer share one source of truth. Persistence
adapters map these to/from the database in a later phase.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from app.sports.registry import Sport


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EnrichmentContext(BaseModel):
    """Layer-2 enrichment signals attached to a pick (SRS §02 Layer 2).

    Per the hard exclusions, none of these may override the floor model. They
    only modulate the confidence score and are logged for pattern tracking.
    """

    injury_flag: bool = Field(default=False, description="Perplexity injury/lineup flag.")
    perplexity_summary: str | None = None
    reddit_sentiment: float = Field(
        default=0.0, ge=-1.0, le=1.0, description="-1..+1 sentiment from Layer 2."
    )
    public_bet_pct: float | None = Field(
        default=None, ge=0, le=100, description="Public ticket % on the model's side."
    )
    public_money_pct: float | None = Field(default=None, ge=0, le=100)
    reverse_line_movement: bool = Field(
        default=False, description="Sharp money aligned against public (with model)."
    )


class PickStatus(str, Enum):
    CANDIDATE = "candidate"  # Passed the floor model, not yet in a slip.
    SLIPPED = "slipped"  # Added to a parlay.
    GRADED = "graded"  # Outcome recorded.


class Pick(BaseModel):
    """A single floor-verified pick (one parlay leg). Mirrors the `picks` table."""

    id: str
    sport: Sport
    game_id: str
    player_id: str
    player_name: str
    market: str  # stat key, e.g. "rec_yds"
    market_label: str
    floor: float
    line: float
    gap: float
    sample_average: float | None = None
    confidence: float = Field(..., ge=0, le=100)
    kelly_stake: float = 0.0
    odds: int | None = Field(default=None, description="American odds for the leg.")
    status: PickStatus = PickStatus.CANDIDATE
    enrichment: EnrichmentContext = Field(default_factory=EnrichmentContext)
    created_at: datetime = Field(default_factory=_utcnow)


class ParlayLeg(BaseModel):
    pick_id: str
    player_name: str
    market_label: str
    floor: float
    line: float
    confidence: float


class Parlay(BaseModel):
    """A same-game parlay assembled by the SGP Builder (SRS §04)."""

    id: str
    sport: Sport
    game_id: str
    legs: list[ParlayLeg]
    combined_confidence: float
    recommended_stake: float
    no_bet: bool = Field(default=False, description="True if < required legs qualified.")
    reason: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Outcome(BaseModel):
    """A graded result written back by the Result Grader (SRS §05 loop)."""

    pick_id: str
    result: str  # "win" | "loss" | "push"
    closing_line: float
    clv: float = Field(..., description="Closing line value vs the line we took.")
    graded_at: datetime = Field(default_factory=_utcnow)

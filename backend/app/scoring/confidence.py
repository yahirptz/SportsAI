"""Confidence Scorer agent (SRS §04 — Confidence Scoring).

Every pick receives a 0–100 score across six weighted factors. Each factor is
normalised to 0..1, multiplied by its weight, and summed to 100. Enrichment
signals may only *modulate* the score — they can never make an ineligible pick
eligible (that is the floor model's exclusive job).

    Floor gap                 30%   larger gap = higher confidence
    Sample consistency        25%   tighter last-N range = higher confidence
    Perplexity enrichment     20%   clean injury/lineup check = higher
    Reddit sentiment          10%   agreement with model = marginal boost
    Public % fade             10%   heavy public on the other side = boost
    Reverse line movement      5%   sharp money aligned with model = boost
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.floor.engine import FloorResult
from app.models.schemas import EnrichmentContext

WEIGHTS = {
    "floor_gap": 0.30,
    "consistency": 0.25,
    "perplexity": 0.20,
    "reddit": 0.10,
    "public_fade": 0.10,
    "rlm": 0.05,
}

# Haircut applied when a player is on a back-to-back / < 2 days rest.
REST_FATIGUE_DISCOUNT = 0.90


class ConfidenceBreakdown(BaseModel):
    """Per-factor contributions, useful for the Agent Feed reasoning summary."""

    floor_gap: float
    consistency: float
    perplexity: float
    reddit: float
    public_fade: float
    rlm: float
    total: float = Field(..., ge=0, le=100)


def _floor_gap_score(floor: float, line: float) -> float:
    """Normalise the floor/line gap relative to the line.

    A gap of >= 25% of the line saturates to 1.0; no gap scores 0.
    """
    if line <= 0:
        return 1.0 if floor > 0 else 0.0
    rel_gap = (floor - line) / line
    return max(0.0, min(1.0, rel_gap / 0.25))


def _consistency_score(result: FloorResult) -> float:
    """Tighter last-N range => higher score. Uses (max-min)/avg as spread."""
    if result.sample_average in (None, 0) or result.sample_max is None or result.sample_min is None:
        return 0.5
    spread = (result.sample_max - result.sample_min) / result.sample_average
    # spread of 0 => 1.0; spread of >=1.0 (range as wide as the mean) => 0.0
    return max(0.0, min(1.0, 1.0 - spread))


def _public_fade_score(enrichment: EnrichmentContext) -> float:
    """Heavy public money on the *other* side is a fade opportunity.

    ``public_bet_pct`` is the public's share on the model's side, so a *low*
    value means the public is fading us (good). 30% or less saturates to 1.0.
    """
    if enrichment.public_bet_pct is None:
        return 0.5
    contra = (100 - enrichment.public_bet_pct) / 100  # public share against us
    return max(0.0, min(1.0, (contra - 0.5) / 0.2)) if contra > 0.5 else 0.0


def score_confidence(result: FloorResult, enrichment: EnrichmentContext) -> ConfidenceBreakdown:
    """Compute the weighted 0–100 confidence score for an eligible pick."""
    if not result.eligible or result.floor is None:
        return ConfidenceBreakdown(
            floor_gap=0, consistency=0, perplexity=0, reddit=0, public_fade=0, rlm=0, total=0
        )

    floor_gap = _floor_gap_score(result.floor, result.line)
    consistency = _consistency_score(result)
    perplexity = 0.0 if enrichment.injury_flag else 1.0
    reddit = max(0.0, enrichment.reddit_sentiment)
    public_fade = _public_fade_score(enrichment)
    rlm = 1.0 if enrichment.reverse_line_movement else 0.0

    raw = {"floor_gap": floor_gap, "consistency": consistency, "perplexity": perplexity,
           "reddit": reddit, "public_fade": public_fade, "rlm": rlm}

    # Only score signals we actually have. Public % and reverse-line-movement need
    # a market-data feed we don't have yet, so when absent we redistribute their
    # weight across the available signals instead of scoring them as zero — that
    # way missing data doesn't cap the score (it's "confidence given what we see").
    available = {"floor_gap", "consistency", "perplexity", "reddit"}
    if enrichment.public_bet_pct is not None:
        available.add("public_fade")
    if enrichment.reverse_line_movement:
        available.add("rlm")

    avail_total = sum(WEIGHTS[k] for k in available)
    eff = {k: WEIGHTS[k] / avail_total for k in available}  # renormalised to sum 1
    contributions = {k: raw[k] * eff.get(k, 0.0) for k in raw}
    total = sum(contributions.values()) * 100

    # Fatigue: a player on a back-to-back / < 2 days rest is a lower-confidence
    # leg (days-rest logic adapted from kyleskom's Add_Days_Rest).
    if enrichment.rest_days is not None and enrichment.rest_days < 2:
        total *= REST_FATIGUE_DISCOUNT
    total = round(total, 1)

    return ConfidenceBreakdown(
        floor_gap=round(contributions["floor_gap"] * 100, 1),
        consistency=round(contributions["consistency"] * 100, 1),
        perplexity=round(contributions["perplexity"] * 100, 1),
        reddit=round(contributions["reddit"] * 100, 1),
        public_fade=round(contributions["public_fade"] * 100, 1),
        rlm=round(contributions["rlm"] * 100, 1),
        total=total,
    )

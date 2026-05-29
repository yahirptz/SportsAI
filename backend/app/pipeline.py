"""Pick generation pipeline — the agent chain wired end to end.

Mirrors the data flow of SRS §04: Sport Router → Floor Model → Odds Scanner →
Confidence Scorer → Kelly Sizer → SGP Builder. This in-memory implementation
runs the pure-Python agents over a data provider; live feed adapters
(SportRadar, OddsJam, etc.) implement the same provider interface in a later
phase.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.floor.engine import GameLog, PlayerStatInput, evaluate_stat
from app.models.schemas import EnrichmentContext, Parlay, Pick, PickStatus
from app.parlay.builder import CorrelationMatrix, build_parlay
from app.scoring.confidence import score_confidence
from app.scoring.kelly import kelly_stake
from app.sports.registry import Sport, route_sport


@dataclass
class PropInput:
    """One raw prop to evaluate: stat logs + live line + enrichment + odds."""

    game_id: str
    player_id: str
    player_name: str
    stat_key: str
    line: float
    odds: int
    logs: list[GameLog]
    enrichment: EnrichmentContext = field(default_factory=EnrichmentContext)


def generate_picks(
    sport: Sport | str,
    props: list[PropInput],
    bankroll: float,
    enrichment=None,
) -> list[Pick]:
    """Run the agent chain over raw props and return eligible, scored picks.

    Ineligible props are dropped (the floor model is the gatekeeper). Eligible
    picks carry their confidence score and Kelly stake. When an enrichment
    service is supplied and enabled, each unique player is enriched once (cached)
    with injury/lineup facts and sentiment BEFORE the floor model runs — so an
    injury flag hard-stops the leg, exactly per SRS §02/§04.
    """
    config = route_sport(sport)
    picks: list[Pick] = []
    enriched: dict[str, dict] = {}

    for prop in props:
        ctx = prop.enrichment
        if enrichment is not None and enrichment.enabled:
            if prop.player_name not in enriched:
                enriched[prop.player_name] = enrichment.enrich_player(
                    prop.player_name, config.label, config.subreddits
                )
            e = enriched[prop.player_name]
            ctx = ctx.model_copy(
                update={
                    "injury_flag": e["injury_flag"],
                    "perplexity_summary": e["perplexity_summary"],
                    "reddit_sentiment": e["reddit_sentiment"],
                }
            )

        stat_input = PlayerStatInput(
            player_id=prop.player_id,
            player_name=prop.player_name,
            stat_key=prop.stat_key,
            line=prop.line,
            logs=prop.logs,
            injury_flag=ctx.injury_flag,
        )
        result = evaluate_stat(stat_input, config)
        if not result.eligible or result.floor is None:
            continue

        breakdown = score_confidence(result, ctx)
        stake = kelly_stake(breakdown.total, bankroll, prop.odds)
        spec = config.stat(prop.stat_key)

        picks.append(
            Pick(
                id=str(uuid.uuid4()),
                sport=config.sport,
                game_id=prop.game_id,
                player_id=prop.player_id,
                player_name=prop.player_name,
                market=prop.stat_key,
                market_label=spec.label if spec else prop.stat_key,
                floor=result.floor,
                line=result.line,
                gap=result.gap or 0.0,
                sample_average=result.sample_average,
                confidence=breakdown.total,
                kelly_stake=stake,
                odds=prop.odds,
                status=PickStatus.CANDIDATE,
                enrichment=ctx,
            )
        )

    return picks


def attach_reasoning(picks: list[Pick], enrichment, limit: int) -> list[Pick]:
    """Generate Claude 'why this pick' summaries for the top-N picks (cost-bounded)."""
    if enrichment is None or not enrichment.enabled:
        return picks
    for p in sorted(picks, key=lambda x: x.confidence, reverse=True)[:limit]:
        facts = (
            f"{p.player_name} — {p.market_label}. Verified floor {p.floor} clears the "
            f"line {p.line} (gap {p.gap}). Last-N average {p.sample_average}. "
            f"Reddit sentiment {p.enrichment.reddit_sentiment}. "
            f"News: {p.enrichment.perplexity_summary or 'no flags'}."
        )
        p.reasoning = enrichment.reason(facts)
    return picks


def build_game_parlay(
    sport: Sport | str,
    game_id: str,
    props: list[PropInput],
    bankroll: float,
    matrix: CorrelationMatrix | None = None,
) -> Parlay:
    """Generate picks for a game and assemble the same-game parlay."""
    config = route_sport(sport)
    candidates = [p for p in generate_picks(sport, props, bankroll) if p.game_id == game_id]
    return build_parlay(game_id, config.sport, candidates, bankroll=bankroll, matrix=matrix)

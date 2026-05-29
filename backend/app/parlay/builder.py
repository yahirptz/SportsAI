"""SGP Builder agent (SRS §04).

Constructs a same-game parlay from floor-verified pick candidates while honoring
two absolute rules:

  - Never build a parlay with negatively correlated legs (SRS §08).
  - If fewer than the required number of legs pass all filters: NO BET — never
    force a parlay (SRS §04 / §08).

Correlations come from the weekly-rebuilt ``correlation_matrix`` hypertable
(SRS §03). Here we model it as a pluggable lookup so the builder can run against
live data or a fixture.
"""

from __future__ import annotations

import uuid

from app.config import settings
from app.models.schemas import Parlay, ParlayLeg, Pick
from app.scoring.kelly import american_to_decimal


class CorrelationMatrix:
    """Pairwise correlation lookup keyed by (player_id, market)."""

    def __init__(self, pairs: dict[tuple[str, str], float] | None = None) -> None:
        # Symmetric storage of correlation between two "player:market" legs.
        self._pairs: dict[frozenset[str], float] = {}
        if pairs:
            for (a, b), corr in pairs.items():
                self._pairs[frozenset({a, b})] = corr

    @staticmethod
    def _key(pick: Pick) -> str:
        return f"{pick.player_id}:{pick.market}"

    def correlation(self, a: Pick, b: Pick) -> float:
        return self._pairs.get(frozenset({self._key(a), self._key(b)}), 0.0)

    def negatively_correlated(self, a: Pick, b: Pick) -> bool:
        return self.correlation(a, b) < settings.min_correlation_for_block


def build_parlay(
    game_id: str,
    sport,
    candidates: list[Pick],
    *,
    bankroll: float,
    matrix: CorrelationMatrix | None = None,
    legs_required: int | None = None,
) -> Parlay:
    """Assemble the highest-confidence non-negatively-correlated parlay.

    Greedily adds candidates by descending confidence, skipping any leg that is
    negatively correlated with an already-selected leg. Returns a NO BET parlay
    if the required leg count cannot be reached.
    """
    matrix = matrix or CorrelationMatrix()
    legs_required = legs_required or settings.parlay_legs

    ranked = sorted(candidates, key=lambda p: p.confidence, reverse=True)
    selected: list[Pick] = []
    for pick in ranked:
        if any(matrix.negatively_correlated(pick, chosen) for chosen in selected):
            continue
        selected.append(pick)
        if len(selected) == legs_required:
            break

    if len(selected) < legs_required:
        return Parlay(
            id=str(uuid.uuid4()),
            sport=sport,
            game_id=game_id,
            legs=[],
            combined_confidence=0.0,
            recommended_stake=0.0,
            no_bet=True,
            reason=(
                f"Only {len(selected)} of required {legs_required} legs passed all "
                f"filters. NO BET — parlay not forced."
            ),
        )

    legs = [
        ParlayLeg(
            pick_id=p.id,
            player_name=p.player_name,
            market_label=p.market_label,
            floor=p.floor,
            line=p.line,
            confidence=p.confidence,
        )
        for p in selected
    ]

    # Combined win probability assumes independence once negatively correlated
    # legs are excluded. Stake uses fractional Kelly on the parlay price.
    combined_p = 1.0
    decimal = 1.0
    for p in selected:
        combined_p *= p.confidence / 100.0
        decimal *= american_to_decimal(p.odds) if p.odds else 1.9

    b = decimal - 1
    f_star = max(0.0, (b * combined_p - (1 - combined_p)) / b) if b > 0 else 0.0
    stake = round(min(bankroll * settings.kelly_fraction * f_star, bankroll * settings.max_stake_pct), 2)

    return Parlay(
        id=str(uuid.uuid4()),
        sport=sport,
        game_id=game_id,
        legs=legs,
        combined_confidence=round(combined_p * 100, 1),
        recommended_stake=stake,
        no_bet=False,
        reason=f"{legs_required}-leg parlay built at decimal odds {round(decimal, 2)}.",
    )

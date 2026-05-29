"""Kelly Sizer agent (SRS §04 — Kelly Sizer).

Computes a recommended stake from confidence + bankroll using a fractional
Kelly criterion. Confidence (0–100) is treated as the model's win probability;
the sizer is deliberately conservative:

    full Kelly fraction  f* = (b * p - q) / b
    recommended stake    = bankroll * kelly_fraction * max(0, f*)

clamped to ``max_stake_pct`` of bankroll (SRS §08 responsible-gambling cap).
"""

from __future__ import annotations

from app.config import settings


def american_to_decimal(odds: int) -> float:
    """Convert American odds to decimal payout multiplier (incl. stake)."""
    if odds > 0:
        return 1 + odds / 100
    return 1 + 100 / abs(odds)


def kelly_stake(
    confidence: float,
    bankroll: float,
    odds: int,
    *,
    kelly_fraction: float | None = None,
    max_stake_pct: float | None = None,
) -> float:
    """Return the recommended stake in bankroll currency.

    ``confidence`` is the 0–100 score; ``odds`` are American odds for the leg.
    Returns 0 if there is no positive edge at the given price.
    """
    kelly_fraction = settings.kelly_fraction if kelly_fraction is None else kelly_fraction
    max_stake_pct = settings.max_stake_pct if max_stake_pct is None else max_stake_pct

    p = max(0.0, min(1.0, confidence / 100.0))
    q = 1 - p
    decimal = american_to_decimal(odds)
    b = decimal - 1  # net fractional odds
    if b <= 0:
        return 0.0

    f_star = (b * p - q) / b
    if f_star <= 0:
        return 0.0

    stake = bankroll * kelly_fraction * f_star
    cap = bankroll * max_stake_pct
    return round(min(stake, cap), 2)

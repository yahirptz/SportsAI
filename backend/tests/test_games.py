"""Moneyline value model tests (pure math, offline)."""

from app.games.model import american_to_prob, moneyline_value


def test_american_to_prob():
    assert round(american_to_prob(-110), 3) == 0.524
    assert round(american_to_prob(+100), 3) == 0.5
    assert round(american_to_prob(+150), 3) == 0.4


def test_pickem_even_records_is_market_aligned():
    # Equal records, even pricing → model ~ market → no lean.
    gv = moneyline_value(
        game_id="g", home="A", away="B",
        home_record=(28, 28), away_record=(28, 28),
        home_ml=-110, away_ml=-110, bankroll=1000,
    )
    assert gv.best is None  # nothing to bet


def test_compression_keeps_probabilities_realistic():
    # A strong vs weak record must NOT yield a lopsided single-game probability.
    gv = moneyline_value(
        game_id="g", home="Strong", away="Weak",
        home_record=(40, 16), away_record=(16, 40),
        home_ml=-200, away_ml=+170, bankroll=1000,
    )
    home_edge = next(e for e in gv.edges if e.side == "home")
    # Even a .714 vs .286 matchup stays well under 70% for a single game.
    assert home_edge.model_prob < 0.70


def test_lean_only_past_threshold_and_stakes_positive():
    gv = moneyline_value(
        game_id="g", home="A", away="B",
        home_record=(45, 12), away_record=(15, 42),
        home_ml=+100, away_ml=-120, bankroll=1000,
    )
    # If a lean exists it must clear the threshold and carry a positive stake.
    if gv.best:
        assert gv.best.edge > 0.06
        assert gv.best.kelly_stake > 0

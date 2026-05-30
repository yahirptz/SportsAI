"""Pitcher-aware game-line model tests (pure math, offline)."""

from app.games.model import Starter, american_to_prob, game_value


def _gv(**kw):
    base = dict(
        game_id="g", home="Home", away="Away",
        home_record=(28, 28), away_record=(28, 28),
        home_starter=Starter(name="H", era=4.0, record="5-5"),
        away_starter=Starter(name="A", era=4.0, record="5-5"),
        home_ml=-110, away_ml=-110, bankroll=1000, total=8.5,
    )
    base.update(kw)
    return game_value(**base)


def test_american_to_prob():
    assert round(american_to_prob(-110), 3) == 0.524
    assert round(american_to_prob(+150), 3) == 0.4


def test_ace_vs_scrub_moves_win_prob_and_total():
    # Home ace (2.00) vs away scrub (6.50): home should be favored and the
    # projected total should sit below a fat book line.
    gv = _gv(
        home_starter=Starter(name="Ace", era=2.0, record="8-1"),
        away_starter=Starter(name="Scrub", era=6.5, record="2-7"),
        total=9.5,
    )
    home_p = next(e for e in gv.edges if e.side == "home").model_prob
    assert home_p > 0.5
    assert gv.proj_total < 9.5  # ace suppresses runs


def test_total_lean_flags_over_when_two_bad_starters():
    gv = _gv(
        home_starter=Starter(name="Bad1", era=6.5, record="2-7"),
        away_starter=Starter(name="Bad2", era=6.8, record="1-8"),
        total=7.0,
    )
    assert gv.proj_total > 7.0
    assert gv.total_lean is not None and gv.total_lean.pick == "over"


def test_even_matchup_no_ml_lean():
    gv = _gv()  # mirror-image teams + starters + even price
    assert gv.best is None


def test_win_prob_stays_realistic():
    gv = _gv(
        home_starter=Starter(name="Ace", era=1.5, record="10-0"),
        away_starter=Starter(name="Scrub", era=7.5, record="0-10"),
        home_record=(45, 11), away_record=(11, 45),
    )
    home_p = next(e for e in gv.edges if e.side == "home").model_prob
    assert home_p <= 0.95  # clamped — no absurd single-game certainty

"""Sample feed data for local development and the demo endpoints.

This stands in for the live ingestion layer (SportRadar / OddsJam / etc.) until
real adapters land. The NBA game below is tuned so a full 8-leg same-game
parlay can be constructed; the NFL game intentionally includes ineligible props
(injury flag, ceiling prop, line above average) to exercise the floor model.
"""

from __future__ import annotations

from app.floor.engine import GameLog
from app.models.schemas import EnrichmentContext
from app.pipeline import PropInput
from app.sports.registry import Sport


def _logs(values: list[float]) -> list[GameLog]:
    return [
        GameLog(game_id=f"g{i}", game_date=f"2026-05-{20 + i:02d}", value=v)
        for i, v in enumerate(values)
    ]


_NBA_GAME = "nba-2026-05-29-BOS-NYK"
_NFL_GAME = "nfl-2026-09-12-KC-BUF"
_MLB_GAME = "mlb-2026-05-29-LAD-SD"


def _nba_props() -> list[PropInput]:
    g = _NBA_GAME
    return [
        PropInput(g, "tatum", "Jayson Tatum", "pts", 22.5, -115, _logs([28, 31, 26, 30, 27]),
                  EnrichmentContext(reddit_sentiment=0.4, public_bet_pct=40, reverse_line_movement=True)),
        PropInput(g, "tatum", "Jayson Tatum", "reb", 6.5, -110, _logs([9, 8, 10, 7, 8]),
                  EnrichmentContext(reddit_sentiment=0.2, public_bet_pct=45)),
        PropInput(g, "brown", "Jaylen Brown", "pts", 18.5, -110, _logs([24, 22, 26, 21, 23]),
                  EnrichmentContext(reddit_sentiment=0.1, public_bet_pct=55)),
        PropInput(g, "white", "Derrick White", "fg3m", 1.5, -120, _logs([3, 2, 4, 2, 3]),
                  EnrichmentContext(reddit_sentiment=0.3, public_bet_pct=35, reverse_line_movement=True)),
        PropInput(g, "brunson", "Jalen Brunson", "ast", 5.5, -110, _logs([8, 7, 9, 8, 7]),
                  EnrichmentContext(reddit_sentiment=0.5, public_bet_pct=30)),
        PropInput(g, "brunson", "Jalen Brunson", "pts", 24.5, -115, _logs([30, 28, 32, 29, 31]),
                  EnrichmentContext(reddit_sentiment=0.4, public_bet_pct=42)),
        PropInput(g, "anunoby", "OG Anunoby", "pts", 12.5, -110, _logs([18, 16, 20, 15, 17]),
                  EnrichmentContext(reddit_sentiment=0.0, public_bet_pct=50)),
        PropInput(g, "bridges", "Mikal Bridges", "pts", 14.5, -110, _logs([19, 21, 18, 22, 20]),
                  EnrichmentContext(reddit_sentiment=0.2, public_bet_pct=48)),
        PropInput(g, "holiday", "Jrue Holiday", "ra", 8.5, -110, _logs([12, 11, 13, 10, 12]),
                  EnrichmentContext(reddit_sentiment=0.1, public_bet_pct=52)),
        # Ineligible: line above the last-5 average (avg 8.0).
        PropInput(g, "porzingis", "Kristaps Porzingis", "reb", 9.5, -110, _logs([8, 8, 8, 8, 8]),
                  EnrichmentContext()),
    ]


def _nfl_props() -> list[PropInput]:
    g = _NFL_GAME
    return [
        PropInput(g, "mahomes", "Patrick Mahomes", "pass_yds", 250.5, -115, _logs([310, 288, 295, 320, 301]),
                  EnrichmentContext(reddit_sentiment=0.3, public_bet_pct=44, reverse_line_movement=True)),
        PropInput(g, "kelce", "Travis Kelce", "rec_yds", 55.5, -110, _logs([72, 80, 68, 90, 75]),
                  EnrichmentContext(reddit_sentiment=0.4, public_bet_pct=38)),
        PropInput(g, "kelce", "Travis Kelce", "rec", 4.5, -120, _logs([7, 8, 6, 9, 7]),
                  EnrichmentContext(reddit_sentiment=0.3, public_bet_pct=40)),
        # Ineligible: injury flag set.
        PropInput(g, "rice", "Rashee Rice", "rec_yds", 45.5, -110, _logs([60, 55, 70, 50, 65]),
                  EnrichmentContext(injury_flag=True, perplexity_summary="Questionable — hamstring")),
        # Ineligible: ceiling prop.
        PropInput(g, "pacheco", "Isiah Pacheco", "longest_rush", 12.5, -110, _logs([18, 22, 15, 25, 20]),
                  EnrichmentContext()),
        # Ineligible: anytime TD missed a game.
        PropInput(g, "kelce", "Travis Kelce", "tds", 0.5, +120, _logs([1, 1, 0, 1, 2]),
                  EnrichmentContext()),
    ]


def _mlb_props() -> list[PropInput]:
    g = _MLB_GAME
    # MLB sample window is last-10. The floor model requires the stat to occur
    # in ALL 10 games, so only consistent contact hitters / a starter's Ks pass
    # — exactly the conservative behaviour the SRS specifies for baseball.
    return [
        PropInput(g, "betts", "Mookie Betts", "hits", 0.5, -135, _logs([1, 2, 1, 1, 2, 1, 1, 3, 1, 2]),
                  EnrichmentContext(reddit_sentiment=0.3, public_bet_pct=44)),
        PropInput(g, "betts", "Mookie Betts", "tb", 0.5, -140, _logs([1, 3, 2, 1, 4, 1, 2, 5, 1, 3]),
                  EnrichmentContext(reddit_sentiment=0.3)),
        PropInput(g, "freeman", "Freddie Freeman", "hits", 0.5, -130, _logs([2, 1, 1, 1, 1, 2, 1, 1, 1, 2]),
                  EnrichmentContext(reddit_sentiment=0.2, public_bet_pct=40)),
        PropInput(g, "ohtani", "Shohei Ohtani", "tb", 1.5, -120, _logs([2, 4, 3, 2, 5, 2, 4, 3, 2, 6]),
                  EnrichmentContext(reddit_sentiment=0.5, public_bet_pct=35, reverse_line_movement=True)),
        PropInput(g, "smith", "Will Smith", "hits", 0.5, -125, _logs([1, 1, 2, 1, 1, 1, 2, 1, 1, 1]),
                  EnrichmentContext(reddit_sentiment=0.1)),
        PropInput(g, "machado", "Manny Machado", "tb", 0.5, -130, _logs([1, 2, 1, 3, 1, 2, 1, 1, 4, 1]),
                  EnrichmentContext(reddit_sentiment=0.2, public_bet_pct=48)),
        PropInput(g, "tatis", "Fernando Tatis Jr.", "hits", 0.5, -135, _logs([1, 1, 1, 2, 1, 1, 3, 1, 1, 2]),
                  EnrichmentContext(reddit_sentiment=0.4, public_bet_pct=42)),
        PropInput(g, "bogaerts", "Xander Bogaerts", "hits", 0.5, -125, _logs([1, 2, 1, 1, 1, 1, 1, 2, 1, 1]),
                  EnrichmentContext(reddit_sentiment=0.1, public_bet_pct=50)),
        PropInput(g, "darvish", "Yu Darvish", "k_pitcher", 4.5, -115, _logs([6, 7, 5, 8, 6, 7, 5, 9, 6, 7]),
                  EnrichmentContext(reddit_sentiment=0.3, public_bet_pct=46, reverse_line_movement=True)),
        # Ineligible: a hitless game in the window (min 0) — discarded.
        PropInput(g, "cronenworth", "Jake Cronenworth", "hits", 1.5, -110, _logs([1, 0, 1, 2, 1, 1, 0, 1, 1, 1]),
                  EnrichmentContext()),
    ]


SAMPLE_PROPS: dict[Sport, list[PropInput]] = {
    Sport.NBA: _nba_props(),
    Sport.NFL: _nfl_props(),
    Sport.MLB: _mlb_props(),
}

SAMPLE_GAMES: dict[Sport, str] = {
    Sport.NBA: _NBA_GAME,
    Sport.NFL: _NFL_GAME,
    Sport.MLB: _MLB_GAME,
}

"""Game-line value model (moneyline / run line / totals).

A separate, clearly-labelled model from the player-prop floor model. Game
markets are efficient, so this is a value *detector*: it builds a model
probability from verified team data and compares it to the book's de-vigged
implied probability, surfacing only positive-edge sides. It does NOT use the
floor concept — there is no last-N "floor" for a game outcome.

Honesty note: the moneyline model uses season win/loss records (the only team
strength signal available cheaply on the SportRadar trial). Totals and run-line
modelling are deferred until runs-scored/allowed data is affordable; their
odds are stored but not yet projected.
"""

from app.games.model import (
    GameValue,
    MoneylineEdge,
    Starter,
    american_to_prob,
    game_value,
    nba_game_value,
)

__all__ = [
    "GameValue", "MoneylineEdge", "Starter",
    "american_to_prob", "game_value", "nba_game_value",
]

"""FanDuel board import → floor board → configurable bet builder.

Turns a pasted FanDuel tiered-prop board into structured props, prices each
tier against the player's verified last-N floor, keeps only the tiers cleared in
ALL recent games, and assembles a bet of the user's chosen shape (single,
moneyline, or an N-leg parlay).
"""

from app.board.builder import FloorPlay, assemble_bet, build_floor_board
from app.board.fanduel import ParsedProp, parse_fanduel

__all__ = ["ParsedProp", "parse_fanduel", "FloorPlay", "build_floor_board", "assemble_bet"]

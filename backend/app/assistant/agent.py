"""Claude agent that drives the floor model via tool use."""

from __future__ import annotations

import json

from anthropic import Anthropic

from app.board import assemble_bet, build_floor_board, parse_fanduel
from app.board.fanduel import parse_fanduel_games
from app.config import settings
from app.games.source import build_game_values, save_game_lines
from app.sports.registry import Sport

SYSTEM = """You are EdgeIQ's betting assistant. You help build same-game and \
cross-game parlays from the floor model and give an honest read.

Hard rules — never break these:
- The floor model only surfaces props a player cleared in EVERY recent game.
- NEVER say a bet "will hit" or call it a lock. Always give an honest probability.
- Prefer fewer, high-cushion legs. Cut variance legs and cold players, even if
  the book lists them as favorites. More legs = lower chance, not better.
- Ground EVERY pick in the build_bet tool's numbers. Don't invent stats.
- Be concise, direct, and plainspoken. A few sentences, not an essay.

When the user wants a pick/parlay or asks "is this good", call build_bet with
the right sport, mode (single/parlay/moneyline) and leg count, then explain the
result: the legs, why they qualified (floor vs line), the combined odds, the
honest probability, and the main risk. If no board is pasted yet, ask for it."""

TOOL = {
    "name": "build_bet",
    "description": (
        "Run the floor model on the pasted FanDuel board and assemble a bet. "
        "Use for any pick, parlay, or 'is this good' request."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sport": {"type": "string", "enum": ["nba", "mlb", "nhl"]},
            "mode": {"type": "string", "enum": ["single", "parlay", "moneyline"]},
            "legs": {"type": "integer", "description": "Number of parlay legs (2-8)."},
            "min_cushion": {"type": "number", "description": "Min floor-over-line cushion."},
        },
        "required": ["sport", "mode"],
    },
}


def _run_tool(inp: dict, board: str, bankroll: float) -> dict:
    sport = Sport(inp["sport"])
    mode = inp.get("mode", "parlay")
    if mode == "moneyline":
        # If the user pasted a game-line block, ingest it so the model has odds.
        parsed = parse_fanduel_games(board or "")
        if parsed:
            save_game_lines(sport, parsed)
        res = build_game_values(sport, bankroll)
        games = [
            {"away": g.away, "home": g.home,
             "edges": [e.model_dump() for e in g.edges],
             "best": (g.best.model_dump() if g.best else None),
             "total_lean": (g.total_lean.model_dump() if g.total_lean else None),
             "injury_notes": g.injury_notes,
             "public_note": g.public_note,
             "home_sentiment": g.home_sentiment, "away_sentiment": g.away_sentiment}
            for g in res.get("games", [])
        ]
        return {"mode": "moneyline", "games": games, "note": res.get("note")}
    board_plays = build_floor_board(sport, parse_fanduel(board or ""))
    bet = assemble_bet(
        board_plays, legs=1 if mode == "single" else inp.get("legs", 3),
        min_cushion=inp.get("min_cushion", 0.0), bankroll=bankroll,
    )
    return {"mode": mode, "board": [p.as_dict() for p in board_plays], "bet": bet}


def run_assistant(messages: list[dict], sport: str, board: str, bankroll: float = 1000.0) -> dict:
    if not settings.anthropic_api_key:
        return {"reply": "Assistant unavailable — no Anthropic API key configured.", "slip": None}

    client = Anthropic(api_key=settings.anthropic_api_key)
    system = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
    # Sharpen over time: inject what the vault has learned from graded bets.
    try:
        from app.vault import patterns_brief
        system.append({"type": "text", "text": "VAULT KNOWLEDGE — " + patterns_brief()})
    except Exception:
        pass
    if board:
        system.append({"type": "text",
                       "text": f"A {sport.upper()} FanDuel board is pasted and available to build_bet."})

    convo = [{"role": m["role"], "content": m["content"]} for m in messages]
    slip = None
    for _ in range(5):
        resp = client.messages.create(
            model=settings.claude_model, max_tokens=1024,
            system=system, tools=[TOOL], messages=convo,
        )
        if resp.stop_reason == "tool_use":
            convo.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    out = _run_tool(block.input, board, bankroll)
                    if out.get("bet") and not out["bet"].get("no_bet"):
                        slip = out  # remember the latest real slip for the card
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": json.dumps(out, default=str)})
            convo.append({"role": "user", "content": results})
            continue
        reply = "".join(b.text for b in resp.content if b.type == "text").strip()
        return {"reply": reply, "slip": slip}
    return {"reply": "Sorry — I couldn't finish that. Try rephrasing.", "slip": slip}

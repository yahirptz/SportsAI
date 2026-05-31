"""The Debate Agent — a skeptic that argues against every proposed leg.

The floor model produces candidates; this agent challenges each one on the
evidence (cushion, the actual last-N values, variance) and keeps only the legs
that survive the challenge. It is the second voice — it does NOT predict, it
attacks. Falls back to keeping every leg if no Claude key is configured.
"""

from __future__ import annotations

import json

from anthropic import Anthropic

from app.board.builder import FloorPlay
from app.config import settings

_SYSTEM = """You are EdgeIQ's skeptic. You are given candidate parlay legs that \
already passed the floor model (the player cleared the line in every recent \
game). Your job is to ARGUE AGAINST each leg and decide keep or cut.

Cut a leg when:
- The cushion is thin (floor barely above the line) AND the player hit the line
  exactly in 2+ of the recent games — that's single-possession/at-bat variance.
- The recent values are erratic (one bad game from busting).
Keep a leg when the floor clears the line with real room across the sample.

You do NOT predict outcomes. You only assess fragility from the numbers given.
Return ONLY JSON: {"verdicts":[{"player":..,"market":..,"keep":true/false,
"reason":"one short sentence"}]}. Be strict — a parlay dies on its weakest leg."""


def debate(plays: list[FloorPlay]) -> dict:
    """Return {'survivors': set[(player,market)], 'verdicts': [...]}"""
    if not plays:
        return {"survivors": set(), "verdicts": []}

    if not settings.anthropic_api_key:
        keys = {(p.player, p.market) for p in plays}
        return {"survivors": keys,
                "verdicts": [{"player": p.player, "market": p.market_label, "keep": True,
                              "reason": "kept (no skeptic available)"} for p in plays]}

    evidence = [
        {"player": p.player, "market": p.market_label, "line": p.line, "floor": p.floor,
         "cushion": p.cushion, "recent_values": p.values, "odds": p.odds}
        for p in plays
    ]
    try:
        client = Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=settings.claude_model, max_tokens=700, system=_SYSTEM,
            messages=[{"role": "user", "content": "Challenge these legs:\n" + json.dumps(evidence)}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        start, end = text.find("{"), text.rfind("}")
        verdicts = json.loads(text[start:end + 1])["verdicts"]
    except Exception:
        keys = {(p.player, p.market) for p in plays}
        return {"survivors": keys,
                "verdicts": [{"player": p.player, "market": p.market_label, "keep": True,
                              "reason": "kept (skeptic unavailable)"} for p in plays]}

    # Map verdicts back to plays by player + market label.
    label_to_key = {(p.player, p.market_label): (p.player, p.market) for p in plays}
    survivors = set()
    for v in verdicts:
        key = label_to_key.get((v.get("player"), v.get("market")))
        if key and v.get("keep"):
            survivors.add(key)
    # Any leg the skeptic didn't address → keep (don't silently drop).
    addressed = {(v.get("player"), v.get("market")) for v in verdicts}
    for p in plays:
        if (p.player, p.market_label) not in addressed:
            survivors.add((p.player, p.market))
    return {"survivors": survivors, "verdicts": verdicts}

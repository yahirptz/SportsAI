"""Claude reasoner (SRS §04 — agent reasoning summaries).

Generates the concise "why this pick" summary shown in the Agent Feed. It is
explanatory only: it summarises the floor-model math and enrichment context the
deterministic agents already produced — it does NOT make or change the pick.

Uses a cached system prompt (Anthropic prompt caching) since the same
instructions are reused across every pick in a slate.
"""

from __future__ import annotations

from anthropic import Anthropic

from app.feeds.circuit import CircuitBreaker

_SYSTEM = (
    "You are EdgeIQ's analyst. In ONE sentence (max 30 words), explain why a "
    "same-game-parlay leg qualified, grounded ONLY in the numbers provided: the "
    "verified floor, the line it clears, the last-N average, and any enrichment "
    "signal. Be precise and sober. Never invent stats. Never give betting advice "
    "beyond describing the edge."
)


class ClaudeReasoner:
    name = "claude"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._breaker = CircuitBreaker("claude")

    def summarize(self, facts: str) -> str:
        try:
            return self._breaker.call(lambda: self._summarize(facts))
        except Exception:
            return ""  # reasoning is cosmetic — never block a pick on it

    def _summarize(self, facts: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=80,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": facts}],
        )
        return "".join(block.text for block in msg.content if block.type == "text").strip()

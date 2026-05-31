"""In-app betting assistant — Claude with the floor model as its tools.

Lets the app work like a conversation: the user pastes a FanDuel board and asks
in plain language ("build me a 3-leg", "is this good?", "who's most likely?").
Claude reasons and calls the floor-model tool to compute real picks, returning a
natural-language reply plus a structured slip for the result card.
"""

from app.assistant.agent import run_assistant

__all__ = ["run_assistant"]

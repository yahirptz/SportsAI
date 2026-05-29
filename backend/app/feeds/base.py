"""Feed provider interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.pipeline import PropInput
from app.sports.registry import Sport


class FeedError(Exception):
    """Raised when a data source is unavailable, stale, or misconfigured."""


@runtime_checkable
class FeedProvider(Protocol):
    """Produces the prop slate for a sport (game logs + lines + enrichment).

    A provider composes the structured stats feed (game logs — the floor model's
    source of truth) with the odds feed (current sportsbook lines). The returned
    :class:`~app.pipeline.PropInput` list is exactly what the agent pipeline
    consumes.
    """

    name: str

    def slate(self, sport: Sport) -> list[PropInput]:
        """Return all candidate props for the sport's current slate."""
        ...

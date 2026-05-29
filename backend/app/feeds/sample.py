"""Sample feed provider — wraps the in-repo fixtures (development default)."""

from __future__ import annotations

from app.feeds.circuit import CircuitBreaker
from app.pipeline import PropInput
from app.sample_data import SAMPLE_PROPS
from app.sports.registry import Sport


class SampleFeedProvider:
    """Serves the bundled sample slate; records healthy state for the source."""

    name = "sample"

    def __init__(self) -> None:
        self._breaker = CircuitBreaker("sample")

    def slate(self, sport: Sport) -> list[PropInput]:
        return self._breaker.call(lambda: list(SAMPLE_PROPS.get(sport, [])))

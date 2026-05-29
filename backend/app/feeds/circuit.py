"""Circuit-breaker watchdog (SRS §01 Layer 1 / §06 feed_health table).

Every data source is wrapped in a circuit breaker. If a source errors or its
data goes stale beyond its freshness threshold, the breaker trips and downstream
agents are hard-stopped (a :class:`~app.feeds.base.FeedError` is raised). The
current state of every source is held in ``HEALTH_REGISTRY`` and surfaced via
the Model Health view (SRS §07).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from app.feeds.base import FeedError

T = TypeVar("T")

# Freshness thresholds in seconds, per SRS §01 Layer 1.
FRESHNESS_THRESHOLDS: dict[str, int] = {
    "sportradar": 300,  # live box scores — 5 minutes
    "fanduel": 90,
    "draftkings": 90,
    "oddsjam": 300,
    "action_network": 600,
    "rotowire": 900,
    "weather": 1800,
    "sample": 10**9,  # sample feed never goes stale
}


@dataclass
class FeedHealth:
    """Live health record for one source (mirrors the feed_health table)."""

    source: str
    status: str = "unknown"  # ok | stale | circuit_broken | unknown
    last_updated: float | None = None
    circuit_broken_at: float | None = None
    detail: str | None = None

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "status": self.status,
            "last_updated": self.last_updated,
            "circuit_broken_at": self.circuit_broken_at,
            "detail": self.detail,
        }


@dataclass
class _Registry:
    feeds: dict[str, FeedHealth] = field(default_factory=dict)

    def get(self, source: str) -> FeedHealth:
        return self.feeds.setdefault(source, FeedHealth(source=source))

    def snapshot(self) -> list[dict]:
        return [h.as_dict() for h in self.feeds.values()]


HEALTH_REGISTRY = _Registry()


class CircuitBreaker:
    """Trips on call failure or stale data for a single source."""

    def __init__(self, source: str, freshness_seconds: int | None = None) -> None:
        self.source = source
        self.freshness = freshness_seconds or FRESHNESS_THRESHOLDS.get(source, 300)
        self.health = HEALTH_REGISTRY.get(source)

    def record_success(self) -> None:
        self.health.status = "ok"
        self.health.last_updated = time.time()
        self.health.circuit_broken_at = None
        self.health.detail = None

    def trip(self, detail: str) -> None:
        self.health.status = "circuit_broken"
        self.health.circuit_broken_at = time.time()
        self.health.detail = detail

    def is_stale(self) -> bool:
        if self.health.last_updated is None:
            return False
        return (time.time() - self.health.last_updated) > self.freshness

    def call(self, fn: Callable[[], T]) -> T:
        """Execute ``fn`` under the breaker. Trips and raises on failure."""
        try:
            result = fn()
        except FeedError:
            raise
        except Exception as exc:  # noqa: BLE001 — any source error trips the breaker
            self.trip(f"{type(exc).__name__}: {exc}")
            raise FeedError(f"Source {self.source!r} tripped circuit breaker: {exc}") from exc
        self.record_success()
        return result

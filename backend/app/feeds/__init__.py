"""Data ingestion layer (SRS §01 Layer 1).

Provides a pluggable :class:`FeedProvider` abstraction, a circuit-breaker
watchdog per source, and concrete providers (sample feed + SportRadar). The
active provider is selected by ``EDGEIQ_FEED_PROVIDER``; if a live provider is
misconfigured or trips its breaker, the API falls back to the sample feed and
reports the degraded state via feed health.
"""

from __future__ import annotations

from app.config import settings
from app.feeds.base import FeedError, FeedProvider
from app.feeds.circuit import HEALTH_REGISTRY, CircuitBreaker, FeedHealth
from app.feeds.odds import OddsBook, StaticOddsBook
from app.feeds.sample import SampleFeedProvider

__all__ = [
    "FeedError",
    "FeedProvider",
    "CircuitBreaker",
    "FeedHealth",
    "HEALTH_REGISTRY",
    "OddsBook",
    "StaticOddsBook",
    "SampleFeedProvider",
    "get_provider",
]

_SAMPLE = SampleFeedProvider()


def get_provider() -> FeedProvider:
    """Return the configured feed provider, falling back to the sample feed.

    Selecting ``sportradar`` requires ``EDGEIQ_SPORTRADAR_API_KEY``; without it
    (or on import failure) we degrade gracefully to the sample feed so the
    platform stays runnable in development.
    """
    choice = settings.feed_provider.lower()
    if choice == "sportradar":
        try:
            from app.feeds.sportradar import build_sportradar_provider

            return build_sportradar_provider()
        except FeedError:
            # Misconfigured live feed → degrade to sample (health reflects this).
            return _SAMPLE
    return _SAMPLE

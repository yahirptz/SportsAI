"""Feed provider + circuit breaker tests."""

import pytest

from app.feeds import SampleFeedProvider, get_provider
from app.feeds.base import FeedError
from app.feeds.circuit import CircuitBreaker
from app.sports.registry import Sport


def test_sample_provider_returns_slate_and_marks_healthy():
    provider = SampleFeedProvider()
    props = provider.slate(Sport.NBA)
    assert props, "sample NBA slate should be non-empty"
    assert provider._breaker.health.status == "ok"


def test_get_provider_defaults_to_sample():
    assert get_provider().name == "sample"


def test_circuit_breaker_trips_on_error():
    breaker = CircuitBreaker("sportradar")

    def boom():
        raise RuntimeError("feed down")

    with pytest.raises(FeedError):
        breaker.call(boom)
    assert breaker.health.status == "circuit_broken"
    assert breaker.health.circuit_broken_at is not None


def test_circuit_breaker_records_success():
    breaker = CircuitBreaker("sportradar")
    assert breaker.call(lambda: 42) == 42
    assert breaker.health.status == "ok"


def test_sportradar_requires_api_key(monkeypatch):
    from app.config import settings
    from app.feeds.sportradar import build_sportradar_provider

    monkeypatch.setattr(settings, "sportradar_api_key", None)
    with pytest.raises(FeedError):
        build_sportradar_provider()

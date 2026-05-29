"""Test fixtures — keep the suite offline and deterministic.

The developer's .env may point the feed at the live SportRadar provider. Tests
must never make network calls, so force the sample feed for the whole session.
"""

import pytest

from app.config import settings


@pytest.fixture(autouse=True, scope="session")
def _force_sample_feed():
    original = settings.feed_provider
    settings.feed_provider = "sample"
    yield
    settings.feed_provider = original

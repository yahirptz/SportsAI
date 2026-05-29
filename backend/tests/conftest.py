"""Test fixtures — keep the suite offline and deterministic.

The developer's .env may point the feed at the live SportRadar provider. Tests
must never make network calls, so force the sample feed for the whole session.
"""

import pytest

from app.config import settings


@pytest.fixture(autouse=True, scope="session")
def _offline_defaults():
    """Force the sample feed and disable enrichment so tests never hit the network."""
    feed, enrich = settings.feed_provider, settings.enrichment_enabled
    settings.feed_provider = "sample"
    settings.enrichment_enabled = False
    yield
    settings.feed_provider, settings.enrichment_enabled = feed, enrich

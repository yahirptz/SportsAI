"""Test fixtures — keep the suite offline and deterministic.

Point the tracking DB at a throwaway temp file BEFORE any app module imports
(so the settings singleton picks it up), and force the sample feed + disable
enrichment so tests never hit the network.
"""

import os
import tempfile

# Must run before `from app.config import settings` anywhere in the test session.
_TEST_DB = os.path.join(tempfile.gettempdir(), "edgeiq_test.db")
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
os.environ["EDGEIQ_TRACKING_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import init_db  # noqa: E402

init_db()


@pytest.fixture(autouse=True, scope="session")
def _offline_defaults():
    feed, enrich = settings.feed_provider, settings.enrichment_enabled
    settings.feed_provider = "sample"
    settings.enrichment_enabled = False
    yield
    settings.feed_provider, settings.enrichment_enabled = feed, enrich

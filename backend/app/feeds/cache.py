"""Tiny on-disk JSON cache for feed responses.

SportRadar's trial tier is rate-limited (~1 req/sec). Historical schedules and
game summaries are immutable once a game is closed, so caching them to disk
makes repeat slate builds fast and keeps us well under the quota. This is a
stopgap until the Redis cache layer (SRS §03) is wired.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "sportradar"


class DiskCache:
    def __init__(self, ttl_seconds: int | None = None, root: Path = CACHE_DIR) -> None:
        self.ttl = ttl_seconds  # None = never expire (historical data is immutable)
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()[:24]
        return self.root / f"{digest}.json"

    def get(self, key: str) -> dict | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        if self.ttl is not None and (time.time() - payload["_ts"]) > self.ttl:
            return None
        return payload["data"]

    def set(self, key: str, data: dict) -> None:
        self._path(key).write_text(json.dumps({"_ts": time.time(), "data": data}))

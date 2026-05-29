"""Reddit sentiment (SRS §02 Layer 2 — sentiment).

Best-effort, key-free sentiment using Reddit's public search JSON. This is a
lightweight lexicon score over recent post titles mentioning the player — a
rough signal that NEVER overrides the floor model and contributes only 10% of
the confidence score. A licensed Reddit API client replaces this later.
"""

from __future__ import annotations

import httpx

from app.feeds.circuit import CircuitBreaker

# Tiny domain lexicon. Crude on purpose — this is a marginal signal.
_POS = {
    "smash", "lock", "easy", "cooking", "fire", "must", "value", "love",
    "confident", "bounce", "healthy", "great", "elite", "hammer", "cash",
}
_NEG = {
    "fade", "avoid", "trap", "injury", "injured", "questionable", "rest",
    "out", "cold", "slump", "regress", "bust", "stay", "risky", "doubt",
}


class RedditSentiment:
    name = "reddit"

    def __init__(self, *, timeout: float = 12.0, limit: int = 25) -> None:
        self._client = httpx.Client(
            timeout=timeout, headers={"User-Agent": "EdgeIQ/1.0 (sentiment)"}
        )
        self._limit = limit
        self._breaker = CircuitBreaker("reddit")

    def score(self, player_name: str, subreddits: list[str]) -> float:
        """Return a sentiment score in [-1, 1]; 0.0 if no signal/unavailable."""
        try:
            return self._breaker.call(lambda: self._score(player_name, subreddits))
        except Exception:
            return 0.0  # best-effort: never block the pipeline on sentiment

    def _score(self, player_name: str, subreddits: list[str]) -> float:
        subs = "+".join(s.removeprefix("r/") for s in subreddits) or "sportsbook"
        resp = self._client.get(
            f"https://www.reddit.com/r/{subs}/search.json",
            params={
                "q": player_name,
                "restrict_sr": "on",
                "sort": "new",
                "limit": self._limit,
                "t": "week",
            },
        )
        resp.raise_for_status()
        posts = resp.json().get("data", {}).get("children", [])
        pos = neg = 0
        for post in posts:
            words = set(post["data"].get("title", "").lower().split())
            pos += len(words & _POS)
            neg += len(words & _NEG)
        total = pos + neg
        if total == 0:
            return 0.0
        return round((pos - neg) / total, 2)

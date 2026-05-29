"""Enrichment orchestration with caching and graceful degradation.

A single :class:`EnrichmentService` fronts Perplexity (facts), Reddit
(sentiment) and Claude (reasoning). It is safe to call unconditionally:

  - If enrichment is disabled or a key is missing, it returns neutral results.
  - Results are cached (per player per day) so a slate costs at most one call
    per unique player, not one per prop.
  - Any provider error degrades to neutral — enrichment never blocks a pick.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from app.config import settings
from app.enrichment.claude import ClaudeReasoner
from app.enrichment.perplexity import PerplexityEnricher
from app.feeds.cache import DiskCache
from app.enrichment.reddit import RedditSentiment


class PlayerEnrichment(dict):
    """{'injury_flag': bool, 'perplexity_summary': str|None, 'reddit_sentiment': float}"""


_NEUTRAL = PlayerEnrichment(injury_flag=False, perplexity_summary=None, reddit_sentiment=0.0)


class EnrichmentService:
    def __init__(
        self,
        perplexity: PerplexityEnricher | None,
        reddit: RedditSentiment | None,
        reasoner: ClaudeReasoner | None,
        cache: DiskCache,
        enabled: bool,
    ) -> None:
        self._perplexity = perplexity
        self._reddit = reddit
        self._reasoner = reasoner
        self._cache = cache
        self.enabled = enabled

    # -- facts + sentiment --------------------------------------------------

    def enrich_player(
        self, player_name: str, sport_label: str, subreddits: list[str]
    ) -> PlayerEnrichment:
        if not self.enabled:
            return _NEUTRAL
        key = f"player:{sport_label}:{player_name}:{date.today()}"
        cached = self._cache.get(key)
        if cached is not None:
            return PlayerEnrichment(**cached)

        result = dict(_NEUTRAL)
        if self._perplexity is not None:
            report = self._perplexity.injury_news(player_name, sport_label)
            result["injury_flag"] = report.injury_flag
            result["perplexity_summary"] = f"[{report.status}] {report.summary}"
        if self._reddit is not None:
            result["reddit_sentiment"] = self._reddit.score(player_name, subreddits)

        self._cache.set(key, result)
        return PlayerEnrichment(**result)

    # -- reasoning ----------------------------------------------------------

    def reason(self, facts: str) -> str:
        if not self.enabled or self._reasoner is None:
            return ""
        key = "reason:" + hashlib.sha256(facts.encode()).hexdigest()[:24]
        cached = self._cache.get(key)
        if cached is not None:
            return cached.get("text", "")
        text = self._reasoner.summarize(facts)
        self._cache.set(key, {"text": text})
        return text


_SERVICE: EnrichmentService | None = None


def get_enrichment_service() -> EnrichmentService:
    """Build (once) the enrichment service from settings and available keys."""
    global _SERVICE
    if _SERVICE is not None:
        return _SERVICE

    enabled = settings.enrichment_enabled
    perplexity = reddit = reasoner = None
    if enabled:
        if settings.perplexity_api_key:
            perplexity = PerplexityEnricher(settings.perplexity_api_key, settings.perplexity_model)
        if settings.reddit_sentiment_enabled:
            reddit = RedditSentiment()
        if settings.anthropic_api_key:
            reasoner = ClaudeReasoner(settings.anthropic_api_key, settings.claude_model)

    cache = DiskCache(
        ttl_seconds=settings.enrichment_cache_ttl,
        root=Path(__file__).resolve().parents[2] / ".cache" / "enrichment",
    )
    _SERVICE = EnrichmentService(perplexity, reddit, reasoner, cache, enabled)
    return _SERVICE


def reset_enrichment_service() -> None:
    """Drop the cached singleton (used by tests after toggling settings)."""
    global _SERVICE
    _SERVICE = None

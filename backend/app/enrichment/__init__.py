"""Context enrichment layer (SRS §02 Layer 2).

Unstructured intelligence that fires before the agent run: Perplexity supplies
facts (injury / lineup / news), Reddit supplies sentiment, and Claude writes the
per-pick reasoning. None of these may override the floor model — an injury flag
hard-stops a leg, everything else only modulates the confidence score.
"""

from app.enrichment.service import EnrichmentService, get_enrichment_service

__all__ = ["EnrichmentService", "get_enrichment_service"]

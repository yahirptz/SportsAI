"""Application configuration (SRS §08 — keys via environment, never hardcoded)."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, sourced from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_prefix="EDGEIQ_", env_file=".env", extra="ignore", populate_by_name=True
    )

    app_name: str = "EdgeIQ"
    version: str = "1.0.0"
    environment: str = "development"

    # Risk controls (SRS §08 Responsible Gambling).
    kelly_fraction: float = 0.25  # Fractional Kelly multiplier.
    max_stake_pct: float = 0.05  # Never stake more than 5% of bankroll on one bet.
    daily_loss_limit_pct: float = 0.10
    weekly_loss_limit_pct: float = 0.25

    # Parlay constraints (SRS §04 / §08).
    parlay_legs: int = 8  # Required legs for a same-game parlay.
    min_correlation_for_block: float = 0.0  # Block negatively correlated legs.

    # Data ingestion (SRS §01). "sample" | "sportradar".
    # SportRadar issues a separate key per sport/product.
    feed_provider: str = "sample"
    sportradar_api_key: str | None = None  # NBA
    sportradar_mlb_api_key: str | None = None  # MLB
    sportradar_access: str = "trial"  # trial | production
    sportradar_lookback_days: int = 30  # bound the game-log walk-back.
    odds_lines_path: str = "data/lines.json"  # operator-supplied lines bridge.

    # Context enrichment (SRS §02 Layer 2). Off by default so the base pipeline
    # stays fast and free; turn on to run Perplexity/Reddit/Claude per slate.
    enrichment_enabled: bool = False
    enrichment_cache_ttl: int = 6 * 3600  # injuries/news change intraday → 6h TTL.
    reasoning_max_legs: int = 8  # cap Claude reasoning calls per build (cost guard).
    reddit_sentiment_enabled: bool = True  # uses free public JSON; best-effort.

    # AI provider keys. Read by their conventional unprefixed env names so the
    # Anthropic SDK and Perplexity share one source of truth.
    anthropic_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "EDGEIQ_ANTHROPIC_API_KEY")
    )
    perplexity_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("PERPLEXITY_API_KEY", "EDGEIQ_PERPLEXITY_API_KEY")
    )
    claude_model: str = "claude-sonnet-4-20250514"
    perplexity_model: str = "sonar"

    # Persistence. Tracking store defaults to local SQLite (zero setup); point
    # at the docker Postgres by setting EDGEIQ_TRACKING_DATABASE_URL.
    tracking_database_url: str = "sqlite:///edgeiq.db"
    obsidian_vault_path: str = "vault"  # local-first markdown vault (SRS §05)
    database_url: str = "postgresql://edgeiq:edgeiq@localhost:5432/edgeiq"
    timescale_url: str = "postgresql://edgeiq:edgeiq@localhost:5433/edgeiq_ts"
    redis_url: str = "redis://localhost:6379/0"


settings = Settings()

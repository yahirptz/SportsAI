"""Application configuration (SRS §08 — keys via environment, never hardcoded)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, sourced from environment variables / .env."""

    model_config = SettingsConfigDict(env_prefix="EDGEIQ_", env_file=".env", extra="ignore")

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
    feed_provider: str = "sample"
    sportradar_api_key: str | None = None
    sportradar_base_url: str = "https://api.sportradar.com/nba/trial/v8/en"
    sportradar_lookback_days: int = 30  # bound the game-log walk-back.

    # External services (placeholders — wired in later phases).
    claude_model: str = "claude-sonnet-4-20250514"
    database_url: str = "postgresql://edgeiq:edgeiq@localhost:5432/edgeiq"
    timescale_url: str = "postgresql://edgeiq:edgeiq@localhost:5433/edgeiq_ts"
    redis_url: str = "redis://localhost:6379/0"


settings = Settings()

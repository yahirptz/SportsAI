"""Sport configuration registry and the sport router."""

from app.sports.registry import (
    SPORTS,
    Sport,
    SportConfig,
    StatKind,
    StatSpec,
    get_config,
    route_sport,
)

__all__ = [
    "SPORTS",
    "Sport",
    "SportConfig",
    "StatKind",
    "StatSpec",
    "get_config",
    "route_sport",
]

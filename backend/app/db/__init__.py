"""Persistence layer: tracked picks + graded outcomes (SRS §05/§06).

Picks the model surfaces are persisted (paper-traded), graded against actual
results, and rolled up into hit rate / ROI / CLV so the system can finally
measure whether it has edge. SQLite by default; Postgres via config.
"""

from app.db.engine import get_session, init_db
from app.db.models import OutcomeRow, TrackedPick

__all__ = ["get_session", "init_db", "TrackedPick", "OutcomeRow"]

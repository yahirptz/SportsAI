"""ORM models for tracked picks and graded outcomes."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TrackedPick(Base):
    """A pick the model surfaced, persisted for grading (paper trade)."""

    __tablename__ = "tracked_picks"
    __table_args__ = (UniqueConstraint("dedup_key", name="uq_pick_dedup"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String, index=True)
    sport: Mapped[str] = mapped_column(String, index=True)
    game_id: Mapped[str] = mapped_column(String, index=True)
    player_id: Mapped[str] = mapped_column(String)
    player_name: Mapped[str] = mapped_column(String)
    market: Mapped[str] = mapped_column(String)
    market_label: Mapped[str] = mapped_column(String)
    line: Mapped[float] = mapped_column(Float)
    floor: Mapped[float] = mapped_column(Float)
    gap: Mapped[float] = mapped_column(Float, default=0.0)
    sample_average: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    odds: Mapped[int | None] = mapped_column(nullable=True)
    kelly_stake: Mapped[float] = mapped_column(Float, default=0.0)
    injury_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    context: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON situational tags
    bet_type: Mapped[str] = mapped_column(String, default="prop")  # prop | moneyline
    status: Mapped[str] = mapped_column(String, default="open", index=True)  # open | graded
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    outcome: Mapped["OutcomeRow | None"] = relationship(
        back_populates="pick", uselist=False, cascade="all, delete-orphan"
    )


class OutcomeRow(Base):
    """A graded result for a tracked pick (Result Grader, SRS §04)."""

    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pick_id: Mapped[str] = mapped_column(ForeignKey("tracked_picks.id"), unique=True, index=True)
    result: Mapped[str] = mapped_column(String)  # win | loss | push
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    closing_line: Mapped[float | None] = mapped_column(Float, nullable=True)
    clv: Mapped[float | None] = mapped_column(Float, nullable=True)
    units: Mapped[float] = mapped_column(Float, default=0.0)  # profit in units at stored odds
    graded_at: Mapped[datetime] = mapped_column(default=_utcnow)

    pick: Mapped["TrackedPick"] = relationship(back_populates="outcome")

"""Repository: persist picks, grade outcomes, roll up performance."""

from __future__ import annotations

from sqlalchemy import func, select

from app.db.engine import get_session
from app.db.models import OutcomeRow, TrackedPick
from app.games.model import american_to_decimal
from app.grading import compute_clv
from app.models.schemas import Pick


def dedup_key(sport: str, game_id: str, player_id: str, market: str, line: float) -> str:
    return f"{sport}:{game_id}:{player_id}:{market}:{line}"


def save_picks(picks: list[Pick]) -> int:
    """Persist newly-surfaced picks (paper trade). Dedupes on game/player/market/line."""
    saved = 0
    with get_session() as s:
        for p in picks:
            key = dedup_key(p.sport.value, p.game_id, p.player_id, p.market, p.line)
            existing = s.scalar(select(TrackedPick.id).where(TrackedPick.dedup_key == key))
            if existing:
                p.id = existing  # hand back the persisted id so the pick stays gradable
                continue
            s.add(TrackedPick(
                id=p.id, dedup_key=key, sport=p.sport.value, game_id=p.game_id,
                player_id=p.player_id, player_name=p.player_name, market=p.market,
                market_label=p.market_label, line=p.line, floor=p.floor, gap=p.gap,
                sample_average=p.sample_average, confidence=p.confidence, odds=p.odds,
                kelly_stake=p.kelly_stake, injury_summary=p.enrichment.perplexity_summary,
            ))
            saved += 1
    return saved


def _result_for_over(line: float, actual: float) -> str:
    if actual > line:
        return "win"
    if actual == line:
        return "push"
    return "loss"


def _units(result: str, odds: int | None) -> float:
    """Flat 1-unit P&L at the stored price (for model evaluation)."""
    decimal = american_to_decimal(odds if odds is not None else -110)
    if result == "win":
        return round(decimal - 1, 3)
    if result == "loss":
        return -1.0
    return 0.0


def record_outcome(
    pick_id: str, actual_value: float, closing_line: float | None = None
) -> dict | None:
    """Grade one tracked pick (floor-model picks are OVER bets)."""
    with get_session() as s:
        pick = s.get(TrackedPick, pick_id)
        if pick is None:
            return None
        result = _result_for_over(pick.line, actual_value)
        clv = compute_clv(pick.line, closing_line) if closing_line is not None else None
        units = _units(result, pick.odds)
        if pick.outcome:
            s.delete(pick.outcome)
            s.flush()
        s.add(OutcomeRow(pick_id=pick.id, result=result, actual_value=actual_value,
                         closing_line=closing_line, clv=clv, units=units))
        pick.status = "graded"
        return {"pick_id": pick.id, "result": result, "actual_value": actual_value,
                "closing_line": closing_line, "clv": clv, "units": units}


def open_picks(sport: str | None = None) -> list[dict]:
    with get_session() as s:
        stmt = select(TrackedPick).where(TrackedPick.status == "open")
        if sport:
            stmt = stmt.where(TrackedPick.sport == sport)
        return [
            {"id": p.id, "sport": p.sport, "game_id": p.game_id, "player_id": p.player_id,
             "player_name": p.player_name, "market": p.market, "line": p.line}
            for p in s.scalars(stmt)
        ]


def performance_summary() -> dict:
    """Hit rate, record, ROI, and avg CLV — overall and per sport."""
    with get_session() as s:
        rows = s.execute(
            select(TrackedPick, OutcomeRow).join(OutcomeRow, OutcomeRow.pick_id == TrackedPick.id)
        ).all()

    buckets: dict[str, dict] = {}

    def bucket(name: str) -> dict:
        return buckets.setdefault(name, {"graded": 0, "wins": 0, "losses": 0, "pushes": 0,
                                         "units": 0.0, "clv_sum": 0.0, "clv_n": 0})

    for pick, oc in rows:
        for name in ("overall", pick.sport):
            b = bucket(name)
            b["graded"] += 1
            b["units"] += oc.units
            b[{"win": "wins", "loss": "losses", "push": "pushes"}[oc.result]] += 1
            if oc.clv is not None:
                b["clv_sum"] += oc.clv
                b["clv_n"] += 1

    def finalize(b: dict) -> dict:
        decided = b["wins"] + b["losses"]
        return {
            "graded": b["graded"], "wins": b["wins"], "losses": b["losses"], "pushes": b["pushes"],
            "hit_rate": round(b["wins"] / decided * 100, 1) if decided else None,
            "units": round(b["units"], 2),
            "roi": round(b["units"] / b["graded"] * 100, 1) if b["graded"] else None,
            "avg_clv": round(b["clv_sum"] / b["clv_n"], 2) if b["clv_n"] else None,
        }

    with get_session() as s:
        open_count = s.scalar(
            select(func.count()).select_from(TrackedPick).where(TrackedPick.status == "open")
        ) or 0

    return {
        "open_picks": open_count,
        "overall": finalize(buckets["overall"]) if "overall" in buckets else None,
        "by_sport": {k: finalize(v) for k, v in buckets.items() if k != "overall"},
    }

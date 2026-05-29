"""End-to-end pipeline and API tests over the sample feed."""

from fastapi.testclient import TestClient

from app.main import app
from app.pipeline import build_game_parlay, generate_picks
from app.sample_data import SAMPLE_GAMES, SAMPLE_PROPS
from app.sports.registry import Sport

client = TestClient(app)


def test_nba_pipeline_produces_full_parlay():
    props = SAMPLE_PROPS[Sport.NBA]
    picks = generate_picks(Sport.NBA, props, bankroll=1000)
    # All eligible picks must clear their line and carry a confidence score.
    assert picks, "expected eligible NBA picks"
    assert all(p.floor >= p.line for p in picks)
    assert all(0 <= p.confidence <= 100 for p in picks)

    parlay = build_game_parlay(Sport.NBA, SAMPLE_GAMES[Sport.NBA], props, bankroll=1000)
    assert not parlay.no_bet
    assert len(parlay.legs) == 8
    assert parlay.recommended_stake >= 0


def test_nfl_floor_model_drops_ineligible_props():
    props = SAMPLE_PROPS[Sport.NFL]
    picks = generate_picks(Sport.NFL, props, bankroll=1000)
    markets = {(p.player_name, p.market) for p in picks}
    # Injury-flagged, ceiling, and all-N-miss props must be excluded.
    assert ("Rashee Rice", "rec_yds") not in markets
    assert ("Isiah Pacheco", "longest_rush") not in markets
    assert ("Travis Kelce", "tds") not in markets
    # Not enough legs for an 8-leg parlay → NO BET, never forced.
    parlay = build_game_parlay(Sport.NFL, SAMPLE_GAMES[Sport.NFL], props, bankroll=1000)
    assert parlay.no_bet


def test_health_and_picks_endpoints():
    assert client.get("/health").json()["status"] == "ok"
    r = client.get("/api/picks/nba")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(body["picks"]) > 0


def test_grade_endpoint_computes_clv():
    picks = client.get("/api/picks/nba").json()["picks"]
    pick_id = picks[0]["id"]
    r = client.post(
        f"/api/picks/{pick_id}/grade",
        json={"actual_value": 99, "closing_line": picks[0]["line"] + 1},
    )
    assert r.status_code == 200
    assert r.json()["result"] == "win"

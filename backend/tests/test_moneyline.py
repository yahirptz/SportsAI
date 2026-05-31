"""Moneyline form-model + endpoint tests (offline — network build monkeypatched)."""

from fastapi.testclient import TestClient

from app.main import app
from app.moneyline import form as form_mod
from app.scoring.kelly import expected_value, payout

client = TestClient(app)

_FAKE_FORM = {
    "sport": "nba",
    "game": {"home": "Home Team", "away": "Away Team", "scheduled": "2026-06-01T00:00:00+00:00"},
    "home": {"team": "Home Team", "form_score": 72.0, "last5": ["W", "W", "L", "W", "W"],
             "margins": [8, 5, -3, 10, 6], "avg_margin": 5.2, "points_allowed_floor": 98,
             "home_record": "3-0", "away_record": "1-1", "rest_days": 2, "pace": 228.0},
    "away": {"team": "Away Team", "form_score": 55.0, "last5": ["L", "W", "L", "L", "W"],
             "margins": [-6, 4, -8, -2, 3], "avg_margin": -1.8, "points_allowed_floor": 105,
             "home_record": "1-1", "away_record": "1-2", "rest_days": 1, "pace": 232.0},
}


def test_expected_value_formula():
    assert payout(150) == 150
    assert round(payout(-200), 1) == 50.0
    # +100 at 60% win => 0.6*100 - 0.4*100 = 20
    assert expected_value(0.60, 100) == 20.0
    # certain loss-priced underdog still negative-ish at low p
    assert expected_value(0.10, -150) < 0


def test_form_score_rewards_winning_and_margin():
    weak = form_mod._form_score(win_rate=0.2, avg_margin=-8, rest=2)
    strong = form_mod._form_score(win_rate=0.8, avg_margin=10, rest=2)
    assert strong > weak
    # back-to-back applies a fatigue haircut to the rest factor
    rested = form_mod._form_score(0.6, 4, rest=3)
    tired = form_mod._form_score(0.6, 4, rest=1)
    assert tired < rested


def test_predict_uses_form_and_adds_ev_kelly(monkeypatch):
    monkeypatch.setattr(form_mod, "build_form", lambda sport: _FAKE_FORM)
    from app.sports.registry import Sport
    out = form_mod.predict_moneyline(Sport.NBA, home_odds=-130, away_odds=110, bankroll=1000)
    assert out["home_form_score"] == 72.0 and out["away_form_score"] == 55.0
    assert 0 < out["home_win_prob"] < 1
    assert "expected_value" in out and "kelly_fraction" in out
    assert "honest_note" in out


def test_form_endpoint(monkeypatch):
    monkeypatch.setattr("app.moneyline.build_form", lambda sport: _FAKE_FORM)
    r = client.get("/api/moneyline/form/nba")
    assert r.status_code == 200 and r.json()["home"]["team"] == "Home Team"


def test_predict_endpoint(monkeypatch):
    monkeypatch.setattr(form_mod, "build_form", lambda sport: _FAKE_FORM)
    r = client.post("/api/moneyline/predict", json={"sport": "nba", "home_odds": -130, "away_odds": 110})
    assert r.status_code == 200
    body = r.json()
    assert "lean" in body and "kelly_fraction" in body and "home_win_prob" in body

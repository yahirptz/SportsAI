"""Odds workflow endpoint tests (sample feed, temp lines file)."""

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_odds_roundtrip_and_unpriced(tmp_path, monkeypatch):
    lines = tmp_path / "lines.json"
    monkeypatch.setattr(settings, "odds_lines_path", str(lines))

    # Starts empty.
    assert client.get("/api/odds/lines").json()["count"] == 0

    # Unpriced lists the sample slate's candidate markets.
    before = client.get("/api/odds/unpriced/nba").json()
    assert before["count"] > 0
    first = before["unpriced"][0]

    # Add a line for that market; it persists and disappears from unpriced.
    r = client.post("/api/odds/lines", json={
        "sport": "nba", "player": first["player"], "market": first["market"],
        "line": 1.5, "odds": -120,
    })
    assert r.status_code == 200 and r.json()["ok"]

    assert client.get("/api/odds/lines").json()["count"] == 1
    after = client.get("/api/odds/unpriced/nba").json()
    assert after["count"] == before["count"] - 1


def test_upsert_rejects_unknown_market(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "odds_lines_path", str(tmp_path / "l.json"))
    r = client.post("/api/odds/lines", json={
        "sport": "nba", "player": "Test", "market": "not_a_stat", "line": 1.5, "odds": -110,
    })
    assert r.status_code == 400

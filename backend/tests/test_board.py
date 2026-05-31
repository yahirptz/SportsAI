"""FanDuel parser + floor board + bet builder tests (offline)."""

from app.board import builder
from app.board.builder import FloorPlay, assemble_bet, build_floor_board
from app.board.fanduel import parse_fanduel
from app.sports.registry import Sport

SAMPLE = """To Score 20+ Points
To Score 20+ Points
Tap a player name or icon for stats and more betting options

Victor Wembanyama
-530

Stephon Castle
+200
Sat 8:10pm ET
More wagers
Show more

2+ Made Threes
2+ Made Threes

Devin Vassell
-350
Sat 8:10pm ET
More wagers
"""


def test_parse_fanduel_tiers():
    props = parse_fanduel(SAMPLE)
    by = {(p.player, p.market): p for p in props}
    wemby = by[("Victor Wembanyama", "pts")]
    assert wemby.threshold == 20 and wemby.line == 19.5 and wemby.odds == -530
    assert wemby.game_time == "Sat 8:10pm ET"
    assert by[("Stephon Castle", "pts")].odds == 200
    vass = by[("Devin Vassell", "fg3m")]
    assert vass.threshold == 2 and vass.line == 1.5 and vass.odds == -350


def test_parse_fanduel_mlb_markets():
    mlb = (
        "To Record 2+ Hits\nAaron Judge\n+180\nSun 1:40pm ET\n"
        "To Record 2+ Total Bases\nAaron Judge\n-140\nSun 1:40pm ET\n"
        "To Record 5+ Strikeouts\nTarik Skubal\n-150\nSun 1:40pm ET\n"
        "1+ RBIs\nShohei Ohtani\n-115\nSun 1:40pm ET\n"
    )
    by = {(p.player, p.market): p for p in parse_fanduel(mlb)}
    assert by[("Aaron Judge", "hits")].line == 1.5
    assert by[("Aaron Judge", "tb")].threshold == 2
    assert by[("Tarik Skubal", "k_pitcher")].threshold == 5
    assert by[("Shohei Ohtani", "rbi")].odds == -115


def test_build_board_keeps_only_all_n_clears(monkeypatch):
    # Synthetic floors: Wemby clears 20+ every game; Castle misses 20+ once.
    monkeypatch.setattr(builder, "get_game_floors", lambda sport, n=6: {
        "Victor Wembanyama": {"pts": [28, 20, 33, 26, 21, 41], "reb": [], "ast": [], "fg3m": []},
        "Stephon Castle": {"pts": [17, 24, 13, 14, 25, 17], "reb": [], "ast": [], "fg3m": []},
        "Devin Vassell": {"fg3m": [4, 2, 2, 3, 6, 3], "pts": [], "reb": [], "ast": []},
    })
    board = build_floor_board(Sport.NBA, parse_fanduel(SAMPLE))
    players = {p.player for p in board}
    assert "Victor Wembanyama" in players      # 20+ all 6
    assert "Devin Vassell" in players          # 2+ threes all 6
    assert "Stephon Castle" not in players     # 20+ only 4/6


def _play(player, odds, prob, market="pts"):
    return FloorPlay(player=player, market=market, market_label="x", threshold=10,
                     line=9.5, odds=odds, floor=12, hit_count=6, n=6, hit_prob=prob,
                     cushion=2, values=[12, 13, 12, 14, 12, 13])


def test_assemble_single_and_parlay():
    plays = [_play("A", -300, 0.9), _play("B", -200, 0.85), _play("C", +120, 0.6)]
    single = assemble_bet(plays, legs=1)
    assert single["leg_count"] == 1 and single["legs"][0]["player"] == "A"

    parlay = assemble_bet(plays, legs=3, bankroll=1000)
    assert parlay["leg_count"] == 3
    assert parlay["combined_decimal"] > 1
    assert 0 <= parlay["recommended_stake"] <= 50  # capped at 5% of 1000


def test_assemble_dedupes_player_and_filters_markets():
    plays = [_play("A", -300, 0.9, "pts"), _play("A", -150, 0.8, "reb"), _play("B", +100, 0.7, "ast")]
    only_ast = assemble_bet(plays, legs=3, markets=["ast"])
    assert [l["player"] for l in only_ast["legs"]] == ["B"]
    # one leg per player even across markets
    both = assemble_bet(plays, legs=5)
    assert [l["player"] for l in both["legs"]] == ["A", "B"]

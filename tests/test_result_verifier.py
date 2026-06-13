"""
test_result_verifier.py — C-3（純函式，不打網路、不寫狀態）
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import result_verifier as rv  # noqa: E402


def _pred(best_pick, fair=None, model="market_implied_v1", gid="g1"):
    return {"game_id": gid, "model": model,
            "fair_prob": fair or {"home": 0.56, "away": 0.44},
            "best_pick": best_pick}


def _result(hs, aws, completed=True, gid="g1"):
    return {"id": gid, "completed": completed, "home_score": hs, "away_score": aws}


PICK_HOME = {"outcome": "home", "edge": 0.038, "odds": 1.85}
PICK_AWAY = {"outcome": "away", "edge": 0.02, "odds": 2.30}


# ── home 勝 + pick 命中 → hit + 正報酬 ───────────────
def test_home_win_pick_hit():
    r = rv.verify(_pred(PICK_HOME), _result(110, 100))
    assert r["winner"] == "home"
    assert r["pick_hit"] is True and r["moneyline_hit"] is True
    assert abs(r["realized_return"] - 0.85) < 1e-9   # odds-1
    assert abs(r["fair_prob_winner"] - 0.56) < 1e-9
    assert r["model"] == "market_implied_v1"


# ── home 勝 + pick 落空（pick away）→ miss + 負報酬 ──
def test_home_win_pick_miss():
    r = rv.verify(_pred(PICK_AWAY), _result(110, 100))
    assert r["winner"] == "home"
    assert r["pick_outcome"] == "away"
    assert r["pick_hit"] is False and r["moneyline_hit"] is False
    assert r["realized_return"] == -1.0
    assert abs(r["fair_prob_winner"] - 0.56) < 1e-9  # winner=home → fair_home


# ── away 勝 ──────────────────────────────────────────
def test_away_win():
    r = rv.verify(_pred(PICK_AWAY), _result(98, 105))
    assert r["winner"] == "away"
    assert r["pick_hit"] is True
    assert abs(r["realized_return"] - 1.30) < 1e-9
    assert abs(r["fair_prob_winner"] - 0.44) < 1e-9  # winner=away → fair_away


# ── draw（FIFA 三向）→ fair_draw 映射 ────────────────
def test_draw():
    pred = _pred({"outcome": "home", "edge": 0.05, "odds": 2.2},
                 fair={"home": 0.45, "away": 0.30, "draw": 0.25})
    r = rv.verify(pred, _result(1, 1))
    assert r["winner"] == "draw"
    assert r["pick_hit"] is False               # 押 home，結果 draw
    assert r["realized_return"] == -1.0
    assert abs(r["fair_prob_winner"] - 0.25) < 1e-9  # winner=draw → fair_draw


# ── best_pick=None → pick/ml/return 皆 null，仍給 fair_prob_winner ─
def test_no_best_pick():
    r = rv.verify(_pred(None), _result(110, 100))
    assert r["winner"] == "home"
    assert r["pick_outcome"] is None
    assert r["pick_hit"] is None
    assert r["moneyline_hit"] is None
    assert r["realized_return"] is None
    assert abs(r["fair_prob_winner"] - 0.56) < 1e-9  # 仍輸出供校準


# ── completed=false → None ───────────────────────────
def test_not_completed_returns_none():
    assert rv.verify(_pred(PICK_HOME), _result(0, 0, completed=False)) is None


# ── 缺 score → None ──────────────────────────────────
def test_missing_score_returns_none():
    assert rv.verify(_pred(PICK_HOME), _result(None, 100)) is None
    assert rv.verify(_pred(PICK_HOME), _result(110, None)) is None


# ── EV 正報酬（高賠率命中）─────────────────────────
def test_ev_positive_high_odds():
    r = rv.verify(_pred({"outcome": "home", "edge": 0.1, "odds": 3.40}), _result(110, 100))
    assert abs(r["realized_return"] - 2.40) < 1e-9


# ── EV 負報酬（落空一律 -1）────────────────────────
def test_ev_negative():
    r = rv.verify(_pred({"outcome": "away", "edge": 0.1, "odds": 3.40}), _result(110, 100))
    assert r["realized_return"] == -1.0


# ── odds 壞值 → realized_return None（防禦）──────────
def test_bad_odds_return_none():
    r = rv.verify(_pred({"outcome": "home", "edge": 0.1, "odds": None}), _result(110, 100))
    assert r["pick_hit"] is True
    assert r["realized_return"] is None


# ── game_id fallback 到 result.id ────────────────────
def test_game_id_fallback():
    pred = {"model": "m", "fair_prob": {"home": 0.5, "away": 0.5}, "best_pick": None}
    r = rv.verify(pred, _result(110, 100, gid="abc"))
    assert r["game_id"] == "abc"

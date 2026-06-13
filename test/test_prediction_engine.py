"""
test_prediction_engine.py — Processing 純數學測試（去 Vig / 共識 / Edge / predict）
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import prediction_engine as pe  # noqa: E402
from constants import MODEL_TAG  # noqa: E402


def book(home=None, away=None, draw=None, key="bk"):
    return {"book": key, "home": home, "away": away, "draw": draw}


def game(books, **kw):
    g = {"id": "g1", "sport": "NBA", "home": "A", "away": "B",
         "start_time": "2026-06-10T12:30:00+08:00", "odds_h2h": books}
    g.update(kw)
    return g


# ── 1. 2-way 去 Vig ──────────────────────────────────
def test_devig_2way():
    fair = pe.devig_one(book(1.90, 1.95))
    assert fair["home"] == pytest.approx(0.5065, abs=1e-3)
    assert fair["away"] == pytest.approx(0.4935, abs=1e-3)
    assert sum(fair.values()) == pytest.approx(1.0)


# ── 2. 3-way（FIFA 含 draw）去 Vig ───────────────────
def test_devig_3way():
    fair = pe.devig_one(book(2.50, 2.90, draw=3.20))
    assert set(fair) == {"home", "away", "draw"}
    assert sum(fair.values()) == pytest.approx(1.0)


# ── 3. 共識 = 多家平均 ───────────────────────────────
def test_consensus_average():
    b1 = book(1.80, 2.20)   # fair 0.55 / 0.45
    b2 = book(2.10, 1.80)
    con = pe.consensus([b1, b2])
    f1, f2 = pe.devig_one(b1), pe.devig_one(b2)
    assert con["home"] == pytest.approx((f1["home"] + f2["home"]) / 2, abs=1e-3)
    assert sum(con.values()) == pytest.approx(1.0)


# ── 4. Edge 正值（某家優於共識）──────────────────────
def test_edge_positive_and_best_pick():
    pred = pe.predict(game([book(1.80, 2.20, key="x"), book(2.10, 1.80, key="y")]))
    # best_odds: home=2.10, away=2.20；共識 away≈0.4942 → edge_away≈0.087
    assert pred["edge"]["away"] == pytest.approx(0.0873, abs=2e-3)
    assert pred["best_pick"]["outcome"] == "away"
    assert pred["best_pick"]["odds"] == 2.20


# ── 5. 無正 edge → best_pick None ────────────────────
def test_no_positive_edge_best_pick_none():
    pred = pe.predict(game([book(1.90, 1.95)]))  # 單一含 vig → 全負
    assert pred["best_pick"] is None
    assert all(v < 0 for v in pred["edge"].values())


# ── 6. 單一 bookmaker：共識 = 該家 ──────────────────
def test_single_bookmaker_consensus():
    b = book(1.80, 2.20)
    assert pe.consensus([b]) == pe.devig_one(b)


# ── 7. fair 機率和 ≈ 1 不變式 ────────────────────────
def test_fair_sums_to_one():
    assert sum(pe.consensus([book(1.5, 3.0)]).values()) == pytest.approx(1.0)
    assert sum(pe.consensus([book(2.5, 2.9, draw=3.2)]).values()) == pytest.approx(1.0)


# ── 8. 無有效市場 → None ─────────────────────────────
def test_no_market_returns_none():
    assert pe.predict(game([])) is None


# ── 9. 無效 price（≤1 / 缺值）→ 略過該家 ─────────────
def test_invalid_price_skipped():
    # home 價 1.0（無效）+ 只剩 away → 該家 <2 outcome → None → predict None
    assert pe.devig_one(book(1.0, 1.95)) is None
    assert pe.predict(game([book(1.0, 1.95)])) is None
    # 缺值
    assert pe.devig_one({"book": "x", "home": None, "away": None, "draw": None}) is None


# ── 11. schema 完整性 ────────────────────────────────
def test_schema_completeness():
    pred = pe.predict(game([book(1.80, 2.20), book(2.10, 1.85)]))
    for key in ("game_id", "sport", "home", "away", "start_time", "market",
                "bookmaker_count", "fair_prob", "best_odds", "edge",
                "best_pick", "avg_overround", "model", "generated_at"):
        assert key in pred
    assert pred["model"] == MODEL_TAG
    assert pred["market"] == "h2h"
    assert pred["bookmaker_count"] == 2


# ── 12. avg_overround 計算 ───────────────────────────
def test_avg_overround():
    # 1/1.90 + 1/1.95 - 1 = 0.0391
    pred = pe.predict(game([book(1.90, 1.95)]))
    assert pred["avg_overround"] == pytest.approx(0.0391, abs=1e-3)

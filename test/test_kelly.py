"""
test_kelly.py — P1 FEATURE 1：Kelly + Risk 引擎單元測試。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import kelly  # noqa: E402


def test_positive_edge_gives_positive_fraction():
    # p=0.6, odds=2.0 → b=1, f=(1*0.6-0.4)/1=0.2
    f = kelly.kelly_fraction(0.6, 2.0)
    assert abs(f - 0.2) < 1e-9


def test_no_edge_fraction_is_negative_then_clipped_to_zero():
    # p=0.5, odds=1.5 → b=0.5, f=(0.5*0.5-0.5)/0.5 = -0.5 → clip 0
    raw = kelly.kelly_fraction(0.5, 1.5)
    assert raw < 0
    assert kelly.clip_fraction(raw) == 0.0


def test_clip_caps_at_025():
    assert kelly.clip_fraction(0.9) == 0.25
    assert kelly.clip_fraction(0.25) == 0.25


def test_clip_zero_and_negative():
    assert kelly.clip_fraction(0.0) == 0.0
    assert kelly.clip_fraction(-0.3) == 0.0


def test_odds_floor_guard_returns_zero():
    # odds <= 1.01 → 0（無可下注空間）
    assert kelly.kelly_fraction(0.99, 1.01) == 0.0
    assert kelly.kelly_fraction(0.99, 1.00) == 0.0


def test_risk_low_boundary():
    assert kelly.classify_risk(0.0) == "low"
    assert kelly.classify_risk(0.0199) == "low"


def test_risk_medium_boundary():
    assert kelly.classify_risk(0.02) == "medium"
    assert kelly.classify_risk(0.06) == "medium"


def test_risk_high():
    assert kelly.classify_risk(0.0601) == "high"
    assert kelly.classify_risk(0.25) == "high"


def test_compute_kelly_with_best_pick():
    pred = {
        "fair_prob": {"home": 0.6, "away": 0.4},
        "best_pick": {"outcome": "home", "edge": 0.08, "odds": 2.0},
    }
    out = kelly.compute_kelly(pred)
    assert out["kelly"]["fraction"] == 0.2
    assert out["kelly"]["clipped_fraction"] == 0.2
    assert out["risk_level"] == "high"


def test_compute_kelly_without_best_pick():
    out = kelly.compute_kelly({"fair_prob": {"home": 0.5}, "best_pick": None})
    assert out["kelly"]["fraction"] == 0.0
    assert out["kelly"]["clipped_fraction"] == 0.0
    assert out["risk_level"] == "low"


def test_compute_kelly_missing_prob_safe():
    pred = {"fair_prob": {}, "best_pick": {"outcome": "home", "odds": 2.0}}
    out = kelly.compute_kelly(pred)
    assert out["kelly"]["clipped_fraction"] == 0.0


def test_attach_is_non_mutating_and_additive():
    pred = {"game_id": "g1", "fair_prob": {"home": 0.6}, "best_pick": {"outcome": "home", "odds": 2.0}}
    before = dict(pred)
    enriched = kelly.attach(pred)
    # 原 dict 不被改動
    assert pred == before
    assert "kelly" not in pred
    # 新 dict 含原欄位 + 新欄位
    assert enriched["game_id"] == "g1"
    assert "kelly" in enriched and "risk_level" in enriched

"""futures_devig 測試。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import futures_devig as fd  # noqa: E402


def test_returns_four_keys_and_fair_sums_to_one():
    out = fd.devig({"A": 2.0, "B": 2.0})
    assert set(out) == {"raw_odds", "implied_probability", "overround", "fair_probability"}
    assert abs(sum(out["fair_probability"].values()) - 1.0) < 1e-9
    assert abs(out["fair_probability"]["A"] - 0.5) < 1e-9
    assert abs(out["overround"] - 1.0) < 1e-9   # 公平盤無 vig


def test_overround_reflects_vig():
    out = fd.devig({"A": 1.5, "B": 2.5})
    assert out["overround"] > 1.0                              # 有 vig
    assert abs(sum(out["fair_probability"].values()) - 1.0) < 1e-9
    assert out["raw_odds"]["A"] == 1.5                         # raw 保留供 audit


def test_lower_odds_higher_fair_prob():
    out = fd.devig({"Fav": 1.5, "Dog": 4.0})
    assert out["fair_probability"]["Fav"] > out["fair_probability"]["Dog"]


def test_insufficient_or_bad_returns_none():
    assert fd.devig({"A": 2.0}) is None          # <2 outcomes
    assert fd.devig({}) is None
    assert fd.devig(None) is None
    assert fd.devig({"A": 1.0, "B": 0.5}) is None  # 無 >1.0 的有效賠率


def test_ignores_invalid_entries_but_keeps_valid():
    out = fd.devig({"A": 2.0, "B": 2.0, "C": "x", "D": True})
    assert set(out["raw_odds"]) == {"A", "B"}      # 非數值/bool 被剔除

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import monte_carlo_engine as mc  # noqa: E402
import score_model as sm  # noqa: E402


def test_run_none_returns_none():
    assert mc.run_monte_carlo(None) is None


def test_poisson_win_prob_normalized_no_nan():
    r = mc.simulate_poisson(1.5, 1.2, n=5000, seed=1)
    wp = r["win_prob"]
    s = wp["home"] + wp["draw"] + wp["away"]
    assert abs(s - 1.0) < 1e-6
    assert all(not math.isnan(v) and 0.0 <= v <= 1.0 for v in wp.values())


def test_mc_converges_to_analytic():
    """MC 勝率必須收斂回 score_model 的 analytic 機率（核心正確性）。"""
    model = sm.build_score_model({
        "sport": "FIFA",
        "odds_totals": [{"book": "x", "line": 2.7}],
        "odds_spreads": [{"book": "x", "home_point": -0.5}],
    })
    analytic = model["outcome_probs"]
    sim = mc.run_monte_carlo(model, n=40000, seed=42)["win_prob"]
    for key in ("home", "draw", "away"):
        assert abs(sim[key] - analytic[key]) < 0.03, f"{key}: MC {sim[key]} vs analytic {analytic[key]}"


def test_mc_variance_within_bound():
    model = sm.build_score_model({
        "sport": "FIFA",
        "odds_totals": [{"book": "x", "line": 2.5}],
        "odds_spreads": [{"book": "x", "home_point": 0.0}],
    })
    a = mc.run_monte_carlo(model, n=20000, seed=1)["win_prob"]["home"]
    b = mc.run_monte_carlo(model, n=20000, seed=2)["win_prob"]["home"]
    assert abs(a - b) < 0.03  # 不同 seed 的變異在界限內


def test_normal_margin_symmetric_when_even():
    model = sm.build_score_model({
        "sport": "NBA",
        "odds_totals": [{"book": "x", "line": 220.5}],
        "odds_spreads": [{"book": "x", "home_point": 0.0}],
    })
    sim = mc.run_monte_carlo(model, n=30000, seed=7)
    assert abs(sim["win_prob"]["home"] - 0.5) < 0.03  # 均勢 → 接近 50/50
    assert "top_scorelines" not in sim  # NBA 無精準比分

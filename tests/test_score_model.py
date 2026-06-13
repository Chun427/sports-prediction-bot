import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import score_model as sm  # noqa: E402


def _fifa_game(total_line=2.5, home_point=-0.5):
    return {
        "sport": "FIFA",
        "odds_totals": [{"book": "x", "line": total_line, "over": 1.9, "under": 1.9}],
        "odds_spreads": [{"book": "x", "home_point": home_point, "away_point": -home_point}],
    }


def test_consensus_total_median():
    assert sm.consensus_total([{"line": 2.0}, {"line": 2.5}, {"line": 3.0}]) == 2.5
    assert sm.consensus_total([]) is None


def test_consensus_supremacy_sign():
    # 主隊被讓分 -1.5 → supremacy = +1.5
    assert sm.consensus_supremacy([{"home_point": -1.5}]) == 1.5
    assert sm.consensus_supremacy([]) is None


def test_split_lambdas_invariants():
    lh, la = sm.split_lambdas(3.0, 1.0)
    assert abs((lh + la) - 3.0) < 1e-9
    assert abs((lh - la) - 1.0) < 1e-9
    assert lh > 0 and la > 0


def test_poisson_grid_normalized_nonneg():
    grid = sm.poisson_grid(1.4, 1.1)
    s = sum(grid.values())
    assert abs(s - 1.0) < 1e-6
    assert all(p >= 0 for p in grid.values())


def test_outcome_probs_sum_to_one():
    grid = sm.poisson_grid(1.5, 1.2)
    op = sm.outcome_probs(grid)
    assert abs(op["home"] + op["draw"] + op["away"] - 1.0) < 1e-3


def test_top_scorelines_sorted_and_len():
    grid = sm.poisson_grid(1.5, 1.2)
    top = sm.top_scorelines(grid, 5)
    assert len(top) == 5
    probs = [t["prob"] for t in top]
    assert probs == sorted(probs, reverse=True)


def test_build_fifa_returns_poisson_with_scores():
    m = sm.build_score_model(_fifa_game(total_line=2.5, home_point=-0.5))
    assert m["type"] == "poisson"
    assert "top_scorelines" in m and len(m["top_scorelines"]) == 5
    # 被看好的主隊 λ 較高 → 勝率較高
    assert m["lambda_home"] > m["lambda_away"]
    assert m["outcome_probs"]["home"] > m["outcome_probs"]["away"]


def test_build_nba_normal_no_exact_scores():
    g = {
        "sport": "NBA",
        "odds_totals": [{"book": "x", "line": 220.5}],
        "odds_spreads": [{"book": "x", "home_point": -6.5}],
    }
    m = sm.build_score_model(g)
    assert m["type"] == "normal_margin"
    assert "top_scorelines" not in m  # NBA 不輸出精準比分
    assert m["outcome_probs"]["home"] > 0.5  # 主隊讓 6.5 → 較被看好


def test_build_returns_none_without_totals():
    g = {"sport": "FIFA", "odds_totals": [], "odds_spreads": [{"book": "x", "home_point": -0.5}]}
    assert sm.build_score_model(g) is None  # 無 λ 來源 → None（不捏造）


def test_unsupported_sport_returns_none():
    g = {"sport": "TENNIS", "odds_totals": [{"book": "x", "line": 2.5}]}
    assert sm.build_score_model(g) is None

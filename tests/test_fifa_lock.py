"""FIFA LOCK — characterization（golden）測試。

目的：保護 FIFA 預測模型不被未來改動破壞。以「固定輸入」pin 住
`build_score_model` 的 deterministic 輸出（λ / Poisson / outcome_probs /
top_scorelines）。任何對 FIFA Poisson / λ split / scoreline 邏輯的更動，
都會讓本測試失敗 → 等於把 FIFA 模型「鎖定」。

⚠️ 這是「FIFA_LOCK」的正確實作：用 golden 測試鎖定 *輸出*，
   而不是在 score_model / monte_carlo 等凍結核心裡注入 `if sport=="FIFA": pass`
   ——後者本身就是修改凍結核心、新增 dead code，反而提高風險。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import monte_carlo_engine as mc  # noqa: E402
import score_model as sm  # noqa: E402

# 固定輸入：total=2.5、home_point=-0.5（主隊小幅被看好）
_FIFA_GAME = {
    "sport": "FIFA",
    "odds_totals": [{"line": 2.5}],
    "odds_spreads": [{"home_point": -0.5}],
}


def test_fifa_in_poisson_sports():
    assert "FIFA" in sm.POISSON_SPORTS
    assert "FIFA" not in sm.NORMAL_SPORTS


def test_fifa_score_model_locked():
    m = sm.build_score_model(_FIFA_GAME)
    assert m is not None
    assert m["type"] == "poisson" and m["sport"] == "FIFA"
    # λ 拆分（鎖定）
    assert m["lambda_home"] == 1.5
    assert m["lambda_away"] == 1.0
    assert m["expected_total"] == 2.5
    assert m["supremacy"] == 0.5
    # 三路機率（去Vig/Poisson 結果，鎖定到小數 4 位）
    op = m["outcome_probs"]
    assert round(op["home"], 4) == 0.4879
    assert round(op["draw"], 4) == 0.2598
    assert round(op["away"], 4) == 0.2522
    # 最可能比分（鎖定）
    top = m["top_scorelines"]
    assert len(top) == 5
    assert top[0]["home"] == 1 and top[0]["away"] == 0
    assert round(top[0]["prob"], 4) == 0.1231


def test_fifa_mc_converges_to_model():
    """MC（seed 固定）應收斂回 analytic 機率（容差 ±0.02，避免跨版本脆弱）。"""
    m = sm.build_score_model(_FIFA_GAME)
    r = mc.run_monte_carlo(m, seed=42)
    wp = r["win_prob"]
    assert abs(wp["home"] - 0.4879) < 0.02
    assert abs(wp["draw"] - 0.2598) < 0.02
    assert abs(wp["away"] - 0.2522) < 0.02

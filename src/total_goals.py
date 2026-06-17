"""total_goals.py — 單場「總進球數分布」display helper（addon）。

誠實邊界：
  • 只「讀」prediction["model_score"] 既有的 lambda_home / lambda_away（Poisson 類才有）。
  • 總進球 T = H + A，H~Poisson(λ_home)、A~Poisson(λ_away) 獨立 → T ~ Poisson(λ_home+λ_away)。
    與模型自身 expected_total（=λ_home+λ_away）一致。
  • 不 import / 不修改 score_model / monte_carlo / Kelly / Edge。純標準數學。
  • NBA（無 lambda）→ 回 None，不顯示（不適用、不捏造）。
  • 僅單場分布；不做「全賽事加總」（無完整賽程，無從加總）。
"""
from __future__ import annotations

import math

_BUCKETS = [("0–1", 0, 1), ("2–3", 2, 3), ("4–5", 4, 5), ("6+", 6, None)]


def bucket_label_of_total(total: int) -> str:
    """實際總分落在哪一桶（邊界與 _BUCKETS 完全一致）；賽後對答案用。"""
    for label, lo, hi in _BUCKETS:
        if hi is None:
            if total >= lo:
                return label
        elif lo <= total <= hi:
            return label
    return _BUCKETS[-1][0]


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def goal_buckets(score: dict, max_goals: int = 20) -> dict | None:
    """回傳 {'mean': float, 'most_likely': str, 'buckets': [(label, prob), ...]}；
    無 lambda（如 NBA）回 None。"""
    if not isinstance(score, dict):
        return None
    lh, la = score.get("lambda_home"), score.get("lambda_away")
    if not isinstance(lh, (int, float)) or not isinstance(la, (int, float)):
        return None
    lam = float(lh) + float(la)
    pmf = [_poisson_pmf(k, lam) for k in range(max_goals + 1)]
    tail = max(0.0, 1.0 - sum(pmf))  # >max_goals 的尾巴併入最後一桶

    out = []
    for label, lo, hi in _BUCKETS:
        if hi is None:
            p = sum(pmf[lo:]) + tail
        else:
            p = sum(pmf[lo:hi + 1])
        out.append((label, p))
    most = max(out, key=lambda x: x[1])[0]
    return {"mean": lam, "most_likely": most, "buckets": out}


def render_total_goals_block(score: dict) -> list[str]:
    """回傳要插入 pregame 的行（list）；不適用時回空 list。"""
    g = goal_buckets(score)
    if not g:
        return []
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    ranked = sorted(g["buckets"], key=lambda x: x[1], reverse=True)
    lines = ["⚽ 總進球數預測"]
    for i, (label, p) in enumerate(ranked):
        m = medals[i] if i < len(medals) else f"{i + 1}."
        lines.append(f"{m} {label}球（{p * 100:.0f}%）")
    lines.append(f"🎯 最可能：{g['most_likely']}球")
    lines.append(f"📊 平均：{g['mean']:.2f}球")
    return lines

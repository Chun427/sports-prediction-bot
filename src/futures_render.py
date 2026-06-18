"""futures_render.py — 只負責「呈現」（Reviewer Rule 2）。

render 只接受『已備妥的資料』並格式化。嚴禁：排序、判斷能力、決定 N/A、決定是否抓 API。
不 import capability_registry、不 import fetcher（Reviewer Rule 3：renderer 不反向依賴）。
提供 render_text() 與 render_json()（未來 LINE/Discord/Telegram/Dashboard/CLI 共用）。

期望 data 結構（由 tournament_futures 準備好）：
  {
    "capability": str, "title": str,
    "available": bool, "na_reason": str | None,
    "source": str | None, "overround": float | None,
    "ranked": [ {"outcome": str, "fair_probability": float}, ... ],  # 已排序
    ... (raw_odds / implied_probability / fair_probability 供 json/audit)
  }
"""
from __future__ import annotations

import json


def render_text(data: dict | None) -> str:
    if not data:
        return "🏆 Futures：N/A"
    title = data.get("title") or data.get("capability") or "Futures"
    if not data.get("available"):
        return f"{title}：N/A（{data.get('na_reason') or '無資料'}）"
    lines = [title]
    for i, r in enumerate(data.get("ranked", []), 1):
        prob = r.get("fair_probability")
        pct = f"{prob * 100:.1f}%" if isinstance(prob, (int, float)) else "—"
        lines.append(f"{i}. {r.get('outcome', '—')}  {pct}")
    lines.append(f"📡 來源：{data.get('source') or '—'}（市場隱含·非模型）")
    return "\n".join(lines)


def render_json(data: dict | None) -> str:
    return json.dumps(data or {}, ensure_ascii=False)

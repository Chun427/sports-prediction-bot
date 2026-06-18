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


# ── 合併獎項呈現（render only：Rule 2，不排序/不判 N/A/不抓 API）────
_MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
_DIV = "━━━━━━━━━━━━━━━━"
_FOOTER = ["📡 數據來源：AI模型+真實數據+賠率", "⚠️ 請理性投注。"]


def render_awards(results: list | None, *, header: str | None = None) -> str:
    """把多個 build() 結果（Champion/GoldenBoot/GoldenGlove…）渲染成合併推播。

    available → Top5（🥇..5️⃣ + 機率）；否則 →「（暫無盤口資料）」。固定 footer。
    嚴禁排序/判斷能力/捏造——只格式化傳入的已備妥資料。
    """
    blocks = []
    for data in results or []:
        d = data or {}
        lines = [d.get("title") or d.get("capability") or "Futures"]
        if not d.get("available"):
            lines.append("（暫無盤口資料）")
        else:
            for i, r in enumerate((d.get("ranked") or [])[:5]):
                prob = r.get("fair_probability")
                pct = f"{prob * 100:.1f}%" if isinstance(prob, (int, float)) else "—"
                lines.append(f"{_MEDALS[i]} {r.get('outcome', '—')} {pct}")
        blocks.append("\n".join(lines))

    parts = []
    if header:
        parts.append(header)
    if blocks:
        parts.append(("\n" + _DIV + "\n").join(blocks))
    parts.append(_DIV + "\n" + "\n".join(_FOOTER))
    return "\n".join(parts)

"""audit_engine.py — V4 Phase 2：系統健康儀表板（KPI 層）。

回答一句話：「這個系統現在準不準？」

設計（對齊 V4_PHASE2_ARCHITECTURE §3.1、§6、V4_FEEDBACK_DESIGN §11）：
  • 唯一入口：只讀 dm.normalized_verified_view()。
  • 唯讀：不寫任何狀態、不 import 核心預測模組、不進 tick() 推播路徑。
  • 樣本不足 → 明確標記「僅供觀察」，不下結論、不推論、不轉型造假。
"""
from __future__ import annotations

import data_manager as dm

MIN_SAMPLE = 100  # 每組樣本低於此 → 標「樣本不足，僅供觀察」


def _as_bool(v):
    if v in (None, ""):
        return None
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


def _as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _rate(bools) -> dict:
    vals = [b for b in bools if b is not None]
    return {"n": len(vals), "hit_rate": (round(sum(vals) / len(vals), 4) if vals else None)}


def _avg(nums):
    vals = [x for x in nums if x is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def build_audit(rows=None) -> dict:
    """產生 baseline 健康報告（結構化 dict）。rows=None → 自 normalized view 讀。"""
    rows = dm.normalized_verified_view() if rows is None else rows
    by_sport: dict[str, list] = {}
    for r in rows:
        by_sport.setdefault((r.get("sport") or "?"), []).append(r)

    report = {"total": len(rows), "min_sample": MIN_SAMPLE, "by_sport": {}}
    for sport, rs in sorted(by_sport.items()):
        report["by_sport"][sport] = {
            "n": len(rs),
            "sufficient": len(rs) >= MIN_SAMPLE,
            "ml": _rate([_as_bool(r.get("pick_hit")) for r in rs]),
            "ah": _rate([_as_bool(r.get("ah_hit")) for r in rs]),
            "ou": _rate([_as_bool(r.get("ou_hit")) for r in rs]),
            "total_goals": _rate([_as_bool(r.get("total_goals_hit")) for r in rs]),
            "scoreline_avg_hits": _avg([_as_float(r.get("scoreline_hit")) for r in rs]),
            "avg_return": _avg([_as_float(r.get("realized_return")) for r in rs]),
        }
    return report


def render_audit(report=None) -> str:
    """把報告渲染成人類可讀文字（給 CLI / 排程報表用）。"""
    rep = build_audit() if report is None else report
    out = [f"📊 Audit Engine — 系統健康（共 {rep['total']} 場驗證）"]
    if not rep["by_sport"]:
        out.append("   （尚無驗證資料）")
        return "\n".join(out)

    def _fmt(label, m):
        if not m or m.get("hit_rate") is None:
            return f"   {label}: 無資料"
        return f"   {label}: {m['hit_rate'] * 100:.0f}%（n={m['n']}）"

    for sport, s in rep["by_sport"].items():
        flag = "" if s["sufficient"] else f"  ⚠️ 樣本不足（<{rep['min_sample']}），僅供觀察"
        out.append(f"── {sport}（n={s['n']}）{flag}")
        out.append(_fmt("ML 獨贏", s["ml"]))
        out.append(_fmt("AH 讓分", s["ah"]))
        out.append(_fmt("OU 大小", s["ou"]))
        out.append(_fmt("總進球（FIFA）", s["total_goals"]))
        sl = s["scoreline_avg_hits"]
        out.append(f"   比分平均命中: {sl if sl is not None else '無資料'} / 5")
        rr = s["avg_return"]
        out.append(f"   平均報酬: {rr * 100:+.1f}%" if rr is not None else "   平均報酬: 無資料")
    return "\n".join(out)

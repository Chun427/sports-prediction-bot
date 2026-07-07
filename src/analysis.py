"""
analysis.py — 命中率分析 / 未命中分析 / 改善建議（Layer 3 分析層，純新增）

Master SOP 合規：
- 不修改 frozen core（notifier / prediction pipeline / JSON schema / battle_report 既有函式）
- Patch only：本檔全部為新增函式，吃 battle_report 既有輸出（classify_miss /
  learning_summary / load_queue）為原料
- Evidence First：所有結論只依 Evidence；無資料時明確寫「Evidence 不足，目前無法判定」，
  絕不臆測
- 所有運動共用同一流程（FIFA / MLB / NBA 不寫死）

三個功能：
  功能一 analyze_single_game()      單場驗證分析
  功能二 analyze_daily()            每日戰報分析
  功能三 improvement_suggestions()  改善建議
外加對應的文字 renderer（沿用單一固定 ━ 分隔線，與 battle_report 一致）。
"""

import battle_report as br
from providers import default_providers

_INSUFFICIENT = "Evidence 不足，目前無法判定"
_INSUFFICIENT_FIX = "目前 Evidence 不足，建議先保存更多資料後再修改模型。"


# ══════════ 集中式 Root Cause Metadata（單一真相來源）══════════
# 監督建議①：human / weight hint / 短標籤 集中一份，未來新增 Root Cause
# （如 WEATHER / REFEREE）只需在此加一列，renderer / hint 全部共用。
# 欄位：
#   human        LINE 顯示的白話原因
#   short_label  「尚未接入」清單用的短名（None 表示非待接入類別）
#   improve      白話改善方向（None 表示無方向性可講）
#   weight_raise / weight_lower / weight_note  工程版權重建議（可判定類別才有）
ROOT_CAUSE_META = {
    "MODEL_DIRECTION_ERROR": {
        "human": "模型看錯了勝方（高估了實際落敗的一方）",
        "short_label": None,
        "improve": "先累積更多相同類型（模型與市場方向分歧）的比賽；"
                   "若同類型錯誤持續發生，再評估是否調整模型。",
        "weight_raise": ["市場共識勝率（devig_winprob）"],
        "weight_lower": ["模型自身方向權重（model_winprob）"],
        "weight_note": "方向與實際相反：市場隱含機率的相對可信度應提高",
    },
    "CUTOFF": {
        "human": "賽前推播未發出（排程／窗口問題，非模型判斷錯誤）",
        "short_label": None,
        "improve": "屬賽前推播未觸發，與模型無關；改善方向為觸發穩定度（排程），非模型。",
        "weight_raise": [],
        "weight_lower": [],
        "weight_note": "非模型問題：賽前推播未觸發（排程/窗口），與權重無關",
    },
    "UNKNOWN": {
        "human": "目前資料不足，暫時無法判斷真正原因",
        "short_label": None,
        "improve": None,
        "weight_raise": None, "weight_lower": None, "weight_note": None,
    },
    "INJURY": {
        "human": "可能有傷兵影響（尚未接入傷兵資料）",
        "short_label": "傷兵資料",
        "improve": None,
        "weight_raise": None, "weight_lower": None, "weight_note": None,
    },
    "LINEUP_CHANGE": {
        "human": "可能有先發陣容異動（尚未接入陣容資料）",
        "short_label": "先發名單",
        "improve": None,
        "weight_raise": None, "weight_lower": None, "weight_note": None,
    },
    "LINE_MOVEMENT": {
        "human": "賽前讓分線可能移動（尚未接入盤口快照）",
        "short_label": "即時盤口（讓分線）",
        "improve": None,
        "weight_raise": None, "weight_lower": None, "weight_note": None,
    },
    "ODDS_MOVEMENT": {
        "human": "賽前賠率可能變動（尚未接入盤口快照）",
        "short_label": "即時盤口（賠率）",
        "improve": None,
        "weight_raise": None, "weight_lower": None, "weight_note": None,
    },
    "MARKET_CHANGE": {
        "human": "市場結構可能變動（尚未接入市場資料）",
        "short_label": "市場結構資料",
        "improve": None,
        "weight_raise": None, "weight_lower": None, "weight_note": None,
    },
    "DATA_DELAY": {
        "human": "資料延遲（尚未接入執行時序資料）",
        "short_label": "執行時序資料",
        "improve": None,
        "weight_raise": None, "weight_lower": None, "weight_note": None,
    },
}

# 健康度星等門檻（監督建議②：不散落 magic number）
# (門檻分數, 星數)，由高到低；分數 >= 門檻即取該星數。
STAR_THRESHOLDS = [(70, 5), (60, 4), (50, 3), (40, 2), (0, 1)]


def _meta(code):
    return ROOT_CAUSE_META.get(code, {})


# 工程版權重建議：由集中 META 衍生（僅保留有 weight_raise/lower 的可判定類別）
_WEIGHT_HINTS = {
    code: {"raise": m["weight_raise"], "lower": m["weight_lower"],
           "note": m["weight_note"]}
    for code, m in ROOT_CAUSE_META.items()
    if m.get("weight_raise") is not None
}


# ────────── 權重方向建議（只依已判定的 Root Cause，不臆測）──────────
# 每個「可判定」的 Root Cause → 對應的權重調整方向建議（純規則，依 Evidence 類型）。
# 待接入的 Root Cause 不在此表 → 一律回「資料不足」。


def analyze_single_game(record, providers=None, context=None):
    """
    功能一：單場驗證分析。回傳結構化 dict（renderer 另處理成文字）。
    只依 Evidence：Root Cause 來自 classify_miss；權重建議只在可判定時給出。
    """
    providers = providers or default_providers()
    flags = (context or {}).get("flags", {}) if context else {}
    ctx = context or br.build_context(flags, record)
    rc = br.classify_miss(record, providers, ctx)

    cause = rc.get("root_cause")
    hint = _WEIGHT_HINTS.get(cause)
    if hint is not None:
        weight_advice = {
            "raise": hint["raise"],
            "lower": hint["lower"],
            "note": hint["note"],
            "insufficient": False,
        }
    else:
        # UNKNOWN 或待接入類別 → 不臆測
        weight_advice = {
            "raise": [],
            "lower": [],
            "note": _INSUFFICIENT,
            "insufficient": True,
        }

    # 缺哪些資料（來自 classify_miss 收集的 pending_providers）
    missing_sources = rc.get("pending_providers", [])

    return {
        "match_id": rc.get("match_id"),
        "sport": rc.get("sport"),
        "root_cause": cause,
        "confidence": rc.get("confidence"),
        "evidence": rc.get("evidence"),
        "source": rc.get("source"),
        "weight_advice": weight_advice,
        "missing_sources": missing_sources,
    }


def analyze_daily(report, learning=None, queue=None):
    """
    功能二：每日戰報分析。全部依 report / learning / queue 既有資料。
    """
    miss = report.get("miss_analysis", {})
    dist = dict(miss.get("distribution", {}))
    imp = report.get("improvement", {})

    total_miss = sum(dist.values())
    # Root Cause 排名 + 各自失敗比例
    ranking = []
    for rc, n in sorted(dist.items(), key=lambda kv: -kv[1]):
        pct = round(n / total_miss * 100, 1) if total_miss else None
        ranking.append({"root_cause": rc, "count": n, "pct": pct})

    # 命中率是否下降 + 原因（只依 improvement 既有欄位）
    declined = imp.get("declined_vs_week")
    decline_reason = imp.get("decline_reason") if declined else None

    # 重複出現的 Root Cause（跨日，來自 learning）
    repeated = None
    if learning and learning.get("available"):
        counts = learning.get("root_cause_counts", {})
        repeated = sorted(
            [(k, v) for k, v in counts.items() if v >= 2 and k != "UNKNOWN"],
            key=lambda kv: -kv[1])

    return {
        "date": report.get("date"),
        "declined_vs_week": declined,
        "decline_reason": decline_reason,
        "today_overall_rate": imp.get("today_overall_rate"),
        "week_overall_rate": imp.get("week_overall_rate"),
        "root_cause_ranking": ranking,
        "top_failure": imp.get("top_failure_root_cause"),
        "largest_error_game": imp.get("largest_error_game"),
        "repeated_failures": repeated,
        "worth_modifying_model": imp.get("worth_modifying_model", "NO"),
        "worth_reason": imp.get("worth_reason"),
    }


def improvement_suggestions(report, learning=None, queue=None):
    """
    功能三：改善建議。只依 Evidence / Learning Store / Validation Queue。
    無證據時回傳明確的「Evidence 不足」訊息。
    """
    providers = default_providers()
    not_connected = [{"root_cause": p.root_cause, "source": p.source_name}
                     for p in providers if not p.is_available()]

    # 依已判定的失敗類型給資料/權重建議（只在可判定時）
    miss = report.get("miss_analysis", {})
    dist = miss.get("distribution", {})
    add_data, lower_weight = [], []
    has_actionable = False
    for rc in dist:
        hint = _WEIGHT_HINTS.get(rc)
        if hint:
            has_actionable = True
            lower_weight.extend(hint["lower"])
    # 待接入 Provider 對應的「應補資料源」
    for nc in not_connected:
        add_data.append(nc["source"])

    # Validation Queue 中已 READY 的建議（可提 PR）
    ready = []
    if queue:
        ready = [{"id": it.get("id"), "reason": it.get("reason"),
                  "expected_gain": it.get("expected_gain"),
                  "modules": it.get("affected_modules")}
                 for it in queue if it.get("status") == "READY_FOR_PR"]

    # Learning 中已驗證有效的策略
    effective = {}
    if learning and learning.get("available"):
        effective = learning.get("effective_strategies", {})

    # 若完全沒有可行動的證據 → 誠實告知
    insufficient = (not has_actionable and not ready and not effective)

    return {
        "insufficient": insufficient,
        "message": _INSUFFICIENT_FIX if insufficient else None,
        "add_data_sources": sorted(set(add_data)),
        "lower_weight": sorted(set(lower_weight)),
        "providers_not_connected": not_connected,
        "ready_for_pr": ready,
        "ready_count": len(ready),   # 抽象化：renderer 只需數量
        "validated_effective_strategies": effective,
    }


# ────────── Renderer（沿用 battle_report 單一固定 ━ 分隔線）──────────
def _line(divider_len_override=None):
    return "━" * (divider_len_override or br.DIVIDER_LEN)


def render_single_analysis_text(analysis, divider_len_override=None):
    """功能一的文字輸出。所有運動共用；只呈現 Evidence。"""
    line = _line(divider_len_override)
    mid = str(analysis.get("match_id", "—"))
    mid = mid[:8] if len(mid) > 8 else mid
    out = ["📊 比賽結果分析", f"　場次：{mid}（{analysis.get('sport','—')}）", line]
    out.append("為什麼沒有命中？（依 Evidence）")
    out.append(f"　可能原因：{analysis.get('root_cause','—')}")
    out.append(f"　信心度：{analysis.get('confidence','—')}")
    out.append(f"　證據：{analysis.get('evidence','—')}")
    out.append(f"　來源：{analysis.get('source','—')}")
    out.append(line)
    wa = analysis.get("weight_advice", {})
    out.append("如果重新預測一次：")
    if wa.get("insufficient"):
        out.append(f"　{_INSUFFICIENT}")
    else:
        raise_ = wa.get("raise") or ["（無）"]
        lower = wa.get("lower") or ["（無）"]
        out.append(f"　應提高權重：{'、'.join(raise_)}")
        out.append(f"　應降低權重：{'、'.join(lower)}")
        if wa.get("note"):
            out.append(f"　說明：{wa['note']}")
    ms = analysis.get("missing_sources", [])
    if ms:
        out.append(line)
        out.append("資料不足（待接入）：")
        for m in ms:
            out.append(f"　- {m.get('root_cause')}：{m.get('unavailable_reason')}")
    return "\n".join(out)


def render_daily_analysis_text(daily, suggestions, divider_len_override=None):
    """功能二+三的文字輸出。所有運動共用。"""
    line = _line(divider_len_override)
    out = ["📊 每日戰報分析", f"📅 {daily.get('date','—')}", line]

    # 命中率是否下降
    tr = daily.get("today_overall_rate")
    wr = daily.get("week_overall_rate")
    out.append("今日命中率為何下降？")
    out.append(f"　今日整體：{'—' if tr is None else str(round(tr*100,1))+'%'}")
    out.append(f"　本週整體：{'—' if wr is None else str(round(wr*100,1))+'%'}")
    if daily.get("declined_vs_week"):
        out.append(f"　下降原因：{daily.get('decline_reason') or _INSUFFICIENT}")
    else:
        out.append("　未較本週下降")
    out.append(line)

    # Root Cause 排名 + 比例
    out.append("主要失敗原因（Root Cause 排名）")
    ranking = daily.get("root_cause_ranking", [])
    if ranking:
        for r in ranking:
            pct = "—" if r["pct"] is None else f"{r['pct']}%"
            out.append(f"　{r['root_cause']}：{r['count']} 場（{pct}）")
    else:
        out.append("　（今日無未命中或無資料）")
    out.append(f"　今天最大失敗因素：{daily.get('top_failure','—')}")

    # 重複出現
    rep = daily.get("repeated_failures")
    if rep:
        out.append("　重複出現：" + "、".join(f"{k}×{v}" for k, v in rep))
    out.append(line)

    # 是否值得改模型
    out.append(f"是否值得修改模型：{daily.get('worth_modifying_model','NO')}")
    if daily.get("worth_reason"):
        out.append(f"　原因：{daily['worth_reason']}")
    out.append(line)

    # 改善方向（功能三）
    out.append("改善方向（依 Evidence / Learning / Queue）")
    if suggestions.get("insufficient"):
        out.append(f"　{suggestions.get('message')}")
    else:
        add = suggestions.get("add_data_sources") or []
        low = suggestions.get("lower_weight") or []
        if add:
            out.append(f"　建議增加資料：{'、'.join(add)}")
        if low:
            out.append(f"　建議降低權重：{'、'.join(low)}")
        eff = suggestions.get("validated_effective_strategies") or {}
        if eff:
            out.append("　已驗證有效策略：" +
                       "、".join(f"{k}({v})" for k, v in eff.items()))
        if suggestions.get("ready_count", 0):
            out.append(f"　可提 PR（已通過驗證）：{suggestions['ready_count']} 項")
    # 未接入 Provider
    nc = suggestions.get("providers_not_connected", [])
    if nc:
        out.append("　尚未接入 Provider：" +
                   "、".join(x["root_cause"] for x in nc))
    return "\n".join(out)


# ══════════ 人類語言層（Patch：LINE 用白話，JSON 保留原碼）══════════
# 依監督修正範圍：只把既有 Evidence 翻成好讀說明；
# 禁止產生 Elo / xG / 壓迫強度 / 主客場權重% / 勝率±% 等系統不存在的內容。

# Root Cause → 人類語言（LINE 顯示用；JSON 仍存原碼）

# 可判定類別 → 白話改善方向（不含任何捏造權重數字）


def human_cause(root_cause):
    """Root Cause 原碼 → 人類語言（讀集中 META）。未知碼原樣回傳（不臆測）。"""
    return _meta(root_cause).get("human", root_cause)


def render_single_analysis_human(analysis, divider_len_override=None):
    """
    功能一・白話版（LINE 用）。只呈現既有 Evidence，翻成好讀語言。
    不輸出工程碼、不產生不存在的權重/進階數據。
    """
    line = _line(divider_len_override)
    cause = analysis.get("root_cause")
    out = ["🧠 AI 賽後分析", line]
    out.append("未命中原因：")
    out.append(f"・{human_cause(cause)}")
    ev = analysis.get("evidence")
    if ev and cause != "UNKNOWN":
        out.append(f"・依據：{ev}")
    out.append(line)

    out.append("如果重新預測：")
    wa = analysis.get("weight_advice", {})
    if wa.get("insufficient"):
        out.append("・目前 Evidence 不足，暫時無法給出調整方向")
    else:
        imp = _meta(cause).get('improve')
        if imp:
            out.append(f"・{imp}")
        # 只有 MODEL_DIRECTION_ERROR 有方向性可講（市場vs模型），不給數字
        if cause == "MODEL_DIRECTION_ERROR":
            out.append("・本場模型較市場更偏離結果，市場共識的相對可信度較高")
    out.append(line)
    out.append("模型學習：")
    out.append("・本場已記入 Learning Store（跨日累積，用於統計最易致敗類型）")
    return "\n".join(out)


def render_daily_analysis_human(daily, suggestions, divider_len_override=None):
    """
    功能二＋三・白話版（LINE 用）。全部依既有資料，翻成好讀語言。
    """
    line = _line(divider_len_override)
    out = ["📈 今日命中率下降分析", f"📅 {daily.get('date','—')}", line]

    tr = daily.get("today_overall_rate")
    wr = daily.get("week_overall_rate")
    if daily.get("declined_vs_week"):
        out.append("今日整體命中率較本週下降。")
    else:
        out.append("今日整體命中率未較本週下降（屬正常波動）。")
    out.append(f"　今日：{'—' if tr is None else str(round(tr*100,1))+'%'}"
               f"　本週：{'—' if wr is None else str(round(wr*100,1))+'%'}")
    out.append(line)

    out.append("主要原因：")
    ranking = daily.get("root_cause_ranking", [])
    if ranking:
        for i, r in enumerate(ranking, 1):
            pct = "—" if r["pct"] is None else f"{r['pct']}%"
            out.append(f"{i}. {human_cause(r['root_cause'])}")
            out.append(f"　　{r['count']} 場（約佔今日失敗 {pct}）")
    else:
        out.append("　今日無未命中或無資料")
    out.append(line)

    out.append("改善建議：")
    out.append(f"　是否修改模型：{daily.get('worth_modifying_model','NO')}")
    if daily.get("worth_modifying_model") == "NO":
        out.append("　目前暫不建議修改模型，建議：")
        out.append("　・持續累積相同類型案例")
        out.append("　・等改善建議通過連續驗證後再評估")
    else:
        out.append(f"　已有 {suggestions.get('ready_count', 0)} 項通過驗證，可評估提出")
    nc = suggestions.get("providers_not_connected", [])
    if nc:
        out.append("　尚未接入的分析來源（補上後可判定更多原因）：")
        labels = [(_meta(x["root_cause"]).get("short_label")
                   or x["root_cause"]) for x in nc]
        for lb in labels:
            out.append(f"　・{lb}")
    return "\n".join(out)


# ══════════ 模型健康度（用真實命中率＋誤差，無捏造）══════════
def model_health(report, learning=None):
    """
    以既有真實數據計算模型健康度：
      - 今日 vs 本週整體命中率差
      - 星等（依今日整體命中率分級）
    不使用任何不存在的指標。
    """
    imp = report.get("improvement", {})
    tr = imp.get("today_overall_rate")
    wr = imp.get("week_overall_rate")
    score = None if tr is None else round(tr * 100, 1)
    delta = None
    if tr is not None and wr is not None:
        delta = round((tr - wr) * 100, 1)
    # 星等：依今日整體命中率（純命中率，無其他捏造因子）
    stars = None
    if score is not None:
        for threshold, n in STAR_THRESHOLDS:
            if score >= threshold:
                stars = n
                break
    return {"score_pct": score, "delta_vs_week": delta, "stars": stars,
            "basis": "今日整體命中率 vs 本週（真實數據，無其他指標）"}


def render_model_health_text(health, divider_len_override=None):
    line = _line(divider_len_override)
    out = ["🩺 今日模型健康度", line]
    s = health.get("score_pct")
    st = health.get("stars")
    out.append(f"　命中率：{'—' if s is None else str(s)+'%'}")
    if st:
        out.append("　評等：" + "⭐" * st + "☆" * (5 - st))
    d = health.get("delta_vs_week")
    if d is not None:
        arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
        out.append(f"　較本週平均：{arrow} {abs(d)}%")
    out.append(f"　依據：{health.get('basis')}")
    return "\n".join(out)

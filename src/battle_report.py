"""
battle_report.py — 每日戰報 + Root Cause Framework + Learning Pipeline
（純新增模組，不修改任何 frozen core）

本版升級（對應監督指令）：
1. 完整 Root Cause Framework：透過 providers.default_providers 判定鏈，
   UNKNOWN 僅為最後 fallback（①）
2. 每個 Root Cause 有 Provider 介面（providers/），未接入資料源不臆測（②）
3. Evidence Model：每筆未命中保存 evidence/confidence/source/unavailable_reason（③）
4. Learning：統計每個 Root Cause 出現次數、對命中率影響、最易致敗類別、
   哪些改善策略有效（④）
5. Engineering Rule：Evidence/Validation/Statistics First，無證據不猜、
   但架構完整、資料一到即可學（⑤）
"""

import os
import csv
import json
import datetime as dt
from collections import defaultdict

try:
    from constants import TW_TZ
except Exception:
    TW_TZ = dt.timezone(dt.timedelta(hours=8))

from providers import default_providers, ROOT_CAUSES

VERIFIED_CSV = "verified_history.csv"
FLAGS_JSON = "flags.json"
REPORT_DIR = "battle_reports"
VALIDATION_QUEUE = "validation_queue.json"
LEARNING_STORE = "rootcause_learning.json"

SPORTS = ["NBA", "MLB", "FIFA"]


# ────────── I/O ──────────
def _read_verified(path=VERIFIED_CSV):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _read_flags(path=FLAGS_JSON):
    if not os.path.exists(path):
        return {}
    try:
        return json.load(open(path))
    except Exception:
        return {}


def _s(r, k):
    v = str(r.get(k, "")).strip()
    return v if v not in ("", "None") else None


def _istrue(r, k):
    v = _s(r, k)
    return None if v is None else v.lower() in ("true", "1")


def _num(r, k):
    v = _s(r, k)
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _tw_date(iso):
    try:
        return dt.datetime.fromisoformat(str(iso)).astimezone(TW_TZ).date()
    except Exception:
        return None


def _norm_sport(v):
    v = (v or "").upper()
    if "FIFA" in v or "SOCCER" in v or "FOOTBALL" in v:
        return "FIFA"
    if "NBA" in v or "BASKET" in v:
        return "NBA"
    if "MLB" in v or "BASE" in v:
        return "MLB"
    return v or "UNKNOWN"


# ────────── 命中統計 ──────────
def _tally(rows):
    out = {s: {"pushed": 0, "hits": 0} for s in SPORTS}
    for r in rows:
        sp = _norm_sport(_s(r, "sport"))
        out.setdefault(sp, {"pushed": 0, "hits": 0})
        ml = _istrue(r, "moneyline_hit")
        if ml is None:
            continue
        out[sp]["pushed"] += 1
        if ml:
            out[sp]["hits"] += 1
    for s in out:
        p = out[s]["pushed"]
        out[s]["rate"] = round(out[s]["hits"] / p, 4) if p else None
    return out


def _filter_by_date(rows, d):
    return [r for r in rows if _tw_date(_s(r, "verified_at")) == d]


def _filter_range(rows, d0, d1):
    return [r for r in rows
            if (_tw_date(_s(r, "verified_at")) or dt.date.min) >= d0
            and (_tw_date(_s(r, "verified_at")) or dt.date.max) <= d1]


# ────────── Root Cause 判定（Provider chain + Evidence Model）──────────
def build_context(flags, record, market=None, injury=None, lineup=None,
                  actions=None):
    """優化一：在一處組好所有快照，Provider 只從 context 取。"""
    return {
        "flags": flags,
        "record": record,
        "market": market,     # 賽前vs賽後盤口快照（待接入）
        "injury": injury,     # 傷兵快照（待接入）
        "lineup": lineup,     # 陣容快照（待接入）
        "actions": actions,   # Actions 執行時序（待接入）
    }


def classify_miss(record, providers, context):
    """
    依 provider 鏈判定未命中的 Root Cause。
    - 取第一個 available=True 且 confidence>0 的 provider 結果。
    - 全部不成立 → UNKNOWN，並收集所有『待接入』provider 的 unavailable_reason。
    回傳含 evidence/confidence/source/unavailable_reason 的 dict（③）。
    """
    unavailable = []
    for p in providers:
        ev = p.evaluate(record, context)
        if ev.available and ev.confidence > 0:
            d = ev.to_dict()
            d["match_id"] = _s(record, "game_id")
            d["sport"] = _norm_sport(_s(record, "sport"))
            return d
        if not ev.available and ev.unavailable_reason:
            unavailable.append({"root_cause": ev.root_cause,
                                "source": ev.source,
                                "unavailable_reason": ev.unavailable_reason})
    return {
        "root_cause": "UNKNOWN",
        "available": True,
        "confidence": 0.0,
        "evidence": "現有已接入資料源無法判定",
        "source": "fallback",
        "unavailable_reason": None,
        "pending_providers": unavailable,     # 哪些類別待資料源接入
        "match_id": _s(record, "game_id"),
        "sport": _norm_sport(_s(record, "sport")),
    }


def miss_analysis(rows, providers, flags):
    misses = []
    for r in rows:
        if _istrue(r, "moneyline_hit") is False:
            ctx = build_context(flags, r)   # 未接入的快照為 None
            misses.append(classify_miss(r, providers, ctx))
    dist = defaultdict(int)
    for m in misses:
        dist[m["root_cause"]] += 1
    # 每個 Root Cause 的平均 confidence
    conf = defaultdict(list)
    for m in misses:
        conf[m["root_cause"]].append(m.get("confidence", 0.0))
    conf_avg = {k: round(sum(v) / len(v), 3) for k, v in conf.items() if v}
    return misses, dict(dist), conf_avg


# ────────── Improvement Report ──────────
def _overall_rate(tl):
    p = sum(v["pushed"] for v in tl.values())
    h = sum(v["hits"] for v in tl.values())
    return round(h / p, 4) if p else None


def _queue_has_ready(path=VALIDATION_QUEUE):
    """優化三：validation_queue 是否有已達 READY_FOR_PR 的建議。"""
    for item in load_queue(path):
        if item.get("status") == "READY_FOR_PR":
            return True
    return False


def improvement(today_rows, week_rows, miss_dist, queue_path=VALIDATION_QUEUE):
    worst = None
    for r in today_rows:
        e, a = _num(r, "expected_total"), _num(r, "actual_total")
        if e is None or a is None:
            continue
        err = abs(a - e)
        if worst is None or err > worst["abs_error"]:
            worst = {"match_id": _s(r, "game_id"), "expected_total": e,
                     "actual_total": a, "abs_error": round(err, 2)}
    today_rate = _overall_rate(_tally(today_rows))
    week_rate = _overall_rate(_tally(week_rows))
    declined = (today_rate is not None and week_rate is not None
                and today_rate < week_rate)
    # 今日最主要失敗類別（排除 UNKNOWN，若有可判定者）
    ranked = sorted([(k, v) for k, v in miss_dist.items() if k != "UNKNOWN"],
                    key=lambda kv: -kv[1])
    top_cause = ranked[0][0] if ranked else "UNKNOWN"
    # 優化三：不寫死。只有 validation_queue 有建議通過 3~5 次驗證(READY_FOR_PR)才 YES。
    ready = _queue_has_ready(queue_path)
    worth = "YES" if ready else "NO"
    worth_reason = ("validation_queue 有建議通過連續驗證（READY_FOR_PR），"
                    "可提交 PR（仍不即時改模型）"
                    if ready else
                    "無通過驗證的改善建議；單日不足以支撐模型修改（Engineering Rule）")
    return {
        "today_overall_rate": today_rate,
        "week_overall_rate": week_rate,
        "declined_vs_week": declined,
        "decline_reason": ("今日整體命中率低於本週均值（樣本波動；需 3~5 日確認趨勢）"
                           if declined else None),
        "largest_error_game": worst,
        "top_failure_root_cause": top_cause,
        "worth_modifying_model": worth,   # YES 僅在 queue READY 時
        "worth_reason": worth_reason,
    }


# ────────── Root Cause Learning（④）──────────
def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        return json.load(open(path))
    except Exception:
        return default


def update_learning(report, path=LEARNING_STORE):
    """
    累積跨日 Root Cause 學習資料：
      - 每個 Root Cause 累計出現次數
      - 每個 Root Cause 當日對『整體命中率』的關聯（該日 miss 佔比 vs 命中率）
      - 記錄每日 top_failure_root_cause，供『最易致敗類別』統計
    純統計、不做因果宣稱（Statistics First）。
    """
    store = _load_json(path, {
        "schema_version": 2,
        "root_cause_counts": {},
        "daily": [],
        "top_failure_history": {},
        "effectiveness": {},   # 優化二：每類 Root Cause 的改善成效
    })
    store.setdefault("effectiveness", {})
    dist = report["miss_analysis"]["distribution"]
    for rc, n in dist.items():
        store["root_cause_counts"][rc] = store["root_cause_counts"].get(rc, 0) + n
        # observed 累計；fixed/improved 由 record_fix_outcome() 於改善驗證時回填
        eff = store["effectiveness"].setdefault(
            rc, {"observed": 0, "fixed": 0, "improved": 0})
        eff["observed"] += n
    top = report["improvement"]["top_failure_root_cause"]
    store["top_failure_history"][top] = store["top_failure_history"].get(top, 0) + 1
    store["daily"].append({
        "date": report["date"],
        "overall_rate": report["improvement"]["today_overall_rate"],
        "distribution": dist,
        "top_failure_root_cause": top,
    })
    json.dump(store, open(path, "w"), ensure_ascii=False, indent=2)
    return store


def record_fix_outcome(root_cause, improved, path=LEARNING_STORE):
    """
    優化二：當某個 Root Cause 的改善策略經驗證後，回填成效。
    - improved=True  → fixed+1, improved+1（該方向確實提升命中）
    - improved=False → fixed+1（有嘗試但未提升）
    未來 validation_queue READY_FOR_PR 的策略部署後，用此回填，
    即可算出「哪些改善真正有效」= improved/observed。
    """
    store = _load_json(path, None)
    if not store:
        return None
    store.setdefault("effectiveness", {})
    eff = store["effectiveness"].setdefault(
        root_cause, {"observed": 0, "fixed": 0, "improved": 0})
    eff["fixed"] += 1
    if improved:
        eff["improved"] += 1
    json.dump(store, open(path, "w"), ensure_ascii=False, indent=2)
    return store


def learning_summary(path=LEARNING_STORE):
    """回傳可讀的學習摘要：最易致敗類別、各類別累計、有效策略（來自 queue）。"""
    store = _load_json(path, None)
    if not store:
        return {"available": False, "reason": "尚無累積資料"}
    counts = store["root_cause_counts"]
    top = sorted(store["top_failure_history"].items(), key=lambda kv: -kv[1])
    eff = store.get("effectiveness", {})
    # 有效策略：improved/observed（僅列已有 fixed 嘗試者）
    effective = {rc: round(v["improved"] / v["observed"], 3)
                 for rc, v in eff.items()
                 if v.get("observed") and v.get("fixed")}
    return {
        "available": True,
        "root_cause_counts": counts,
        "most_frequent_failure": top[0][0] if top else None,
        "days_accumulated": len(store["daily"]),
        "effectiveness": eff,
        "effective_strategies": effective,   # rc → 改善有效比率
    }


# ────────── Validation Queue（不立即生效）──────────
def load_queue(path=VALIDATION_QUEUE):
    return _load_json(path, [])


def enqueue_validation(reason, expected_gain, modules,
                       path=VALIDATION_QUEUE, now=None):
    q = load_queue(path)
    now = now or dt.datetime.now(TW_TZ)
    q.append({
        "id": f"vq-{now.strftime('%Y%m%d%H%M%S')}",
        "reason": reason,
        "expected_gain": expected_gain,
        "affected_modules": modules,
        "created_date": now.date().isoformat(),
        "support_count": 0,
        "checked_dates": [],
        "status": "PENDING",
    })
    json.dump(q, open(path, "w"), ensure_ascii=False, indent=2)
    return q


def review_queue(daily_report, path=VALIDATION_QUEUE,
                 min_support=3, max_support=5):
    q = load_queue(path)
    if not q:
        return q
    d = daily_report["date"]
    support = not daily_report["improvement"]["declined_vs_week"]
    for item in q:
        if item["status"] in ("READY_FOR_PR", "DISCARDED"):
            continue
        if d in item["checked_dates"]:
            continue
        item["checked_dates"].append(d)
        if support:
            item["support_count"] += 1
            if item["support_count"] >= min_support:
                item["status"] = "READY_FOR_PR"
        else:
            item["status"] = "DISCARDED"
    json.dump(q, open(path, "w"), ensure_ascii=False, indent=2)
    return q


# ────────── 主流程 ──────────
def build_daily_report(target_date=None, verified_path=VERIFIED_CSV,
                       flags_path=FLAGS_JSON, report_dir=REPORT_DIR,
                       persist=True):
    rows = _read_verified(verified_path)
    flags = _read_flags(flags_path)
    providers = default_providers()

    today = target_date or dt.datetime.now(TW_TZ).date()
    yday = today - dt.timedelta(days=1)
    wk0 = today - dt.timedelta(days=today.weekday())
    mo0 = today.replace(day=1)

    today_rows = _filter_by_date(rows, today)
    misses, dist, conf_avg = miss_analysis(today_rows, providers, flags)

    report = {
        "date": today.isoformat(),
        "generated_at": dt.datetime.now(TW_TZ).isoformat(),
        "per_sport": {
            "today": _tally(today_rows),
            "yesterday": _tally(_filter_by_date(rows, yday)),
            "this_week": _tally(_filter_range(rows, wk0, today)),
            "this_month": _tally(_filter_range(rows, mo0, today)),
            "all_time": _tally(rows),
        },
        "miss_analysis": {
            "distribution": dist,
            "confidence_avg": conf_avg,
            "details": misses,            # 每筆含 evidence/confidence/source
            "framework": {
                "root_causes": ROOT_CAUSES,
                "providers": [p.__class__.__name__ for p in providers],
                "available_providers": [p.__class__.__name__ for p in providers
                                        if p.is_available()],
            },
        },
        "improvement": improvement(today_rows,
                                   _filter_range(rows, wk0, today), dist),
        "schema_version": 2,
    }

    if persist:
        os.makedirs(report_dir, exist_ok=True)
        base = os.path.join(report_dir, f"battle_{today.isoformat()}.json")
        path = base
        if os.path.exists(base):
            ts = dt.datetime.now(TW_TZ).strftime("%H%M%S")
            path = os.path.join(report_dir,
                                f"battle_{today.isoformat()}.{ts}.json")
        json.dump(report, open(path, "w"), ensure_ascii=False, indent=2)
        report["_saved_path"] = path

    return report


def run_battle_report(target_date=None):
    rep = build_daily_report(target_date=target_date)
    update_learning(rep)     # ④ 累積 Root Cause 學習
    review_queue(rep)        # ⑤ 檢核 validation queue
    return rep


if __name__ == "__main__":
    r = run_battle_report()
    print(json.dumps(r, ensure_ascii=False, indent=2)[:1500])

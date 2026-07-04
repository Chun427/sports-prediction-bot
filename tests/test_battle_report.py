"""Root Cause Framework / Provider / Learning 測試（純新增）。"""
import os
import sys
import csv
import json
import datetime as dt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import battle_report as br            # noqa: E402
from providers import default_providers, ROOT_CAUSES  # noqa: E402
from providers.impls import (         # noqa: E402
    CutoffProvider, ModelDirectionProvider, InjuryProvider,
    LineMovementProvider,
)

TZ = dt.timezone(dt.timedelta(hours=8))
D = dt.date(2026, 7, 3)


def _write(path, rows):
    fields = ["verified_at", "game_id", "sport", "winner", "pick_outcome",
              "moneyline_hit", "expected_total", "actual_total"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _sample(chdir):
    os.chdir(chdir)
    at = dt.datetime(2026, 7, 3, 10, 0, tzinfo=TZ).isoformat()
    rows = [
        {"verified_at": at, "game_id": "f1", "sport": "FIFA", "winner": "home",
         "pick_outcome": "home", "moneyline_hit": "True",
         "expected_total": "3", "actual_total": "2"},
        {"verified_at": at, "game_id": "f2", "sport": "FIFA", "winner": "away",
         "pick_outcome": "home", "moneyline_hit": "False",
         "expected_total": "3", "actual_total": "6"},   # 有pre → 方向誤判
        {"verified_at": at, "game_id": "m1", "sport": "MLB", "winner": "home",
         "pick_outcome": "away", "moneyline_hit": "False",
         "expected_total": "9", "actual_total": "8"},   # 無pre → CUTOFF
    ]
    _write("verified_history.csv", rows)
    json.dump({"f1": {"pre": True}, "f2": {"pre": True}},
              open("flags.json", "w"))    # m1 無 pre


# ── Provider 介面 ──
def test_framework_has_all_root_causes():
    for rc in ["MODEL_DIRECTION_ERROR", "CUTOFF", "INJURY", "LINEUP_CHANGE",
               "LINE_MOVEMENT", "ODDS_MOVEMENT", "MARKET_CHANGE",
               "DATA_DELAY", "UNKNOWN"]:
        assert rc in ROOT_CAUSES


def test_stub_provider_unavailable_not_guessing():
    ev = InjuryProvider().evaluate({"game_id": "x"}, {})
    assert ev.available is False
    assert ev.confidence == 0.0
    assert ev.unavailable_reason  # 有明確 reason，不臆測


def test_line_movement_provider_reports_needed_source():
    ev = LineMovementProvider().evaluate({"game_id": "x"}, {})
    assert ev.available is False
    assert "快照" in ev.unavailable_reason


def test_cutoff_provider_available():
    p = CutoffProvider()
    ev = p.evaluate({"game_id": "m1"}, {"flags": {"m1": {}}})
    assert ev.available and ev.confidence > 0
    assert ev.root_cause == "CUTOFF"


def test_model_direction_provider():
    ev = ModelDirectionProvider().evaluate(
        {"game_id": "z", "pick_outcome": "home", "winner": "away"})
    assert ev.root_cause == "MODEL_DIRECTION_ERROR"
    assert ev.available and ev.confidence > 0


# ── Evidence Model in report ──
def test_report_miss_has_evidence_fields(tmp_path):
    _sample(tmp_path)
    r = br.build_daily_report(target_date=D, persist=False)
    for m in r["miss_analysis"]["details"]:
        for key in ("root_cause", "confidence", "source"):
            assert key in m


def test_report_classifies_cutoff_and_direction(tmp_path):
    _sample(tmp_path)
    r = br.build_daily_report(target_date=D, persist=False)
    dist = r["miss_analysis"]["distribution"]
    assert dist.get("MODEL_DIRECTION_ERROR") == 1   # f2
    assert dist.get("CUTOFF") == 1                   # m1
    # UNKNOWN 不是唯一輸出
    assert dist.get("UNKNOWN", 0) == 0


def test_report_lists_pending_providers_when_unknown(tmp_path):
    os.chdir(tmp_path)
    at = dt.datetime(2026, 7, 3, 10, 0, tzinfo=TZ).isoformat()
    # 一場：有pre、方向正確、卻仍未命中（moneyline False但winner==pick）
    _write("verified_history.csv", [
        {"verified_at": at, "game_id": "u1", "sport": "MLB", "winner": "home",
         "pick_outcome": "home", "moneyline_hit": "False",
         "expected_total": "8", "actual_total": "8"}])
    json.dump({"u1": {"pre": True}}, open("flags.json", "w"))
    r = br.build_daily_report(target_date=D, persist=False)
    d = r["miss_analysis"]["details"][0]
    assert d["root_cause"] == "UNKNOWN"
    # 列出待接入 provider（架構完整）
    assert any(p["root_cause"] in ("INJURY", "LINE_MOVEMENT")
               for p in d.get("pending_providers", []))


# ── Learning（④）──
def test_learning_accumulates_counts(tmp_path):
    _sample(tmp_path)
    rep = br.build_daily_report(target_date=D, persist=False)
    br.update_learning(rep)
    s = br.learning_summary()
    assert s["available"]
    assert s["root_cause_counts"].get("CUTOFF", 0) >= 1
    assert s["days_accumulated"] == 1


def test_learning_most_frequent_failure(tmp_path):
    _sample(tmp_path)
    for _ in range(3):
        rep = br.build_daily_report(target_date=D, persist=False)
        br.update_learning(rep)
    s = br.learning_summary()
    assert s["most_frequent_failure"] in ("CUTOFF", "MODEL_DIRECTION_ERROR")


# ── Regression ×2 ──
def test_regression_deterministic_1(tmp_path):
    _sample(tmp_path)
    a = br.build_daily_report(target_date=D, persist=False)
    b = br.build_daily_report(target_date=D, persist=False)
    a.pop("generated_at"); b.pop("generated_at")
    assert a == b


def test_regression_deterministic_2(tmp_path):
    _sample(tmp_path)
    a = br.build_daily_report(target_date=D, persist=False)
    b = br.build_daily_report(target_date=D, persist=False)
    assert a["miss_analysis"]["distribution"] == b["miss_analysis"]["distribution"]


# ── Validation queue（沿用規則）──
def test_queue_needs_3_supports(tmp_path):
    _sample(tmp_path)
    br.enqueue_validation("r", "+2%", ["m"],
                          now=dt.datetime(2026, 7, 1, tzinfo=TZ))
    q = None
    for day in ["2026-07-01", "2026-07-02", "2026-07-03"]:
        q = br.review_queue({"date": day,
                             "improvement": {"declined_vs_week": False}})
    assert q[0]["status"] == "READY_FOR_PR"


def test_queue_discards_on_break(tmp_path):
    _sample(tmp_path)
    br.enqueue_validation("r", "+1%", ["x"],
                          now=dt.datetime(2026, 7, 1, tzinfo=TZ))
    br.review_queue({"date": "2026-07-01",
                     "improvement": {"declined_vs_week": False}})
    q = br.review_queue({"date": "2026-07-02",
                         "improvement": {"declined_vs_week": True}})
    assert q[0]["status"] == "DISCARDED"


# ── 優化一：context 驅動 ──
def test_provider_reads_from_context(tmp_path):
    from providers.impls import CutoffProvider
    ev = CutoffProvider().evaluate({"game_id": "g"}, {"flags": {"g": {"pre": True}}})
    assert ev.confidence == 0.0  # 有pre → 非CUTOFF
    ev2 = CutoffProvider().evaluate({"game_id": "g"}, {"flags": {"g": {}}})
    assert ev2.confidence > 0     # 無pre → CUTOFF


def test_market_provider_needs_context_market(tmp_path):
    from providers.impls import OddsMovementProvider
    ev = OddsMovementProvider().evaluate({"game_id": "g"}, {"market": None})
    assert ev.available is False and "market" in ev.unavailable_reason


# ── 優化二：effectiveness ──
def test_learning_effectiveness_records(tmp_path):
    _sample(tmp_path)
    rep = br.build_daily_report(target_date=D, persist=False)
    br.update_learning(rep)
    br.record_fix_outcome("CUTOFF", improved=True)
    s = br.learning_summary()
    assert s["effectiveness"]["CUTOFF"]["observed"] >= 1
    assert s["effectiveness"]["CUTOFF"]["improved"] == 1
    assert s["effective_strategies"].get("CUTOFF") is not None


# ── 優化三：worth_modifying_model 動態 ──
def test_worth_modify_yes_when_queue_ready(tmp_path):
    _sample(tmp_path)
    # 無 READY → NO
    r = br.build_daily_report(target_date=D, persist=False)
    assert r["improvement"]["worth_modifying_model"] == "NO"
    # 造一個 READY_FOR_PR 建議 → YES
    br.enqueue_validation("r", "+2%", ["m"],
                          now=dt.datetime(2026, 7, 1, tzinfo=TZ))
    for day in ["2026-07-01", "2026-07-02", "2026-07-03"]:
        br.review_queue({"date": day,
                         "improvement": {"declined_vs_week": False}})
    r2 = br.build_daily_report(target_date=D, persist=False)
    assert r2["improvement"]["worth_modifying_model"] == "YES"

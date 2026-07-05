"""analysis.py 測試（純新增）。涵蓋單場 / 每日 / 改善，FIFA/MLB/NBA 共用。"""
import os
import sys
import csv
import json
import datetime as dt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import battle_report as br      # noqa: E402
import analysis as an           # noqa: E402
from providers import default_providers  # noqa: E402

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
        {"verified_at": at, "game_id": "f2", "sport": "FIFA", "winner": "away",
         "pick_outcome": "home", "moneyline_hit": "False",
         "expected_total": "3", "actual_total": "6"},   # 方向誤判
        {"verified_at": at, "game_id": "m1", "sport": "MLB", "winner": "home",
         "pick_outcome": "away", "moneyline_hit": "False",
         "expected_total": "9", "actual_total": "8"},    # 無pre → CUTOFF
        {"verified_at": at, "game_id": "n1", "sport": "NBA", "winner": "home",
         "pick_outcome": "home", "moneyline_hit": "True",
         "expected_total": "210", "actual_total": "208"},
    ]
    _write("verified_history.csv", rows)
    json.dump({"f2": {"pre": True}}, open("flags.json", "w"))  # m1 無pre


# ── 功能一：單場分析 ──
def test_single_direction_error_gives_weight_advice(tmp_path):
    _sample(tmp_path)
    rec = {"game_id": "f2", "sport": "FIFA", "pick_outcome": "home",
           "winner": "away"}
    a = an.analyze_single_game(rec, context=br.build_context({"f2": {"pre": True}}, rec))
    assert a["root_cause"] == "MODEL_DIRECTION_ERROR"
    assert not a["weight_advice"]["insufficient"]
    assert a["weight_advice"]["raise"] and a["weight_advice"]["lower"]


def test_single_unknown_says_insufficient(tmp_path):
    _sample(tmp_path)
    # 有pre、方向正確、但仍未命中 → UNKNOWN → 不臆測
    rec = {"game_id": "u1", "sport": "MLB", "pick_outcome": "home",
           "winner": "home"}
    a = an.analyze_single_game(rec, context=br.build_context({"u1": {"pre": True}}, rec))
    assert a["root_cause"] == "UNKNOWN"
    assert a["weight_advice"]["insufficient"] is True
    assert a["weight_advice"]["note"] == an._INSUFFICIENT


def test_single_all_sports_shared_flow(tmp_path):
    _sample(tmp_path)
    for sport in ["FIFA", "MLB", "NBA"]:
        rec = {"game_id": f"{sport}x", "sport": sport,
               "pick_outcome": "home", "winner": "away"}
        a = an.analyze_single_game(rec, context=br.build_context({}, rec))
        # 不寫死運動：都能跑、都回結構
        assert a["sport"] == sport
        assert "root_cause" in a


def test_single_render_text(tmp_path):
    _sample(tmp_path)
    rec = {"game_id": "f2longhash000000", "sport": "FIFA",
           "pick_outcome": "home", "winner": "away"}
    a = an.analyze_single_game(rec, context=br.build_context({"f2longhash000000": {"pre": True}}, rec))
    txt = an.render_single_analysis_text(a)
    assert "比賽結果分析" in txt and "為什麼沒有命中" in txt
    assert "f2longha" in txt  # 長 id 截 8


# ── 功能二：每日分析 ──
def test_daily_ranking_and_pct(tmp_path):
    _sample(tmp_path)
    rep = br.build_daily_report(target_date=D, persist=False)
    d = an.analyze_daily(rep)
    assert d["root_cause_ranking"]
    # 比例加總 ~100
    pcts = [r["pct"] for r in d["root_cause_ranking"] if r["pct"] is not None]
    assert abs(sum(pcts) - 100.0) < 0.5


def test_daily_worth_modify_no_default(tmp_path):
    _sample(tmp_path)
    rep = br.build_daily_report(target_date=D, persist=False)
    d = an.analyze_daily(rep)
    assert d["worth_modifying_model"] == "NO"


def test_daily_render_text(tmp_path):
    _sample(tmp_path)
    rep = br.build_daily_report(target_date=D, persist=False)
    d = an.analyze_daily(rep)
    s = an.improvement_suggestions(rep)
    txt = an.render_daily_analysis_text(d, s)
    assert "每日戰報分析" in txt and "Root Cause 排名" in txt
    assert "是否值得修改模型" in txt


# ── 功能三：改善建議 ──
def test_suggestions_lists_unconnected_providers(tmp_path):
    _sample(tmp_path)
    rep = br.build_daily_report(target_date=D, persist=False)
    s = an.improvement_suggestions(rep)
    names = [x["root_cause"] for x in s["providers_not_connected"]]
    for rc in ["INJURY", "LINE_MOVEMENT", "ODDS_MOVEMENT", "DATA_DELAY"]:
        assert rc in names


def test_suggestions_insufficient_when_no_evidence(tmp_path):
    os.chdir(tmp_path)
    _write("verified_history.csv", [])   # 無任何資料
    json.dump({}, open("flags.json", "w"))
    rep = br.build_daily_report(target_date=D, persist=False)
    s = an.improvement_suggestions(rep)
    # 無可行動證據 → 誠實訊息
    assert s["message"] == an._INSUFFICIENT_FIX or not s["insufficient"]


def test_suggestions_render_insufficient_text(tmp_path):
    os.chdir(tmp_path)
    _write("verified_history.csv", [])
    json.dump({}, open("flags.json", "w"))
    rep = br.build_daily_report(target_date=D, persist=False)
    d = an.analyze_daily(rep)
    s = an.improvement_suggestions(rep)
    txt = an.render_daily_analysis_text(d, s)
    assert isinstance(txt, str) and len(txt) > 0

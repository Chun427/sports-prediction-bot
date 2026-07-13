"""
test_ground_truth.py — ADR-002 Ground Truth Contract 回歸測試

涵蓋：
  1. Regular Win / Regular Draw / Extra Time / Penalty（足球）
  2. MLB 延長局 / NBA OT → 必須 NORMAL 且計入（證明零影響）
  3. Migration：舊 CSV 無新欄位 → 自動補空、不遺失資料
  4. 指標排除：污染列不計入 battle_report / daily_report
"""
import os
import sys
import csv
import json
import datetime as dt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import result_verifier as rv          # noqa: E402
import battle_report as br            # noqa: E402
import daily_report as dr             # noqa: E402
import data_manager as dm             # noqa: E402

TZ = dt.timezone(dt.timedelta(hours=8))
D = dt.date(2026, 7, 3)


def _pred(gid, sport, pick="home"):
    return {
        "game_id": gid, "sport": sport, "model": "market_implied_v1",
        "best_pick": {"outcome": pick, "odds": 2.0},
        "fair_prob": {"home": 0.5, "away": 0.3, "draw": 0.2},
        "best_odds": {"home": 2.0, "away": 3.0, "draw": 3.5},
    }


def _result(gid, hs, aws, completed=True):
    return {"id": gid, "completed": completed,
            "home_score": hs, "away_score": aws}


# ── 1. 足球四情境 ──
def test_regular_win():
    out = rv.verify(_pred("g1", "FIFA"), _result("g1", 2, 1))
    assert out["winner"] == "home"
    assert out["result_status"] == "NORMAL"
    assert out["verification_source"] == "THE_ODDS"


def test_regular_draw():
    out = rv.verify(_pred("g2", "FIFA"), _result("g2", 0, 0))
    assert out["winner"] == "draw"
    assert out["result_status"] == "NORMAL"


def test_extra_time_marked_via_registry_not_by_bracket():
    """
    ADR-002 §8 + 監督修正①：
    runtime 無法取得 90 分比分 → 不以『淘汰賽』臆測污染（會誤殺乾淨資料）。
    延長賽場在 verify() 當下仍為 NORMAL；污染僅由 registry（Evidence）事後標記。
    """
    out = rv.verify(_pred("g3", "FIFA"), _result("g3", 3, 2))  # 正規2-2→延長3-2
    assert out["result_status"] == "NORMAL"      # 不臆測
    assert out["verification_source"] == "THE_ODDS"


def test_penalty_stays_draw():
    """PK 不計入比分 → API 回 0-0 → 正確為 draw。"""
    out = rv.verify(_pred("g4", "FIFA"), _result("g4", 0, 0))
    assert out["winner"] == "draw"
    assert out["result_status"] == "NORMAL"


# ── 2. MLB / NBA 零影響（延長局 / OT 必須計入）──
def test_mlb_extra_innings_counts_as_normal():
    """ADR-002 §3.2：棒球無平手，延長局計入 → NORMAL、winner=home。"""
    out = rv.verify(_pred("m1", "MLB"), _result("m1", 4, 3))
    assert out["winner"] == "home"
    assert out["result_status"] == "NORMAL"      # 必須計入


def test_nba_overtime_counts_as_normal():
    """ADR-002 §3.2：籃球 OT 計入 → NORMAL。"""
    out = rv.verify(_pred("n1", "NBA"), _result("n1", 98, 95))
    assert out["winner"] == "home"
    assert out["result_status"] == "NORMAL"


# ── 3. Migration Test（監督要求）──
def _write_legacy_csv(path, n=10):
    """舊 CSV：無 result_status / verification_source / verification_note。"""
    legacy = [f for f in dm.VERIFIED_FIELDS
              if f not in ("result_status", "verification_source",
                           "verification_note")]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=legacy)
        w.writeheader()
        for i in range(n):
            w.writerow({k: "" for k in legacy} | {
                "game_id": f"old{i}", "sport": "MLB", "winner": "home",
                "moneyline_hit": "True", "verified_at": "2026-07-01T10:00:00+08:00"})
    return legacy


def test_migration_adds_columns_without_data_loss(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = dm.VERIFIED_HISTORY if hasattr(dm, "VERIFIED_HISTORY") \
        else "verified_history.csv"
    legacy = _write_legacy_csv(path, n=10)

    # 觸發 migration（append 一筆新記錄）
    dm.append_verified({"game_id": "new1", "sport": "MLB", "winner": "away",
                        "result_status": "NORMAL",
                        "verification_source": "THE_ODDS"})

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fields = csv.DictReader(open(path, encoding="utf-8")).fieldnames

    # 新欄位已加入 header
    for col in ("result_status", "verification_source", "verification_note"):
        assert col in fields, col
    # 舊欄位仍為前綴（無遺失）
    assert fields[:len(legacy)] == legacy
    # 資料無遺失：10 舊 + 1 新
    assert len(rows) == 11
    # 舊列的新欄位自動補空（不 backfill）
    old = [r for r in rows if str(r["game_id"]).startswith("old")]
    assert len(old) == 10
    assert all(r["result_status"] == "" for r in old)
    # 舊列原始資料未被破壞
    assert all(r["winner"] == "home" for r in old)


# ── 4. 指標排除（污染列不計入）──
def _vh(path, rows):
    fields = ["verified_at", "game_id", "sport", "winner", "pick_outcome",
              "moneyline_hit", "expected_total", "actual_total",
              "result_status", "verification_source", "verification_note"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def test_battle_report_excludes_contaminated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    at = dt.datetime(2026, 7, 3, 10, 0, tzinfo=TZ).isoformat()
    _vh("verified_history.csv", [
        # 乾淨：命中
        {"verified_at": at, "game_id": "c1", "sport": "FIFA", "winner": "home",
         "pick_outcome": "home", "moneyline_hit": "True",
         "result_status": "NORMAL", "verification_source": "THE_ODDS"},
        # 污染：假命中（延長賽），必須被排除
        {"verified_at": at, "game_id": "x1", "sport": "FIFA", "winner": "home",
         "pick_outcome": "home", "moneyline_hit": "True",
         "result_status": "CONFIRMED_ET", "verification_source": "GIT_HISTORY"},
    ])
    json.dump({}, open("flags.json", "w"))
    rep = br.build_daily_report(target_date=D, persist=False)
    fifa = rep["per_sport"]["today"]["FIFA"]
    # 只算乾淨的 1 場，污染的不計入
    assert fifa["pushed"] == 1, fifa
    assert fifa["hits"] == 1


def test_daily_report_rate_excludes_contaminated():
    rows = [
        {"moneyline_hit": "True", "result_status": "NORMAL"},
        {"moneyline_hit": "True", "result_status": "CONFIRMED_ET"},  # 排除
        {"moneyline_hit": "False", "result_status": "SUSPECTED_ET"},  # 排除
    ]
    hit, tot = dr._rate(rows, "moneyline_hit")
    assert (hit, tot) == (1, 1)


def test_legacy_rows_without_status_still_count():
    """向後相容：舊列 result_status 為空 → 視為 NORMAL，仍計入（不遺失歷史）。"""
    rows = [
        {"moneyline_hit": "True", "result_status": ""},
        {"moneyline_hit": "False"},   # 完全無此欄
    ]
    hit, tot = dr._rate(rows, "moneyline_hit")
    assert (hit, tot) == (1, 2)


# ── 5. Registry 完整性 ──
def test_registry_valid():
    root = os.path.join(os.path.dirname(__file__), "..")
    p = os.path.join(root, "contamination_registry.json")
    assert os.path.exists(p)
    data = json.load(open(p, encoding="utf-8"))
    entries = data.get("items") or data["entries"]
    assert len(entries) == 4
    for e in entries:
        assert e["result_status"] in ("CONFIRMED_ET", "SUSPECTED_ET", "UNVERIFIED")
        assert e["verification_source"] in ("GIT_HISTORY", "SECOND_PROVIDER", "MANUAL")
        assert e["game_id_prefix"] and e["expected_actual_total"]


# ── 6. Registry ↔ CSV 一致性（CI assertion，防止漂移）──
def _root():
    return os.path.join(os.path.dirname(__file__), "..")


def _load_registry():
    p = os.path.join(_root(), "contamination_registry.json")
    data = json.load(open(p, encoding="utf-8"))
    return data, (data.get("items") or data.get("entries", []))


def test_registry_has_version_metadata():
    """監督要求①：Registry 必須版本化，且宣告為 SSOT。"""
    data, items = _load_registry()
    assert isinstance(data.get("version"), int)
    assert data.get("last_updated")
    assert data.get("generated_by")   # 半年後可知由哪個工具產生，非人工亂改
    assert "Single Source of Truth" in data.get("_ssot_notice", "")
    assert items


def test_registry_matches_csv_confirmed_et():
    """
    監督要求②：Registry 筆數必須與 verified_history.csv 中
    result_status=CONFIRMED_ET 的筆數完全一致。
    不一致 → 表示有人直接改了 CSV，或改了 Registry 卻沒跑 migration → FAIL。
    """
    _, items = _load_registry()
    csv_path = os.path.join(_root(), "verified_history.csv")
    if not os.path.exists(csv_path):
        return   # 測試環境無資料檔時跳過
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if "result_status" not in (rows[0].keys() if rows else {}):
        return   # 尚未 migration 的環境

    confirmed = [r for r in rows
                 if str(r.get("result_status", "")).strip() == "CONFIRMED_ET"]
    reg_confirmed = [e for e in items
                     if e.get("result_status") == "CONFIRMED_ET"]

    assert len(confirmed) == len(reg_confirmed), (
        f"Registry 與 CSV 漂移！Registry 有 {len(reg_confirmed)} 筆 CONFIRMED_ET，"
        f"但 CSV 有 {len(confirmed)} 筆。請重新執行 "
        f"scripts/mark_contamination.py --apply"
    )

    # 每一筆 registry 的 game_id 都必須在 CSV 中找到對應且已標記
    csv_ids = [str(r.get("game_id", "")) for r in confirmed]
    for e in reg_confirmed:
        pre = e["game_id_prefix"]
        assert any(gid.startswith(pre) for gid in csv_ids), (
            f"Registry 的 {pre} 在 CSV 中未被標記為 CONFIRMED_ET"
        )


def test_no_unregistered_contamination_in_csv():
    """反向檢查：CSV 中不得有 Registry 未登記的 CONFIRMED_ET（防止有人直接改 CSV）。"""
    _, items = _load_registry()
    csv_path = os.path.join(_root(), "verified_history.csv")
    if not os.path.exists(csv_path):
        return
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows or "result_status" not in rows[0]:
        return
    prefixes = [e["game_id_prefix"] for e in items]
    for r in rows:
        if str(r.get("result_status", "")).strip() == "CONFIRMED_ET":
            gid = str(r.get("game_id", ""))
            assert any(gid.startswith(p) for p in prefixes), (
                f"CSV 中的 {gid[:8]} 標為 CONFIRMED_ET，但 Registry 未登記 → "
                f"疑似有人直接修改 CSV。Registry 為唯一人工確認來源。"
            )

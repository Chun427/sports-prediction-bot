"""
test_snapshot.py — C-1 prediction snapshot 落盤（State + pre-push wiring）

不打網路：log-only pusher + 注入 predictor。
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import data_manager as dm  # noqa: E402
import notifier  # noqa: E402
import sports_prediction as sp  # noqa: E402
from constants import PREDICTIONS_FILE, TW_TZ  # noqa: E402

BASE = datetime(2026, 6, 9, 12, 0, tzinfo=TW_TZ)
PRED = {"game_id": "g1", "sport": "NBA", "home": "H", "away": "A",
        "start_time": "2026-06-09T12:30:00+08:00",
        "fair_prob": {"home": 0.56, "away": 0.44},
        "best_odds": {"home": 1.85, "away": 2.30},
        "best_pick": {"outcome": "home", "edge": 0.038, "odds": 1.85},
        "model": "market_implied_v1"}


def _game(gid, start):
    return {"id": gid, "start_time": start.isoformat()}


# ── CRUD roundtrip ───────────────────────────────────
def test_snapshot_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert dm.load_predictions() == {}
    dm.save_prediction("g1", PRED)
    preds = dm.load_predictions()
    assert "g1" in preds
    assert preds["g1"]["prediction"] == PRED
    assert "pre_pushed_at" in preds["g1"]
    dm.remove_prediction("g1")
    assert dm.load_predictions() == {}


def test_remove_missing_is_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dm.remove_prediction("nope")  # 不應拋出
    assert dm.load_predictions() == {}


# ── 毀損降級 → {} ────────────────────────────────────
def test_corrupt_predictions_degrades(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / PREDICTIONS_FILE).write_text("{ not json", encoding="utf-8")
    assert dm.load_predictions() == {}  # Fail-safe


def test_non_dict_predictions_degrades(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / PREDICTIONS_FILE).write_text("[1,2,3]", encoding="utf-8")
    assert dm.load_predictions() == {}


# ── 原子寫入：多次 save 累積 ─────────────────────────
def test_multiple_snapshots_accumulate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dm.save_prediction("g1", PRED)
    dm.save_prediction("g2", {**PRED, "game_id": "g2"})
    preds = dm.load_predictions()
    assert set(preds.keys()) == {"g1", "g2"}


# ── wiring：pre-push 成功 + 有 prediction → 落盤 ─────
def test_pregame_push_saves_snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    start = BASE + timedelta(minutes=30)  # 窗內
    pushed = sp.run_pregame_push(BASE, [_game("g1", start)], notifier.log_only_pusher,
                                 predictor=lambda g: {**PRED, "game_id": g["id"]})
    assert pushed == ["g1"]
    preds = dm.load_predictions()
    assert "g1" in preds and preds["g1"]["prediction"]["model"] == "market_implied_v1"


# ── wiring：DRY_RUN（log-only）也存 snapshot ─────────
def test_dry_run_also_saves_snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    start = BASE + timedelta(minutes=30)
    pusher = notifier.make_pusher(True)  # DRY_RUN log-only
    sp.run_pregame_push(BASE, [_game("g1", start)], pusher,
                        predictor=lambda g: {**PRED, "game_id": g["id"]})
    assert "g1" in dm.load_predictions()


# ── wiring：無 prediction（無 predictor）→ 不存 ──────
def test_no_predictor_does_not_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    start = BASE + timedelta(minutes=30)
    sp.run_pregame_push(BASE, [_game("g1", start)], notifier.log_only_pusher)  # 無 predictor
    assert dm.load_predictions() == {}  # 沒有 prediction → 不落盤


# ── wiring：predict()→None（無有效市場）→ 不存 ──────
def test_predict_none_does_not_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    start = BASE + timedelta(minutes=30)
    sp.run_pregame_push(BASE, [_game("g1", start)], notifier.log_only_pusher,
                        predictor=lambda g: None)
    assert dm.load_predictions() == {}


# ── wiring：push 失敗（pusher False）→ 不存 ──────────
def test_push_failed_does_not_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    start = BASE + timedelta(minutes=30)
    sp.run_pregame_push(BASE, [_game("g1", start)], lambda g: False,
                        predictor=lambda g: {**PRED, "game_id": g["id"]})
    assert dm.load_predictions() == {}  # 未送出 → 不 mark、不落盤

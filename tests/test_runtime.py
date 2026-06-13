"""
test_runtime.py — runtime entry wiring（pusher 來自 notifier；TD2 fail-fast）

不打真實 API：log-only pusher 不需網路；fail-fast 在任何 fetch / 網路前發生。
"""
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import sports_prediction as sp  # noqa: E402
import data_manager as dm  # noqa: E402
import notifier  # noqa: E402
from constants import TW_TZ  # noqa: E402

BASE = datetime(2026, 6, 9, 12, 0, tzinfo=TW_TZ)


def _game(gid, start):
    return {"id": gid, "start_time": start.isoformat()}


# ── log-only pusher 串接 idempotency（pusher 來自 notifier）─
def test_log_only_pusher_marks_idempotency(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    start = BASE + timedelta(minutes=30)  # 窗內
    first = sp.run_pregame_push(BASE, [_game("g1", start)], notifier.log_only_pusher)
    assert first == ["g1"]
    assert dm.is_pushed("g1", "pre") is True
    assert "[DRY_RUN_PUSH] game_id=g1 would_send=True" in capsys.readouterr().out
    # 下一個 tick 仍在窗內 → 已推過 → 不重推
    second = sp.run_pregame_push(BASE + timedelta(minutes=15), [_game("g1", start)],
                                 notifier.log_only_pusher)
    assert second == []


# ── wiring：predictor 注入 → 推播摘要 + 模板預覽 ─────
def test_push_with_prediction_logs_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    start = BASE + timedelta(minutes=30)
    pred = {"sport": "NBA", "home": "H", "away": "A", "start_time": start.isoformat(),
            "bookmaker_count": 2, "fair_prob": {"home": 0.56, "away": 0.44},
            "best_odds": {"home": 1.85, "away": 2.30}, "avg_overround": 0.04,
            "best_pick": {"outcome": "home", "edge": 0.038, "odds": 1.85},
            "model": "market_implied_v1"}
    pushed = sp.run_pregame_push(BASE, [_game("g1", start)], notifier.log_only_pusher,
                                 predictor=lambda g: pred)
    assert pushed == ["g1"]
    assert dm.is_pushed("g1", "pre") is True
    out = capsys.readouterr().out
    assert "[DRY_RUN_PUSH] game_id=g1 would_send=True | home=56.0% away=44.0% best_pick=home edge=+3.8% @1.85" in out
    assert "市場隱含勝率" in out  # 模板預覽也被印出


# ── wiring：predict()→None → SKIP_NO_PREDICTION ──────
def test_predict_none_skips(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    start = BASE + timedelta(minutes=30)
    pushed = sp.run_pregame_push(BASE, [_game("g1", start)], notifier.log_only_pusher,
                                 predictor=lambda g: None)
    assert pushed == []                        # 不呼叫 pusher
    assert dm.is_pushed("g1", "pre") is False  # 不 mark，idempotency 不變
    out = capsys.readouterr().out
    assert "[SKIP_NO_PREDICTION] game_id=g1 reason=no_valid_h2h_market" in out
    assert "[DRY_RUN_PUSH]" not in out


# ── balanced 閘門：無 +EV 標的 且 無可用模型 → SKIP_NO_ACTIONABLE ──
def test_gate_skips_when_no_edge_and_no_model(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    start = BASE + timedelta(minutes=30)
    pred = {"sport": "NBA", "home": "H", "away": "A", "start_time": start.isoformat(),
            "fair_prob": {"home": 0.5, "away": 0.5}, "best_odds": {"home": 2.0, "away": 2.0},
            "best_pick": None, "model": "market_implied_v1"}
    pushed = sp.run_pregame_push(BASE, [_game("g1", start)], notifier.log_only_pusher,
                                 predictor=lambda g: pred)
    assert pushed == []                        # 不發空訊息
    assert dm.is_pushed("g1", "pre") is False  # 不 mark
    assert "[SKIP_NO_ACTIONABLE] game_id=g1 reason=no_edge_no_model" in capsys.readouterr().out


# ── balanced 閘門：無 pick 但有可用模型(totals 在) → 仍推 ──
def test_gate_pushes_when_model_present_even_without_pick(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    start = BASE + timedelta(minutes=30)
    game = {"id": "g1", "start_time": start.isoformat(), "sport": "FIFA",
            "odds_totals": [{"book": "x", "line": 2.5}],
            "odds_spreads": [{"book": "x", "home_point": -0.5}]}
    pred = {"sport": "FIFA", "home": "H", "away": "A", "start_time": start.isoformat(),
            "fair_prob": {"home": 0.5, "away": 0.3, "draw": 0.2},
            "best_odds": {"home": 2.0, "away": 3.0}, "best_pick": None,
            "model": "market_implied_v1"}
    pushed = sp.run_pregame_push(BASE, [game], notifier.log_only_pusher,
                                 predictor=lambda g: pred)
    assert pushed == ["g1"]                     # 有可用模型 → 仍發
    assert dm.is_pushed("g1", "pre") is True


# ── TD2 fail-fast：缺 ODDS_API_KEY_1 → SystemExit ────
def test_main_fail_fast_missing_odds_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ODDS_API_KEY_1", raising=False)
    monkeypatch.delenv("ODDS_API_KEY_2", raising=False)
    monkeypatch.setenv("DRY_RUN", "true")
    with pytest.raises(SystemExit):
        sp.main(["push"])  # validate_secrets 在 fetch 前即 fail-fast（無網路）


# ── TD2 fail-fast：DRY_RUN=false 缺 TG → SystemExit ──
def test_main_fail_fast_missing_tg_when_not_dry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ODDS_API_KEY_1", "dummy")  # ODDS 有設
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.delenv("TG_TOKEN", raising=False)
    monkeypatch.delenv("TG_CHAT", raising=False)
    with pytest.raises(SystemExit):
        sp.main(["push"])  # 缺 TG → fail-fast（在 fetch 前，無網路）


# ── validate_secrets 直接單元測試（pass cases，不觸網路）─
def test_validate_secrets_dry_run_ok(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY_1", "x")
    monkeypatch.delenv("TG_TOKEN", raising=False)
    monkeypatch.delenv("TG_CHAT", raising=False)
    sp.validate_secrets(dry_run=True)  # 不應拋出


def test_validate_secrets_real_mode_ok(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY_1", "x")
    monkeypatch.setenv("TG_TOKEN", "t")
    monkeypatch.setenv("TG_CHAT", "c")
    sp.validate_secrets(dry_run=False)  # 齊全 → 不應拋出

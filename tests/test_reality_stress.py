"""
test_reality_stress.py — Phase 4.5 Chaos / Reality Simulation Layer
目的：
驗證 system 在真實失真條件下仍保持：
- 不 crash
- idempotent 正確
- state 不損毀
- 分支可達性（避免假性綠燈）
"""
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import data_manager as dm
import sports_prediction as sp
import notifier
from constants import TW_TZ
from data_fetcher import AllKeysUnavailable

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=TW_TZ)


# ─────────────────────────────
# 1. TIME DRIFT / ORDER CHAOS
# ─────────────────────────────
def test_time_drift_no_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def drift_fetcher(h):
        return [
            {
                "id": f"g{i}",
                "start_time": (
                    NOW + timedelta(minutes=random.randint(-30, 90))
                ).isoformat(),
                "home": "A",
                "away": "B",
            }
            for i in range(20)
        ]

    pushed = sp.tick(
        NOW,
        drift_fetcher,
        notifier.log_only_pusher,
    )
    assert isinstance(pushed, list)


# ─────────────────────────────
# 2. API CHAOS → ALL KEYS FAIL PATH (REAL)
# ─────────────────────────────
def test_api_partial_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def chaos_fetcher(h):
        raise AllKeysUnavailable("simulated failure")

    pushed = sp.tick(
        NOW,
        chaos_fetcher,
        notifier.log_only_pusher,
    )
    # 必須走「吞噬路徑」，不能 crash
    assert pushed == []


# ─────────────────────────────
# 3. DUPLICATE TICK IDEMPOTENCY
# ─────────────────────────────
def test_duplicate_tick_idempotency(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fetcher(h):
        return [{
            "id": "g1",
            "start_time": NOW.isoformat(),
            "home": "A",
            "away": "B",
        }]

    pusher = notifier.log_only_pusher
    r1 = sp.tick(NOW, fetcher, pusher)
    r2 = sp.tick(NOW, fetcher, pusher)
    assert r1 == ["g1"]
    assert r2 == []


# ─────────────────────────────
# 4. STATE CORRUPTION RECOVERY (REAL PATH TRIGGERED)
# ─────────────────────────────
def test_state_file_corruption_recovery(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 故意破壞 state
    with open("flags.json", "w") as f:
        f.write("{broken-json")

    def fetcher(h):
        return [{
            "id": "g1",
            "start_time": NOW.isoformat(),
            "home": "A",
            "away": "B",
        }]

    pushed = sp.tick(
        NOW,
        fetcher,
        notifier.log_only_pusher,
    )
    # 1. crash-free  2. corruption → fallback → recovery
    assert pushed == ["g1"]
    assert dm.is_pushed("g1", "pre") is True

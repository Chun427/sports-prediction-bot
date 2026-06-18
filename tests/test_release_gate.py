"""release_gate 測試 — gate 不打 API、可注入 pytest 結果。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import release_gate as rg  # noqa: E402


def test_ready_full_score_when_all_pass():
    s = rg.is_production_ready(pytest_passed=True)
    assert s["ready"] is True
    assert s["score"] == 100.0
    assert s["blockers"] == []


def test_runtime_default_ready_with_pytest_warning():
    # 預設（runtime）：不跑 pytest → +15 不計，仍 ready；score=85
    s = rg.is_production_ready()
    assert s["ready"] is True
    assert s["score"] == 85.0
    assert any("pytest" in w for w in s["warnings"])


def test_pytest_fail_is_hard_blocker():
    s = rg.is_production_ready(pytest_passed=False)
    assert s["ready"] is False
    assert "pytest fail" in s["blockers"]


def test_market_validation_failure_blocks(monkeypatch):
    import futures_validation

    def _boom(_b):
        raise RuntimeError("boom")

    monkeypatch.setattr(futures_validation, "validate_outright_key", _boom)
    s = rg.is_production_ready(pytest_passed=True)
    assert s["ready"] is False
    assert any("market validation" in b for b in s["blockers"])


def test_shape_keys_present():
    s = rg.is_production_ready()
    assert set(s) == {"ready", "score", "blockers", "warnings"}
    assert isinstance(s["blockers"], list) and isinstance(s["warnings"], list)

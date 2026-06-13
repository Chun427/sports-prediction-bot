"""
test_scores_fetch.py — C-2 fetch_scores（賽果抓取，truth loop）

全程注入 fake transport，不打真實 /scores。
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402

import data_fetcher as df  # noqa: E402
from data_fetcher import AllKeysUnavailable, HttpResponse, KeyManager  # noqa: E402
from constants import TW_TZ  # noqa: E402

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=TW_TZ)


def _km(transport, keys=None):
    return KeyManager(keys or [("ODDS_API_KEY_1", "k1")],
                      now_fn=lambda: NOW, transport=transport)


def _score_ev(gid, home, away, hs, aws, completed=True):
    return {"id": gid, "completed": completed, "home_team": home, "away_team": away,
            "scores": [{"name": home, "score": str(hs)}, {"name": away, "score": str(aws)}],
            "last_update": "2026-06-10T03:50:00Z"}


# ── 解析完賽結果 ─────────────────────────────────────
def test_parse_completed_scores(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake(url):
        return HttpResponse(200, {"x-requests-remaining": "100"},
                            [_score_ev("g1", "Lakers", "Celtics", 110, 102)])

    out = df.fetch_scores("NBA", ["g1"], key_manager=_km(fake))
    assert "g1" in out
    r = out["g1"]
    assert r["completed"] is True
    assert r["home_score"] == 110 and r["away_score"] == 102
    assert r["home_team"] == "Lakers" and r["away_team"] == "Celtics"


# ── URL 帶 eventIds + daysFrom ───────────────────────
def test_url_has_eventids_and_daysfrom(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake(url):
        seen["url"] = url
        return HttpResponse(200, {"x-requests-remaining": "100"}, [])

    df.fetch_scores("NBA", ["g1", "g2"], key_manager=_km(fake), days_from=2)
    assert "/scores" in seen["url"]
    assert "daysFrom=2" in seen["url"]
    assert "g1" in seen["url"] and "g2" in seen["url"]  # eventIds batch


# ── 空 ids → 不發請求 ────────────────────────────────
def test_empty_ids_no_request(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake(url):
        raise AssertionError("should not call transport with empty ids")

    assert df.fetch_scores("NBA", [], key_manager=_km(fake)) == {}


# ── 未完賽 / 無分數 → completed False, score None ────
def test_incomplete_game(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake(url):
        return HttpResponse(200, {"x-requests-remaining": "100"},
                            [{"id": "g1", "completed": False, "home_team": "A",
                              "away_team": "B", "scores": None}])

    r = df.fetch_scores("NBA", ["g1"], key_manager=_km(fake))["g1"]
    assert r["completed"] is False
    assert r["home_score"] is None and r["away_score"] is None


# ── 壞 record（無 id / 壞分數）→ Safe Skip ───────────
def test_bad_records_safe_skip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake(url):
        return HttpResponse(200, {"x-requests-remaining": "100"}, [
            {"completed": True},  # 無 id → skip
            {"id": "g2", "home_team": "A", "away_team": "B",
             "scores": [{"name": "A", "score": "x"}, {"name": "B", "score": "3"}]},  # 壞分數
        ])

    out = df.fetch_scores("NBA", ["g1", "g2"], key_manager=_km(fake))
    assert "g2" in out
    assert out["g2"]["home_score"] is None  # "x" 跳過
    assert out["g2"]["away_score"] == 3


# ── bad status → 回 {} ───────────────────────────────
def test_bad_status_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake(url):
        return HttpResponse(500, {}, None)

    assert df.fetch_scores("NBA", ["g1"], key_manager=_km(fake)) == {}


# ── 不支援運動 → 回 {} ───────────────────────────────
def test_unknown_sport_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake(url):
        raise AssertionError("should not call transport for unknown sport")

    assert df.fetch_scores("CRICKET", ["g1"], key_manager=_km(fake)) == {}


# ── 全部 key 不可用 → AllKeysUnavailable 上拋（不吞）─
def test_all_keys_unavailable_propagates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake(url):  # 429 → cooldown → 切換 → 唯一 key 用盡 → raise
        return HttpResponse(429, {}, None)

    with pytest.raises(AllKeysUnavailable):
        df.fetch_scores("NBA", ["g1"], key_manager=_km(fake))

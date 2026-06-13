"""
test_data_fetcher.py — Fetch 層單元測試（KeyManager / fetch_upcoming_games / DEBUG_API_SCHEMA）

全部使用 fake HTTP transport + fake clock，不打真實 API。
"""
import json
import os
import sys
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import data_manager as dm  # noqa: E402
import obs  # noqa: E402
import sports_prediction as sp  # noqa: E402
from constants import ENV_DEBUG_API_SCHEMA, SPORT_NBA, TW_TZ  # noqa: E402
from data_fetcher import (  # noqa: E402
    AllKeysUnavailable,
    HttpResponse,
    KeyManager,
    fetch_upcoming_games,
)

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=TW_TZ)
K1, K2 = "secretval1", "secretval2"
KEYS = [("ODDS_API_KEY_1", K1), ("ODDS_API_KEY_2", K2)]


def _ok(body, remaining="100"):
    return HttpResponse(200, {"x-requests-remaining": remaining}, body)


def _rl():  # HTTP 429
    return HttpResponse(429, {}, {"message": "rate limited"})


def _quota_401():  # 配額耗盡（401 + usage 訊息）
    return HttpResponse(401, {}, {"message": "Usage quota has been reached"})


def _quota_header():  # 配額耗盡（x-requests-remaining=0）
    return HttpResponse(200, {"x-requests-remaining": "0"}, [])


class FakeTransport:
    """依 URL 中的 apiKey 對應回應；回應可為單一 HttpResponse 或 list（依序彈出）。"""
    def __init__(self, by_key):
        self.by_key = by_key
        self.urls: list[str] = []

    def __call__(self, url: str) -> HttpResponse:
        self.urls.append(url)
        kv = parse_qs(urlparse(url).query).get("apiKey", [""])[0]
        spec = self.by_key[kv]
        if isinstance(spec, list):
            return spec.pop(0)
        return spec

    def used_keys(self):
        return [parse_qs(urlparse(u).query).get("apiKey", [""])[0] for u in self.urls]


def _km(by_key, now=NOW):
    return KeyManager(KEYS, now_fn=lambda: now, transport=FakeTransport(by_key))


class FakePusher:
    def __init__(self):
        self.calls = []

    def __call__(self, g):
        self.calls.append(str(g.get("id")))
        return True

    @property
    def count(self):
        return len(self.calls)


# ── 1. KEY1 預設優先 ─────────────────────────────────
def test_key1_preferred(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    km = _km({K1: _ok([]), K2: _ok([])})
    km.get("/sports/x/events")
    assert km._transport.used_keys() == [K1]


# ── 2. KEY1 429 → KEY2 ───────────────────────────────
def test_key1_429_switches_key2(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    km = _km({K1: _rl(), K2: _ok([])})
    resp = km.get("/sports/x/events")
    assert resp.status == 200
    assert km._transport.used_keys() == [K1, K2]
    # KEY1 cooldown 已落盤
    state = dm.load_key_state()
    assert state["ODDS_API_KEY_1"]["cooldown_until"]


# ── 3. cooldown 期間持續使用 KEY2 ───────────────────
def test_during_cooldown_uses_key2(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 預先讓 KEY1 cooldown 到 NOW+30 分
    dm.save_key_state({"ODDS_API_KEY_1": {
        "cooldown_until": (NOW + timedelta(minutes=30)).isoformat()}})
    km = _km({K1: _ok([]), K2: _ok([])})
    km.get("/sports/x/events")
    assert km._transport.used_keys() == [K2]  # KEY1 被跳過


# ── 4. cooldown 到期恢復 KEY1 ────────────────────────
def test_cooldown_expired_restores_key1(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # KEY1 cooldown 已過期（NOW-1 分）
    dm.save_key_state({"ODDS_API_KEY_1": {
        "cooldown_until": (NOW - timedelta(minutes=1)).isoformat()}})
    km = _km({K1: _ok([]), K2: _ok([])})
    km.get("/sports/x/events")
    assert km._transport.used_keys() == [K1]  # KEY1 重回優先


# ── 5. 配額耗盡觸發切換 ──────────────────────────────
def test_quota_exhausted_header_switches(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # KEY1 配額耗盡（x-requests-remaining=0）→ 切 KEY2 成功
    km = _km({K1: _quota_header(), K2: _ok([])})
    resp = km.get("/sports/x/events")
    assert resp.status == 200
    assert km._transport.used_keys() == [K1, K2]
    assert dm.load_key_state()["ODDS_API_KEY_1"]["cooldown_until"]


def test_quota_401_detected_as_unavailable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # KEY1 401 + usage 訊息 → 視為不可用 → 切 KEY2
    km = _km({K1: _quota_401(), K2: _ok([])})
    resp = km.get("/sports/x/events")
    assert resp.status == 200
    assert km._transport.used_keys() == [K1, K2]


# ── 6. 兩把都不可用 → AllKeysUnavailable ─────────────
def test_all_keys_unavailable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    km = _km({K1: _rl(), K2: _rl()})
    with pytest.raises(AllKeysUnavailable):
        km.get("/sports/x/events")
    state = dm.load_key_state()
    assert state["ODDS_API_KEY_1"]["cooldown_until"]
    assert state["ODDS_API_KEY_2"]["cooldown_until"]


# ── 7. cooldown 跨 process 持久化 ────────────────────
def test_cooldown_persists_across_processes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # process #1：KEY1 429 → 落盤 cooldown
    _km({K1: _rl(), K2: _ok([])}).get("/sports/x/events")
    # process #2：全新 KeyManager 實例（模擬新 run）→ 讀到持久化 cooldown → 用 KEY2
    km2 = _km({K1: _ok([]), K2: _ok([])})
    km2.get("/sports/x/events")
    assert km2._transport.used_keys() == [K2]


# ── 8. key_state.json 毀損降級 ───────────────────────
def test_corrupt_key_state_degrades(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "key_state.json").write_text("{not valid", encoding="utf-8")
    km = _km({K1: _ok([]), K2: _ok([])})
    km.get("/sports/x/events")  # 不應 crash
    assert km._transport.used_keys() == [K1]  # 降級全部可用 → KEY1


# ── 9. 金鑰本體不落盤 ────────────────────────────────
def test_key_value_not_persisted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _km({K1: _rl(), K2: _ok([])}).get("/sports/x/events")
    content = (tmp_path / "key_state.json").read_text(encoding="utf-8")
    assert K1 not in content and K2 not in content  # 只存 env 名 + 時間戳
    assert "ODDS_API_KEY_1" in content


# ── 10. UTC → TW 時區轉換 ────────────────────────────
def test_utc_to_tw_conversion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 04:30 UTC == 12:30 TW
    ev = {"id": "e1", "commence_time": "2026-06-10T04:30:00Z",
          "home_team": "A", "away_team": "B"}
    km = _km({K1: _ok([ev]), K2: _ok([ev])})
    games = fetch_upcoming_games(48, key_manager=km, now_fn=lambda: NOW, sports=[SPORT_NBA])
    assert len(games) == 1
    start = games[0]["start_time"]
    assert start.startswith("2026-06-10T12:30:00") and start.endswith("+08:00")


# ── 11. 壞 record Safe Skip ──────────────────────────
def test_bad_record_safe_skip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    good = {"id": "g", "commence_time": "2026-06-10T05:00:00Z", "home_team": "A", "away_team": "B"}
    no_time = {"id": "x", "home_team": "A", "away_team": "B"}       # 缺 commence_time
    no_id = {"commence_time": "2026-06-10T05:00:00Z"}               # 缺 id
    bad_time = {"id": "y", "commence_time": "not-a-date"}           # 壞時間
    km = _km({K1: _ok([good, no_time, no_id, bad_time]), K2: _ok([])})
    games = fetch_upcoming_games(48, key_manager=km, now_fn=lambda: NOW, sports=[SPORT_NBA])
    assert [g["id"] for g in games] == ["g"]  # 只留好的，不崩


# ── 12. 空回應回 [] ──────────────────────────────────
def test_empty_response_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    km = _km({K1: _ok([]), K2: _ok([])})
    games = fetch_upcoming_games(48, key_manager=km, now_fn=lambda: NOW, sports=[SPORT_NBA])
    assert games == []


# ── 13. DEBUG_API_SCHEMA = true ──────────────────────
def test_debug_schema_true(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(ENV_DEBUG_API_SCHEMA, "true")
    obs.reset_schema_cache()
    ev = {"id": "e1", "commence_time": "2026-06-10T05:00:00Z", "home_team": "A", "away_team": "B"}
    km = _km({K1: _ok([ev]), K2: _ok([ev])})
    fetch_upcoming_games(48, key_manager=km, now_fn=lambda: NOW, sports=[SPORT_NBA])
    out = capsys.readouterr().out
    assert "[schema] NBA raw[0]" in out
    assert "[schema] NBA parsed[0]" in out


# ── 14. DEBUG_API_SCHEMA = false ─────────────────────
def test_debug_schema_false(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(ENV_DEBUG_API_SCHEMA, raising=False)
    obs.reset_schema_cache()
    ev = {"id": "e1", "commence_time": "2026-06-10T05:00:00Z", "home_team": "A", "away_team": "B"}
    km = _km({K1: _ok([ev]), K2: _ok([ev])})
    fetch_upcoming_games(48, key_manager=km, now_fn=lambda: NOW, sports=[SPORT_NBA])
    out = capsys.readouterr().out
    assert "[schema]" not in out  # production no-op


# ── 15. tick() 對 AllKeysUnavailable 跳過本輪 ────────
def test_tick_skips_on_all_keys_unavailable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 真實串接：tick → ensure_pool → fetch_upcoming_games（兩把 429）→ AllKeysUnavailable
    km = _km({K1: _rl(), K2: _rl()})

    def fetcher(hours_ahead):
        return fetch_upcoming_games(hours_ahead, key_manager=km,
                                    now_fn=lambda: NOW, sports=[SPORT_NBA])

    pusher = FakePusher()
    pushed = sp.tick(NOW, fetcher, pusher)  # 12:00 刷新時刻
    assert pushed == []
    assert pusher.count == 0


# ── 16/17/18. /odds h2h 解析（Processing 切片）────────
def _odds_event(eid="e1"):
    return {
        "id": eid, "commence_time": "2026-06-10T05:00:00Z",
        "home_team": "A", "away_team": "B",
        "bookmakers": [
            {"key": "dk", "markets": [{"key": "h2h", "outcomes": [
                {"name": "A", "price": 1.90}, {"name": "B", "price": 1.95}]}]},
            {"key": "fd", "markets": [{"key": "h2h", "outcomes": [
                {"name": "A", "price": 1.85}, {"name": "B", "price": 2.00}]}]},
        ],
    }


def test_odds_parsed_into_game(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    km = _km({K1: _ok([_odds_event()]), K2: _ok([])})
    games = fetch_upcoming_games(48, key_manager=km, now_fn=lambda: NOW, sports=[SPORT_NBA])
    assert len(games) == 1
    rows = games[0]["odds_h2h"]
    assert len(rows) == 2
    assert rows[0]["home"] == 1.90 and rows[0]["away"] == 1.95
    assert rows[0]["draw"] is None


def test_event_without_bookmakers_parses_empty_odds(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 舊 /events 形狀（無 bookmakers）→ 仍解析、odds_h2h 為空（向後相容）
    ev = {"id": "e1", "commence_time": "2026-06-10T05:00:00Z", "home_team": "A", "away_team": "B"}
    km = _km({K1: _ok([ev]), K2: _ok([])})
    games = fetch_upcoming_games(48, key_manager=km, now_fn=lambda: NOW, sports=[SPORT_NBA])
    assert games[0]["odds_h2h"] == []


def test_bad_bookmaker_safe_skip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ev = {
        "id": "e1", "commence_time": "2026-06-10T05:00:00Z", "home_team": "A", "away_team": "B",
        "bookmakers": [
            {"key": "broken"},  # 缺 markets → Safe Skip
            {"key": "ok", "markets": [{"key": "h2h", "outcomes": [
                {"name": "A", "price": 1.90}, {"name": "B", "price": 1.95}]}]},
        ],
    }
    km = _km({K1: _ok([ev]), K2: _ok([])})
    games = fetch_upcoming_games(48, key_manager=km, now_fn=lambda: NOW, sports=[SPORT_NBA])
    rows = games[0]["odds_h2h"]
    assert len(rows) == 1 and rows[0]["book"] == "ok"

"""
test_notifier.py — Output 層（render_pregame / TelegramSender / make_pusher）

全程注入 fake transport，不送真實 Telegram。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import notifier as nf  # noqa: E402
from notifier import TgResponse  # noqa: E402

PRED_2WAY = {
    "game_id": "g1", "sport": "NBA", "home": "Lakers", "away": "Celtics",
    "start_time": "2026-06-11T10:30:00+08:00", "market": "h2h", "bookmaker_count": 5,
    "fair_prob": {"home": 0.561, "away": 0.439},
    "best_odds": {"home": 1.85, "away": 2.30},
    "edge": {"home": 0.038, "away": -0.010},
    "best_pick": {"outcome": "home", "edge": 0.038, "odds": 1.85},
    "avg_overround": 0.045, "model": "market_implied_v1",
    "generated_at": "2026-06-11T10:05:00+08:00",
}

PRED_3WAY = {
    **PRED_2WAY, "sport": "FIFA",
    "fair_prob": {"home": 0.45, "away": 0.30, "draw": 0.25},
    "best_odds": {"home": 2.20, "away": 3.40, "draw": 3.10},
    "best_pick": None,
}


# ── render：2-way 內容 ───────────────────────────────
def test_render_2way_content():
    msg = nf.render_pregame(PRED_2WAY)
    assert "賽前分析" in msg
    assert "Lakers" in msg and "Celtics" in msg
    assert "56.1%" in msg and "43.9%" in msg          # fair prob
    assert "1.85" in msg and "2.3" in msg             # best odds
    assert "edge +3.8% @ 1.85" in msg                 # best pick
    assert "market_implied_v1" in msg
    assert "非投注建議" in msg                          # disclaimer 必在


# ── render：3-way（含和局）───────────────────────────
def test_render_3way_draw():
    msg = nf.render_pregame(PRED_3WAY)
    assert "和局" in msg and "25.0%" in msg


# ── render：best_pick None → 無價值標的 ──────────────
def test_render_no_value_pick():
    p = {**PRED_2WAY, "best_pick": None}
    msg = nf.render_pregame(p)
    assert "無價值標的" in msg


# ── render：golden / 契約結構釘樁 ────────────────────
def test_render_contract_sections():
    msg = nf.render_pregame(PRED_2WAY)
    for section in ("🎯 精算師預測系統 — 賽前分析", "📐 市場隱含勝率",
                    "💰 最佳賠率", "💎 價值分析", "🔖 模型："):
        assert section in msg


# ── TelegramSender：payload / URL / 成功 ─────────────
def test_sender_payload_and_success():
    captured = {}

    def fake(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return TgResponse(200, True)

    ok = nf.TelegramSender("TOK", "CHAT", transport=fake).send("hello")
    assert ok is True
    assert captured["url"].endswith("/botTOK/sendMessage")
    assert captured["payload"] == {"chat_id": "CHAT", "text": "hello"}


# ── TelegramSender：失敗重試 → False ─────────────────
def test_sender_retry_then_false():
    calls = {"n": 0}

    def fake(url, payload):
        calls["n"] += 1
        return TgResponse(500, False)

    ok = nf.TelegramSender("T", "C", transport=fake, retry=3).send("x")
    assert ok is False
    assert calls["n"] == 3  # 重試滿 3 次


def test_sender_exception_does_not_crash():
    def boom(url, payload):
        raise RuntimeError("network down")

    assert nf.TelegramSender("T", "C", transport=boom, retry=2).send("x") is False


# ── make_pusher：DRY_RUN → log-only（不觸網路）───────
def test_make_pusher_dry_run(capsys):
    pusher = nf.make_pusher(True)
    ok = pusher({"id": "g1", "prediction": PRED_2WAY})
    assert ok is True
    out = capsys.readouterr().out
    assert "[DRY_RUN_PUSH] game_id=g1 would_send=True" in out
    assert "市場隱含勝率" in out  # 預覽模板


# ── make_pusher：real → render + send ────────────────
def test_make_pusher_real_sends():
    sent = {}

    def fake(url, payload):
        sent["text"] = payload["text"]
        return TgResponse(200, True)

    pusher = nf.make_pusher(False, token="T", chat="C", transport=fake)
    ok = pusher({"id": "g1", "prediction": PRED_2WAY})
    assert ok is True
    assert "賽前分析" in sent["text"] and "Lakers" in sent["text"]


# ── make_pusher：real 但無 prediction → 不送、False ──
def test_make_pusher_real_no_prediction():
    def fake(url, payload):
        raise AssertionError("should not send without prediction")

    pusher = nf.make_pusher(False, token="T", chat="C", transport=fake)
    assert pusher({"id": "g1"}) is False

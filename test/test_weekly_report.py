"""
test_weekly_report.py — P1 FEATURE 2：每週基本報表彙整測試。

全程注入 rows（不依賴實體 verified_history.csv）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import weekly_report as wr  # noqa: E402
import notifier as nf  # noqa: E402


def _row(sport, ml_hit, rr, fpw, verified_at="2026-05-22T10:00:00+08:00"):
    return {
        "verified_at": verified_at,
        "game_id": "g",
        "sport": sport,
        "winner": "home",
        "pick_outcome": "home",
        "pick_hit": str(ml_hit),
        "moneyline_hit": str(ml_hit),
        "realized_return": str(rr),
        "fair_prob_winner": str(fpw),
        "model": "market_implied_v1",
    }


def test_empty_rows_safe_fallback():
    r = wr.build_weekly_report(rows=[])
    assert r["total_games"] == 0
    assert r["win_rate"] == 0.0
    assert r["sport_breakdown"] == {}


def test_win_rate_from_moneyline_hit():
    rows = [_row("NBA", True, 1.0, 0.55), _row("NBA", False, -1.0, 0.45),
            _row("NBA", True, 0.9, 0.60), _row("NBA", True, 0.8, 0.58)]
    r = wr.build_weekly_report(rows=rows)
    assert r["total_games"] == 4
    assert r["win_rate"] == 0.75  # 3/4


def test_avg_realized_return_mean():
    rows = [_row("MLB", True, 1.0, 0.5), _row("MLB", False, -1.0, 0.5)]
    r = wr.build_weekly_report(rows=rows)
    assert r["avg_realized_return"] == 0.0
    assert r["ev_trend"] == 0.0


def test_market_calibration_mean():
    rows = [_row("NBA", True, 1.0, 0.50), _row("NBA", True, 1.0, 0.70)]
    r = wr.build_weekly_report(rows=rows)
    assert r["market_calibration"] == 0.6


def test_sport_breakdown():
    rows = [_row("NBA", True, 1.0, 0.6), _row("NBA", False, -1.0, 0.4),
            _row("MLB", True, 1.0, 0.55)]
    r = wr.build_weekly_report(rows=rows)
    assert set(r["sport_breakdown"].keys()) == {"NBA", "MLB"}
    assert r["sport_breakdown"]["NBA"]["games"] == 2
    assert r["sport_breakdown"]["NBA"]["win_rate"] == 0.5
    assert r["sport_breakdown"]["MLB"]["win_rate"] == 1.0


def test_csv_string_parsing_handles_blank():
    rows = [_row("NBA", True, 1.0, 0.6)]
    rows.append({**_row("NBA", True, 1.0, 0.6), "moneyline_hit": "", "realized_return": "", "fair_prob_winner": ""})
    r = wr.build_weekly_report(rows=rows)
    # 空字串不計入；win_rate 仍由有效那筆決定
    assert r["total_games"] == 2
    assert r["win_rate"] == 1.0


def test_week_range_derived_from_verified_at():
    rows = [_row("NBA", True, 1.0, 0.6, "2026-05-22T10:00:00+08:00"),
            _row("NBA", False, -1.0, 0.4, "2026-05-28T10:00:00+08:00")]
    r = wr.build_weekly_report(rows=rows)
    assert r["week_range"] == "2026-05-22 ~ 2026-05-28"


def test_week_range_explicit_override():
    rows = [_row("NBA", True, 1.0, 0.6)]
    r = wr.build_weekly_report(rows=rows, week_range="W21")
    assert r["week_range"] == "W21"


def test_render_contains_key_fields():
    rows = [_row("NBA", True, 1.0, 0.6), _row("MLB", False, -1.0, 0.4)]
    r = wr.build_weekly_report(rows=rows)
    text = nf.render_weekly_report(r)
    assert "本週預測週報" in text
    assert "獨贏命中率" in text
    assert "🏀 100.0%" in text and "⚾ 0.0%" in text   # 固定 contract：emoji 各運動列
    assert "大小盤命中：N/A" in text                     # 未追蹤 → N/A（不捏造）
    assert "數據分析，請理性投注" in text


def test_render_empty_report_does_not_crash():
    text = nf.render_weekly_report(wr.build_weekly_report(rows=[]))
    assert "預測週報" in text
    assert "0 場" in text

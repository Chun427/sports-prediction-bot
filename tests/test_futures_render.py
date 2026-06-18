"""futures_render 測試 — renderer 只格式化已備妥的資料。"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import futures_render as fr  # noqa: E402


def _available_data():
    return {
        "capability": "Champion", "title": "🏆 冠軍機率（市場隱含·去Vig）",
        "available": True, "na_reason": None, "source": "odds_api_outrights",
        "overround": 1.08,
        "ranked": [
            {"outcome": "Spain", "fair_probability": 0.182},
            {"outcome": "France", "fair_probability": 0.175},
        ],
    }


def test_text_lists_ranked_with_pct():
    txt = fr.render_text(_available_data())
    assert "冠軍機率" in txt
    assert "Spain" in txt and "18.2" in txt        # 不綁定空格/前綴格式
    assert "France" in txt and "17.5" in txt
    assert txt.index("Spain") < txt.index("France")  # 只驗順序：Spain 在前
    assert "非模型" in txt


def test_text_na_shows_reason():
    data = {"capability": "BallonDor", "title": "金球", "available": False,
            "na_reason": "Odds API 不涵蓋此獎項", "ranked": []}
    txt = fr.render_text(data)
    assert "N/A" in txt and "不涵蓋" in txt


def test_text_empty_input_safe():
    assert "N/A" in fr.render_text(None)
    assert "N/A" in fr.render_text({})


def test_json_roundtrips():
    s = fr.render_json(_available_data())
    back = json.loads(s)
    assert back["capability"] == "Champion" and back["available"] is True
    assert back["ranked"][0]["outcome"] == "Spain"


def test_render_awards_mixed_available_and_na():
    results = [
        {"capability": "Champion", "title": "🏆 冠軍預測", "available": True,
         "ranked": [{"outcome": "Brazil", "fair_probability": 0.184},
                    {"outcome": "France", "fair_probability": 0.152}]},
        {"capability": "GoldenBoot", "title": "👟 金靴獎", "available": False, "na_reason": "待 API"},
        {"capability": "GoldenGlove", "title": "🧤 金手套獎", "available": False, "na_reason": "無盤"},
    ]
    txt = fr.render_awards(results, header="🏆 World Cup 獎項")
    assert "🏆 World Cup 獎項" in txt
    assert "🥇 Brazil 18.4%" in txt and "🥈 France 15.2%" in txt
    assert "👟 金靴獎" in txt and "（暫無盤口資料）" in txt        # N/A 不捏造
    assert "🧤 金手套獎" in txt
    assert "數據來源：AI模型+真實數據+賠率" in txt and "請理性投注" in txt   # 固定 footer

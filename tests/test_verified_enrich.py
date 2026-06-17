"""verified_enrich（V4 Phase 1）測試 — 合成資料、不依賴網路/實體 CSV。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import verified_enrich as ve  # noqa: E402


def _fifa_pred():
    return {
        "sport": "FIFA", "home": "H", "away": "A", "phase": "pre_match_40m",
        "edge": {"home": 0.05, "draw": -0.10, "away": -0.02},
        "fair_prob": {"home": 0.50, "draw": 0.30, "away": 0.20},
        "model_mc": {"win_prob": {"home": 0.55, "draw": 0.25, "away": 0.20}},
        "model_score": {
            "sport": "FIFA", "lambda_home": 1.6, "lambda_away": 1.0,
            "expected_total": 2.6,
            "top_scorelines": [
                {"home": 2, "away": 1, "prob": 0.10},
                {"home": 1, "away": 0, "prob": 0.09},
            ],
        },
    }


def test_fifa_scoreline_and_total_and_diag():
    r = {"completed": True, "home_score": 2, "away_score": 1}
    e = ve.enrich(_fifa_pred(), r, "FIFA")
    assert e["scoreline_hit"] == 1                  # 2–1 命中一組
    assert e["actual_total"] == 3
    assert isinstance(e["total_goals_hit"], bool)   # FIFA 有總進球桶
    assert e["expected_total"] == 2.6
    assert e["phase"] == "pre_match_40m"
    # 診斷欄位取主推方向（home＝MC argmax）
    assert e["model_winprob"] == 0.55
    assert e["devig_winprob"] == 0.50
    assert e["confidence"] == 0.55
    assert e["edge"] == 0.05


def test_mlb_total_goals_is_none():
    pred = _fifa_pred()
    pred["sport"] = "MLB"
    pred["model_score"]["sport"] = "MLB"
    e = ve.enrich(pred, {"completed": True, "home_score": 5, "away_score": 4}, "MLB")
    assert e["total_goals_hit"] is None             # 非 FIFA → None（避免 schema bias）
    assert e["actual_total"] == 9


def test_no_top_scorelines_gives_none():
    pred = _fifa_pred()
    pred["model_score"].pop("top_scorelines")
    e = ve.enrich(pred, {"completed": True, "home_score": 1, "away_score": 1}, "FIFA")
    assert e["scoreline_hit"] is None               # 無 top_scorelines → None（不算 0）


def test_missing_scores_safe_none_no_crash():
    e = ve.enrich({"sport": "MLB"}, {"completed": True}, "MLB")
    assert e["actual_total"] is None
    assert e["ah_hit"] is None and e["ou_hit"] is None
    assert e["scoreline_hit"] is None and e["total_goals_hit"] is None


def test_total_keys_present():
    e = ve.enrich(_fifa_pred(), {"completed": True, "home_score": 0, "away_score": 0}, "FIFA")
    for k in ("ah_hit", "ou_hit", "scoreline_hit", "total_goals_hit", "edge",
              "confidence", "model_winprob", "devig_winprob",
              "expected_total", "actual_total", "phase"):
        assert k in e


# ── data_manager schema 層（V4 收尾）─────────────────────
import data_manager as dm  # noqa: E402


def test_schema_version_and_legacy_prefix():
    assert dm.VERIFIED_SCHEMA_VERSION >= 2
    # 舊欄位必須是新 schema 的前綴（guard 已在 import 時 assert，這裡再明確驗一次）
    assert dm.VERIFIED_FIELDS[:len(dm._LEGACY_VERIFIED_FIELDS)] == dm._LEGACY_VERIFIED_FIELDS


def test_atomic_migration_preserves_old_and_no_tmp(tmp_path, monkeypatch):
    csv_path = tmp_path / "verified_history.csv"
    # 舊 10 欄檔
    csv_path.write_text(
        "verified_at,game_id,sport,winner,pick_outcome,pick_hit,moneyline_hit,"
        "realized_return,fair_prob_winner,model\n"
        "2026-01-01,g1,MLB,home,home,True,True,0.1,0.55,market_v1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dm, "VERIFIED_HISTORY_CSV", str(csv_path))
    dm.append_verified({"game_id": "g2", "sport": "FIFA", "ah_hit": True, "phase": "early_12h"})
    view = dm.normalized_verified_view()
    assert len(view) == 2
    assert len(view[0].keys()) == len(dm.VERIFIED_FIELDS)     # 統一 21 欄
    assert view[0]["pick_hit"] == "True"                      # 舊值保留
    assert view[0]["ah_hit"] is None                          # 舊列新欄＝None（不 backfill/不猜）
    assert view[1]["ah_hit"] == "True" and view[1]["phase"] == "early_12h"
    assert not (tmp_path / "verified_history.csv.tmp").exists()  # 原子改名後無殘留 tmp


def test_normalized_view_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "VERIFIED_HISTORY_CSV", str(tmp_path / "nope.csv"))
    assert dm.normalized_verified_view() == []

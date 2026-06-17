"""dev_preview.py — 隔離式手動預覽 runner（完全不影響 production）。

用途：在本機手動預覽各種推播畫面，方便檢查版面。
  • 只「讀」weekly_games.json / verified_history.csv / predictions.json。
  • 不寫任何 state、不碰 is_pushed、不呼叫 tick()、不送 Telegram（只 print）。
  • 重用既有 predict + score_model + 蒙地卡羅 + notifier render，畫面 100% 等同正式推播。
  • 檔名刻意非 test_ 開頭 → 不會被 pytest 收集，不影響 CI。

用法（環境變數控制）：
  FORCE_STAGE=early_12h     FORCE_SPORT=FIFA  python src/dev_preview.py
  FORCE_STAGE=pre_match_40m FORCE_SPORT=MLB   python src/dev_preview.py
  FORCE_STAGE=single_match                    python src/dev_preview.py
  FORCE_STAGE=postgame                        python src/dev_preview.py
  FORCE_STAGE=worldcup_batch                  python src/dev_preview.py
  FORCE_STAGE=weekly                          python src/dev_preview.py

stage：early_12h / pre_match_40m / single_match / postgame / worldcup_batch / weekly
sport：FIFA / MLB / NBA（留空=全部）
"""
from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_manager as dm
import monte_carlo_engine
import notifier
import prediction_engine
import score_model
import worldcup_batch

try:
    import weekly_report
except Exception:  # noqa: BLE001
    weekly_report = None

_UTC = datetime.timezone.utc
_DIV = "═" * 40


def _load_games() -> list[dict]:
    d = dm._read_json("weekly_games.json", {"games": []})
    games = d.get("games", []) if isinstance(d, dict) else (d or [])
    return games or []


def _filter_sport(games: list[dict], sport: str) -> list[dict]:
    if not sport:
        return games
    return [g for g in games if (g.get("sport") or "").upper() == sport.upper()]


def _within_hours(g: dict, lo: float, hi: float) -> bool:
    ct = g.get("commence_time_utc") or g.get("start_time") or ""
    try:
        t = datetime.datetime.fromisoformat(ct.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return False
    dh = (t - datetime.datetime.now(_UTC)).total_seconds() / 3600
    return lo <= dh <= hi


def _full_predict(g: dict) -> dict | None:
    """重現推播路徑：predict（市場）→ 補 score_model + 蒙地卡羅。只讀，不寫。"""
    pred = prediction_engine.predict(g)
    if not pred:
        return None
    score = score_model.build_score_model(g)
    mc = monte_carlo_engine.run_monte_carlo(score)
    return {**pred, "model_score": score, "model_mc": mc}


def _emit(title: str, msg: str) -> None:
    print(f"\n{_DIV}\n  {title}\n{_DIV}")
    print(msg)


def _preview_pregame(games: list[dict], header: str, only_one: bool) -> None:
    # 取 12h 內；若都不在窗內，仍取最近幾場供版面預覽
    near = [g for g in games if _within_hours(g, -2, 12)] or games
    near = near[:1] if only_one else near
    if not near:
        print("（無符合條件的賽事）")
        return
    for g in near:
        pred = _full_predict(g)
        label = f"{g.get('sport')}｜{g.get('away')} @ {g.get('home')}"
        if not pred:
            print(f"\n（{label}：predict 回 None＝無有效 h2h 市場，正式流程會略過此場）")
            continue
        _emit(label, notifier.render_pregame_lite(pred, header_kind=header))


def _preview_postgame(sport: str) -> None:
    rows = dm.read_verified()
    if sport:
        rows = [r for r in rows if (r.get("sport") or "").upper() == sport.upper()]
    if not rows:
        print("（verified_history 無資料，無法預覽賽後）")
        return
    preds = dm._read_json("predictions.json", {})
    print("⚠️ 離線預覽限制：賽後『實際比分』只來自 live scores API（repo 無此資料），"
          "故『比分5組/總進球』會是略過；獨贏結果取自 verified_history（真實）。")
    for r in rows[-3:]:  # 最近 3 筆
        gid = r.get("game_id", "")
        pred = preds.get(str(gid)) or preds.get(gid) or {}
        if isinstance(pred, dict) and "prediction" in pred:
            pred = pred["prediction"]
        if not pred:
            pred = {"sport": r.get("sport"), "home": "", "away": "", "model_score": {}}
        verification = {"pick_outcome": r.get("pick_outcome"), "pick_hit": str(r.get("pick_hit", "")).lower() == "true",
                        "winner": r.get("winner"), "verified_at": r.get("verified_at", "")}
        result = {}  # 離線無真實比分
        _emit(f"賽後｜{r.get('sport')}｜{gid[:8]}",
              notifier.render_postgame_eval(verification, pred, result))


def _preview_worldcup() -> None:
    rows = [r for r in dm.read_verified() if (r.get("sport") or "").upper() == "FIFA"]
    n = worldcup_batch.BATCH_SIZE
    if len(rows) < n:
        print(f"（FIFA 已驗證 {len(rows)} 場，未滿 {n} 場 → 尚無批次可推）")
        return
    _emit("WorldCup 批次（預覽，不寫 state）",
          worldcup_batch.render_worldcup_batch(rows[:n], 1))


def _preview_weekly() -> None:
    if weekly_report is None:
        print("（weekly_report 模組不可用）")
        return
    rep = weekly_report.build_weekly_report(dm.read_verified())
    print("📅 本週統計（read-only，僅資料預覽）：")
    for k, v in (rep.items() if isinstance(rep, dict) else []):
        print(f"  {k}: {v}")


def run(stage: str, sport: str) -> None:
    games = _filter_sport(_load_games(), sport)
    if stage == "early_12h":
        _preview_pregame(games, "early", only_one=False)
    elif stage == "pre_match_40m":
        _preview_pregame(games, "final", only_one=False)
    elif stage == "single_match":
        _preview_pregame(games, "final", only_one=True)
    elif stage == "postgame":
        _preview_postgame(sport)
    elif stage == "worldcup_batch":
        _preview_worldcup()
    elif stage == "weekly":
        _preview_weekly()
    else:
        print(f"未知 stage：{stage}（可用：early_12h / pre_match_40m / single_match / "
              f"postgame / worldcup_batch / weekly）")


if __name__ == "__main__":
    stage = os.environ.get("FORCE_STAGE", "early_12h")
    sport = os.environ.get("FORCE_SPORT", "")
    print(f"[DEV PREVIEW] 隔離預覽｜stage={stage}｜sport={sport or 'ALL'}｜"
          f"不寫 state、不碰 is_pushed、不送 Telegram")
    run(stage, sport)

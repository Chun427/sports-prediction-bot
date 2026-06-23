"""collector.py — Feature Collector 編排（完全獨立子系統）。

職責：讀 verified_history.csv（已完成的 MLB 場）→ 對每場各隊呼叫各來源 → 合併成列 → append。

關鍵保證：
- 不 import prediction_engine / sports_prediction / scheduler / notifier（零 production 耦合）。
- 任何來源失敗 → 該欄 NA，整體不中斷（資料品質記在 source_status）。
- 可注入所有來源（offline 測試）；CLI 直接跑會嘗試真實來源（沙箱無網路時全 NA）。
- 不做任何模型、不做任何分析（純蒐集）。
"""

from __future__ import annotations

import csv
import datetime as dt
import os
from . import schema, storage
from .sources import mlb_statsapi, pybaseball_src


def _verified_mlb(vh_path: str) -> list[dict]:
    if not os.path.exists(vh_path):
        return []
    with open(vh_path, newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("sport") == "MLB"]


def _resolve_game_context(game_id: str, weekly_games_path: str = "weekly_games.json") -> dict:
    """用 game_id join weekly_games 取 team/opponent（純資料 join，零推論）。

    用真實欄位：weekly_games 的 `id`/`home`/`away`（非 home_team/away_team）。
    注意：weekly_games 是滾動視窗（約 48h），只能補「仍在池內」的場；
    已滾出的舊場 → 回空（team 維持 NA，誠實）。
    """
    import json
    if not game_id or not os.path.exists(weekly_games_path):
        return {}
    try:
        wk = json.load(open(weekly_games_path))
        games = wk if isinstance(wk, list) else (wk.get("games") or [])
        for g in games:
            if str(g.get("id")) == str(game_id):
                return {"team": g.get("home"), "opponent": g.get("away"), "home_away": "home"}
    except Exception:
        pass
    return {}


def build_row(game: dict, *, statsapi_ctx=None, pitcher_fetcher=None, now=None,
              weekly_games_path="weekly_games.json") -> dict:
    """為單場單隊組一列 feature（全 NA 起始，各來源填能填的）。"""
    now = now or dt.datetime.utcnow()
    row = schema.empty_row()
    row["collected_at"] = now.isoformat(timespec="seconds")
    row["game_pk"] = schema.coerce(game.get("game_id"))
    row["game_date"] = schema.coerce((game.get("verified_at") or "")[:10])
    row["actual_winner"] = schema.coerce(game.get("winner"))
    row["actual_total"] = schema.coerce(game.get("actual_total"))

    # team/opponent：用 game_id join weekly_games（純資料 join，取不到→NA）
    ctx_game = _resolve_game_context(row["game_pk"], weekly_games_path)
    row["team"] = schema.coerce(ctx_game.get("team"))
    row["opponent"] = schema.coerce(ctx_game.get("opponent"))
    row["home_away"] = schema.coerce(ctx_game.get("home_away"))
    statuses = []

    # 來源 1：MLB Stats API 情境（先發名、球場）
    ctx_fn = statsapi_ctx or mlb_statsapi.fetch_team_context
    ctx = ctx_fn(row["team"], row["game_date"])
    for k, v in ctx.items():
        if k.startswith("source_"):
            statuses.append(f"{k}={v}")
        elif k in schema.COLUMNS:
            row[k] = schema.coerce(v)

    # 來源 2：pybaseball 先發進階數據（用來源1拿到的 sp_name）
    season = int(row["game_date"][:4]) if row["game_date"][:4].isdigit() else now.year
    pdata = pybaseball_src.fetch_pitcher(row.get("sp_name", schema.NA), season, fetcher=pitcher_fetcher)
    for k, v in pdata.items():
        if k.startswith("source_"):
            statuses.append(f"{k}={v}")
        elif k in schema.COLUMNS:
            row[k] = schema.coerce(v)

    row["source_status"] = ";".join(statuses) if statuses else schema.NA
    return row


def run(vh_path: str = "verified_history.csv", out_path: str = storage.DEFAULT_PATH,
        *, statsapi_ctx=None, pitcher_fetcher=None, now=None,
        weekly_games_path="weekly_games.json") -> dict:
    """主流程：蒐集所有 MLB 已驗證場的 feature 並 append。回傳摘要。"""
    games = _verified_mlb(vh_path)
    rows = [build_row(g, statsapi_ctx=statsapi_ctx, pitcher_fetcher=pitcher_fetcher, now=now,
                      weekly_games_path=weekly_games_path) for g in games]
    written = storage.append_rows(rows, out_path)
    return {"verified_mlb": len(games), "rows_built": len(rows),
            "rows_appended": written, "total_in_db": storage.row_count(out_path)}


if __name__ == "__main__":
    summary = run()
    print({"feature_collector": summary})

"""pybaseball_src.py — pybaseball 來源（投手進階數據）。

重要：pybaseball 非官方 API，是 scraping wrapper。設計為 optional import + 失敗即 NA。
production 長期依賴應搭配 cache，不可每次 live scrape。
授權注意：FanGraphs/BBRef ToS 對 scraping/商業用途有限制。
"""

from __future__ import annotations

from typing import Callable
from .. import schema

PITCHER_FIELDS = ["sp_era", "sp_fip", "sp_xfip", "sp_whip", "sp_k_pct", "sp_bb_pct",
                  "sp_hardhit_pct", "sp_barrel_pct"]


def _pybaseball_available() -> bool:
    try:
        import pybaseball  # noqa: F401
        return True
    except Exception:
        return False


def fetch_pitcher(sp_name: str, season: int, *, fetcher: Callable | None = None) -> dict[str, str]:
    """回傳先發投手進階數據（全 NA 起始）。失敗/無套件 → NA，絕不 raise。"""
    row = {f: schema.NA for f in PITCHER_FIELDS}
    if not sp_name or sp_name == schema.NA:
        row["source_pybaseball_sp"] = "SKIP_NO_NAME"
        return row
    if fetcher is None and not _pybaseball_available():
        row["source_pybaseball_sp"] = "UNAVAILABLE"
        return row
    try:
        data = fetcher(sp_name, season) if fetcher else _real_pitcher(sp_name, season)
        if not data:
            row["source_pybaseball_sp"] = "FAIL"
            return row
        for f in PITCHER_FIELDS:
            row[f] = schema.coerce(data.get(f))
        row["source_pybaseball_sp"] = "OK"
    except Exception:
        row["source_pybaseball_sp"] = "FAIL"
    return row


def _real_pitcher(sp_name: str, season: int) -> dict | None:
    try:
        from pybaseball import pitching_stats
        df = pitching_stats(season, season)
        m = df[df["Name"].str.lower() == sp_name.lower()]
        if m.empty:
            return None
        r = m.iloc[0]
        def g(*keys):
            for k in keys:
                if k in r and r[k] == r[k]:  # not NaN
                    return r[k]
            return None
        return {
            "sp_era": g("ERA"), "sp_fip": g("FIP"), "sp_xfip": g("xFIP"),
            "sp_whip": g("WHIP"), "sp_k_pct": g("K%"), "sp_bb_pct": g("BB%"),
            "sp_hardhit_pct": g("HardHit%"), "sp_barrel_pct": g("Barrel%"),
        }
    except Exception:
        return None

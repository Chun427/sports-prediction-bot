"""futures_devig.py — 純函式：一組 outright 賠率 → 去 Vig。

單一職責＝機率數學。不抓 API、不排序、不 render、不查 registry。
回傳四件套（raw_odds / implied_probability / overround / fair_probability），
讓 audit 後續不必重算（Reviewer Rule 4）。
"""
from __future__ import annotations


def devig(odds: dict[str, float]) -> dict | None:
    """odds: {outcome_name: decimal_odds}。

    乘法歸一去 Vig。有效 outcome < 2 或總和非正 → None（不捏造）。
    """
    raw = {k: float(v) for k, v in (odds or {}).items()
           if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 1.0}
    if len(raw) < 2:
        return None
    implied = {k: 1.0 / v for k, v in raw.items()}
    overround = sum(implied.values())
    if overround <= 0:
        return None
    fair = {k: p / overround for k, p in implied.items()}
    return {
        "raw_odds": raw,
        "implied_probability": implied,
        "overround": overround,
        "fair_probability": fair,
    }

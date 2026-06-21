"""capability_registry.py — 系統能力的唯一事實來源（Rule 1）。

任何地方都不得寫死能力（禁止 `if champion:` / `if golden_boot:`）；一律查此 registry。

設計（market 是唯一真相）：
  • 不再有寫死的 supported 旗標。某能力「是否可用」一律由 runtime 市場驗證決定
    （tournament_futures.build() → futures_fetcher.fetch() → futures_validation.validate_outright_key()）。
  • registry 只宣告：candidate outright_key（None = 無已知市場）、source、
    permanent_na（市場根本不存在 → 永久 N/A，連 fetch 都不做）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    name: str
    outright_key: str | None    # 候選 Odds API outright sport key（None＝無已知市場 → N/A）
    source: str | None          # 資料來源描述（例：odds_api_outrights）
    permanent_na: str | None    # 有值＝市場根本不存在，永久 N/A（不 fetch、不驗證）


_REGISTRY: dict[str, Capability] = {
    # 已知存在的市場 key（runtime 仍會驗證有無回盤）
    "Champion":      Capability("Champion", "soccer_fifa_world_cup_winner", "odds_api_outrights", None),
    # 官方證據（the-odds-api.com /sports 清單）：世足 outright 僅 soccer_fifa_world_cup_winner 一個 key。
    # top_goalscorer / best_goalkeeper 在官方清單「不存在」→ 設 permanent_na（誠實 N/A、不空打無效 key、不捏造）。
    "TopGoalscorer": Capability("TopGoalscorer", None, "odds_api_outrights", "The Odds API 無此 outright sport key（官方清單僅 soccer_fifa_world_cup_winner）"),
    "GoldenBoot":    Capability("GoldenBoot", None, "odds_api_outrights", "The Odds API 無金靴 outright sport key（官方清單僅 soccer_fifa_world_cup_winner）"),
    "GoldenGlove":   Capability("GoldenGlove", None, "odds_api_outrights", "The Odds API 無金手套 outright sport key（官方清單僅 soccer_fifa_world_cup_winner）"),
    # 待 API key（尚無候選 key）→ 無 key → N/A
    "GroupWinner":   Capability("GroupWinner", None, None, None),
    "Qualified":     Capability("Qualified", None, None, None),
    # 市場根本不存在 → 永久 N/A（不 fetch）
    "BallonDor":     Capability("BallonDor", None, None, "Odds API 不涵蓋此獎項 → 永久 N/A"),
    "BestXI":        Capability("BestXI", None, None, "無此下注市場 → 永久 N/A"),
    "MVP":           Capability("MVP", None, None, "無此下注市場 → 永久 N/A"),
}


def get(name: str) -> Capability | None:
    return _REGISTRY.get(name)


def outright_key(name: str) -> str | None:
    c = _REGISTRY.get(name)
    return c.outright_key if c else None


def source_of(name: str) -> str | None:
    c = _REGISTRY.get(name)
    return c.source if c else None


def permanent_na_of(name: str) -> str | None:
    c = _REGISTRY.get(name)
    return c.permanent_na if c else None


def is_candidate(name: str) -> bool:
    """是否值得 runtime 嘗試（有候選 key 且非永久 N/A）。真正可用與否仍由 build() 的市場驗證決定。"""
    c = _REGISTRY.get(name)
    return bool(c and c.outright_key and not c.permanent_na)


def all_capabilities() -> list[Capability]:
    return list(_REGISTRY.values())


def candidate_capabilities() -> list[Capability]:
    return [c for c in _REGISTRY.values() if c.outright_key and not c.permanent_na]

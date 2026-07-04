"""
providers/impls.py — 各 Root Cause 的 Provider 實作

分兩類：
1) 現在就能判定（有 repo 內資料）：
   - CutoffProvider          ← context['flags']（賽前推播是否觸發）
   - ModelDirectionProvider  ← context['record']（pick vs 實際勝方）
2) 待外部資料源接入（架構已備妥）：
   - InjuryProvider          ← context['injury']
   - LineupProvider          ← context['lineup']
   - LineMovementProvider    ← context['market']（讓分線賽前vs賽後）
   - OddsMovementProvider    ← context['market']（賠率賽前vs賽後）
   - MarketChangeProvider    ← context['market']（市場開關/暫停）
   - DataDelayProvider       ← context['actions']（Actions 執行時序，ephemeral）

優化一：所有資料一律從 context 取。未來接 API＝在 Battle Report 組 context 時
把對應快照塞進去，並把該 Provider is_available() 改 True，evaluate() 讀 context。
Provider 本身不再自己找資料。
"""

from providers.base import RootCauseProvider, Evidence


def _s(r, k):
    v = str(r.get(k, "")).strip()
    return v if v not in ("", "None") else None


def _ctx(context):
    return context or {}


# ───────────────── 現在可判定 ─────────────────
class CutoffProvider(RootCauseProvider):
    root_cause = "CUTOFF"
    source_name = "flags.json"

    def is_available(self):
        return True

    def evaluate(self, record, context=None):
        flags = _ctx(context).get("flags", {}) or {}
        gid = _s(record, "game_id")
        v = flags.get(gid) if gid else None
        pre = bool(isinstance(v, dict) and v.get("pre"))
        if not pre:
            return Evidence(self.root_cause, available=True, confidence=0.9,
                            evidence=f"flags.pre 未標記（game_id={gid}）賽前推播未觸發",
                            source=self.source_name)
        return Evidence(self.root_cause, available=True, confidence=0.0,
                        evidence="賽前推播已觸發，非 CUTOFF",
                        source=self.source_name)


class ModelDirectionProvider(RootCauseProvider):
    root_cause = "MODEL_DIRECTION_ERROR"
    source_name = "verified_history"

    def is_available(self):
        return True

    def evaluate(self, record, context=None):
        pick = _s(record, "pick_outcome")
        winner = _s(record, "winner")
        if pick and winner:
            if winner.lower() != pick.lower() and pick.lower() != "draw":
                return Evidence(self.root_cause, available=True, confidence=0.8,
                                evidence=f"pick={pick} 實際勝方={winner}（方向相反）",
                                source=self.source_name)
            return Evidence(self.root_cause, available=True, confidence=0.0,
                            evidence="方向正確或平手，非方向誤判",
                            source=self.source_name)
        return self._unavailable("verified_history 缺 pick_outcome / winner")


# ───────────────── 待外部資料源（context-aware 掛勾備妥） ─────────────────
class InjuryProvider(RootCauseProvider):
    root_cause = "INJURY"
    source_name = "injury_api"

    def is_available(self):
        return False

    def evaluate(self, record, context=None):
        snap = _ctx(context).get("injury")
        if not snap:
            return self._unavailable(
                "尚未接入傷兵資料源；context['injury'] 為空。"
                "未來：injury API 提供賽前傷兵名單即可於此判定")
        # 掛勾點：snap 就緒時在此比對關鍵球員缺陣 → Evidence(available=True)
        return self._unavailable("injury snapshot 格式待定義")


class LineupProvider(RootCauseProvider):
    root_cause = "LINEUP_CHANGE"
    source_name = "lineup_api"

    def is_available(self):
        return False

    def evaluate(self, record, context=None):
        snap = _ctx(context).get("lineup")
        if not snap:
            return self._unavailable(
                "尚未接入先發陣容資料源；context['lineup'] 為空。"
                "未來：lineup API 賽前/臨場陣容即可於此判定")
        return self._unavailable("lineup snapshot 格式待定義")


class _MarketBased(RootCauseProvider):
    """共用：需 context['market']（賽前vs賽後盤口快照）。"""
    def is_available(self):
        return False

    def _need_market(self, context, what):
        snap = _ctx(context).get("market")
        if not snap:
            return self._unavailable(
                f"尚未接入盤口雙時點快照；context['market'] 為空。"
                f"未來：賽前 vs 賽後 {what} 快照即可於此判定")
        return None


class LineMovementProvider(_MarketBased):
    root_cause = "LINE_MOVEMENT"
    source_name = "odds_snapshot"

    def evaluate(self, record, context=None):
        miss = self._need_market(context, "讓分線(handicap line)")
        if miss:
            return miss
        return self._unavailable("market snapshot 讓分線欄位待定義")


class OddsMovementProvider(_MarketBased):
    root_cause = "ODDS_MOVEMENT"
    source_name = "odds_snapshot"

    def evaluate(self, record, context=None):
        miss = self._need_market(context, "moneyline 賠率")
        if miss:
            return miss
        return self._unavailable("market snapshot 賠率欄位待定義")


class MarketChangeProvider(_MarketBased):
    root_cause = "MARKET_CHANGE"
    source_name = "market_provider"

    def evaluate(self, record, context=None):
        miss = self._need_market(context, "市場開關/暫停/重新開盤事件")
        if miss:
            return miss
        return self._unavailable("market snapshot 事件流欄位待定義")


class DataDelayProvider(RootCauseProvider):
    root_cause = "DATA_DELAY"
    source_name = "actions_run_log"

    def is_available(self):
        return False

    def evaluate(self, record, context=None):
        snap = _ctx(context).get("actions")
        if not snap:
            return self._unavailable(
                "需 GitHub Actions 執行時序（run log）；context['actions'] 為空。"
                "為 ephemeral，未持久化到 repo")
        return self._unavailable("actions run-log 格式待定義")


def default_providers():
    """
    回傳 Root Cause 判定鏈（順序 = 優先序）。
    優化一：Provider 不再吃建構參數（flags），資料一律走 context。
    未來新增 WeatherProvider / RefereeProvider 等，在此 append 即可。
    """
    return [
        CutoffProvider(),
        ModelDirectionProvider(),
        InjuryProvider(),
        LineupProvider(),
        LineMovementProvider(),
        OddsMovementProvider(),
        MarketChangeProvider(),
        DataDelayProvider(),
    ]

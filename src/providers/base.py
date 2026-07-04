"""
providers/base.py — Root Cause 資料源 Provider 介面 + Evidence 資料模型

設計目標（對應監督指令）：
- 每個 Root Cause 都有一個 Provider 介面，即使目前無資料源，架構先備妥（②）
- Provider 統一回傳 Evidence（含 confidence / source / unavailable_reason）（③）
- 未來接 API 時只需實作對應 Provider 的 fetch()，Battle Report 完全不用改

Engineering Rule：沒有資料源時回傳 Evidence(available=False)，
Battle Report 端只在 available=True 時採用該 Root Cause，否則 fallback UNKNOWN。
"""

import datetime as dt

# ── Root Cause 全集（UNKNOWN 僅為最後 fallback）──
ROOT_CAUSES = [
    "MODEL_DIRECTION_ERROR",
    "CUTOFF",
    "INJURY",
    "LINEUP_CHANGE",
    "LINE_MOVEMENT",
    "ODDS_MOVEMENT",
    "MARKET_CHANGE",
    "DATA_DELAY",
    "UNKNOWN",
]


class Evidence:
    """單一 Root Cause 判定的證據物件（③ Evidence Model）。"""

    __slots__ = ("root_cause", "available", "confidence", "evidence",
                 "source", "unavailable_reason")

    def __init__(self, root_cause, available=False, confidence=0.0,
                 evidence=None, source=None, unavailable_reason=None):
        self.root_cause = root_cause
        self.available = available            # 是否有足夠資料判定
        self.confidence = float(confidence)   # 0.0~1.0
        self.evidence = evidence              # 人類可讀證據字串/結構
        self.source = source                  # 資料來源標記（provider 名/API）
        self.unavailable_reason = unavailable_reason  # 為何無法判定

    def to_dict(self):
        return {
            "root_cause": self.root_cause,
            "available": self.available,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
            "source": self.source,
            "unavailable_reason": self.unavailable_reason,
        }


class RootCauseProvider:
    """
    Provider 介面基底。每個資料源子類別覆寫：
      - root_cause: 這個 provider 負責判定的 Root Cause
      - is_available(): 資料源是否已接入
      - evaluate(record, context): 回傳 Evidence

    context 是共用資料袋（優化一）：Battle Report 在一處組好所有快照，
    Provider 只從 context 取，不各自去找檔案/打 API。典型 context：
      {
        "flags":  {...},            # 賽前推播旗標
        "record": {...},            # 當前 verified_history 這一列
        "market": <market_snapshot 或 None>,   # 賽前vs賽後盤口（待接入）
        "injury": <injury_snapshot 或 None>,   # 傷兵（待接入）
        "lineup": <lineup_snapshot 或 None>,   # 陣容（待接入）
      }
    未接入的快照為 None → 對應 Provider 回 available=False（含 unavailable_reason），
    絕不臆測。
    """

    root_cause = "UNKNOWN"
    source_name = "base"

    def is_available(self):
        return False

    def _unavailable(self, reason):
        return Evidence(self.root_cause, available=False, confidence=0.0,
                        source=self.source_name, unavailable_reason=reason)

    def evaluate(self, record, context=None):
        raise NotImplementedError


def now_tw():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
